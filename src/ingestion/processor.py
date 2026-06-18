import os
import sys
import logging
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import datetime, timedelta
import shutil

from src.utils import normalize_patient_name

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


class CPAPIngestion:
    def __init__(self, reset=False):
        self.reset = reset
        if not os.path.exists(PROCESSED_DIR):
            os.makedirs(PROCESSED_DIR)
        elif self.reset:
            # Apaga apenas a tabela CPAP (summary/), preservando dados da Smartband
            summary_dir = os.path.join(PROCESSED_DIR, "summary")
            if os.path.exists(summary_dir):
                logger.info("Limpando dados CPAP existentes (Reset)...")
                shutil.rmtree(summary_dir)
            else:
                logger.info("Nenhum dado CPAP anterior encontrado para limpar.")

    def read_str_edf(self, file_path):
        import mne
        import warnings
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        try:
            raw = mne.io.read_raw_edf(file_path, preload=True, verbose=False)
            data = raw.get_data()
            signal_labels = raw.ch_names
            df = pd.DataFrame(data.T, columns=signal_labels)
            start_time = raw.info['meas_date']
            if start_time is not None:
                start_time = start_time.replace(tzinfo=None)
            else:
                start_time = datetime(2000, 1, 1)
            df['data_terapia'] = [start_time + timedelta(seconds=t) for t in raw.times]
            return df
        except Exception as e:
            logger.error(f"Erro ao ler {file_path} com MNE: {e}")
            return None

    def process_all_users(self):
        if not os.path.exists(SD_DATA_DIR):
            logger.error(f"Diretorio de dados CPAP nao encontrado: {SD_DATA_DIR}")
            return
        users = [d for d in os.listdir(SD_DATA_DIR) if os.path.isdir(os.path.join(SD_DATA_DIR, d))]
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

    def save_to_parquet(self, df, table_name, dedupe_keys):
        output_root = os.path.join(PROCESSED_DIR, table_name)
        if not os.path.exists(output_root):
            os.makedirs(output_root)
        for patient in df['patient'].unique():
            patient_slug = normalize_patient_name(patient)
            patient_new_data = df[df['patient'] == patient].copy()
            patient_new_data['patient_slug'] = patient_slug
            partition_path = os.path.join(output_root, f"patient_slug={patient_slug}")
            if os.path.exists(partition_path) and any(os.scandir(partition_path)) and not self.reset:
                df_existing = pd.read_parquet(partition_path)
                if 'patient_slug' not in df_existing.columns:
                    df_existing['patient_slug'] = patient_slug
                df_combined = pd.concat([df_existing, patient_new_data]).drop_duplicates(subset=dedupe_keys)
                diff = len(df_combined) - len(df_existing)
                if diff > 0:
                    logger.info(f" - Usuario {patient}: {diff} novos registros adicionados.")
                    shutil.rmtree(partition_path)
                    table = pa.Table.from_pandas(df_combined)
                    pq.write_to_dataset(table, root_path=output_root, partition_cols=['patient_slug'])
                else:
                    logger.info(f" - Usuario {patient}: Nenhum dado novo encontrado.")
            else:
                logger.info(f" - Usuario {patient}: {len(patient_new_data)} registros (nova carga).")
                table = pa.Table.from_pandas(patient_new_data)
                pq.write_to_dataset(table, root_path=output_root, partition_cols=['patient_slug'])


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Processamento de dados CPAP SD para Parquet.")
    parser.add_argument("--reset", action="store_true", help="Limpa dados CPAP processados antes de iniciar.")
    args = parser.parse_args()
    processor = CPAPIngestion(reset=args.reset)
    processor.process_all_users()
    logger.info("Processamento CPAP concluido com sucesso.")
