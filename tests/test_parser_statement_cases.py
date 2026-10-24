import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from wsi_dicom_bench.negative_bench import parser_statement_cases as cases
from wsi_dicom_bench.negative_bench.mutations import generate_case


class ParserStatementCases(unittest.TestCase):
    def test_each_checked_parser_statement_has_one_case(self):
        named = [identifier for case in cases.CASES for identifier in case["requirement_ids"]]

        self.assertEqual(len(cases.CASES), 11)
        self.assertEqual(len(named), 21)
        self.assertEqual(len(named), len(set(named)))

    @unittest.skipUnless(os.environ.get("WSI_DICOM_CANDIDATE"), "needs candidate CLI")
    def test_cases_generate_and_fail_pixel_structure(self):
        candidate = Path(os.environ["WSI_DICOM_CANDIDATE"])
        root = Path(cases.__file__).parent
        source = root / "controls-v4/CP10-EVRLE-16F.dcm"
        with tempfile.TemporaryDirectory() as temporary:
            for case in cases.CASES:
                with self.subTest(case=case["case_id"]):
                    output = Path(temporary) / case["case_id"]
                    output.mkdir()
                    generate_case(
                        {**case, "deterministic_seed": f"test:{case['case_id']}"},
                        source,
                        output,
                    )
                    result = subprocess.run(
                        [candidate, "validate", str(output), "--profile", "general", "--json"],
                        env={**os.environ, "PATH": ""}, capture_output=True, text=True, timeout=30,
                    )
                    report = json.loads(result.stdout)
                    failed = {
                        check["name"] for check in report["checks"]
                        if check["status"] == "failed"
                    }
                    self.assertIn("intrinsic-pixel-structure", failed, case["case_id"])


if __name__ == "__main__":
    unittest.main()
