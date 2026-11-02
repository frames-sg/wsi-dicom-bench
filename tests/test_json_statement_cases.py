import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from wsi_dicom_bench.negative_bench import json_statement_cases as cases


class JsonStatementCases(unittest.TestCase):
    def test_real_candidate_accepts_control_and_localizes_each_json_defect(self):
        candidate = os.environ.get("WSI_DICOM_CANDIDATE")
        if not candidate:
            self.skipTest("set WSI_DICOM_CANDIDATE to validate the JSON challenge corpus")
        root = Path(cases.__file__).parent
        source = root / "controls-v4" / f"{cases.CONTROL_ID}.dcm"
        with tempfile.TemporaryDirectory() as temporary:
            for case in [None, *cases.CASES]:
                identifier = case["case_id"] if case else None
                with self.subTest(case=identifier or "control"):
                    path = Path(temporary) / f"{identifier or 'control'}.json"
                    path.write_bytes(cases.build_document(identifier, source))
                    result = subprocess.run(
                        [candidate, "validate-json", str(path), "--json",
                         "--transfer-syntax", cases.TRANSFER_SYNTAX],
                        capture_output=True, text=True, timeout=30,
                    )
                    report = json.loads(result.stdout)
                    failed = {check["name"] for check in report["checks"]
                              if check["status"] == "failed"}
                    expected = ({*(f"intrinsic-wsi-dicom-{rule}" for rule in case["expected"]),
                                 *case["expected_cascades"]} if case else set())
                    self.assertEqual(failed, expected, result.stdout)
                    self.assertEqual(result.returncode, 1 if case else 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
