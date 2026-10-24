import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from wsi_dicom_bench.negative_bench import deidentification_statement_cases as cases
from wsi_dicom_bench.negative_bench.mutations import generate_case


class DeidentificationStatementCases(unittest.TestCase):
    def test_real_candidate_accepts_protected_controls_and_detects_each_breach(self):
        candidate = os.environ.get("WSI_DICOM_CANDIDATE")
        if not candidate:
            self.skipTest("set WSI_DICOM_CANDIDATE to validate the de-identification corpus")
        root = Path(cases.__file__).parent
        sources = {
            cases.CONTROL_ID: root / cases.CONTROL_PATH,
            cases.ENCRYPTED_CONTROL_ID: root / cases.ENCRYPTED_CONTROL_PATH,
            cases.FILESET_CONTROL_ID: root / cases.FILESET_CONTROL_PATHS[0],
        }

        def failed(path):
            result = subprocess.run([candidate, "validate", str(path), "--json"],
                                    env={**os.environ, "PATH": ""}, capture_output=True,
                                    text=True, timeout=30)
            report = json.loads(result.stdout)
            failures = [(check["name"], check["message"]) for check in report["checks"]
                        if check["status"] == "failed"]
            self.assertEqual(result.returncode, int(bool(failures)), result.stderr)
            return failures

        for control, source in sources.items():
            with self.subTest(control=control):
                path = source.parent if source.name == "DICOMDIR" else source
                self.assertEqual(failed(path), [])
        with tempfile.TemporaryDirectory() as temporary:
            for case in cases.CASES:
                with self.subTest(case=case["case_id"]):
                    output = Path(temporary) / case["case_id"]
                    output.mkdir()
                    generate_case({**case, "deterministic_seed": case["case_id"]}, sources[case["control"]], output)
                    failures = failed(output)
                    self.assertEqual({name for name, _ in failures},
                                     {f"intrinsic-wsi-dicom-{rule}" for rule in case["expected"]}, failures)


if __name__ == "__main__":
    unittest.main()
