import os
from typing import Optional
import pandas as pd

from ...utils import normalize_patient_name

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PROCESSED_BASE_DIR = os.path.join(BASE_DIR, "data", "processed")
PROCESSED_DIR = os.path.join(PROCESSED_BASE_DIR, "summary")
SMARTBAND_DIR = PROCESSED_BASE_DIR

_cpap_cache: dict = {}       # cache_key → df
_cpap_mtime: dict = {}       # cache_key → mtime
_smartband_cache: dict = {}  # cache_key → df
_smartband_mtime: dict = {}  # cache_key → mtime


def _dir_mtime(path: str) -> float:
    """Retorna o mtime mais recente dentro de um diretório (recursivo)."""
    if not os.path.exists(path):
        return 0.0
    if os.path.isfile(path):
        return os.path.getmtime(path)
    latest = 0.0
    for root, _, files in os.walk(path):
        for f in files:
            t = os.path.getmtime(os.path.join(root, f))
            if t > latest:
                latest = t
    return latest


def invalidate_cache():
    _cpap_cache.clear()
    _cpap_mtime.clear()
    _smartband_cache.clear()
    _smartband_mtime.clear()


def load_cpap_data(patient=None):
    cache_key = patient or "__all__"

    path = PROCESSED_DIR
    if patient:
        patient_slug = normalize_patient_name(patient)
        path = os.path.join(PROCESSED_DIR, "patient_slug=" + patient_slug)

    current_mtime = _dir_mtime(path)
    if cache_key in _cpap_cache and _cpap_mtime.get(cache_key) == current_mtime:
        return _cpap_cache[cache_key]

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
    _cpap_mtime[cache_key] = current_mtime
    return df


def load_smartband_table(table_name, patient=None):
    cache_key = table_name + "/" + (patient or "__all__")

    path = os.path.join(SMARTBAND_DIR, table_name)
    if patient:
        patient_slug = normalize_patient_name(patient)
        path = os.path.join(path, "patient_slug=" + patient_slug)

    current_mtime = _dir_mtime(path)
    if cache_key in _smartband_cache and _smartband_mtime.get(cache_key) == current_mtime:
        return _smartband_cache[cache_key]

    if not os.path.exists(path):
        return pd.DataFrame()

    df = pd.read_parquet(path)
    _smartband_cache[cache_key] = df
    _smartband_mtime[cache_key] = current_mtime
    return df
