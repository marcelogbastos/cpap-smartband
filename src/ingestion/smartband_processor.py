"""
Smartband Data Processor
========================
Processa os CSVs exportados do Smartband (Xiaomi Mi Fitness) e gera Parquets estruturados
para integração com o pipeline CPAP-ResMed existente.

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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import datetime, timezone, timedelta
import shutil

# Configurações de Caminhos
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SMARTBAND_DIR = os.path.join(BASE_DIR, "data", "Smartband")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")

# Timezone offset: dados usam timezone=-12 para UTC-3 (Brasília)
TZ_OFFSET = timedelta(hours=-3)
TZ_BRT = timezone(TZ_OFFSET)


def find_csv(table_name):
    """Encontra o CSV mais recente para uma tabela Smartband."""
    pattern = os.path.join(SMARTBAND_DIR, f"*_MiFitness_{table_name}.csv")
    files = glob.glob(pattern)
    if not files:
        return None
    # Retorna o mais recente (pelo prefixo de data no nome)
    return sorted(files)[-1]


def epoch_to_datetime(epoch_val):
    """Converte epoch seconds para datetime UTC-3."""
    if pd.isna(epoch_val) or epoch_val == 0:
        return pd.NaT
    return datetime.fromtimestamp(int(epoch_val), tz=TZ_BRT)


def safe_json_parse(val):
    """Parse JSON de forma segura, retornando dict vazio em caso de erro."""
    if pd.isna(val):
        return {}
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return {}


def save_parquet(df, table_name, patient_slug="marcelo"):
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
    def __init__(self, patient_slug="marcelo"):
        self.patient_slug = patient_slug
        self.df_raw = None
        self.df_agg = None
        self.df_profile = None

    def load_raw_data(self):
        """Carrega hlth_center_fitness_data.csv."""
        path = find_csv("hlth_center_fitness_data")
        if not path:
            logger.info("❌ hlth_center_fitness_data.csv não encontrado")
            return False
        logger.info(f"  Lendo: {os.path.basename(path)}")
        self.df_raw = pd.read_csv(path)
        logger.info(f"  → {len(self.df_raw)} registros brutos carregados")
        return True

    def load_aggregated_data(self):
        """Carrega hlth_center_aggregated_fitness_data.csv."""
        path = find_csv("hlth_center_aggregated_fitness_data")
        if not path:
            logger.info("❌ hlth_center_aggregated_fitness_data.csv não encontrado")
            return False
        logger.info(f"  Lendo: {os.path.basename(path)}")
        self.df_agg = pd.read_csv(path)
        logger.info(f"  → {len(self.df_agg)} registros agregados carregados")
        return True

    def load_profile_data(self):
        """Carrega user_member_profile.csv."""
        path = find_csv("user_member_profile")
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
        for _, row in df_sleep.iterrows():
            val = safe_json_parse(row['Value'])
            if not val:
                continue

            bedtime = epoch_to_datetime(val.get('bedtime', 0))
            wake_up = epoch_to_datetime(val.get('wake_up_time', val.get('device_wake_up_time', 0)))

            # Calcular data da sessão de sono (noon-to-noon, consistente com CPAP)
            if bedtime is not pd.NaT:
                sleep_date = (bedtime - timedelta(hours=12)).date()
            else:
                sleep_date = epoch_to_datetime(row['Time']).date() if row['Time'] else None

            # Contar estágios do sono a partir dos items
            items = val.get('items', [])
            stage_counts = {2: 0, 3: 0, 4: 0, 5: 0}  # Acordado, Leve, Profundo, REM
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
                'stage_awake_min': round(stage_counts[2], 1),
                'stage_light_min': round(stage_counts[3], 1),
                'stage_deep_min': round(stage_counts[4], 1),
                'stage_rem_min': round(stage_counts[5], 1),
                'num_stages': len(items),
                'patient': self.patient_slug.title()
            })

        df = pd.DataFrame(records)
        df['sleep_date'] = pd.to_datetime(df['sleep_date'])
        # Remover duplicatas (mesmo sleep_date)
        df = df.drop_duplicates(subset=['sleep_date'], keep='last')
        save_parquet(df, "smartband_sleep", self.patient_slug)
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

            report_date = epoch_to_datetime(row['Time']).date()

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
                'patient': self.patient_slug.title()
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
        df_combined['patient'] = 'Marcelo'
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
                report_date = epoch_to_datetime(row['Time']).date()
                records.append({
                    'report_date': report_date,
                    'steps': val.get('steps', 0),
                    'distance_m': val.get('distance', 0),
                    'calories': val.get('calories', 0),
                    'patient': self.patient_slug.title()
                })

        # Calorias agregados diários
        df_cal_agg = self.df_agg[
            (self.df_agg['Tag'] == 'daily_report') & (self.df_agg['Key'] == 'calories')
        ].copy()

        cal_map = {}
        for _, row in df_cal_agg.iterrows():
            val = safe_json_parse(row['Value'])
            if val:
                report_date = epoch_to_datetime(row['Time']).date()
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
        df['patient'] = self.patient_slug.title()
        save_parquet(df, "smartband_profile", self.patient_slug)
        return df

    def process_all(self):
        """Executa todo o pipeline de processamento Smartband."""
        logger.info("\n" + "=" * 60)
        logger.info("  Smartband Data Processor")
        logger.info("=" * 60)

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Processamento de dados Smartband para Parquet.")
    parser.add_argument("--patient", default="marcelo", help="Slug do paciente (default: marcelo)")
    args = parser.parse_args()

    processor = SmartbandProcessor(patient_slug=args.patient)
    success = processor.process_all()
    sys.exit(0 if success else 1)
