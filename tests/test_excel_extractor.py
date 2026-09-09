from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from excel_extractor import excel_extractor  # noqa: E402


class ExcelExtractorTests(unittest.TestCase):
    def test_extracts_content_from_a_workbook(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "estimate.xlsx"
            pd.DataFrame(
                [{"Description": "Side panel dent", "Lab. Cost": 125.0}]
            ).to_excel(workbook_path, index=False, sheet_name="Estimate")

            extracted = excel_extractor(str(workbook_path))

        self.assertIn("=== SHEET: Estimate ===", extracted)
        self.assertIn("Side panel dent", extracted)
        self.assertIn("125", extracted)


if __name__ == "__main__":
    unittest.main()
