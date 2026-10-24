import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from wsi_dicom_bench.negative_bench import file_set_statement_cases as cases
from wsi_dicom_bench.negative_bench.mutations import generate_case


class FileSetStatementCases(unittest.TestCase):
    def test_real_candidate_accepts_scaffolds_and_localizes_file_set_defects(self):
        candidate = os.environ.get("WSI_DICOM_CANDIDATE")
        if not candidate:
            self.skipTest("set WSI_DICOM_CANDIDATE to validate the File-set challenge corpus")
        source = Path(cases.__file__).parent / "controls-v7" / "iods" / "fileset" / "DICOMDIR"
        document_source = Path(cases.__file__).parent / cases.DOCUMENT_CONTROL_PATHS[0]
        original = source.read_bytes()
        controls = [{"case_id": name, "mutation_name": "file_set_edits",
                     "mutation_parameters": parameters, "expected": []}
                    for name, parameters in [
                        ("control", {}), ("icon-control", {"icon": {}}),
                        ("empty-control", {"empty_directory": True}),
                        ("private-control", {"private_record": True}),
                    ]]
        controls.append({"case_id": "document-control", "mutation_name": "file_set_edits",
                         "control": cases.DOCUMENT_CONTROL_ID, "mutation_parameters": {}, "expected": []})
        with tempfile.TemporaryDirectory() as temporary:
            for case in [*controls, *cases.CASES]:
                with self.subTest(case=case["case_id"]):
                    output = Path(temporary) / case["case_id"]
                    output.mkdir()
                    selected = document_source if case.get("control") == cases.DOCUMENT_CONTROL_ID else source
                    generate_case({**case, "deterministic_seed": case["case_id"]}, selected, output)
                    result = subprocess.run(
                        [candidate, "validate", str(output), "--json"],
                        # This regression checks intrinsic localization. External
                        # tool limits are adjudicated in the complete challenge.
                        env={**os.environ, "PATH": ""}, capture_output=True, text=True, timeout=30,
                    )
                    report = json.loads(result.stdout)
                    failed = {check["name"] for check in report["checks"]
                              if check["status"] == "failed"}
                    diagnostics = [(check["name"], check["message"]) for check in report["checks"]
                                   if check["status"] == "failed"]
                    if case["case_id"] == "REQ-FILESET-006":
                        self.assertNotIn("no Directory Record references it", str(diagnostics))
                        self.assertIn("referenced by at most one Directory Record", str(diagnostics))
                    self.assertEqual(failed, {f"intrinsic-wsi-dicom-{rule}" for rule in case["expected"]}, diagnostics)
                    self.assertEqual(result.returncode, int(bool(failed)), result.stderr)
        self.assertEqual(source.read_bytes(), original, "generation changed its source DICOMDIR")


if __name__ == "__main__":
    unittest.main()
