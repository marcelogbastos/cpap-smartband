from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import date
import pandas as pd
import logging

logger = logging.getLogger(__name__)

from ..schemas.models import PatientDataResponse, SmartbandDataResponse, MonthlySleepTable, MonthlyCpapTable, CorrelationResponse
from ..services.data_loader import load_cpap_data, load_smartband_table, PROCESSED_BASE_DIR
from ..services.cpap_scoring import calculate_myair_score

router = APIRouter(prefix="/api")


@router.get("/health")
def health_check():
    """Verifica se o servidor está ativo e responsivo."""
    return {"status": "ok", "service": "CPAP Analytics API"}

@router.get("/patients", response_model=List[str])
def get_patients():
    """Retorna a lista de pacientes disponíveis, varrendo todas as tabelas em data/processed/.

    Detecta qualquer paciente que tenha dados em qualquer tabela (CPAP ou Smartband),
    não apenas na tabela summary.
    """
    try:
        import os
        if not os.path.exists(PROCESSED_BASE_DIR):
            return []

        slugs: set[str] = set()
        for table_dir in os.listdir(PROCESSED_BASE_DIR):
            table_path = os.path.join(PROCESSED_BASE_DIR, table_dir)
            if not os.path.isdir(table_path):
                continue
            for partition in os.listdir(table_path):
                if partition.startswith("patient_slug="):
                    slugs.add(partition.split("=")[1])

        return sorted(slug.title() for slug in slugs)
    except Exception as e:
        logger.error(f"Error loading patients: {e}")
        raise HTTPException(status_code=500, detail="Failed to load patient data")

@router.get("/data/{patient}", response_model=PatientDataResponse)
def get_patient_data(patient: str, start_date: Optional[str] = Query(None), end_date: Optional[str] = Query(None)):
    """Retorna KPIs e série temporal do CPAP para um paciente.

    Args:
        patient: Nome do paciente (case-insensitive).
        start_date: Data inicial no formato YYYY-MM-DD (opcional).
        end_date: Data final no formato YYYY-MM-DD (opcional).

    Returns:
        Estrutura JSON com `kpis` e `timeseries` (conforme `PatientDataResponse`).
    """
    try:
        df_all = load_cpap_data(patient)
        df = df_all[df_all['patient'] == patient].copy()
        if df.empty:
            return {"kpis": {"usage_mins": 0, "ahi": 0, "leak": 0, "score": 0, "mask_events": 0, "leak_95": 0, "mask_on_off": 0, "pressure": 0}, "timeseries": {}}
        
        if start_date:
            df = df[df['data_terapia'] >= pd.Timestamp(start_date)]
        if end_date:
            df = df[df['data_terapia'] <= pd.Timestamp(end_date)]
        
        if df.empty:
            return {"kpis": {"usage_mins": 0, "ahi": 0, "leak": 0, "score": 0, "mask_events": 0, "leak_95": 0, "mask_on_off": 0, "pressure": 0}, "timeseries": {}}
        
        df = df.sort_values('data_terapia')
        
        session_df = df.groupby('data_sessao').agg({
            'usage_mins': 'max',
            'AHI': 'mean',
            'Leak.95': 'mean',
            'MaskEvents': 'max',
            'BlowPress.95': 'mean'
        }).reset_index()
        
        session_df['score'] = session_df.apply(calculate_myair_score, axis=1)
        session_df['data_sessao'] = session_df['data_sessao'].astype(str)
        
        last = session_df.iloc[-1]
        
        return {
            "kpis": {
                "usage_mins": float(last['usage_mins']),
                "ahi": float(last['AHI']),
                "leak": float(last['Leak.95']),
                "score": int(last['score']),
                "mask_events": float(last['MaskEvents']) if not pd.isna(last['MaskEvents']) else 0,
                "leak_95": float(last['Leak.95']) if not pd.isna(last['Leak.95']) else 0,
                "mask_on_off": float(last['MaskEvents']) if not pd.isna(last['MaskEvents']) else 0,
                "pressure": float(last['BlowPress.95']) if not pd.isna(last['BlowPress.95']) else 0
            },
            "timeseries": session_df.to_dict(orient="list")
        }
    except Exception as e:
        logger.error(f"Error loading patient data for {patient}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load patient data")

@router.get("/smartband/{patient}/daily", response_model=SmartbandDataResponse)
def get_smartband_daily(patient: str, start_date: Optional[str] = Query(None), end_date: Optional[str] = Query(None)):
    """Retorna dados diários de sono e atividade do Smartband para o paciente.

    Filtra por paciente e intervalo de datas quando fornecidos.
    """
    try:
        df_sleep = load_smartband_table("smartband_sleep_daily", patient)
        df_activity = load_smartband_table("smartband_activity", patient)
        
        res = {"sleep": {}, "activity": {}}
        
        if not df_sleep.empty:
            df_p = df_sleep[df_sleep['patient'].str.lower() == patient.lower()].copy()
            if not df_p.empty:
                if start_date:
                    df_p = df_p[df_p['report_date'] >= pd.Timestamp(start_date)]
                if end_date:
                    df_p = df_p[df_p['report_date'] <= pd.Timestamp(end_date)]
                if not df_p.empty:
                    df_p = df_p.sort_values('report_date')
                    df_p['report_date'] = df_p['report_date'].dt.strftime('%Y-%m-%d')
                    for col in df_p.select_dtypes(include=['category']).columns:
                        df_p[col] = df_p[col].astype(str)
                    df_p = df_p.fillna(0)
                    res["sleep"] = df_p.to_dict(orient="list")
                
        if not df_activity.empty:
            df_a = df_activity[df_activity['patient'].str.lower() == patient.lower()].copy()
            if not df_a.empty:
                if start_date:
                    df_a = df_a[df_a['report_date'] >= pd.Timestamp(start_date)]
                if end_date:
                    df_a = df_a[df_a['report_date'] <= pd.Timestamp(end_date)]
                if not df_a.empty:
                    df_a = df_a.sort_values('report_date')
                    df_a['report_date'] = df_a['report_date'].dt.strftime('%Y-%m-%d')
                    for col in df_a.select_dtypes(include=['category']).columns:
                        df_a[col] = df_a[col].astype(str)
                    df_a = df_a.fillna(0)
                    res["activity"] = df_a.to_dict(orient="list")
                
        return res
    except Exception as e:
        logger.error(f"Error loading Smartband data for {patient}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load Smartband data")

@router.get("/smartband/{patient}/monthly-sleep", response_model=MonthlySleepTable)
def get_monthly_sleep_table(patient: str, year: int = Query(None), month: int = Query(None)):
    """Retorna a tabela mensal de sono (linhas) para o paciente no mês/ano solicitado.

    Se `year` e `month` não forem informados, retorna todas as linhas disponíveis.
    """
    try:
        df_sleep = load_smartband_table("smartband_sleep_daily", patient)
        if df_sleep.empty:
            return {"rows": []}
        
        df_p = df_sleep[df_sleep['patient'].str.lower() == patient.lower()].copy()
        if df_p.empty:
            return {"rows": []}
        
        if year and month:
            df_p['report_date'] = pd.to_datetime(df_p['report_date'])
            df_p = df_p[(df_p['report_date'].dt.year == year) & (df_p['report_date'].dt.month == month)]
            df_p = df_p.sort_values('report_date')
            df_p['report_date'] = df_p['report_date'].dt.strftime('%Y-%m-%d')
        
        df_p = df_p[['report_date', 'total_duration_min', 'rem_min', 'deep_min', 'light_min', 'awake_min', 'sleep_score']]
        for col in df_p.columns:
            if col != 'report_date':
                df_p[col] = pd.to_numeric(df_p[col], errors='coerce').fillna(0)
        
        rows = df_p.to_dict(orient="records")
        return {"rows": rows}
    except Exception as e:
        logger.error(f"Error loading monthly sleep data for {patient}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load monthly sleep data")

@router.get("/cpap/{patient}/monthly", response_model=MonthlyCpapTable)
def get_cpap_monthly_table(patient: str, year: int = Query(None), month: int = Query(None)):
    """Retorna a tabela mensal de sessões CPAP para o paciente no mês/ano solicitado.

    Retorna métricas agregadas por `data_sessao` e aplica o cálculo de score.
    """
    try:
        df_all = load_cpap_data(patient)
        if df_all.empty:
            return {"rows": []}
        
        df = df_all[df_all['patient'] == patient].copy()
        if df.empty:
            return {"rows": []}
        
        df = df[df['PatientHours'] > 0].copy()
        
        if year and month:
            df['sessao_dt'] = pd.to_datetime(df['data_sessao'])
            df = df[(df['sessao_dt'].dt.year == year) & (df['sessao_dt'].dt.month == month)]
            df = df.drop(columns=['sessao_dt'])
        
        if df.empty:
            return {"rows": []}
        
        session_df = df.groupby('data_sessao').agg({
            'usage_mins': 'max',
            'AHI': 'mean',
            'Leak.95': 'max',
            'MaskEvents': 'max',
            'MaskPress.95': 'max',
            'TidVol.50': 'max',
            'MinVent.50': 'max',
            'RespRate.50': 'max',
            'BlowPress.95': 'max'
        }).reset_index()
        
        session_df['score'] = session_df.apply(calculate_myair_score, axis=1)
        session_df['data_sessao'] = session_df['data_sessao'].astype(str)
        session_df = session_df.sort_values('data_sessao', ascending=False)
        session_df = session_df.fillna(0)
        session_df['AHI'] = session_df['AHI'].clip(lower=0)
        
        select_columns = ['data_sessao', 'usage_mins', 'AHI', 'Leak.95', 'MaskEvents', 'score', 'MaskPress.95', 'TidVol.50', 'MinVent.50', 'RespRate.50', 'BlowPress.95']
        session_df = session_df[select_columns]
        
        rename_map = {
            'AHI': 'ahi',
            'Leak.95': 'leak_95',
            'MaskEvents': 'mask_events',
            'MaskPress.95': 'pressure',
            'TidVol.50': 'tidal_volume',
            'MinVent.50': 'minute_ventilation',
            'RespRate.50': 'breath_rate',
            'BlowPress.95': 'p95_pressure'
        }
        session_df = session_df.rename(columns=rename_map)
        
        rows = session_df.to_dict(orient="records")
        return {"rows": rows}
    except Exception as e:
        logger.error(f"Error loading monthly CPAP data for {patient}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load monthly CPAP data")

@router.get("/correlation/{patient}", response_model=CorrelationResponse)
def get_correlation(patient: str):
    """Retorna métricas de correlação entre CPAP e sono da Smartband.

    Para cada métrica de sono (sleep_score, sono profundo, REM, tempo acordado),
    compara a média em noites com bom controle de CPAP (AHI < 5) versus noites
    com AHI elevado (AHI >= 5), cruzando por data.

    Também retorna os pares (ahi, sleep_score) para exibir um scatter chart.
    """
    try:
        # --- CPAP: agrega por sessão ---
        df_cpap_all = load_cpap_data(patient)
        if df_cpap_all.empty:
            return {"metrics": [], "nights_with_both": 0, "ahi_sleep_score_pairs": {}}

        df_cpap = df_cpap_all[df_cpap_all['patient'] == patient].copy()
        if df_cpap.empty:
            return {"metrics": [], "nights_with_both": 0, "ahi_sleep_score_pairs": {}}

        cpap_by_day = df_cpap.groupby('data_sessao').agg(
            ahi=('AHI', 'mean'),
            usage_mins=('usage_mins', 'max'),
            score=('AHI', 'count')  # placeholder, recalculado abaixo
        ).reset_index()
        cpap_by_day['data_sessao'] = cpap_by_day['data_sessao'].astype(str)

        df_sleep = load_smartband_table("smartband_sleep_daily", patient)
        if df_sleep.empty:
            return {"metrics": [], "nights_with_both": 0, "ahi_sleep_score_pairs": {}}

        df_sleep_p = df_sleep[df_sleep['patient'].str.lower() == patient.lower()].copy()
        if df_sleep_p.empty:
            return {"metrics": [], "nights_with_both": 0, "ahi_sleep_score_pairs": {}}

        df_sleep_p['report_date'] = pd.to_datetime(df_sleep_p['report_date']).dt.strftime('%Y-%m-%d')

        merged = pd.merge(
            cpap_by_day[['data_sessao', 'ahi', 'usage_mins']],
            df_sleep_p[['report_date', 'sleep_score', 'deep_min', 'rem_min', 'awake_min', 'total_duration_min']],
            left_on='data_sessao',
            right_on='report_date',
            how='inner'
        )

        if merged.empty:
            return {"metrics": [], "nights_with_both": 0, "ahi_sleep_score_pairs": {}}

        for col in ['ahi', 'sleep_score', 'deep_min', 'rem_min', 'awake_min', 'total_duration_min', 'usage_mins']:
            merged[col] = pd.to_numeric(merged[col], errors='coerce').fillna(0)

        good = merged[merged['ahi'] < 5]
        bad  = merged[merged['ahi'] >= 5]

        def _avgs(col, higher_better):
            return {
                "label": col,
                "good_nights_avg": round(float(good[col].mean()), 1) if not good.empty else 0.0,
                "bad_nights_avg":  round(float(bad[col].mean()),  1) if not bad.empty  else 0.0,
                "n_good": int(len(good)),
                "n_bad":  int(len(bad)),
                "direction": "higher_is_better" if higher_better else "lower_is_better",
            }

        metrics = [
            _avgs("sleep_score",        True),
            _avgs("deep_min",           True),
            _avgs("rem_min",            True),
            _avgs("awake_min",          False),
            _avgs("total_duration_min", True),
        ]

        scatter_pairs = {
            "ahi":         [round(float(v), 2) for v in merged['ahi'].tolist()],
            "sleep_score": [round(float(v), 1) for v in merged['sleep_score'].tolist()],
            "dates":       merged['data_sessao'].tolist(),
        }

        return {
            "metrics": metrics,
            "nights_with_both": int(len(merged)),
            "ahi_sleep_score_pairs": scatter_pairs,
        }
    except Exception as e:
        logger.error(f"Error loading correlation data for {patient}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load correlation data")


@router.get("/available-periods")
def get_available_periods(patient=None):
    try:
        df = load_cpap_data(patient) if patient else load_cpap_data()
        if df.empty:
            return {"periods": []}
        df['data_terapia'] = pd.to_datetime(df['data_terapia'], errors='coerce')
        df = df.dropna(subset=['data_terapia'])
        if df.empty:
            return {"periods": []}
        df['year'] = df['data_terapia'].dt.year
        df['month'] = df['data_terapia'].dt.month
        periods = []
        for year in sorted(df['year'].unique(), reverse=True):
            year_data = df[df['year'] == year]
            for month in sorted(year_data['month'].unique(), reverse=True):
                periods.append({"year": int(year), "month": int(month)})
        return {"periods": periods}
    except Exception as e:
        logger.error(f"Error loading available periods: {e}")
        raise HTTPException(status_code=500, detail="Failed to load available periods")
