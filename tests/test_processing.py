"""Testes da ingestão (STR.edf e Mi Fitness) e dos endpoints que dependem dela."""

import os
import shutil
import tempfile
import unittest
from datetime import date, datetime

import numpy as np
import pandas as pd

from src.ingestion import processor as cpap_proc
from src.ingestion.processor import read_resmed_str
from src.ingestion.smartband_processor import report_day
from src.visualization.services import data_loader
from src.visualization.services.cpap_scoring import (
    calculate_mask_seal_score,
    calculate_myair_score,
)


def write_edf(path, start, signals, n_records, record_duration=86400):
    """Grava um EDF mínimo. signals: lista de dicts com
    label, dim, pmin, pmax, dmin, dmax, digital (array n_records x n_samples)."""
    ns = len(signals)

    def pad(v, w):
        return str(v).ljust(w)[:w]

    hdr = pad("0", 8) + pad("X", 80) + pad("Startdate X", 80)
    hdr += start.strftime("%d.%m.%y") + start.strftime("%H.%M.%S")
    hdr += pad(256 + ns * 256, 8) + pad("", 44) + pad(n_records, 8) + pad(record_duration, 8) + pad(ns, 4)
    sh = ""
    for key, w in [("label", 16), ("transducer", 80), ("dim", 8), ("pmin", 8), ("pmax", 8),
                   ("dmin", 8), ("dmax", 8), ("prefilter", 80), ("n", 8), ("reserved", 32)]:
        for s in signals:
            if key == "n":
                val = s["digital"].shape[1]
            else:
                val = s.get(key, "")
            sh += pad(val, w)
    body = b"".join(
        np.concatenate([s["digital"][r] for s in signals]).astype("<i2").tobytes()
        for r in range(n_records)
    )
    with open(path, "wb") as fh:
        fh.write(hdr.encode("latin-1") + sh.encode("latin-1") + body)


def one(label, dim, pmin, pmax, dmin, dmax, values):
    return {"label": label, "dim": dim, "pmin": pmin, "pmax": pmax, "dmin": dmin, "dmax": dmax,
            "digital": np.array(values, dtype=int).reshape(-1, 1)}


class ReadResmedStrTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "STR.edf")
        start = datetime(2026, 8, 16, 12, 0, 0)
        write_edf(self.path, start, [
            {"label": "MaskOn", "dim": "min.", "pmin": 0, "pmax": 1440, "dmin": 0, "dmax": 1440,
             "digital": np.array([[600] + [-1] * 9, [-1] * 10, [700, 900] + [-1] * 8])},
            one("Duration", "min.", 0, 1440, 0, 1440, [401, -1, 431]),
            one("AHI", "", 0, 240, 0, 2400, [71, -1, 18]),
            one("Leak.95", "L/s", 0, 2, 0, 100, [11, -1, 14]),   # 0.22 L/s, 0.28 L/s
            one("MaskEvents", "", 0, 255, 0, 255, [4, -1, 2]),
        ], n_records=3)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_one_row_per_day_with_exact_values(self):
        df = read_resmed_str(self.path)
        self.assertEqual(len(df), 3)
        self.assertEqual(df["AHI"].iloc[0], 7.1)
        self.assertEqual(df["AHI"].iloc[2], 1.8)
        self.assertEqual(df["MaskEvents"].tolist()[0], 4)
        self.assertEqual(df["data_terapia"].tolist(),
                         [pd.Timestamp("2026-08-16 12:00"), pd.Timestamp("2026-08-17 12:00"),
                          pd.Timestamp("2026-08-18 12:00")])

    def test_multi_sample_channels_are_not_columns(self):
        self.assertNotIn("MaskOn", read_resmed_str(self.path).columns)

    def test_missing_values_become_nan(self):
        df = read_resmed_str(self.path)
        self.assertTrue(df.iloc[1][["Duration", "AHI", "Leak.95"]].isna().all())

    def test_leak_is_converted_to_l_per_min(self):
        df = read_resmed_str(self.path)
        self.assertAlmostEqual(df["Leak.95"].iloc[0], 13.2)
        self.assertAlmostEqual(df["Leak.95"].iloc[2], 16.8)


class SaveToParquetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = cpap_proc.PROCESSED_DIR
        cpap_proc.PROCESSED_DIR = self.tmp

    def tearDown(self):
        cpap_proc.PROCESSED_DIR = self._orig
        shutil.rmtree(self.tmp)

    def _day(self, ts, ahi):
        return pd.DataFrame({"data_terapia": [pd.Timestamp(ts)], "AHI": [ahi], "patient": ["Marcelo"]})

    def _saved(self):
        return pd.read_parquet(os.path.join(self.tmp, "summary"))

    def test_legacy_resampled_data_is_replaced(self):
        legacy = pd.DataFrame({
            "data_terapia": pd.date_range("2026-08-18 12:00", periods=10, freq="144min"),
            "AHI": np.linspace(1, 9, 10), "patient": "Marcelo"})
        ing = cpap_proc.CPAPIngestion()
        ing.save_to_parquet(legacy, "summary", ["patient", "data_terapia"])
        ing.save_to_parquet(self._day("2026-08-18 12:00", 1.8), "summary", ["patient", "data_terapia"])
        saved = self._saved()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved["AHI"].iloc[0], 1.8)

    def test_newer_reading_of_same_day_wins(self):
        ing = cpap_proc.CPAPIngestion()
        keys = ["patient", "data_terapia"]
        ing.save_to_parquet(self._day("2026-08-17 12:00", 2.3), "summary", keys)
        ing.save_to_parquet(self._day("2026-08-18 12:00", 0.5), "summary", keys)
        ing.save_to_parquet(self._day("2026-08-18 12:00", 1.8), "summary", keys)
        saved = self._saved().sort_values("data_terapia")
        self.assertEqual(saved["AHI"].tolist(), [2.3, 1.8])


class DataLoaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = data_loader.PROCESSED_DIR
        data_loader.PROCESSED_DIR = self.tmp
        data_loader.invalidate_cache()
        part = os.path.join(self.tmp, "patient_slug=marcelo")
        os.makedirs(part)
        pd.DataFrame({
            "data_terapia": pd.to_datetime(["2026-08-16 12:00", "2026-08-17 12:00", "2026-08-18 12:00"]),
            "Duration": [401.0, np.nan, 431.0], "AHI": [7.1, np.nan, 1.8],
            "MaskEvents": [4.0, np.nan, 2.0],
            "PatientHours": [533.0, np.nan, 546.0], "patient": "Marcelo",
        }).to_parquet(os.path.join(part, "data.parquet"))

    def tearDown(self):
        data_loader.PROCESSED_DIR = self._orig
        data_loader.invalidate_cache()
        shutil.rmtree(self.tmp)

    def test_nights_without_usage_are_excluded(self):
        df = data_loader.load_cpap_data("Marcelo")
        self.assertEqual([str(d) for d in df["data_sessao"]], ["2026-08-16", "2026-08-18"])

    def test_mask_removals_ignore_first_on_and_last_off(self):
        # MaskEvents 4 = 2 sessões = 1 remoção; MaskEvents 2 = 1 sessão = 0 remoções
        df = data_loader.load_cpap_data("Marcelo")
        self.assertEqual(df["mask_removals"].tolist(), [1.0, 0.0])


class SmartbandDateTests(unittest.TestCase):
    def test_report_day_ignores_local_timezone(self):
        # 2026-04-14 00:00 UTC -> relatório do dia 14 (em UTC-3 seria dia 13)
        self.assertEqual(report_day(1776124800), date(2026, 4, 14))


class ScoringTests(unittest.TestCase):
    def test_mask_seal_uses_l_per_min(self):
        self.assertEqual(calculate_mask_seal_score(16.8), 19)
        self.assertEqual(calculate_mask_seal_score(4.8), 20)
        self.assertEqual(calculate_mask_seal_score(60), 0)

    def test_myair_score_combines_components(self):
        row = pd.Series({"usage_mins": 431, "Leak.95": 16.8, "MaskEvents": 2, "AHI": 1.8})
        self.assertEqual(calculate_myair_score(row), 70 + 19 + 5 + 5)

    def test_myair_score_counts_removals_not_raw_mask_events(self):
        base = {"usage_mins": 420, "Leak.95": 10, "AHI": 1}
        # noite normal (MaskEvents=2) e noite com 3 remoções (MaskEvents=8)
        self.assertEqual(calculate_myair_score(pd.Series({**base, "MaskEvents": 2})), 100)
        self.assertEqual(calculate_myair_score(pd.Series({**base, "mask_removals": 3})), 99)
        self.assertEqual(calculate_myair_score(pd.Series({**base, "MaskEvents": 8})), 99)

    def test_myair_score_is_zero_without_usage(self):
        self.assertEqual(calculate_myair_score(pd.Series({"usage_mins": 0})), 0)


def write_mifitness_export(folder, date="20260819", uid="1595395722"):
    """Cria uma exportação mínima do Mi Fitness (1 noite, 1 dia de passos)."""
    import json
    os.makedirs(folder, exist_ok=True)
    pre = os.path.join(folder, f"{date}_{uid}_MiFitness_")
    sleep = {"bedtime": 1776126600, "wake_up_time": 1776154380, "duration": 463,
             "sleep_deep_duration": 122, "sleep_light_duration": 234, "sleep_rem_duration": 107,
             "sleep_awake_duration": 0, "items": []}
    pd.DataFrame([
        {"Uid": uid, "Sid": "x", "Key": "sleep", "Time": 1776126600, "Value": json.dumps(sleep)},
        {"Uid": uid, "Sid": "x", "Key": "heart_rate", "Time": 1776126600, "Value": json.dumps({"time": 1776126600, "bpm": 60})},
        {"Uid": uid, "Sid": "x", "Key": "spo2", "Time": 1776126600, "Value": json.dumps({"time": 1776126600, "spo2": 97})},
    ]).to_csv(pre + "hlth_center_fitness_data.csv", index=False)
    daily = {"sleep_score": 80, "total_duration": 463, "sleep_deep_duration": 122, "sleep_light_duration": 234,
             "sleep_rem_duration": 107, "sleep_awake_duration": 0,
             "segment_details": [{"bedtime": 1776126600, "duration": 463, "avg_hr": 59}]}
    pd.DataFrame([
        {"Uid": uid, "Sid": "d", "Tag": "daily_report", "Key": "sleep", "Time": 1776124800, "Value": json.dumps(daily)},
        {"Uid": uid, "Sid": "d", "Tag": "daily_report", "Key": "steps", "Time": 1776124800,
         "Value": json.dumps({"steps": 7113, "distance": 3506, "calories": 416})},
    ]).to_csv(pre + "hlth_center_aggregated_fitness_data.csv", index=False)


class SmartbandFoldersTests(unittest.TestCase):
    def setUp(self):
        from src.ingestion import smartband_processor as sp
        self.sp = sp
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "Smartband")
        self.out = os.path.join(self.tmp, "processed")
        self._orig = (sp.SMARTBAND_DIR, sp.PROCESSED_DIR)
        sp.SMARTBAND_DIR, sp.PROCESSED_DIR = self.src, self.out

    def tearDown(self):
        self.sp.SMARTBAND_DIR, self.sp.PROCESSED_DIR = self._orig
        shutil.rmtree(self.tmp)

    def test_discovers_one_folder_per_patient(self):
        write_mifitness_export(os.path.join(self.src, "Marcelo"))
        write_mifitness_export(os.path.join(self.src, "João Silva"), uid="42")
        os.makedirs(os.path.join(self.src, "vazia"))
        names = [n for n, _ in self.sp.discover_patients()]
        self.assertEqual(names, ["João Silva", "Marcelo"])

    def test_uses_latest_export_of_the_folder(self):
        folder = os.path.join(self.src, "Marcelo")
        write_mifitness_export(folder, date="20260701")
        write_mifitness_export(folder, date="20260819")
        date, uid, tables = self.sp.latest_export(folder)
        self.assertEqual((date, uid), ("20260819", "1595395722"))
        self.assertTrue(tables["hlth_center_fitness_data"].endswith("20260819_1595395722_MiFitness_hlth_center_fitness_data.csv"))

    def test_patient_name_comes_from_folder(self):
        write_mifitness_export(os.path.join(self.src, "João Silva"))
        self.assertEqual(self.sp.main([]), 0)
        daily = pd.read_parquet(os.path.join(self.out, "smartband_sleep_daily"))
        self.assertEqual(daily["patient"].tolist(), ["João Silva"])
        self.assertEqual(daily["patient_slug"].astype(str).tolist(), ["joao_silva"])
        # noite de 13->14/04: relatório do dia 14 é gravado como noite de 13/04
        self.assertEqual(str(daily["report_date"].iloc[0].date()), "2026-04-13")
        steps = pd.read_parquet(os.path.join(self.out, "smartband_activity"))
        self.assertEqual(str(steps["report_date"].iloc[0].date()), "2026-04-14")

    def test_patient_filter_and_loose_files(self):
        write_mifitness_export(os.path.join(self.src, "Marcelo"))
        write_mifitness_export(self.src)  # CSVs soltos na raiz: ignorados
        self.assertEqual(self.sp.main(["--patient", "outro"]), 1)
        self.assertEqual(self.sp.main(["--patient", "marcelo"]), 0)
        self.assertEqual(os.listdir(os.path.join(self.out, "smartband_sleep_daily")), ["patient_slug=marcelo"])


if __name__ == "__main__":
    unittest.main()
