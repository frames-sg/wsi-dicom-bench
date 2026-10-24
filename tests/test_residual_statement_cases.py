import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from wsi_dicom_bench.negative_bench import residual_statement_cases as cases
from wsi_dicom_bench.negative_bench.mutations import generate_case


class ResidualStatementCases(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("WSI_DICOM_CANDIDATE"), "needs candidate CLI")
    def test_cases_generate_and_fail_their_assigned_rules(self):
        candidate = Path(os.environ["WSI_DICOM_CANDIDATE"])
        root = Path(cases.__file__).parent
        sources = {
            "CP10-EVRLE-16F": root / "controls-v4/CP10-EVRLE-16F.dcm",
            "V7-FILESET": root / "controls-v7/iods/fileset/DICOMDIR",
            "V7-SEG-FRACTIONAL": root / "controls-v7/iods/seg-fractional.dcm",
            "V7-SR-TID1500": root / "controls-v7/iods/sr-tid1500.dcm",
            "W7-SET-PYRAMID-3L-LOT": root / "controls-v7/wsi/W7-SET-PYRAMID-3L-LOT",
            "W7-TS-DEFLATED-IMAGE-FRAME":
                root / "controls-v7/wsi/W7-TS-DEFLATED-IMAGE-FRAME.dcm",
            "W7-TS-ENCAPSULATED-UNCOMPRESSED":
                root / "controls-v7/wsi/W7-TS-ENCAPSULATED-UNCOMPRESSED.dcm",
            "W7-TS-HTJ2K-RPCL-128": root / "controls-v7/wsi/W7-TS-HTJ2K-RPCL-128.dcm",
            "W7-TS-J2K-PART1-ICT": root / "controls-v7/wsi/W7-TS-J2K-PART1-ICT.dcm",
            "W7-TS-JXL-LOSSLESS-RGB": root / "controls-v7/wsi/W7-TS-JXL-LOSSLESS-RGB.dcm",
        }
        named = [identifier for case in cases.CASES for identifier in case["requirement_ids"]]
        self.assertEqual(len(named), len(set(named)))
        with tempfile.TemporaryDirectory() as temporary:
            for case in cases.CASES:
                with self.subTest(case=case["case_id"]):
                    output = Path(temporary) / case["case_id"]
                    output.mkdir()
                    generate_case(
                        {**case, "deterministic_seed": f"test:{case['case_id']}"},
                        sources[case["control"]],
                        output,
                    )
                    result = subprocess.run(
                        [candidate, "validate", str(output), "--profile", "general", "--json"],
                        env={**os.environ, "PATH": ""}, capture_output=True, text=True, timeout=30,
                    )
                    report = json.loads(result.stdout)
                    failed = {
                        ("intrinsic-wsi-dicom-pixel-structure"
                         if check["name"] == "intrinsic-pixel-structure" else check["name"])
                        for check in report["checks"] if check["status"] == "failed"
                    }
                    expected = {f"intrinsic-wsi-dicom-{rule}" for rule in case["expected"]}
                    self.assertTrue(expected <= failed, (case["case_id"], sorted(failed)))


if __name__ == "__main__":
    unittest.main()
