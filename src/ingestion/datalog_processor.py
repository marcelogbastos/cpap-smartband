"""Processamento da pasta DATALOG do cartão SD (dados detalhados de cada sessão).

Para cada sessão (arquivos AAAAMMDD_HHMMSS_*.edf):
  - *_EVE.edf  → eventos respiratórios com horário (apneia central/obstrutiva,
                 hipopneia, despertar...)            → tabela cpap_events
  - *_PLD.edf  → pressão, fuga, frequência respiratória, ronco, limitação de
                 fluxo a cada 2 s, agregados em janelas de 30 s → cpap_signals
  - *_SAD.edf  → pulso/SpO2 do oxímetro (só existe com oxímetro conectado;
                 sessões sem dados válidos são ignoradas) → cpap_oximetry

A noite de cada registro segue a mesma regra do STR.edf: data de início − 12 h
(uma sessão iniciada à 01:30 do dia 29 pertence à noite do dia 28).
"""

import glob
import logging
import os
from datetime import timedelta

import numpy as np
import pandas as pd

from src.ingestion.edf import read_edf, to_l_per_min

logger = logging.getLogger(__name__)

BUCKET_S = 30

# rótulo no PLD -> (coluna de saída, agregação)
PLD_SIGNALS = {
    "MaskPress.2s": ("mask_press", "mean"),
    "Press.2s": ("press", "mean"),
    "EprPress.2s": ("epr_press", "mean"),
    "Leak.2s": ("leak", "mean"),           # convertido para L/min
    "RespRate.2s": ("resp_rate", "mean"),
    "TidVol.2s": ("tid_vol", "mean"),
    "MinVent.2s": ("min_vent", "mean"),
    "Snore.2s": ("snore", "max"),
    "FlowLim.2s": ("flow_lim", "max"),
}

EVENT_TYPES = {
    "Obstructive Apnea": "obstrutiva",
    "Central Apnea": "central",
    "Apnea": "nao_classificada",
    "Hypopnea": "hipopneia",
    "Arousal": "despertar",
    "RERA": "rera",
    "CSR": "csr",
}


def night_of(ts) -> pd.Timestamp:
    return (pd.Timestamp(ts) - pd.Timedelta(hours=12)).normalize()


def _bucketize(edf, spec, rename_leak=True):
    """Agrega os sinais de um EDF contínuo em janelas de BUCKET_S segundos."""
    cols = {}
    t = None
    for label, (name, how) in spec.items():
        if label not in edf.signals:
            continue
        secs, values = edf.series(label)
        if label.startswith("Leak") and rename_leak:
            values = to_l_per_min(values, edf.signals[label].dimension)
        bucket = (secs // BUCKET_S).astype(int)
        s = pd.Series(values).groupby(bucket)
        cols[name] = s.max() if how == "max" else s.mean()
        t = cols[name].index if t is None else t.union(cols[name].index)
    if not cols:
        return pd.DataFrame()
    df = pd.DataFrame(cols).reindex(t)
    df["time"] = [edf.start + timedelta(seconds=int(b) * BUCKET_S) for b in df.index]
    return df.reset_index(drop=True)


def read_session_events(path) -> pd.DataFrame:
    edf = read_edf(path)
    rows = []
    for onset, duration, text in edf.annotations:
        if text == "Recording starts":
            continue
        rows.append({
            "time": edf.start + timedelta(seconds=onset),
            "event": EVENT_TYPES.get(text, text),
            "duration_s": duration,
        })
    return pd.DataFrame(rows, columns=["time", "event", "duration_s"])


def read_session_signals(path) -> pd.DataFrame:
    return _bucketize(read_edf(path), PLD_SIGNALS)


def read_session_oximetry(path) -> pd.DataFrame:
    edf = read_edf(path)
    spec = {"Pulse.1s": ("pulse", "mean"), "SpO2.1s": ("spo2", "mean")}
    df = _bucketize(edf, spec)
    if df.empty or not df.drop(columns="time").notna().any().any():
        return pd.DataFrame()
    return df.dropna(subset=[c for c in ("pulse", "spo2") if c in df.columns], how="all")


def process_datalog(datalog_dir: str, patient: str):
    """Lê todas as sessões de DATALOG. Retorna (eventos, sinais, oximetria)."""
    events, signals, oxi = [], [], []
    for path in sorted(glob.glob(os.path.join(datalog_dir, "*", "*_EVE.edf"))):
        try:
            df = read_session_events(path)
            if not df.empty:
                df["session"] = os.path.basename(path)[:15]
                events.append(df)
        except Exception as e:
            logger.warning(f"   Ignorando {os.path.basename(path)}: {e}")
    for path in sorted(glob.glob(os.path.join(datalog_dir, "*", "*_PLD.edf"))):
        try:
            df = read_session_signals(path)
            if not df.empty:
                df["session"] = os.path.basename(path)[:15]
                signals.append(df)
        except Exception as e:
            logger.warning(f"   Ignorando {os.path.basename(path)}: {e}")
    for path in sorted(glob.glob(os.path.join(datalog_dir, "*", "*_SAD.edf"))):
        try:
            df = read_session_oximetry(path)
            if not df.empty:
                df["session"] = os.path.basename(path)[:15]
                oxi.append(df)
        except Exception as e:
            logger.warning(f"   Ignorando {os.path.basename(path)}: {e}")

    def finish(parts):
        if not parts:
            return pd.DataFrame()
        df = pd.concat(parts, ignore_index=True).sort_values("time")
        df["night"] = df["time"].map(night_of)
        df["patient"] = patient
        return df.reset_index(drop=True)

    return finish(events), finish(signals), finish(oxi)
