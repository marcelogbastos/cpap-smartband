import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed", "summary")
SMARTBAND_DIR = os.path.join(BASE_DIR, "data", "processed")

def load_cpap_data():
    if not os.path.exists(PROCESSED_DIR):
        return pd.DataFrame()
    df = pd.read_parquet(PROCESSED_DIR)
    df['data_sessao'] = (df['data_terapia'] - pd.Timedelta(hours=12)).dt.date
    df = df[df['PatientHours'] > 0].copy()
    
    for patient in df['patient'].unique():
        p_mask = df['patient'] == patient
        p_dur = df.loc[p_mask, 'Duration'].copy()
        if not p_dur.empty and p_dur.max() > 1440:
            df.loc[p_mask, 'usage_mins'] = p_dur / 60
        else:
            df.loc[p_mask, 'usage_mins'] = p_dur
        df.loc[p_mask, 'usage_mins'] = df.loc[p_mask, 'usage_mins'].fillna(0)
            
    return df

def load_smartband_table(table_name):
    path = os.path.join(SMARTBAND_DIR, table_name)
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_parquet(path)
