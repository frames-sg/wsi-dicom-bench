import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from wsi_dicom_bench.negative_bench import generic_iod_statement_cases as cases
from wsi_dicom_bench.negative_bench.mutations import generate_case


class GenericIodStatementCases(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("WSI_DICOM_CANDIDATE"), "needs candidate CLI")
    def test_lossy_pathology_controls_pass(self):
        candidate = Path(os.environ["WSI_DICOM_CANDIDATE"])
        root = Path(cases.__file__).parent
        for relative in (
            "controls-v7/iods/seg-fractional-mpeg2.dcm",
            "controls-v7/iods/pm-jpegls-near.dcm",
        ):
            result = subprocess.run(
                [candidate, "validate", str(root / relative), "--json"],
                env={**os.environ, "PATH": ""}, capture_output=True, text=True, timeout=30,
            )
            report = json.loads(result.stdout)
            self.assertEqual(
                [check["name"] for check in report["checks"]
                 if check["status"] == "failed"],
                [], relative,
            )

    @unittest.skipUnless(os.environ.get("WSI_DICOM_CANDIDATE"), "needs candidate CLI")
    def test_cases_localize_failures_or_advisories(self):
        candidate = Path(os.environ["WSI_DICOM_CANDIDATE"])
        root = Path(cases.__file__).parent
        sources = {
            "CP10-EVRLE-16F": root / "controls-v4/CP10-EVRLE-16F.dcm",
            "CP02-JPEG-16F": root / "controls-v4/CP02-JPEG-16F.dcm",
            "V7-MPEG2-HIGH-MONO": root / "controls-v7/motion/mpeg2-high-mono.dcm",
            "V7-SEG-FRACTIONAL-MPEG2":
                root / "controls-v7/iods/seg-fractional-mpeg2.dcm",
            "V7-PM-JPEGLS-NEAR": root / "controls-v7/iods/pm-jpegls-near.dcm",
        }
        with tempfile.TemporaryDirectory() as temporary:
            for case in cases.CASES:
                with self.subTest(case=case["case_id"]):
                    output = Path(temporary) / case["case_id"]
                    output.mkdir()
                    generate_case(
                        {**case, "deterministic_seed": f"test:{case['case_id']}"},
                        sources[case["control"]], output,
                    )
                    result = subprocess.run(
                        [candidate, "validate", str(output), "--profile", "general", "--json"],
                        env={**os.environ, "PATH": ""}, capture_output=True, text=True, timeout=30,
                    )
                    report = json.loads(result.stdout)
                    checks = {check["name"]: check for check in report["checks"]}
                    expected = {
                        "intrinsic-pixel-structure" if rule == "pixel-structure"
                        else f"intrinsic-wsi-dicom-{rule}"
                        for rule in case["expected"]
                    }
                    if case.get("expected_evidence") == "advisory":
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertTrue(all(checks[name]["status"] == "passed"
                                            for name in expected))
                        advisories = [message for optional in report["optional"]
                                      for message in optional.get("advisories", [])]
                        self.assertTrue(any(case["expected_advisory_contains"] in message
                                            for message in advisories), advisories)
                    else:
                        failed = {name for name, check in checks.items()
                                  if check["status"] == "failed"}
                        self.assertTrue(expected <= failed, (case["case_id"], failed))


if __name__ == "__main__":
    unittest.main()
