import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from wsi_dicom_bench.negative_bench import pixel_structure_statement_cases as cases
from wsi_dicom_bench.negative_bench.mutations import generate_case


class PixelStructureStatementCases(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("WSI_DICOM_CANDIDATE"), "needs candidate CLI")
    def test_cases_generate_and_fail_pixel_structure(self):
        candidate = Path(os.environ["WSI_DICOM_CANDIDATE"])
        root = Path(cases.__file__).parent / "controls-v7/wsi"
        sources = {
            cases.J2K: root / f"{cases.J2K}.dcm",
            cases.ENCAPSULATED_UNCOMPRESSED:
                root / f"{cases.ENCAPSULATED_UNCOMPRESSED}.dcm",
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
                        [candidate, "validate", str(output), "--json"],
                        env={**os.environ, "PATH": ""}, capture_output=True, text=True,
                        timeout=30,
                    )
                    report = json.loads(result.stdout)
                    failed = {check["name"] for check in report["checks"]
                              if check["status"] == "failed"}
                    self.assertIn("intrinsic-pixel-structure", failed, case["case_id"])


if __name__ == "__main__":
    unittest.main()
