"""Testes das análises: tendências/adesão, noite detalhada, correlação e leitor da DATALOG."""

import os
import shutil
import tempfile
import unittest
from datetime import datetime

import numpy as np
import pandas as pd

from src.ingestion.datalog_processor import night_of, process_datalog
from src.visualization.services import analysis as an
from tests.test_processing import write_edf


def cpap_rows(days):
    """DataFrame no formato do data_loader (uma linha por noite usada).
    days: lista de (data, horas, ahi, cai, oai, hi, press95)."""
    rows = []
    for d, h, ahi, cai, oai, hi, p95 in days:
        rows.append({"data_sessao": pd.Timestamp(d).date(), "data_terapia": pd.Timestamp(d) + pd.Timedelta(hours=12),
                     "usage_mins": h * 60, "AHI": ahi, "CAI": cai, "OAI": oai, "UAI": 0.0, "HI": hi,
                     "Leak.50": 1.0, "Leak.95": 10.0, "Leak.Max": 20.0, "MaskPress.50": 7.0, "MaskPress.95": p95,
                     "MaskPress.Max": p95, "RespRate.50": 12.0, "mask_removals": 0.0,
                     "Mode": 1.0, "S.AS.MinPress": 4.0, "S.AS.MaxPress": 11.0, "S.C.Press": 8.0, "S.EPR.Level": 1.0})
    return pd.DataFrame(rows)


class TrendsTests(unittest.TestCase):
    def setUp(self):
        # 10 dias de calendário, uso em 7; 2 noites curtas (< 4 h); 3 dias sem uso
        self.df = cpap_rows([
            ("2026-09-01", 6, 2.0, 1.0, 0.5, 0.5, 9.0),
            ("2026-09-02", 5, 4.0, 3.0, 0.5, 0.5, 11.0),   # pressão no máximo
            ("2026-09-03", 3, 6.0, 5.0, 0.5, 0.5, 10.0),   # < 4 h
            ("2026-09-05", 7, 1.0, 0.5, 0.25, 0.25, 9.0),
            ("2026-09-06", 2, 8.0, 6.0, 1.0, 1.0, 10.9),  # < 4 h, no máximo
            ("2026-09-08", 6, 2.0, 1.5, 0.25, 0.25, 9.5),
            ("2026-09-10", 5, 3.0, 2.0, 0.5, 0.5, 9.0),
        ])

    def test_calendar_includes_days_without_use(self):
        t = an.compute_trends(self.df)
        self.assertEqual(len(t["days"]), 10)
        unused = [d["date"] for d in t["days"] if not d["used"]]
        self.assertEqual(unused, ["2026-09-04", "2026-09-07", "2026-09-09"])
        self.assertEqual([d["usage_h"] for d in t["days"] if not d["used"]], [0.0, 0.0, 0.0])

    def test_adherence_counts_calendar_days(self):
        s = an.compute_trends(self.df)["summary"]
        self.assertEqual(s["nights_used"], 7)
        self.assertEqual(s["nights_adherent"], 5)      # ≥ 4 h
        self.assertEqual(s["adherence_pct"], 50.0)      # 5 de 10 dias
        self.assertFalse(s["adherence_ok"])

    def test_ahi_is_weighted_by_usage_hours(self):
        s = an.compute_trends(self.df)["summary"]
        h = np.array([6, 5, 3, 7, 2, 6, 5]); ahi = np.array([2, 4, 6, 1, 8, 2, 3])
        self.assertAlmostEqual(s["ahi_avg"], round(float((h * ahi).sum() / h.sum()), 2))
        cai = np.array([1, 3, 5, .5, 6, 1.5, 2])
        self.assertAlmostEqual(s["central_share_pct"], round(100 * (h * cai).sum() / (h * ahi).sum(), 1), places=0)

    def test_pressure_at_max_flag(self):
        t = an.compute_trends(self.df)
        flagged = [d["date"] for d in t["days"] if d["press_at_max"]]
        self.assertEqual(flagged, ["2026-09-02", "2026-09-06"])
        self.assertEqual(t["summary"]["nights_press_at_max"], 2)

    def test_days_parameter_limits_the_window(self):
        t = an.compute_trends(self.df, days=5)
        self.assertEqual([d["date"] for d in t["days"]][0], "2026-09-06")
        self.assertEqual(t["summary"]["days"], 5)

    def test_rolling_adherence(self):
        days = an.compute_trends(self.df)["days"]
        # no 3º dia: 2 de 3 dias com ≥ 4 h
        self.assertAlmostEqual(days[2]["adherence_30"], 66.67, places=1)

    def test_observations_flag_low_adherence_and_central_events(self):
        obs = an.compute_trends(self.df)["observations"]
        texts = " ".join(o["text"] for o in obs)
        self.assertIn("abaixo da meta", texts)
        self.assertIn("apneias centrais", texts)

    def test_settings_changes_are_detected(self):
        df = self.df.copy()
        df.loc[df["data_sessao"] >= pd.Timestamp("2026-09-06").date(), "S.AS.MaxPress"] = 13.0
        ch = an.compute_trends(df)["settings_changes"]
        self.assertEqual(len(ch), 1)
        self.assertEqual(ch[0]["date"], "2026-09-06")
        self.assertEqual((ch[0]["from"]["set_max"], ch[0]["to"]["set_max"]), (11.0, 13.0))

    def test_medians_match_resscan_criteria(self):
        s = an.compute_trends(self.df)["summary"]
        self.assertEqual(s["ahi_median"], 3.0)             # mediana de [2, 4, 6, 1, 8, 2, 3]
        self.assertEqual(s["cai_median"], 2.0)
        self.assertEqual(s["usage_median_used_nights_h"], 5.0)
        self.assertEqual((s["nights_short"], s["nights_unused"]), (2, 3))
        self.assertEqual(s["leak95_median"], 10.0)

    def test_pressure_prefers_device_target(self):
        df = self.df.copy()
        df["TgtIPAP.95"] = df["MaskPress.95"] + 0.1
        t = an.compute_trends(df)
        self.assertAlmostEqual(t["days"][0]["press95"], 9.1)

    def test_epr_enable_flag_in_settings(self):
        df = self.df.copy()
        df["S.EPR.EPREnable"] = 0.0
        cs = an.compute_trends(df)["current_settings"]
        self.assertEqual((cs["epr"], cs["epr_on"]), (1.0, 0.0))


class NightTests(unittest.TestCase):
    def test_night_of_uses_noon_to_noon(self):
        self.assertEqual(night_of("2026-09-29 01:29:58"), pd.Timestamp("2026-09-28"))
        self.assertEqual(night_of("2026-09-28 23:10:00"), pd.Timestamp("2026-09-28"))

    def test_events_are_assigned_to_sleep_stages(self):
        n = pd.Timestamp("2026-09-28")
        t0 = pd.Timestamp("2026-09-28 23:00")
        signals = pd.DataFrame({"time": pd.date_range(t0, periods=241, freq="30s"), "mask_press": 8.0,
                                "leak": 1.0, "session": "s1", "night": n})
        stages = pd.DataFrame({"start": [t0, t0 + pd.Timedelta(hours=1)],
                               "end": [t0 + pd.Timedelta(hours=1), t0 + pd.Timedelta(hours=2)],
                               "stage": ["leve", "rem"], "night": n})
        events = pd.DataFrame({"time": [t0 + pd.Timedelta(minutes=10), t0 + pd.Timedelta(minutes=70),
                                        t0 + pd.Timedelta(minutes=80), t0 + pd.Timedelta(minutes=90)],
                               "event": ["central", "obstrutiva", "hipopneia", "despertar"],
                               "duration_s": [12, 15, 0, 0], "night": n})
        res = an.compute_night("2026-09-28", signals, events, stages, pd.DataFrame(), pd.DataFrame())
        by = {r["stage"]: r for r in res["events_by_stage"]}
        self.assertEqual(by["leve"]["events"], 1)
        self.assertEqual(by["rem"]["events"], 2)          # despertar não conta como apneia/hipopneia
        self.assertAlmostEqual(by["rem"]["per_hour"], 2.0)
        self.assertEqual(len(res["sessions"]), 1)
        self.assertEqual(res["event_counts"]["central"], 1)

    def test_night_without_data(self):
        empty = pd.DataFrame()
        self.assertFalse(an.compute_night("2026-01-01", empty, empty, empty, empty, empty)["has_data"])


class DatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        night = os.path.join(self.tmp, "20260928")
        os.makedirs(night)
        start = datetime(2026, 9, 29, 1, 30, 0)
        # PLD: 2 registros de 60 s, 30 amostras (0,5 Hz) de pressão e fuga (L/s)
        write_edf(os.path.join(night, "20260929_013000_PLD.edf"), start, [
            {"label": "MaskPress.2s", "dim": "cmH2O", "pmin": 0, "pmax": 30, "dmin": 0, "dmax": 1500,
             "digital": np.full((2, 30), 400)},                      # 8 cmH2O
            {"label": "Leak.2s", "dim": "L/s", "pmin": 0, "pmax": 2, "dmin": 0, "dmax": 100,
             "digital": np.full((2, 30), 10)},                       # 0,2 L/s = 12 L/min
        ], n_records=2, record_duration=60)
        # EVE: arquivo só de anotações (EDF+)
        tal = b"+0\x14\x14Recording starts\x14\x00+120\x1512\x14Central Apnea\x14\x00+300\x14Hypopnea\x14\x00"
        ann = np.frombuffer(tal.ljust(120, b"\x00"), dtype="<i2").reshape(1, -1)
        write_edf(os.path.join(night, "20260929_013000_EVE.edf"), start, [
            {"label": "EDF Annotations", "dim": "", "pmin": -1, "pmax": 1, "dmin": -32768, "dmax": 32767, "digital": ann},
        ], n_records=1, record_duration=0)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_reads_events_and_signals(self):
        events, signals, oxi = process_datalog(self.tmp, "Marcelo")
        self.assertEqual(events["event"].tolist(), ["central", "hipopneia"])
        self.assertEqual(events["duration_s"].tolist(), [12.0, 0.0])
        self.assertEqual(str(events["time"].iloc[0]), "2026-09-29 01:32:00")
        self.assertTrue((events["night"] == pd.Timestamp("2026-09-28")).all())
        self.assertEqual(len(signals), 4)                            # 120 s em janelas de 30 s
        self.assertAlmostEqual(signals["mask_press"].iloc[0], 8.0)
        self.assertAlmostEqual(signals["leak"].iloc[0], 12.0)        # L/s -> L/min
        self.assertTrue(oxi.empty)


class CorrelationTests(unittest.TestCase):
    def test_spearman_detects_monotonic_relation(self):
        x = np.arange(30, dtype=float)
        r = an.spearman(x, x ** 2)
        self.assertEqual(r["rho"], 1.0)
        self.assertLess(r["p"], 0.01)

    def test_spearman_on_noise_is_not_significant(self):
        rng = np.random.default_rng(1)
        r = an.spearman(rng.normal(size=40), rng.normal(size=40))
        self.assertGreater(r["p"], 0.05)

    def test_small_samples_are_flagged(self):
        self.assertIn("poucas noites", an.strength_label(0.6, 0.01, 12))
        self.assertEqual(an.strength_label(None, None, 3), "dados insuficientes")

    def test_nightly_dataset_treats_missing_stages_as_nan(self):
        sleep = pd.DataFrame({"report_date": pd.to_datetime(["2026-09-01", "2026-09-02"]),
                              "sleep_score": [80, 0], "total_duration_min": [400, 300],
                              "deep_min": [90, 0], "rem_min": [80, 0], "awake_min": [5, 0], "avg_hr": [55, 0]})
        ds = an.nightly_dataset(cpap_rows([("2026-09-01", 6, 2, 1, .5, .5, 9)]), sleep, pd.DataFrame())
        row2 = ds[ds["date"] == pd.Timestamp("2026-09-02")].iloc[0]
        self.assertTrue(np.isnan(row2["deep_min"]) and np.isnan(row2["sleep_score"]))
        self.assertEqual(row2["awake_min"], 0)


if __name__ == "__main__":
    unittest.main()
