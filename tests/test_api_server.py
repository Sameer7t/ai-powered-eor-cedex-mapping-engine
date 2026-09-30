import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from starlette.testclient import TestClient
from server import app


class ServerApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_endpoint(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["service"], "ai-powered-eor-cedex-mapping-engine")

    def test_reference_mappings_endpoint(self):
        response = self.client.get("/api/reference-mappings")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(data["tank_codes_count"], 0)
        self.assertGreater(data["dry_codes_count"], 0)

    def test_serve_index_html(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("CEDEX", response.text)
        self.assertIn("EOR CEDEX", response.text)

    def test_process_dry_demo_sample(self):
        response = self.client.post("/api/process-demo", json={"sample_type": "dry"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["total_estimates"], 1)
        self.assertGreater(len(data["invoices"]), 0)


    def test_generate_reports_endpoint(self):
        sample_invoice = {
            "container_id": "TEST1234567",
            "container_type": "22K1",
            "jobs": [
                {
                    "job_id": 1,
                    "location": "AFXX",
                    "component": "YXT",
                    "repair": "AX",
                    "damage": "DY",
                    "status": "mapped",
                    "cedex_code": "AFXX YXT AX DY",
                    "manhour": 1.0,
                    "labour_cost": 50.0,
                    "material_cost_aed": 0.0,
                }
            ],
        }
        response = self.client.post("/api/generate-reports", json={"invoices": [sample_invoice]})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIsNotNone(data["success_report_file"])
        self.assertTrue(data["all_mapped"])


if __name__ == "__main__":
    unittest.main()
