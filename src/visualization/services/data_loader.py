import os
from typing import Optional
import pandas as pd
import unicodedata
from pandas import DataFrame

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed", "summary")
SMARTBAND_DIR = os.path.join(BASE_DIR, "data", "processed")

def normalize_patient_name(name: str) -> str:
    """Normaliza o nome do paciente para uso em caminhos de arquivo (remove acentos e espaços).

    Args:
        name: Nome do paciente (ex: 'Marcelo')

    Returns:
        Slug normalizado em minúsculas sem acentos (ex: 'marcelo').
    """
    return "".join(
        c for c in unicodedata.normalize("NFD", name)
        if unicodedata.category(c) != "Mn"
    ).lower().replace(" ", "_")

def load_cpap_data(patient: Optional[str] = None) -> pd.DataFrame:
    path = PROCESSED_DIR
    if patient:
        patient_slug = normalize_patient_name(patient)
        path = os.path.join(PROCESSED_DIR, f"patient_slug={patient_slug}")
        
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
            
    return df

def load_smartband_table(table_name: str, patient: Optional[str] = None) -> pd.DataFrame:
    path = os.path.join(SMARTBAND_DIR, table_name)
    if patient:
        patient_slug = normalize_patient_name(patient)
        path = os.path.join(path, f"patient_slug={patient_slug}")
        
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_parquet(path)

