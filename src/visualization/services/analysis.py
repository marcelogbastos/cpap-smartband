"""Cálculos das abas de análise (Tendências, Noite detalhada, Correlação, Relatório).

Funções puras sobre DataFrames — os endpoints só carregam os dados e chamam estas
funções, o que facilita testar.
"""

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ADHERENCE_MIN_H = 4.0      # noite "usada" para fins de adesão
ADHERENCE_TARGET = 70.0    # % das noites na janela (critério usual das operadoras)
MIN_N_CORRELATION = 20     # abaixo disso a correlação é marcada como pouco confiável


# ─── utilidades ────────────────────────────────────────────────────────────────

def _num(v, nd=2):
    """float JSON-safe (NaN/inf -> None)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(f):
        return None
    return round(f, nd)


def _col(df, name):
    return df[name] if name in df.columns else pd.Series(np.nan, index=df.index)


def _records(df: pd.DataFrame, nd=2) -> List[dict]:
    out = []
    for row in df.to_dict(orient="records"):
        rec = {}
        for k, v in row.items():
            if isinstance(v, (pd.Timestamp,)):
                rec[k] = v.strftime("%Y-%m-%dT%H:%M:%S") if (v.hour or v.minute or v.second) else v.strftime("%Y-%m-%d")
            elif isinstance(v, (bool, np.bool_)):
                rec[k] = bool(v)
            elif isinstance(v, (int, np.integer)):
                rec[k] = int(v)
            elif isinstance(v, (float, np.floating)):
                rec[k] = _num(v, nd)
            elif v is None or (isinstance(v, float) and np.isnan(v)):
                rec[k] = None
            else:
                rec[k] = v
        out.append(rec)
    return out


# ─── Tendências ────────────────────────────────────────────────────────────────

def pressure_range(row) -> tuple:
    """Faixa de pressão configurada: AutoSet (Mode 1) usa mín/máx; CPAP fixo usa a pressão única."""
    mode = row.get("Mode")
    if mode == 1 or (pd.notna(row.get("S.AS.MaxPress")) and mode != 0):
        return row.get("S.AS.MinPress"), row.get("S.AS.MaxPress")
    p = row.get("S.C.Press")
    return p, p


def nightly_cpap(df: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por noite com uso, a partir do DataFrame do data_loader (já filtrado por uso > 0)."""
    if df.empty:
        return pd.DataFrame()
    d = df.sort_values("data_terapia").groupby("data_sessao").last().reset_index()
    out = pd.DataFrame({
        "date": pd.to_datetime(d["data_sessao"]),
        "usage_h": d["usage_mins"] / 60.0,
        "ahi": _col(d, "AHI"), "oai": _col(d, "OAI"), "cai": _col(d, "CAI"),
        "uai": _col(d, "UAI"), "hi": _col(d, "HI"),
        "leak50": _col(d, "Leak.50"), "leak95": _col(d, "Leak.95"), "leak_max": _col(d, "Leak.Max"),
        "press50": _col(d, "MaskPress.50"), "press95": _col(d, "MaskPress.95"), "press_max": _col(d, "MaskPress.Max"),
        "resp_rate": _col(d, "RespRate.50"), "mask_removals": _col(d, "mask_removals"),
        "mode": _col(d, "Mode"), "epr": _col(d, "S.EPR.Level"),
    })
    rng = d.apply(lambda r: pressure_range(r), axis=1, result_type="expand") if not d.empty else None
    out["set_min"] = rng[0].values if rng is not None else np.nan
    out["set_max"] = rng[1].values if rng is not None else np.nan
    return out


def compute_trends(df: pd.DataFrame, start: Optional[str] = None, end: Optional[str] = None,
                   days: Optional[int] = None) -> dict:
    """Série diária do calendário + resumo. `days` = últimos N dias do histórico (ignora `start`)."""
    nights = nightly_cpap(df)
    if nights.empty:
        return {"days": [], "summary": {}, "settings_changes": []}

    # Calendário completo (noites sem uso = 0 h) — necessário para a adesão
    cal = pd.date_range(nights["date"].min(), nights["date"].max(), freq="D")
    daily = nights.set_index("date").reindex(cal)
    daily.index.name = "date"
    daily["used"] = daily["usage_h"].notna()
    daily["usage_h"] = daily["usage_h"].fillna(0.0)
    daily["adherent"] = daily["usage_h"] >= ADHERENCE_MIN_H

    r7 = lambda s: s.rolling("7D", min_periods=1).mean()
    r30 = lambda s: s.rolling("30D", min_periods=1).mean()
    daily["ahi_7"], daily["ahi_30"] = r7(daily["ahi"]), r30(daily["ahi"])
    daily["usage_7"], daily["usage_30"] = r7(daily["usage_h"]), r30(daily["usage_h"])
    daily["leak95_7"], daily["leak95_30"] = r7(daily["leak95"]), r30(daily["leak95"])
    daily["adherence_30"] = daily["adherent"].astype(float).rolling("30D", min_periods=1).mean() * 100
    daily["days_in_window"] = daily["adherent"].rolling("30D", min_periods=1).count()
    daily["press_at_max"] = (daily["press95"] >= daily["set_max"] - 0.2) & daily["set_max"].notna() & (daily["set_min"] != daily["set_max"])

    # mudanças de configuração ao longo do tempo
    changes = []
    cfg_cols = ["mode", "set_min", "set_max", "epr"]
    prev = None
    for date, row in nights.set_index("date")[cfg_cols].iterrows():
        cur = tuple(None if pd.isna(v) else float(v) for v in row.values)
        if prev is not None and cur != prev:
            changes.append({"date": date.strftime("%Y-%m-%d"),
                            "from": dict(zip(cfg_cols, prev)), "to": dict(zip(cfg_cols, cur))})
        prev = cur

    view = daily
    if days:
        last = pd.Timestamp(end) if end else daily.index.max()
        start = (last - pd.Timedelta(days=int(days) - 1)).strftime("%Y-%m-%d")
    if start:
        view = view[view.index >= pd.Timestamp(start)]
    if end:
        view = view[view.index <= pd.Timestamp(end)]

    return {
        "days": _records(view.reset_index()),
        "summary": summarize_period(view),
        "observations": observations(summarize_period(view)),
        "settings_changes": changes,
        "current_settings": dict(zip(cfg_cols, [_num(v) for v in nights.iloc[-1][cfg_cols].values])),
        "adherence_min_h": ADHERENCE_MIN_H,
        "adherence_target": ADHERENCE_TARGET,
    }


def summarize_period(daily: pd.DataFrame) -> dict:
    """Resumo de um período (DataFrame diário do calendário, com noites sem uso)."""
    if daily.empty:
        return {}
    used = daily[daily["used"]]
    w = used["usage_h"]
    total_h = float(w.sum())

    def wavg(col):  # média ponderada pelas horas de uso (= eventos/hora do período)
        s = used[col]
        m = s.notna() & (w > 0)
        return _num((s[m] * w[m]).sum() / w[m].sum()) if m.any() and w[m].sum() > 0 else None

    ahi = wavg("ahi")
    cai, oai, hi, uai = wavg("cai"), wavg("oai"), wavg("hi"), wavg("uai")
    central_share = _num(100 * cai / ahi, 1) if ahi and cai is not None else None
    n_days = int(len(daily))
    return {
        "start": daily.index.min().strftime("%Y-%m-%d"),
        "end": daily.index.max().strftime("%Y-%m-%d"),
        "days": n_days,
        "nights_used": int(len(used)),
        "nights_adherent": int(daily["adherent"].sum()),
        "adherence_pct": _num(100 * daily["adherent"].mean(), 1),
        "adherence_ok": bool(100 * daily["adherent"].mean() >= ADHERENCE_TARGET),
        "usage_avg_all_days_h": _num(daily["usage_h"].mean()),
        "usage_avg_used_nights_h": _num(w.mean()) if len(w) else None,
        "total_hours": _num(total_h, 1),
        "ahi_avg": ahi, "ahi_median": _num(used["ahi"].median()),
        "ahi_max": _num(used["ahi"].max()),
        "nights_ahi_ge_5": int((used["ahi"] >= 5).sum()),
        "oai_avg": oai, "cai_avg": cai, "hi_avg": hi, "uai_avg": uai,
        "central_share_pct": central_share,
        "leak95_avg": _num(used["leak95"].mean()), "leak95_max": _num(used["leak95"].max()),
        "nights_leak_gt_24": int((used["leak95"] > 24).sum()),
        "press95_avg": _num(used["press95"].mean()),
        "press50_avg": _num(used["press50"].mean()),
        "nights_press_at_max": int(daily["press_at_max"].sum()) if "press_at_max" in daily else 0,
        "set_min": _num(used["set_min"].iloc[-1]) if len(used) else None,
        "set_max": _num(used["set_max"].iloc[-1]) if len(used) else None,
    }


def _br(v, nd=1) -> str:
    """Número no formato brasileiro (vírgula decimal)."""
    return "—" if v is None else f"{v:.{nd}f}".replace(".", ",")


def observations(summary: dict) -> List[dict]:
    """Pontos de atenção do período, em linguagem factual (não é diagnóstico)."""
    obs = []
    if not summary:
        return obs
    adh = summary.get("adherence_pct")
    if adh is not None:
        if adh < ADHERENCE_TARGET:
            obs.append({"level": "alerta", "text":
                f"Adesão de {adh:.0f}% no período (noites com ≥ {ADHERENCE_MIN_H:.0f} h): abaixo da meta de "
                f"{ADHERENCE_TARGET:.0f}% usada pelas operadoras."})
        else:
            obs.append({"level": "ok", "text": f"Adesão de {adh:.0f}% no período — dentro da meta de {ADHERENCE_TARGET:.0f}%."})
    share, ahi = summary.get("central_share_pct"), summary.get("ahi_avg")
    if share is not None and ahi is not None and ahi >= 1 and share >= 50:
        obs.append({"level": "atencao", "text":
            f"{share:.0f}% do IAH vem de apneias centrais (índice central médio {_br(summary.get('cai_avg'), 2)} ev/h). "
            "Predomínio de eventos centrais é um dado a levar ao médico: a conduta pode ser diferente da apneia obstrutiva."})
    if ahi is not None:
        n5 = summary.get("nights_ahi_ge_5", 0)
        lvl = "ok" if ahi < 5 else "alerta"
        obs.append({"level": lvl, "text": f"IAH médio de {_br(ahi)} ev/h" + (f"; {n5} noite(s) com IAH ≥ 5." if n5 else ".")})
    n_max, used = summary.get("nights_press_at_max", 0), summary.get("nights_used", 0)
    if used and n_max and n_max / used >= 0.1:
        obs.append({"level": "atencao", "text":
            f"A pressão P95 chegou ao máximo configurado ({_br(summary.get('set_max'))} cmH₂O) em {n_max} de {used} noites "
            f"({100 * n_max / used:.0f}%). Se o IAH não estiver controlado, a faixa de pressão é um ponto a revisar com o médico."})
    nl = summary.get("nights_leak_gt_24", 0)
    if nl:
        obs.append({"level": "atencao", "text": f"Fuga P95 acima de 24 L/min em {nl} noite(s): verifique o ajuste da máscara."})
    return obs


# ─── Noite detalhada ───────────────────────────────────────────────────────────

def stage_at(times: pd.Series, stages: pd.DataFrame) -> pd.Series:
    """Fase do sono (smartband) em cada instante; None fora dos intervalos registrados."""
    if stages.empty or times.empty:
        return pd.Series([None] * len(times), index=times.index, dtype=object)
    st = stages.sort_values("start").reset_index(drop=True)
    idx = np.searchsorted(st["start"].values, times.values, side="right") - 1
    out = []
    for t, i in zip(times.values, idx):
        if i >= 0 and t < st.at[i, "end"].to_datetime64():
            out.append(st.at[i, "stage"])
        else:
            out.append(None)
    return pd.Series(out, index=times.index, dtype=object)


def compute_night(night: str, signals: pd.DataFrame, events: pd.DataFrame,
                  stages: pd.DataFrame, vitals: pd.DataFrame, oximetry: pd.DataFrame) -> dict:
    """Monta a linha do tempo de uma noite e cruza eventos do CPAP com as fases do sono."""
    n = pd.Timestamp(night)
    sel = lambda df: df[df["night"] == n].sort_values("time") if not df.empty else df
    sig = sel(signals)
    ev = sel(events)
    st = stages[stages["night"] == n].sort_values("start") if not stages.empty else stages

    sessions = []
    if not sig.empty:
        for s, g in sig.groupby("session"):
            sessions.append({"start": g["time"].min(), "end": g["time"].max() + pd.Timedelta(seconds=30)})
    # janela = sessões do CPAP ∪ sono da pulseira, com margem
    bounds = [x for s in sessions for x in (s["start"], s["end"])]
    if not st.empty:
        bounds += [st["start"].min(), st["end"].max()]
    if not bounds:
        return {"night": night, "has_data": False}
    w0, w1 = min(bounds) - pd.Timedelta(minutes=15), max(bounds) + pd.Timedelta(minutes=15)

    vit = vitals
    if not vit.empty:
        vt = pd.to_datetime(vit["timestamp"])
        if getattr(vt.dt, "tz", None) is not None:
            vt = vt.dt.tz_localize(None)      # hora local de parede
        vit = vit.assign(t=vt)
        vit = vit[(vit["t"] >= w0) & (vit["t"] <= w1)]
    hr = vit[vit["metric"] == "heart_rate"] if not vit.empty else vit
    spo2 = vit[vit["metric"] == "spo2"] if not vit.empty else vit
    oxi = oximetry[oximetry["night"] == n] if not oximetry.empty else oximetry

    # eventos × fase do sono
    apnea_types = ["obstrutiva", "central", "hipopneia", "nao_classificada"]
    ev = ev.copy()
    if not ev.empty:
        ev["stage"] = stage_at(ev["time"], st)
    by_stage = []
    if not st.empty:
        # tempo em cada fase durante o uso do CPAP
        hours_on_cpap_by_stage = {}
        for _, r in st.iterrows():
            overlap = 0.0
            for s in sessions:
                a, b = max(r["start"], s["start"]), min(r["end"], s["end"])
                if b > a:
                    overlap += (b - a).total_seconds() / 3600
            hours_on_cpap_by_stage[r["stage"]] = hours_on_cpap_by_stage.get(r["stage"], 0.0) + overlap
        for stage in ["acordado", "leve", "profundo", "rem"]:
            hours = hours_on_cpap_by_stage.get(stage, 0.0)
            e = ev[(ev["stage"] == stage) & ev["event"].isin(apnea_types)] if not ev.empty else ev
            by_stage.append({"stage": stage, "hours_on_cpap": _num(hours),
                             "events": int(len(e)),
                             "per_hour": _num(len(e) / hours) if hours >= 0.25 else None})
        if not ev.empty:
            outside = ev[ev["stage"].isna() & ev["event"].isin(apnea_types)]
            if len(outside):
                by_stage.append({"stage": "sem_registro", "hours_on_cpap": None,
                                 "events": int(len(outside)), "per_hour": None})

    def pts(df, tcol, vcol):
        if df.empty:
            return []
        return [{"t": t.strftime("%Y-%m-%dT%H:%M:%S"), "v": _num(v)} for t, v in zip(df[tcol], df[vcol]) if pd.notna(v)]

    sig_cols = ["mask_press", "press", "leak", "resp_rate", "tid_vol", "min_vent", "snore", "flow_lim"]
    return {
        "night": night,
        "has_data": True,
        "window": {"start": w0.strftime("%Y-%m-%dT%H:%M:%S"), "end": w1.strftime("%Y-%m-%dT%H:%M:%S")},
        "sessions": [{"start": s["start"].strftime("%Y-%m-%dT%H:%M:%S"),
                      "end": s["end"].strftime("%Y-%m-%dT%H:%M:%S")} for s in sessions],
        "signals": {c: pts(sig, "time", c) for c in sig_cols if c in sig.columns} if not sig.empty else {},
        "events": [{"t": t.strftime("%Y-%m-%dT%H:%M:%S"), "type": e, "duration_s": _num(d, 0),
                    "stage": s} for t, e, d, s in zip(ev["time"], ev["event"], ev["duration_s"],
                                                      ev["stage"] if "stage" in ev else [None] * len(ev))]
                  if not ev.empty else [],
        "stages": [{"start": a.strftime("%Y-%m-%dT%H:%M:%S"), "end": b.strftime("%Y-%m-%dT%H:%M:%S"), "stage": s}
                   for a, b, s in zip(st["start"], st["end"], st["stage"])] if not st.empty else [],
        "heart_rate": pts(hr, "t", "value"),
        "spo2": pts(spo2, "t", "value"),
        "oximetry": {"pulse": pts(oxi, "time", "pulse"), "spo2": pts(oxi, "time", "spo2")} if not oxi.empty else None,
        "events_by_stage": by_stage,
        "event_counts": ev["event"].value_counts().to_dict() if not ev.empty else {},
    }


# ─── Correlação ────────────────────────────────────────────────────────────────

CORR_VARS = {
    # CPAP (noite)
    "usage_h": ("Uso do CPAP", "h", "cpap"),
    "ahi": ("IAH", "ev/h", "cpap"),
    "cai": ("Índice de apneia central", "ev/h", "cpap"),
    "oai": ("Índice de apneia obstrutiva", "ev/h", "cpap"),
    "hi": ("Índice de hipopneia", "ev/h", "cpap"),
    "leak95": ("Fuga P95", "L/min", "cpap"),
    "press95": ("Pressão P95", "cmH₂O", "cpap"),
    "mask_removals": ("Remoções de máscara", "", "cpap"),
    # Smartband (noite)
    "sleep_score": ("Score do sono", "", "sono"),
    "total_sleep_h": ("Sono total", "h", "sono"),
    "deep_min": ("Sono profundo", "min", "sono"),
    "rem_min": ("Sono REM", "min", "sono"),
    "awake_min": ("Tempo acordado", "min", "sono"),
    "sleep_avg_hr": ("FC média no sono", "bpm", "sono"),
    # Dia anterior à noite
    "steps": ("Passos no dia", "", "dia"),
}


def nightly_dataset(cpap_df: pd.DataFrame, sleep_daily: pd.DataFrame, activity: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por noite com variáveis do CPAP, do sono (pulseira) e da atividade do dia."""
    nights = nightly_cpap(cpap_df)
    base = nights[["date", "usage_h", "ahi", "cai", "oai", "hi", "leak95", "press95", "mask_removals"]] \
        if not nights.empty else pd.DataFrame(columns=["date"])
    if not sleep_daily.empty:
        s = pd.DataFrame({
            "date": pd.to_datetime(sleep_daily["report_date"]).dt.normalize(),
            "sleep_score": pd.to_numeric(sleep_daily["sleep_score"], errors="coerce").replace(0, np.nan),
            "total_sleep_h": pd.to_numeric(sleep_daily["total_duration_min"], errors="coerce").replace(0, np.nan) / 60,
            # 0 min de profundo/REM = registro sem estágios (incompleto), não "zero sono profundo"
            "deep_min": pd.to_numeric(sleep_daily["deep_min"], errors="coerce").replace(0, np.nan),
            "rem_min": pd.to_numeric(sleep_daily["rem_min"], errors="coerce").replace(0, np.nan),
            "awake_min": pd.to_numeric(sleep_daily["awake_min"], errors="coerce"),
            "sleep_avg_hr": pd.to_numeric(_col(sleep_daily, "avg_hr"), errors="coerce").replace(0, np.nan),
        })
        base = base.merge(s, on="date", how="outer")
    if not activity.empty:
        a = pd.DataFrame({"date": pd.to_datetime(activity["report_date"]).dt.normalize(),
                          "steps": pd.to_numeric(activity["steps"], errors="coerce").replace(0, np.nan)})
        base = base.merge(a, on="date", how="left")
    return base.sort_values("date").reset_index(drop=True)


def _rank(a):
    return pd.Series(a).rank().to_numpy()


def spearman(x: np.ndarray, y: np.ndarray, permutations: int = 2000, seed: int = 0) -> dict:
    """Correlação de Spearman com p-valor por permutação (sem depender de SciPy)."""
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    n = int(len(x))
    if n < 5 or np.std(x) == 0 or np.std(y) == 0:
        return {"n": n, "rho": None, "p": None}
    rx, ry = _rank(x), _rank(y)
    rx = (rx - rx.mean()) / rx.std()
    ry = (ry - ry.mean()) / ry.std()
    rho = float(np.mean(rx * ry))
    rng = np.random.default_rng(seed)
    perm = np.array([np.mean(rx * rng.permutation(ry)) for _ in range(permutations)])
    p = float((np.sum(np.abs(perm) >= abs(rho)) + 1) / (permutations + 1))
    return {"n": n, "rho": round(rho, 3), "p": round(p, 4)}


def strength_label(rho: Optional[float], p: Optional[float], n: int) -> str:
    if rho is None:
        return "dados insuficientes"
    a = abs(rho)
    s = "desprezível" if a < 0.1 else "fraca" if a < 0.3 else "moderada" if a < 0.5 else "forte"
    if p is not None and p >= 0.05:
        s += " (não significativa)"
    if n < MIN_N_CORRELATION:
        s += " — poucas noites"
    return s


def correlation_matrix(ds: pd.DataFrame, permutations: int = 1000) -> dict:
    """Spearman entre variáveis do CPAP/dia (linhas) e do sono (colunas)."""
    rows = [k for k, v in CORR_VARS.items() if v[2] in ("cpap", "dia") and k in ds.columns]
    cols = [k for k, v in CORR_VARS.items() if v[2] == "sono" and k in ds.columns]
    cells = []
    for r in rows:
        for c in cols:
            res = spearman(ds[r].to_numpy(float), ds[c].to_numpy(float), permutations)
            res.update({"x": r, "y": c, "label": strength_label(res["rho"], res["p"], res["n"])})
            cells.append(res)
    return {"rows": rows, "cols": cols, "cells": cells,
            "vars": {k: {"label": v[0], "unit": v[1], "group": v[2]} for k, v in CORR_VARS.items()},
            "min_n": MIN_N_CORRELATION}


def correlation_pair(ds: pd.DataFrame, x: str, y: str) -> dict:
    if x not in ds.columns or y not in ds.columns:
        raise KeyError(f"variável desconhecida: {x if x not in ds.columns else y}")
    d = ds[["date", x, y]].dropna()
    res = spearman(d[x].to_numpy(float), d[y].to_numpy(float))
    slope = intercept = None
    if len(d) >= 3 and d[x].std() > 0:
        slope, intercept = np.polyfit(d[x].astype(float), d[y].astype(float), 1)
    res.update({
        "x": x, "y": y, "label": strength_label(res["rho"], res["p"], res["n"]),
        "points": [{"date": dt.strftime("%Y-%m-%d"), "x": _num(a), "y": _num(b)} for dt, a, b in zip(d["date"], d[x], d[y])],
        "fit": {"slope": _num(slope, 4), "intercept": _num(intercept, 4)} if slope is not None else None,
        "min_n": MIN_N_CORRELATION,
    })
    return res
