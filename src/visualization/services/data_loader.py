import os
from typing import Optional
import pandas as pd

from ...utils import normalize_patient_name

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PROCESSED_BASE_DIR = os.path.join(BASE_DIR, "data", "processed")
PROCESSED_DIR = os.path.join(PROCESSED_BASE_DIR, "summary")
SMARTBAND_DIR = PROCESSED_BASE_DIR

_cpap_cache = {}
_smartband_cache = {}


def invalidate_cache():
    _cpap_cache.clear()
    _smartband_cache.clear()


def load_cpap_data(patient=None):
    cache_key = patient or "__all__"
    if cache_key in _cpap_cache:
        return _cpap_cache[cache_key]

    path = PROCESSED_DIR
    if patient:
        patient_slug = normalize_patient_name(patient)
        path = os.path.join(PROCESSED_DIR, "patient_slug=" + patient_slug)

    if not os.path.exists(path):
        return pd.DataFrame()

    df = pd.read_parquet(path)
    df['data_sessao'] = (df['data_terapia'] - pd.Timedelta(hours=12)).dt.date
    df = df[df['PatientHours'] > 0].copy()

    for p in df['patient'].unique():
        p_mask = df['patient'] == p
        p_dur = df.loc[p_mask, 'Duration'].copy()
        if not p_dur.empty and p_dur.max() > 1440:
            df.loc[p_mask, 'usage_mins'] = p_dur / 60
        else:
            df.loc[p_mask, 'usage_mins'] = p_dur
        df.loc[p_mask, 'usage_mins'] = df.loc[p_mask, 'usage_mins'].fillna(0)

    _cpap_cache[cache_key] = df
    return df


def load_smartband_table(table_name, patient=None):
    cache_key = table_name + "/" + (patient or "__all__")
    if cache_key in _smartband_cache:
        return _smartband_cache[cache_key]

    path = os.path.join(SMARTBAND_DIR, table_name)
    if patient:
        patient_slug = normalize_patient_name(patient)
        path = os.path.join(path, "patient_slug=" + patient_slug)

    if not os.path.exists(path):
        return pd.DataFrame()

    df = pd.read_parquet(path)
    _smartband_cache[cache_key] = df
    return df
