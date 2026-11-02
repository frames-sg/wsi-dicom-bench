import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from wsi_dicom_bench.negative_bench import motion_statement_cases as cases
from wsi_dicom_bench.negative_bench.mutations import generate_case


class MotionStatementCases(unittest.TestCase):
    def test_real_candidate_accepts_monochrome_controls_and_rejects_each_defect(self):
        candidate = os.environ.get("WSI_DICOM_CANDIDATE")
        if not candidate:
            self.skipTest("set WSI_DICOM_CANDIDATE to validate the motion corpus")
        root = Path(cases.__file__).parent

        def check(path):
            result = subprocess.run([candidate, "validate", str(path), "--json"],
                                    env={**os.environ, "PATH": ""}, capture_output=True,
                                    text=True, timeout=30)
            report = json.loads(result.stdout)
            failures = {item["name"] for item in report["checks"] if item["status"] == "failed"}
            self.assertEqual(result.returncode, int(bool(failures)), result.stderr)
            return failures, report

        for control, path in cases.CONTROL_PATHS.items():
            with self.subTest(control=control):
                failed, report = check(root / path)
                self.assertEqual(failed, set(), report)
        with tempfile.TemporaryDirectory() as temporary:
            for case in cases.CASES:
                with self.subTest(case=case["case_id"]):
                    output = Path(temporary) / case["case_id"]
                    output.mkdir()
                    generate_case({**case, "deterministic_seed": case["case_id"]},
                                  root / cases.CONTROL_PATHS[case["control"]], output)
                    failed, report = check(output)
                    expected = {"intrinsic-pixel-structure" if rule == "pixel-structure"
                                else f"intrinsic-wsi-dicom-{rule}" for rule in case["expected"]}
                    expected.update(case.get("expected_cascades", []))
                    self.assertEqual(failed, expected, [(c["name"], c["message"]) for c in report["checks"] if c["status"] == "failed"])


if __name__ == "__main__":
    unittest.main()
