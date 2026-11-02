import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import pydicom

from wsi_dicom_bench.negative_bench import residual_metadata_statement_cases as cases
from wsi_dicom_bench.negative_bench.mutations import generate_case


ASSIGNED = {
    "Ps10_7_1_02d941",
    "Ps10_7_1_1_1_1add3e",
    "Ps10_7_1_1_1_3653a7",
    "Ps10_7_1_1_1_5ec65a",
    "Ps10_7_1_2f09d3",
    "Ps10_7_1_607718",
    "Ps10_7_1_6b69cd",
    "Ps10_7_1_7cdb3d",
    "Ps10_7_1_a0dff3",
    "Ps10_7_1_a2a04a",
    "Ps10_8_6_6f3918",
    "Ps3_C_12_1_1_1_ac243d",
    "Ps5_10_8_d4693e",
    "Ps5_6_2_2_78baa9",
    "Ps5_A_7_e5c0fa",
    "Ps3_C_7_1_4_1_1_64e8d5",
    "Ps3_C_7_6_16_1_InConcatenationNumber_f490dd",
    "Ps3_C_7_6_16_1_InConcatenationTotalNumber_4fdb6d",
    "Ps3_C_7_6_16_1_SOPInstanceUIDOfConcatenationSource_487ffc",
    "Ps3_C_7_6_16_2_2_4_241add",
    "Ps3_C_7_6_16_2_2_4_3fcf86",
    "Ps3_C_7_6_16_2_2_4_b6a910",
    "Ps3_C_7_6_16_2_2_4_c53142",
    "Ps3_C_7_6_1_1_5_491487",
    "Ps3_C_7_9_LossyImageCompression_e641df",
    "Ps3_C_8_12_4_1_LossyImageCompression_debf6c",
    "Ps3_C_8_20_2_2_042c5f",
    "Ps3_C_8_20_2_LossyImageCompression_9c833d",
    "Ps3_C_8_32_2_1_7fa3d3",
    "Ps3_C_8_32_2_LossyImageCompression_a5f421",
}

EXPECTED_MESSAGES = {
    "REQ-RMD-001": "has an invalid VR",
    "REQ-RMD-002": 'the "DICM" Prefix is missing',
    "REQ-RMD-003": "odd Value Length 3",
    "REQ-RMD-004": "VR UN, which shall not be used for File Meta Information",
    "REQ-RMD-005": "Private Information (0002,0102): Type 1C present although its condition is not met",
    "REQ-RMD-006": "is not an absolute URL",
    "REQ-RMD-007": 'uses the scheme "https"',
    "REQ-RMD-008": "a colon and a port number",
    "REQ-RMD-009": "shall not be used for PS3.10 media storage",
    "REQ-RMD-010": "the Patient Module Attributes of a group are those its entire group shares",
    "REQ-RMD-011": "not strictly increasing",
    "REQ-RMD-012": "In-concatenation Total Number shall be greater than one",
    "REQ-RMD-013": "SOP Instance UID of Concatenation Source differs",
    "REQ-RMD-014": "Dimension Index Sequence differs",
    "REQ-RMD-015": "Shared Functional Groups Sequence differs",
    "REQ-RMD-016": "Per-Frame Functional Groups Item structure differs",
    "REQ-RMD-017": "Attributes outside the per-instance ones differs",
    "REQ-RMD-018": "once 01 it is not reset",
    "REQ-RMD-019": "once 01 it is not reset",
    "REQ-RMD-020": "once 01 it is not reset",
    "REQ-RMD-021": 'the Value shall be "01" for a Segmentation Instance',
    "REQ-RMD-022": 'the Value shall be "01" for a Parametric Map Instance',
}


class ResidualMetadataStatementCases(unittest.TestCase):
    def test_assigned_statements_are_accounted_for_once(self):
        authored = [
            identifier
            for case in cases.CASES
            for identifier in case["requirement_ids"]
        ]
        mapped = list(cases.NAMED_BY_EXISTING)
        corrected = list(cases.DISPOSITION_CORRECTIONS)
        accounted = [*authored, *mapped, *corrected]
        self.assertEqual(len(accounted), len(set(accounted)))
        self.assertEqual(set(accounted), ASSIGNED)

    def test_new_byte_and_same_instance_operations_generate_the_authored_defects(self):
        root = Path(cases.__file__).parent
        sources = {
            "REQ-RMD-001": root / "controls-v7/mutation-sources/CP11-MONO-EVRLE-4F.dcm",
            "REQ-RMD-002": root / "controls-v7/mutation-sources/CP11-MONO-EVRLE-4F.dcm",
            "REQ-RMD-018": root / "controls-v7/mutation-sources/CP11-MONO-EVRLE-4F.dcm",
        }
        by_id = {case["case_id"]: case for case in cases.CASES}
        with tempfile.TemporaryDirectory() as temporary:
            outputs = {}
            for case_id, source in sources.items():
                output = Path(temporary) / case_id
                output.mkdir()
                outputs[case_id] = generate_case(
                    {**by_id[case_id], "deterministic_seed": f"test:{case_id}"},
                    source,
                    output,
                )[0]

            implicit = outputs["REQ-RMD-001"][0].read_bytes()
            implementation = implicit.index(b"\x02\x00\x13\x00")
            self.assertNotEqual(implicit[implementation + 4:implementation + 6], b"SH")
            self.assertEqual(implicit[implementation + 4:implementation + 8], b"\x0e\x00\x00\x00")

            prefixed = outputs["REQ-RMD-002"][0].read_bytes()
            self.assertEqual(prefixed[128:132], b"DICX")

            first, second = (pydicom.dcmread(path) for path in outputs["REQ-RMD-018"])
            self.assertEqual(first.SOPInstanceUID, second.SOPInstanceUID)
            self.assertEqual(first.file_meta.MediaStorageSOPInstanceUID, first.SOPInstanceUID)
            self.assertEqual(second.file_meta.MediaStorageSOPInstanceUID, second.SOPInstanceUID)
            self.assertEqual((first.LossyImageCompression, second.LossyImageCompression),
                             ("01", "00"))

    @unittest.skipUnless(os.environ.get("WSI_DICOM_CANDIDATE"), "needs candidate CLI")
    def test_cases_generate_and_fail_their_assigned_rules(self):
        candidate = Path(os.environ["WSI_DICOM_CANDIDATE"])
        root = Path(cases.__file__).parent
        sources = {
            "CP11-MONO-EVRLE-4F":
                root / "controls-v7/mutation-sources/CP11-MONO-EVRLE-4F.dcm",
            "V7-PM-FLOAT": root / "controls-v7/iods/pm-float.dcm",
            "V7-SEG-BINARY": root / "controls-v7/iods/seg-binary.dcm",
            "V7-SEG-FOR-SET": root / "controls-v7/iods/sets/seg-for",
            "W7-CONCATENATION-2X4F": root / "controls-v7/wsi/W7-CONCATENATION-2X4F",
        }
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
                        env={**os.environ, "PATH": ""},
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    report = json.loads(result.stdout)
                    failed = {
                        check["name"]
                        for check in report["checks"]
                        if check["status"] == "failed"
                    }
                    expected = {
                        rule if rule.startswith("intrinsic-") else f"intrinsic-wsi-dicom-{rule}"
                        for rule in case["expected"]
                    }
                    self.assertTrue(expected <= failed, (case["case_id"], sorted(failed)))
                    target = next(
                        check for check in report["checks"] if check["name"] in expected
                    )
                    self.assertIn(EXPECTED_MESSAGES[case["case_id"]], target["message"])


if __name__ == "__main__":
    unittest.main()
