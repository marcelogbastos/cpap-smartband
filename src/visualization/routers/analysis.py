"""Endpoints das abas de análise: Tendências, Noite detalhada, Correlação e Relatório."""

import logging
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from ..services import analysis as an
from ..services.data_loader import load_cpap_data, load_smartband_table
from .api import _filter_patient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def _table(name: str, patient: str) -> pd.DataFrame:
    return _filter_patient(load_smartband_table(name, patient), patient)


def _cpap(patient: str) -> pd.DataFrame:
    return _filter_patient(load_cpap_data(patient), patient)


def _fail(what: str, patient: str, e: Exception):
    logger.exception(f"Erro em {what} para {patient}: {e}")
    raise HTTPException(status_code=500, detail=f"Falha ao calcular {what}")


@router.get("/trends/{patient}")
def get_trends(patient: str, start: Optional[str] = Query(None), end: Optional[str] = Query(None),
               days: Optional[int] = Query(None, ge=1)):
    """Série diária (calendário completo) com tipos de evento, adesão, pressão vs faixa e médias móveis."""
    try:
        return an.compute_trends(_cpap(patient), start, end, days)
    except Exception as e:
        _fail("tendências", patient, e)


@router.get("/night/{patient}/dates")
def get_night_dates(patient: str):
    """Noites com dados detalhados (sessões do CPAP e/ou fases do sono da pulseira)."""
    try:
        dates = {}
        for table, key in (("cpap_signals", "cpap"), ("smartband_sleep_stages", "sleep")):
            df = _table(table, patient)
            if not df.empty:
                for d in pd.to_datetime(df["night"]).dt.strftime("%Y-%m-%d").unique():
                    dates.setdefault(d, {"date": d, "cpap": False, "sleep": False})[key] = True
        return {"nights": sorted(dates.values(), key=lambda x: x["date"])}
    except Exception as e:
        _fail("lista de noites", patient, e)


@router.get("/night/{patient}/{night}")
def get_night(patient: str, night: str):
    """Linha do tempo de uma noite: sessões, pressão/fuga, eventos, fases do sono, FC e SpO2."""
    try:
        pd.Timestamp(night)
    except Exception:
        raise HTTPException(status_code=400, detail="Data inválida (use AAAA-MM-DD)")
    try:
        res = an.compute_night(
            night,
            signals=_table("cpap_signals", patient),
            events=_table("cpap_events", patient),
            stages=_table("smartband_sleep_stages", patient),
            vitals=_table("smartband_vitals", patient),
            oximetry=_table("cpap_oximetry", patient),
        )
        # resumo do STR e da pulseira para a mesma noite
        nights = an.nightly_cpap(_cpap(patient))
        row = nights[nights["date"] == pd.Timestamp(night)] if not nights.empty else nights
        res["cpap_summary"] = an._records(row)[0] if len(row) else None
        sleep = _table("smartband_sleep_daily", patient)
        if not sleep.empty:
            s = sleep[pd.to_datetime(sleep["report_date"]).dt.normalize() == pd.Timestamp(night)]
            cols = [c for c in ["sleep_score", "total_duration_min", "deep_min", "light_min", "rem_min",
                                "awake_min", "avg_hr", "min_hr", "avg_spo2", "min_spo2"] if c in s.columns]
            res["sleep_summary"] = an._records(s[cols])[0] if len(s) else None
        return res
    except HTTPException:
        raise
    except Exception as e:
        _fail("noite detalhada", patient, e)


def _dataset(patient: str) -> pd.DataFrame:
    return an.nightly_dataset(_cpap(patient),
                              _table("smartband_sleep_daily", patient),
                              _table("smartband_activity", patient))


@router.get("/correlation/{patient}/matrix")
def get_correlation_matrix(patient: str):
    """Spearman entre variáveis do CPAP/atividade e do sono, com p-valor e n de noites."""
    try:
        return an.correlation_matrix(_dataset(patient))
    except Exception as e:
        _fail("matriz de correlação", patient, e)


@router.get("/correlation/{patient}/pair")
def get_correlation_pair(patient: str, x: str = Query(...), y: str = Query(...)):
    """Pontos (uma noite cada), reta de tendência e Spearman para um par de variáveis."""
    if x not in an.CORR_VARS or y not in an.CORR_VARS:
        raise HTTPException(status_code=400, detail="Variável desconhecida")
    try:
        return an.correlation_pair(_dataset(patient), x, y)
    except Exception as e:
        _fail("correlação", patient, e)


@router.get("/report/{patient}")
def get_report(patient: str, start: Optional[str] = Query(None), end: Optional[str] = Query(None),
               days: Optional[int] = Query(None, ge=1)):
    """Dados do relatório para consulta: resumo do período, configuração, sono e piores noites."""
    try:
        trends = an.compute_trends(_cpap(patient), start, end, days)
        days = trends["days"]
        sleep = _table("smartband_sleep_daily", patient)
        sleep_summary = None
        if not sleep.empty and days:
            d0, d1 = days[0]["date"], days[-1]["date"]
            sd = pd.to_datetime(sleep["report_date"]).dt.normalize()
            s = sleep[(sd >= pd.Timestamp(d0)) & (sd <= pd.Timestamp(d1))]
            if len(s):
                num = lambda c: pd.to_numeric(s[c], errors="coerce").astype(float).replace(0, float("nan"))
                sleep_summary = {
                    "nights": int(len(s)),
                    "score_avg": an._num(num("sleep_score").mean(), 1),
                    "total_h_avg": an._num(num("total_duration_min").mean() / 60),
                    "deep_min_avg": an._num(num("deep_min").mean(), 0),
                    "rem_min_avg": an._num(num("rem_min").mean(), 0),
                    "light_min_avg": an._num(num("light_min").mean(), 0),
                    "awake_min_avg": an._num(pd.to_numeric(s["awake_min"], errors="coerce").mean(), 0),
                    "avg_hr": an._num(num("avg_hr").mean(), 0) if "avg_hr" in s else None,
                }
        worst = sorted([d for d in days if d.get("used") and d.get("ahi") is not None],
                       key=lambda d: d["ahi"], reverse=True)[:7]
        return {
            "patient": patient,
            "summary": trends["summary"],
            "observations": trends["observations"],
            "current_settings": trends.get("current_settings"),
            "settings_changes": trends["settings_changes"],
            "sleep": sleep_summary,
            "worst_nights": worst,
            "days": days,
            "adherence_min_h": an.ADHERENCE_MIN_H,
            "adherence_target": an.ADHERENCE_TARGET,
        }
    except Exception as e:
        _fail("relatório", patient, e)
