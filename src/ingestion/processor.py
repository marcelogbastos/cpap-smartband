import os
import sys
import logging
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import datetime, timedelta
import shutil

from src.utils import normalize_patient_name
from src.ingestion.edf import read_edf, to_l_per_min
from src.ingestion.datalog_processor import process_datalog

LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

import sys as _sys
_sh = logging.StreamHandler(stream=_sys.stdout)
if hasattr(_sh.stream, 'reconfigure'): _sh.stream.reconfigure(encoding='utf-8', errors='replace')
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        _sh,
        logging.FileHandler(os.path.join(LOGS_DIR, "processor.log"), encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SD_DATA_DIR = os.path.join(BASE_DIR, "data", "cpap_sd")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")


def _has_files(path) -> bool:
    """Diretório existe e não está vazio (fecha o iterador — no Windows um
    scandir aberto pode travar a pasta e impedir o rmtree seguinte)."""
    if not os.path.isdir(path):
        return False
    with os.scandir(path) as it:
        return any(True for _ in it)


def read_resmed_str(file_path) -> pd.DataFrame:
    """Lê o STR.edf: uma linha por dia (1 registro EDF = 1 dia, iniciando ao meio-dia).

    - Só sinais com 1 amostra por registro viram colunas (MaskOn/MaskOff, com
      10 amostras/dia, ficam de fora).
    - Valores ausentes (ResMed grava -1) viram NaN.
    - Fuga (Leak.*) é gravada em L/min (o arquivo usa L/s).
    """
    edf = read_edf(file_path)
    columns = {}
    for label, sig in edf.signals.items():
        if sig.samples_per_record != 1:
            continue
        values = sig.physical[:, 0]
        if label.startswith("Leak."):
            values = to_l_per_min(values, sig.dimension)
        columns[label] = values
    df = pd.DataFrame(columns)
    df["data_terapia"] = [edf.start + timedelta(days=d) for d in range(edf.n_records)]
    return df


class CPAPIngestion:
    def __init__(self, reset=False):
        self.reset = reset
        if not os.path.exists(PROCESSED_DIR):
            os.makedirs(PROCESSED_DIR)
        elif self.reset:
            # Apaga apenas a tabela CPAP (summary/), preservando dados da Smartband
            for table in ("summary", "cpap_events", "cpap_signals", "cpap_oximetry"):
                table_dir = os.path.join(PROCESSED_DIR, table)
                if os.path.exists(table_dir):
                    logger.info(f"Limpando dados CPAP existentes (Reset): {table}")
                    shutil.rmtree(table_dir)

    def read_str_edf(self, file_path):
        """Lê o STR.edf da ResMed e devolve uma linha por dia (registro EDF).

        O STR.edf mistura sinais com 1 amostra/dia (AHI, Leak.95, Duration...)
        e sinais com 10 amostras/dia (MaskOn/MaskOff). Leitores genéricos (MNE)
        reamostram tudo para a mesma taxa e interpolam, distorcendo os valores
        diários. Aqui cada sinal é lido na sua taxa nativa: sinais de 1
        amostra/registro viram colunas; os demais são ignorados.
        """
        try:
            df = read_resmed_str(file_path)
            logger.info(f" - {len(df)} dias lidos de {os.path.basename(file_path)}")
            return df
        except Exception as e:
            logger.error(f"Erro ao ler {file_path}: {e}")
            return None

    def process_all_users(self, only_patient=None):
        if not os.path.exists(SD_DATA_DIR):
            logger.error(f"Diretorio de dados CPAP nao encontrado: {SD_DATA_DIR}")
            return
        users = sorted(d for d in os.listdir(SD_DATA_DIR) if os.path.isdir(os.path.join(SD_DATA_DIR, d)))
        if only_patient:
            wanted = normalize_patient_name(only_patient)
            users = [u for u in users if normalize_patient_name(u) == wanted]
        if not users:
            logger.warning("Nenhum paciente encontrado em data/cpap_sd/")
            return
        for user in users:
            logger.info(f"\nProcessando usuario: {user}")
            user_path = os.path.join(SD_DATA_DIR, user)
            str_path = os.path.join(user_path, "STR.edf")
            if os.path.exists(str_path):
                logger.info(" - Lendo sumario estatistico (STR.edf)")
                df_summary = self.read_str_edf(str_path)
                if df_summary is not None:
                    df_summary['patient'] = user
                    self.save_to_parquet(df_summary, "summary", ["patient", "data_terapia"])
            else:
                logger.warning(f" - STR.edf nao encontrado para {user}")

            datalog = os.path.join(user_path, "DATALOG")
            if os.path.isdir(datalog):
                logger.info(" - Lendo sessoes detalhadas (DATALOG)")
                events, signals, oxi = process_datalog(datalog, user)
                for table, df in (("cpap_events", events), ("cpap_signals", signals), ("cpap_oximetry", oxi)):
                    if not df.empty:
                        self.save_sessions(df, table, user)
                logger.info(f"   {signals['session'].nunique() if not signals.empty else 0} sessoes, "
                            f"{len(events)} eventos"
                            + (f", oximetria em {oxi['session'].nunique()} sessoes" if not oxi.empty else ""))

    def save_sessions(self, df, table_name, patient):
        """Grava dados por sessão: sessões presentes em `df` substituem as antigas,
        sessões que já saíram do cartão SD são preservadas."""
        slug = normalize_patient_name(patient)
        output_root = os.path.join(PROCESSED_DIR, table_name)
        partition = os.path.join(output_root, f"patient_slug={slug}")
        df = df.copy()
        if _has_files(partition) and not self.reset:
            old = pd.read_parquet(partition)
            old = old[~old["session"].isin(df["session"].unique())]
            df = pd.concat([old.drop(columns=["patient_slug"], errors="ignore"), df], ignore_index=True)
        df = df.sort_values("time").reset_index(drop=True)
        df["patient_slug"] = slug
        if os.path.exists(partition):
            shutil.rmtree(partition)
        os.makedirs(output_root, exist_ok=True)
        pq.write_to_dataset(pa.Table.from_pandas(df, preserve_index=False),
                            root_path=output_root, partition_cols=["patient_slug"])

    def save_to_parquet(self, df, table_name, dedupe_keys):
        output_root = os.path.join(PROCESSED_DIR, table_name)
        if not os.path.exists(output_root):
            os.makedirs(output_root)
        for patient in df['patient'].unique():
            patient_slug = normalize_patient_name(patient)
            patient_new_data = df[df['patient'] == patient].copy()
            patient_new_data['patient_slug'] = patient_slug
            partition_path = os.path.join(output_root, f"patient_slug={patient_slug}")
            df_existing = None
            if _has_files(partition_path) and not self.reset:
                df_existing = pd.read_parquet(partition_path)
                if 'patient_slug' not in df_existing.columns:
                    df_existing['patient_slug'] = patient_slug
                # Formato antigo (MNE): várias linhas interpoladas por dia -> descartar
                if df_existing['data_terapia'].dt.normalize().duplicated().any():
                    logger.info(f" - Usuario {patient}: dados no formato antigo (reamostrados), reconstruindo do zero.")
                    df_existing = None

            if df_existing is not None:
                # keep='last': o dado novo prevalece (o dia corrente é atualizado a cada leitura do SD)
                df_combined = (pd.concat([df_existing, patient_new_data])
                               .drop_duplicates(subset=dedupe_keys, keep='last')
                               .sort_values('data_terapia'))
                logger.info(f" - Usuario {patient}: {len(df_combined) - len(df_existing)} novos dias; {len(df_combined)} no total.")
            else:
                df_combined = patient_new_data
                logger.info(f" - Usuario {patient}: {len(df_combined)} registros (nova carga).")

            if os.path.exists(partition_path):
                shutil.rmtree(partition_path)
            table = pa.Table.from_pandas(df_combined, preserve_index=False)
            pq.write_to_dataset(table, root_path=output_root, partition_cols=['patient_slug'])

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Processamento de dados CPAP SD para Parquet.")
    parser.add_argument("--reset", action="store_true", help="Limpa dados CPAP processados antes de iniciar.")
    parser.add_argument("--patient", default=None,
                        help="Processa só este paciente (nome da pasta em data/cpap_sd). Padrão: todos.")
    args = parser.parse_args()
    processor = CPAPIngestion(reset=args.reset)
    processor.process_all_users(only_patient=args.patient)
    logger.info("Processamento CPAP concluido com sucesso.")
