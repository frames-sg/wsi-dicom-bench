import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from wsi_dicom_bench.negative_bench import basic_image_statement_cases as cases
from wsi_dicom_bench.negative_bench.mutations import generate_case


class BasicImageStatementCases(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("WSI_DICOM_CANDIDATE"), "needs candidate CLI")
    def test_cases_generate_and_fail_image_metadata(self):
        candidate = Path(os.environ["WSI_DICOM_CANDIDATE"])
        root = Path(cases.__file__).parent
        sources = {
            "CP10-EVRLE-16F": root / "controls-v4/CP10-EVRLE-16F.dcm",
            "CP14-MONO16-EVRLE": root / "controls-v4/CP14-MONO16-EVRLE.dcm",
            **{
                name: root / "controls-v7/wsi" / f"{name}.dcm"
                for name in (
                    "W7-TS-JPEG-BASELINE-YBR422", "W7-TS-RLE-RGB",
                    "W7-TS-JPEG-LS-LOSSLESS-RGB", "W7-TS-J2K-PART1-ICT",
                    "W7-TS-HTJ2K-RPCL-128", "W7-TS-JXL-LOSSLESS-RGB",
                )
            },
        }
        named = [identifier for case in cases.CASES for identifier in case["requirement_ids"]]
        self.assertEqual(len(cases.CASES), 15)
        self.assertEqual(len(named), 19)
        self.assertEqual(len(named), len(set(named)))
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
                    failed = {
                        check["name"] for check in report["checks"]
                        if check["status"] == "failed"
                    }
                    self.assertIn(
                        "intrinsic-wsi-dicom-image-metadata", failed, case["case_id"]
                    )


if __name__ == "__main__":
    unittest.main()
