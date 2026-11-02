import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from wsi_dicom_bench.negative_bench import signature_statement_cases as cases
from wsi_dicom_bench.negative_bench.mutations import generate_case


class SignatureStatementCases(unittest.TestCase):
    def test_real_candidate_verifies_controls_and_rejects_each_mac_defect(self):
        candidate = os.environ.get("WSI_DICOM_CANDIDATE")
        if not candidate:
            self.skipTest("set WSI_DICOM_CANDIDATE to validate the signature corpus")
        root = Path(cases.__file__).parent
        sources = {cases.CONTROL_ID: root / cases.CONTROL_PATH,
                   cases.TIMESTAMP_CONTROL_ID: root / cases.TIMESTAMP_CONTROL_PATH}
        rule = "intrinsic-wsi-dicom-digital-signatures"

        def check(path):
            result = subprocess.run([candidate, "validate", str(path), "--json"],
                                    env={**os.environ, "PATH": ""}, capture_output=True,
                                    text=True, timeout=30)
            report = json.loads(result.stdout)
            failures = {item["name"] for item in report["checks"] if item["status"] == "failed"}
            self.assertEqual(result.returncode, int(bool(failures)), result.stderr)
            signature = next(item for item in report["checks"] if item["name"] == rule)
            return failures, signature

        for control, source in sources.items():
            with self.subTest(control=control):
                failures, signature = check(source)
                self.assertEqual(failures, set(), signature)
                self.assertEqual(signature["status"], "passed")
                self.assertIn("1 Digital Signature verified", signature["message"])
                if control == cases.TIMESTAMP_CONTROL_ID:
                    self.assertIn("1 with a verified Certified Timestamp", signature["message"])
        with tempfile.TemporaryDirectory() as temporary:
            for case in cases.CASES:
                with self.subTest(case=case["case_id"]):
                    output = Path(temporary) / case["case_id"]
                    output.mkdir()
                    generate_case({**case, "deterministic_seed": case["case_id"]}, sources[case["control"]], output)
                    failures, signature = check(output)
                    self.assertEqual(failures, {rule}, signature)
                    self.assertEqual(signature["status"], "failed")


if __name__ == "__main__":
    unittest.main()
