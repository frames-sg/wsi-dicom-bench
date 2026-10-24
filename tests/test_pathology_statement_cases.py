import json
import os
import tempfile
import unittest
from pathlib import Path

import pydicom

from wsi_dicom_bench.negative_bench import controls_v7_iods, pathology_statement_cases
from wsi_dicom_bench.negative_bench.mutations import generate_case


class PathologyStatementCaseTests(unittest.TestCase):
    def test_cases_name_catalog_statements_once_and_generate_readable_objects(self):
        requirements_path = (
            Path(__file__).parents[1]
            / "src/wsi_dicom_bench/rules/wsi-dicom-requirements-v1.json"
        )
        catalog = json.loads(requirements_path.read_text(encoding="utf-8"))
        requirements = {entry["id"]: entry for entry in catalog["requirements"]}
        controls = {}
        for control in controls_v7_iods.CONTROLS:
            paths = [controls_v7_iods.CONTROLS_DIR / path for path in control["paths"]]
            controls[control["id"]] = (
                paths[0] if len(paths) == 1 else Path(os.path.commonpath(paths))
            )
        cases = pathology_statement_cases.CASES

        self.assertEqual(len({case["case_id"] for case in cases}), len(cases))
        named = [identifier for case in cases for identifier in case["requirement_ids"]]
        self.assertEqual(len(named), len(set(named)))
        self.assertFalse(set(named) & set(pathology_statement_cases.UNCOVERED))
        for identifier in named:
            self.assertIn(identifier, requirements)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for case in cases:
                output = root / case["case_id"]
                output.mkdir()
                outputs, _ = generate_case(
                    {**case, "deterministic_seed": f"test:{case['case_id']}"},
                    controls[case["control"]],
                    output,
                )
                self.assertTrue(outputs, case["case_id"])
                for path in outputs:
                    dataset = pydicom.dcmread(path)
                    self.assertTrue(dataset.SOPInstanceUID, case["case_id"])

    def test_float_pixel_data_native_format_case_is_encoded_as_fragments(self):
        case = next(
            case
            for case in pathology_statement_cases.CASES
            if case["case_id"] == "REQ-PATH-092"
        )
        control = next(
            control
            for control in controls_v7_iods.CONTROLS
            if control["id"] == case["control"]
        )
        source = controls_v7_iods.CONTROLS_DIR / control["paths"][0]
        with tempfile.TemporaryDirectory() as temporary:
            outputs, _ = generate_case(
                {**case, "deterministic_seed": "test:REQ-PATH-092"},
                source,
                Path(temporary),
            )
            (output,) = outputs
            dataset = pydicom.dcmread(output)
            self.assertTrue(dataset["FloatPixelData"].is_undefined_length)
            self.assertTrue(output.read_bytes().endswith(b"\xfe\xff\xdd\xe0\0\0\0\0"))


if __name__ == "__main__":
    unittest.main()
