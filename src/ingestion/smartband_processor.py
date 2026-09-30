"""
Smartband Data Processor
========================
Processa os CSVs exportados do Smartband (Xiaomi Mi Fitness) e gera Parquets estruturados
para integração com o pipeline CPAP-ResMed existente.

Entrada (uma pasta por paciente, igual ao CPAP):
  data/Smartband/<Paciente>/<AAAAMMDD>_<UID>_MiFitness_<tabela>.csv

O nome da pasta é o nome do paciente (ex.: data/Smartband/Marcelo e
data/cpap_sd/Marcelo apontam para a mesma pessoa).

Saída:
  data/processed/smartband_sleep/       → dados de sono por sessão (raw)
  data/processed/smartband_sleep_daily/  → agregados diários de sono (com sleep_score)
  data/processed/smartband_vitals/       → FC e SpO2 contínuos
  data/processed/smartband_activity/     → passos e calorias diários
"""

import os
import sys
import glob
import json
import argparse
import logging

# Configurar logging com arquivo
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

import sys
_stream_handler = logging.StreamHandler(stream=sys.stdout)
_stream_handler.stream.reconfigure(encoding='utf-8', errors='replace') if hasattr(_stream_handler.stream, 'reconfigure') else None
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        _stream_handler,
        logging.FileHandler(os.path.join(LOGS_DIR, "smartband_processor.log"), encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import datetime, timezone, timedelta
import re
import shutil

from src.utils import normalize_patient_name

# Configurações de Caminhos
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SMARTBAND_DIR = os.path.join(BASE_DIR, "data", "Smartband")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")

# Carrega .env manualmente se existir
env_path = os.path.join(BASE_DIR, ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                key, val = line.strip().split("=", 1)
                # Não sobrescreve variáveis já definidas (ex.: pelo Docker)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

# Timezone offset: dados usam fuso horário configurado (default: UTC-3 Brasília)
try:
    tz_hours = int(os.environ.get("TZ_OFFSET_HOURS", "-3"))
except ValueError:
    tz_hours = -3

TZ_OFFSET = timedelta(hours=tz_hours)
TZ_BRT = timezone(TZ_OFFSET)



EXPORT_RE = re.compile(r"^(?P<date>\d{8})_(?P<uid>\d+)_MiFitness_(?P<table>.+)\.csv$")


def list_exports(folder):
    """Agrupa os CSVs do Mi Fitness de uma pasta por exportação.

    Retorna {(data, uid): {tabela: caminho}}, onde data (AAAAMMDD) e uid vêm do
    nome do arquivo gerado pelo app.
    """
    exports = {}
    if not os.path.isdir(folder):
        return exports
    for name in os.listdir(folder):
        m = EXPORT_RE.match(name)
        if m:
            key = (m.group("date"), m.group("uid"))
            exports.setdefault(key, {})[m.group("table")] = os.path.join(folder, name)
    return exports


def latest_export(folder):
    """Escolhe a exportação mais recente (pela data no nome) de uma pasta.

    Retorna (data, uid, {tabela: caminho}) ou None. Avisa se a pasta mistura
    exportações de contas Mi Fitness diferentes (UIDs distintos), o que indica
    arquivos de outra pessoa na pasta do paciente.
    """
    exports = list_exports(folder)
    if not exports:
        return None
    uids = {uid for _, uid in exports}
    if len(uids) > 1:
        logger.warning(f"  ⚠️ {folder} contém exportações de contas diferentes (UIDs: {', '.join(sorted(uids))}). "
                       "Cada pasta deve ter os arquivos de um único paciente.")
    date, uid = max(exports)
    return date, uid, exports[(date, uid)]


def discover_patients(root=None):
    """Lista as pastas de paciente em data/Smartband que contêm exportações do Mi Fitness.

    Retorna [(nome_do_paciente, caminho_da_pasta)], ordenado pelo nome.
    """
    root = root or SMARTBAND_DIR
    if not os.path.isdir(root):
        return []
    found = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if os.path.isdir(path) and list_exports(path):
            found.append((name, path))
    return found


def epoch_to_datetime(epoch_val):
    """Converte epoch seconds para datetime UTC-3."""
    if pd.isna(epoch_val) or epoch_val == 0:
        return pd.NaT
    return datetime.fromtimestamp(int(epoch_val), tz=TZ_BRT)


# Códigos de fase do sono do Mi Fitness (campo 'state' dos items).
# Conferido contra os totais do próprio registro (sleep_deep/light/rem/awake_duration):
# a soma dos intervalos de cada código bate com o total correspondente em todas as noites.
STAGE_NAMES = {2: 'profundo', 3: 'leve', 4: 'rem', 5: 'acordado'}


def report_day(epoch_val):
    """Dia de referência de um registro `daily_report` do Mi Fitness.

    O campo `Time` desses registros é a meia-noite UTC do dia local a que o
    relatório se refere (a data do calendário vem codificada como UTC). Por isso
    a data é lida em UTC, sem aplicar fuso — aplicar UTC-3 recuaria um dia.
    """
    return datetime.fromtimestamp(int(epoch_val), tz=timezone.utc).date()


def safe_json_parse(val):
    """Parse JSON de forma segura, retornando dict vazio em caso de erro."""
    if pd.isna(val):
        return {}
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return {}


def save_parquet(df, table_name, patient_slug):
    """Salva DataFrame como Parquet particionado por paciente."""
    output_dir = os.path.join(PROCESSED_DIR, table_name)
    partition_dir = os.path.join(output_dir, f"patient_slug={patient_slug}")

    # Limpa partição existente
    if os.path.exists(partition_dir):
        shutil.rmtree(partition_dir)

    os.makedirs(output_dir, exist_ok=True)

    df_out = df.copy()
    df_out['patient_slug'] = patient_slug

    table = pa.Table.from_pandas(df_out)
    pq.write_to_dataset(table, root_path=output_dir, partition_cols=['patient_slug'])
    logger.info(f"  ✅ {table_name}: {len(df)} registros salvos")


class SmartbandProcessor:
    def __init__(self, patient_name, source_dir=None):
        self.patient_name = patient_name
        self.patient_slug = normalize_patient_name(patient_name)
        self.source_dir = source_dir or os.path.join(SMARTBAND_DIR, patient_name)
        self.export = None   # (data, uid, {tabela: caminho})
        self.df_raw = None
        self.df_agg = None
        self.df_profile = None

    def _csv(self, table_name):
        if self.export is None:
            self.export = latest_export(self.source_dir)
        if self.export is None:
            return None
        return self.export[2].get(table_name)

    def load_raw_data(self):
        """Carrega hlth_center_fitness_data.csv."""
        path = self._csv("hlth_center_fitness_data")
        if not path:
            logger.info("❌ hlth_center_fitness_data.csv não encontrado")
            return False
        logger.info(f"  Lendo: {os.path.basename(path)}")
        self.df_raw = pd.read_csv(path)
        logger.info(f"  → {len(self.df_raw)} registros brutos carregados")
        return True

    def load_aggregated_data(self):
        """Carrega hlth_center_aggregated_fitness_data.csv."""
        path = self._csv("hlth_center_aggregated_fitness_data")
        if not path:
            logger.info("❌ hlth_center_aggregated_fitness_data.csv não encontrado")
            return False
        logger.info(f"  Lendo: {os.path.basename(path)}")
        self.df_agg = pd.read_csv(path)
        logger.info(f"  → {len(self.df_agg)} registros agregados carregados")
        return True

    def load_profile_data(self):
        """Carrega user_member_profile.csv."""
        path = self._csv("user_member_profile")
        if not path:
            logger.info("❌ user_member_profile.csv não encontrado")
            return False
        logger.info(f"  Lendo: {os.path.basename(path)}")
        self.df_profile = pd.read_csv(path)
        logger.info(f"  → {len(self.df_profile)} registros de perfil carregados")
        return True

    def process_sleep_raw(self):
        """Processa registros de sono bruto → smartband_sleep."""
        df_sleep = self.df_raw[self.df_raw['Key'] == 'sleep'].copy()
        if df_sleep.empty:
            logger.info("  ⚠️ Nenhum registro de sono encontrado")
            return

        records = []
        stages = []
        for _, row in df_sleep.iterrows():
            val = safe_json_parse(row['Value'])
            if not val:
                continue

            for item in val.get('items', []):
                state = item.get('state')
                start, end = item.get('start_time'), item.get('end_time')
                if state in STAGE_NAMES and start and end and end > start:
                    stages.append({
                        'start': epoch_to_datetime(start).replace(tzinfo=None),   # hora local
                        'end': epoch_to_datetime(end).replace(tzinfo=None),
                        'stage': STAGE_NAMES[state],
                    })

            bedtime = epoch_to_datetime(val.get('bedtime', 0))
            wake_up = epoch_to_datetime(val.get('wake_up_time', val.get('device_wake_up_time', 0)))

            # Calcular data da sessão de sono (noon-to-noon, consistente com CPAP)
            if bedtime is not pd.NaT:
                sleep_date = (bedtime - timedelta(hours=12)).date()
            else:
                sleep_date = epoch_to_datetime(row['Time']).date() if row['Time'] else None

            # Contar estágios do sono a partir dos items
            items = val.get('items', [])
            stage_counts = {2: 0, 3: 0, 4: 0, 5: 0}  # Profundo, Leve, REM, Acordado (ver STAGE_NAMES)
            for item in items:
                state = item.get('state', 0)
                if state in stage_counts:
                    start = item.get('start_time', 0)
                    end = item.get('end_time', 0)
                    if start and end:
                        stage_counts[state] += (end - start) / 60  # em minutos

            records.append({
                'sleep_date': sleep_date,
                'bedtime': bedtime,
                'wake_up_time': wake_up,
                'duration_min': val.get('duration', 0),
                'deep_min': val.get('sleep_deep_duration', 0),
                'light_min': val.get('sleep_light_duration', 0),
                'rem_min': val.get('sleep_rem_duration', 0),
                'awake_min': val.get('sleep_awake_duration', 0),
                'awake_count': val.get('awake_count', 0),
                'breath_quality': val.get('breath_quality', 0),
                'avg_hr': val.get('avg_hr', 0),
                'min_hr': val.get('min_hr', 0),
                'max_hr': val.get('max_hr', 0),
                'avg_spo2': val.get('avg_spo2', 0),
                'min_spo2': val.get('min_spo2', 0),
                'max_spo2': val.get('max_spo2', 0),
                'stage_awake_min': round(stage_counts[5], 1),
                'stage_light_min': round(stage_counts[3], 1),
                'stage_deep_min': round(stage_counts[2], 1),
                'stage_rem_min': round(stage_counts[4], 1),
                'num_stages': len(items),
                'patient': self.patient_name
            })

        df = pd.DataFrame(records)
        df['sleep_date'] = pd.to_datetime(df['sleep_date'])
        # Remover duplicatas (mesmo sleep_date)
        df = df.drop_duplicates(subset=['sleep_date'], keep='last')
        save_parquet(df, "smartband_sleep", self.patient_slug)

        if stages:
            df_st = pd.DataFrame(stages).drop_duplicates(subset=['start', 'end']).sort_values('start')
            # mesma regra de noite do CPAP: início − 12 h
            df_st['night'] = (df_st['start'] - pd.Timedelta(hours=12)).dt.normalize()
            df_st['patient'] = self.patient_name
            save_parquet(df_st.reset_index(drop=True), "smartband_sleep_stages", self.patient_slug)
        return df

    def process_sleep_daily(self):
        """Processa agregados diários de sono → smartband_sleep_daily."""
        df_sleep = self.df_agg[
            (self.df_agg['Tag'] == 'daily_report') & (self.df_agg['Key'] == 'sleep')
        ].copy()
        if df_sleep.empty:
            logger.info("  ⚠️ Nenhum agregado de sono encontrado")
            return

        records = []
        for _, row in df_sleep.iterrows():
            val = safe_json_parse(row['Value'])
            if not val:
                continue

            # O relatório de sono é rotulado pelo dia em que se acorda; o CPAP
            # rotula a noite pelo dia em que ela começa (meio-dia a meio-dia).
            # Subtrai 1 dia para as duas fontes casarem.
            report_date = report_day(row['Time']) - timedelta(days=1)

            # Extrair segmento principal do segment_details
            segments = val.get('segment_details', [])
            main_segment = None
            nap_count = 0
            for seg in segments:
                dur = seg.get('duration', 0)
                if main_segment is None or dur > main_segment.get('duration', 0):
                    main_segment = seg
                if seg.get('avg_hr', 0) == 0 and dur < 120:
                    nap_count += 1

            records.append({
                'report_date': report_date,
                'sleep_score': val.get('sleep_score', 0),
                'sleep_stage': val.get('sleep_stage', 0),
                'total_duration_min': val.get('total_duration', 0),
                'deep_min': val.get('sleep_deep_duration', 0),
                'light_min': val.get('sleep_light_duration', 0),
                'rem_min': val.get('sleep_rem_duration', 0),
                'awake_min': val.get('sleep_awake_duration', 0),
                'day_sleep_evaluation': val.get('day_sleep_evaluation', 0),
                'long_sleep_evaluation': val.get('long_sleep_evaluation', 0),
                'avg_hr': val.get('avg_hr', 0),
                'min_hr': val.get('min_hr', 0),
                'max_hr': val.get('max_hr', 0),
                'avg_spo2': val.get('avg_spo2', 0),
                'min_spo2': val.get('min_spo2', 0),
                'max_spo2': val.get('max_spo2', 0),
                'num_segments': len(segments),
                'nap_count': nap_count,
                'patient': self.patient_name
            })

        df = pd.DataFrame(records)
        df['report_date'] = pd.to_datetime(df['report_date'])
        df = df.drop_duplicates(subset=['report_date'], keep='last')
        save_parquet(df, "smartband_sleep_daily", self.patient_slug)
        return df

    def process_vitals(self):
        """Processa FC e SpO2 contínuos → smartband_vitals."""
        # Heart Rate
        df_hr = self.df_raw[self.df_raw['Key'] == 'heart_rate'].copy()
        hr_records = []
        for _, row in df_hr.iterrows():
            val = safe_json_parse(row['Value'])
            if val:
                ts = epoch_to_datetime(val.get('time', row['Time']))
                hr_records.append({
                    'timestamp': ts,
                    'bpm': val.get('bpm', 0),
                    'type': 'continuous',
                    'date': ts.date() if ts is not pd.NaT else None,
                    'hour': ts.hour if ts is not pd.NaT else None
                })

        # Resting Heart Rate
        df_rhr = self.df_raw[self.df_raw['Key'] == 'resting_heart_rate'].copy()
        for _, row in df_rhr.iterrows():
            val = safe_json_parse(row['Value'])
            if val:
                ts = epoch_to_datetime(row['Time'])
                hr_records.append({
                    'timestamp': ts,
                    'bpm': val.get('bpm', 0),
                    'type': 'resting',
                    'date': ts.date() if ts is not pd.NaT else None,
                    'hour': ts.hour if ts is not pd.NaT else None
                })

        # SpO2
        df_spo2 = self.df_raw[self.df_raw['Key'] == 'spo2'].copy()
        spo2_records = []
        for _, row in df_spo2.iterrows():
            val = safe_json_parse(row['Value'])
            if val:
                ts = epoch_to_datetime(val.get('time', row['Time']))
                spo2_records.append({
                    'timestamp': ts,
                    'spo2': val.get('spo2', 0),
                    'date': ts.date() if ts is not pd.NaT else None,
                    'hour': ts.hour if ts is not pd.NaT else None
                })

        # Combinar em um único dataset de vitals
        df_hr_out = pd.DataFrame(hr_records)
        df_hr_out['metric'] = 'heart_rate'
        df_hr_out['value'] = df_hr_out['bpm']
        df_hr_out['sub_type'] = df_hr_out['type']

        df_spo2_out = pd.DataFrame(spo2_records)
        df_spo2_out['metric'] = 'spo2'
        df_spo2_out['value'] = df_spo2_out['spo2']
        df_spo2_out['sub_type'] = 'continuous'

        # Unificar
        cols = ['timestamp', 'metric', 'value', 'sub_type', 'date', 'hour']
        df_combined = pd.concat([
            df_hr_out[cols] if not df_hr_out.empty else pd.DataFrame(columns=cols),
            df_spo2_out[cols] if not df_spo2_out.empty else pd.DataFrame(columns=cols)
        ], ignore_index=True)

        df_combined['date'] = pd.to_datetime(df_combined['date'])
        df_combined = df_combined.sort_values('timestamp')
        df_combined['patient'] = self.patient_name
        save_parquet(df_combined, "smartband_vitals", self.patient_slug)
        return df_combined

    def process_daily_activity(self):
        """Processa passos e calorias diários → smartband_activity."""
        # Passos agregados diários
        df_steps_agg = self.df_agg[
            (self.df_agg['Tag'] == 'daily_report') & (self.df_agg['Key'] == 'steps')
        ].copy()

        records = []
        for _, row in df_steps_agg.iterrows():
            val = safe_json_parse(row['Value'])
            if val:
                report_date = report_day(row['Time'])
                records.append({
                    'report_date': report_date,
                    'steps': val.get('steps', 0),
                    'distance_m': val.get('distance', 0),
                    'calories': val.get('calories', 0),
                    'patient': self.patient_name
                })

        # Calorias agregados diários
        df_cal_agg = self.df_agg[
            (self.df_agg['Tag'] == 'daily_report') & (self.df_agg['Key'] == 'calories')
        ].copy()

        cal_map = {}
        for _, row in df_cal_agg.iterrows():
            val = safe_json_parse(row['Value'])
            if val:
                report_date = report_day(row['Time'])
                cal_map[report_date] = val.get('calories', 0)

        df = pd.DataFrame(records)
        if not df.empty:
            df['total_calories'] = df['report_date'].map(cal_map).fillna(df['calories'])
            df['report_date'] = pd.to_datetime(df['report_date'])
            df = df.drop_duplicates(subset=['report_date'], keep='last')
        save_parquet(df, "smartband_activity", self.patient_slug)
        return df

    def process_profile(self):
        """Processa metadados do paciente → smartband_profile."""
        if self.df_profile is None or self.df_profile.empty:
            logger.info("  ⚠️ Nenhum perfil encontrado")
            return

        df = self.df_profile.copy()
        df['patient'] = self.patient_name
        save_parquet(df, "smartband_profile", self.patient_slug)
        return df

    def process_all(self):
        """Executa todo o pipeline de processamento Smartband."""
        logger.info("\n" + "=" * 60)
        logger.info("  Smartband Data Processor")
        logger.info("=" * 60)

        logger.info(f"  Paciente: {self.patient_name}  (pasta: {self.source_dir})")
        if self.export is None:
            self.export = latest_export(self.source_dir)
        if self.export is None:
            logger.info("  ❌ Nenhuma exportação do Mi Fitness encontrada nesta pasta")
            return False
        logger.info(f"  Exportação: {self.export[0]}  conta Mi Fitness (UID): {self.export[1]}")

        logger.info("\n📂 Carregando dados brutos...")
        if not self.load_raw_data():
            return False

        logger.info("\n📂 Carregando dados agregados...")
        if not self.load_aggregated_data():
            return False

        logger.info("\n📂 Carregando perfil do paciente...")
        self.load_profile_data()

        logger.info("\n🛏️  Processando sono (bruto)...")
        self.process_sleep_raw()

        logger.info("\n🛏️  Processando sono (agregado diário)...")
        self.process_sleep_daily()

        logger.info("\n❤️  Processando sinais vitais (FC + SpO2)...")
        self.process_vitals()

        logger.info("\n🚶 Processando atividade diária...")
        self.process_daily_activity()

        logger.info("\n👤 Processando perfil do paciente...")
        self.process_profile()

        logger.info("\n" + "=" * 60)
        logger.info("  ✅ Processamento Smartband concluído!")
        logger.info("=" * 60)
        return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="Processamento de dados Smartband para Parquet.")
    parser.add_argument("--patient", default=None,
                        help="Processa só este paciente (nome da pasta em data/Smartband). Padrão: todos.")
    args = parser.parse_args(argv)

    patients = discover_patients()

    loose = [f for f in (os.listdir(SMARTBAND_DIR) if os.path.isdir(SMARTBAND_DIR) else [])
             if EXPORT_RE.match(f)]
    if loose:
        logger.warning(f"⚠️ {len(loose)} CSV(s) soltos em data/Smartband/ foram ignorados. "
                       "Mova-os para data/Smartband/<Paciente>/ (mesmo nome da pasta em data/cpap_sd).")

    if args.patient:
        wanted = normalize_patient_name(args.patient)
        patients = [p for p in patients if normalize_patient_name(p[0]) == wanted]

    if not patients:
        logger.error("Nenhuma pasta de paciente com exportação do Mi Fitness encontrada em data/Smartband/<Paciente>/")
        return 1

    ok = True
    for name, path in patients:
        ok = SmartbandProcessor(name, path).process_all() and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
