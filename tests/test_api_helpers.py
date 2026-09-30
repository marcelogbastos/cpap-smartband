import unittest
from unittest import mock

import pandas as pd

from src.visualization.routers.api import _filter_patient, get_smartband_daily, get_patients
from src.visualization.services.cpap_scoring import calculate_ahi_score


class ApiHelpersTests(unittest.TestCase):
    def test_filter_patient_is_case_and_accent_insensitive(self):
        data = pd.DataFrame({"patient": ["Joao Silva", "Marcelo"], "value": [1, 2]})

        result = _filter_patient(data, "JOÃO SILVA")

        self.assertEqual(result["value"].tolist(), [1])

    def test_filter_patient_returns_empty_for_unknown_patient(self):
        data = pd.DataFrame({"patient": ["Marcelo"], "value": [1]})

        result = _filter_patient(data, "unknown")

        self.assertTrue(result.empty)

    def test_ahi_score_uses_documented_thresholds(self):
        self.assertEqual(calculate_ahi_score(6.99), 5)
        self.assertEqual(calculate_ahi_score(7), 4)

    def test_smartband_daily_matches_accented_patient_name(self):
        sleep = pd.DataFrame({
            "patient": ["João Silva", "Marcelo"],
            "report_date": pd.to_datetime(["2026-08-18", "2026-08-18"]),
            "sleep_score": [80, 70],
        })
        empty = pd.DataFrame()
        with mock.patch("src.visualization.routers.api.load_smartband_table",
                        side_effect=lambda table, patient=None: sleep if table == "smartband_sleep_daily" else empty):
            # o seletor de pacientes envia o slug em Title Case: "Joao_Silva"
            result = get_smartband_daily("Joao_Silva", start_date=None, end_date=None)
        self.assertEqual(result["sleep"]["sleep_score"], [80])

    def test_patients_list_uses_real_names(self):
        import os, shutil, tempfile
        tmp = tempfile.mkdtemp()
        try:
            for table, name, slug in [("summary", "João Silva", "joao_silva"),
                                      ("smartband_sleep_daily", "Marcelo", "marcelo")]:
                part = os.path.join(tmp, table, f"patient_slug={slug}")
                os.makedirs(part)
                pd.DataFrame({"patient": [name]}).to_parquet(os.path.join(part, "d.parquet"))
            with mock.patch("src.visualization.routers.api.PROCESSED_BASE_DIR", tmp):
                self.assertEqual(get_patients(), ["João Silva", "Marcelo"])
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()