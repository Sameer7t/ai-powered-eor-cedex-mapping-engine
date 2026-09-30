import os
import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from data_loader import get_cedex_sheet, get_damage_codes, get_iso_equipment_group
from engine_service import (
    detect_container_route,
    compute_confidence,
    process_single_estimate_data,
    DEMO_DRY_ESTIMATE,
)


class EngineServiceTests(unittest.TestCase):
    def test_data_loader_returns_dataframes(self):
        df_tn = get_cedex_sheet("TN")
        df_gp = get_cedex_sheet("GP")
        df_dmg = get_damage_codes()
        df_iso = get_iso_equipment_group()

        self.assertFalse(df_tn.empty)
        self.assertFalse(df_gp.empty)
        self.assertFalse(df_dmg.empty)
        self.assertFalse(df_iso.empty)

    def test_detect_container_route(self):
        self.assertEqual(detect_container_route("22K1"), "tank")
        self.assertEqual(detect_container_route("IMO 1"), "tank")
        self.assertEqual(detect_container_route("22G1"), "dry")
        self.assertEqual(detect_container_route("40HC"), "dry")
        self.assertEqual(detect_container_route("UNKNOWN_TANK_EQUIP"), "tank")

    def test_compute_confidence(self):
        complete_jobs = [{
            "location": "BX", "component": "PSC", "repair": "RP",
            "damage": "DT", "status": "mapped"
        }]
        score, level = compute_confidence(complete_jobs)
        self.assertGreaterEqual(score, 0.75)
        self.assertEqual(level, "high")

        empty_jobs = [{"status": "unmapped"}]
        score_low, level_low = compute_confidence(empty_jobs)
        self.assertLess(score_low, 0.75)

    def test_process_dry_estimate_deterministic(self):
        invoice = process_single_estimate_data(DEMO_DRY_ESTIMATE)
        self.assertEqual(invoice["container_id"], "TSLU0527650")
        self.assertEqual(invoice["route"], "dry")
        self.assertEqual(len(invoice["jobs"]), 3)

        # First job should map to Panel replacement dented
        job_1 = invoice["jobs"][0]
        self.assertEqual(job_1["status"], "mapped")
        self.assertIn("PSC", job_1["cedex_code"])


if __name__ == "__main__":
    unittest.main()
