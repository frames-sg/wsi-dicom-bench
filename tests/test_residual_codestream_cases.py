import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from wsi_dicom_bench.negative_bench import residual_codestream_cases as cases
from wsi_dicom_bench.negative_bench.mutations import generate_case


class ResidualCodestreamCases(unittest.TestCase):
    def test_real_candidate_accepts_controls_and_localizes_codec_defects(self):
        candidate = os.environ.get("WSI_DICOM_CANDIDATE")
        if not candidate:
            self.skipTest("set WSI_DICOM_CANDIDATE to validate codec statements")
        root = Path(cases.__file__).parent

        def source(control):
            if control in cases.CONTROL_PATHS:
                return root / cases.CONTROL_PATHS[control]
            if control == "V7-WAVEFORM":
                return root / "controls-v7/iods/waveform.dcm"
            return root / ("controls-v7/wsi" if control.startswith("W7-") else "controls-v4") / (control + ".dcm")

        def check(path):
            result = subprocess.run([candidate, "validate", str(path), "--json"],
                                    capture_output=True, text=True,
                                    env={**os.environ, "PATH": ""}, timeout=30)
            report = json.loads(result.stdout)
            failed = {c["name"] for c in report["checks"] if c["status"] == "failed"}
            diagnostics = [(c["name"], c["message"]) for c in report["checks"] if c["status"] == "failed"]
            self.assertEqual(result.returncode, int(bool(failed)), result.stderr)
            return failed, diagnostics

        for control in cases.CONTROL_PATHS:
            failed, diagnostics = check(source(control))
            self.assertEqual(failed, set(), (control, diagnostics))
        with tempfile.TemporaryDirectory() as temporary:
            for case in cases.CASES:
                with self.subTest(case=case["case_id"]):
                    output = Path(temporary) / case["case_id"]
                    output.mkdir()
                    generate_case({**case, "deterministic_seed": case["case_id"]}, source(case["control"]), output)
                    failed, diagnostics = check(output)
                    expected = {rule if rule.startswith("intrinsic-") else "intrinsic-wsi-dicom-" + rule for rule in case["expected"]}
                    expected.update(case.get("expected_cascades", []))
                    self.assertEqual(failed, expected, diagnostics)
                    self.assertTrue(any(case["message_fragment"] in message for _, message in diagnostics), diagnostics)


if __name__ == "__main__":
    unittest.main()
