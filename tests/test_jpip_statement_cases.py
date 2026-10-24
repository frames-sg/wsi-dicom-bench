import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from wsi_dicom_bench.negative_bench import jpip_statement_cases as cases


class JpipStatementCases(unittest.TestCase):
    def test_real_candidate_accepts_reference_controls_and_rejects_defects(self):
        candidate = os.environ.get("WSI_DICOM_CANDIDATE")
        if not candidate:
            self.skipTest("set WSI_DICOM_CANDIDATE to validate JPIP metadata")
        source = Path(cases.__file__).parent / cases.CONTROL_PATH
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "metadata.json"
            controls = [(None, f"1.2.840.10008.1.2.4.{suffix}") for suffix in (94, 95, 204, 205)]
            probes = [*controls, *((case, case["transfer_syntax"]) for case in cases.CASES)]
            for case, syntax in probes:
                identifier = case["case_id"] if case else None
                with self.subTest(case=identifier, syntax=syntax):
                    path.write_bytes(cases.build_document(identifier, source))
                    result = subprocess.run([candidate, "validate-json", str(path), "--json",
                                             "--transfer-syntax", syntax], capture_output=True,
                                            text=True, env={**os.environ, "PATH": ""}, timeout=30)
                    report = json.loads(result.stdout)
                    failed = {check["name"] for check in report["checks"] if check["status"] == "failed"}
                    expected = ({rule if rule.startswith("intrinsic-") else f"intrinsic-wsi-dicom-{rule}"
                                 for rule in case["expected"]} if case else set())
                    if case:
                        expected.update(case["expected_cascades"])
                    self.assertEqual(failed, expected, [(c["name"], c["message"]) for c in report["checks"] if c["status"] == "failed"])
                    self.assertEqual(result.returncode, int(bool(expected)), result.stderr)


if __name__ == "__main__":
    unittest.main()
