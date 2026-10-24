import struct
import tempfile
import unittest
from pathlib import Path

import pydicom

from wsi_dicom_bench.negative_bench import controls_v7_iods
from wsi_dicom_bench.negative_bench import controls_v7_mutation_sources
from wsi_dicom_bench.negative_bench import iod_statement_cases
from wsi_dicom_bench.negative_bench.controls_v7_wsi import frame_offset_problems
from wsi_dicom_bench.negative_bench.mutations import generate_case


class V7ControlTests(unittest.TestCase):
    def test_iod_builder_corrects_source_frame_offsets(self):
        level_zero, level_one = controls_v7_iods._load_sources()

        self.assertEqual(frame_offset_problems(level_zero), [])
        self.assertEqual(frame_offset_problems(level_one), [])

    def test_annotation_polygons_wind_clockwise(self):
        root = controls_v7_iods.CONTROLS_DIR
        for name in ("ann-2d.dcm", "ann-3d.dcm"):
            dataset = pydicom.dcmread(root / name)
            for group in dataset.AnnotationGroupSequence:
                if str(group.GraphicType) != "POLYGON":
                    continue
                raw = group.DoublePointCoordinatesData
                coordinates = struct.unpack(f"<{len(raw) // 8}d", raw)
                raw_indices = group.LongPrimitivePointIndexList
                starts = [value - 1 for value in struct.unpack(f"<{len(raw_indices) // 4}I", raw_indices)]
                starts.append(len(coordinates))
                for first_index, end_index in zip(starts[:-1], starts[1:], strict=True):
                    points = list(zip(coordinates[first_index:end_index:2],
                                      coordinates[first_index + 1:end_index:2], strict=True))
                    twice_area = sum(
                        first[0] * second[1] - second[0] * first[1]
                        for first, second in zip(points, [*points[1:], points[0]], strict=True)
                    )
                    self.assertLess(twice_area, 0, f"{name} polygon is not clockwise")

    def test_rebased_mutation_sources_change_only_slide_offsets(self):
        self.assertEqual(controls_v7_mutation_sources.verify(), [])

        def values(dataset, path=()):
            result = {}
            for element in dataset:
                current = (*path, element.tag)
                if element.VR == "SQ":
                    for index, item in enumerate(element.value):
                        result.update(values(item, (*current, index)))
                else:
                    result[current] = (element.VR, element.value)
            return result

        changed = []
        for paths in controls_v7_mutation_sources.SOURCES.values():
            for relative in paths:
                before = values(pydicom.dcmread(controls_v7_mutation_sources.SOURCE_DIR / relative))
                after = values(
                    pydicom.dcmread(controls_v7_mutation_sources.CONTROLS_DIR / relative)
                )
                self.assertEqual(set(before), set(after))
                for path in before:
                    if before[path] != after[path]:
                        changed.append(path)
                        self.assertEqual(path[-1], 0x0040072A)
        self.assertTrue(changed)


class V7StatementCaseTests(unittest.TestCase):
    def test_known_short_vr_can_be_rewritten_as_explicit_un(self):
        case = next(case for case in iod_statement_cases.CASES
                    if case["case_id"] == "REQ-IOD-042")
        source = (controls_v7_iods.PACKAGE_DIR / "controls-v4" /
                  "CP10-EVRLE-16F.dcm")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            generate_case({**case, "deterministic_seed": "test:REQ-IOD-042"}, source, output)
            encoded = (output / "instance.dcm").read_bytes()

        self.assertIn(b"\x08\x00\x30\x10UN\x00\x00\x20\x00\x00\x00", encoded)


class V7DraftTests(unittest.TestCase):
    def test_draft_manifest_registers_controls_cases_and_honest_coverage(self):
        import json

        from wsi_dicom_bench.negative_bench import (
            basic_image_statement_cases,
            controls_v7_wsi,
            deidentification_statement_cases,
            file_set_statement_cases,
            generic_iod_statement_cases,
            http_statement_cases,
            iod_statement_cases,
            jpip_statement_cases,
            json_statement_cases,
            motion_statement_cases,
            parser_statement_cases,
            pathology_statement_cases,
            pixel_structure_statement_cases,
            residual_metadata_statement_cases,
            residual_codestream_cases,
            residual_statement_cases,
            requirement_cases,
            signature_statement_cases,
        )
        from wsi_dicom_bench.negative_bench.build_v7 import (
            CARRIED_CANDIDATE_GAPS,
            TRUE_UID_REUSE_CASE_ID,
            V6_MANIFEST,
            build_manifest,
            load_carried_observations,
            load_statement_observations,
            load_http_observations,
        )

        manifest = build_manifest()
        v6 = json.loads(V6_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], "wsi-dicom-negative-bench-manifest-v7-draft")
        self.assertEqual(manifest["status"], "draft_unfrozen")
        self.assertEqual(
            len(manifest["valid_controls"]),
            len(controls_v7_wsi.CONTROLS) + len(controls_v7_iods.CONTROLS) + 13,
        )
        self.assertEqual(len(manifest["mutation_sources"]), len(v6["valid_controls"]))
        ready = [case for case in iod_statement_cases.CASES
                 if case["case_id"] not in iod_statement_cases.BLOCKED_CASES]
        from wsi_dicom_bench.negative_bench import metadata_statement_cases
        self.assertEqual(
            len(manifest["evaluation_cases"]),
            len(v6["evaluation_cases"])
            - len(manifest["core_profile_evaluation_cases"])
            - len(manifest["candidate_gap_cases"])
            + len(ready) + len(basic_image_statement_cases.CASES)
            + sum(case.get("expected_evidence") != "advisory"
                  for case in generic_iod_statement_cases.CASES)
            + len(metadata_statement_cases.CASES)
            + len(motion_statement_cases.CASES)
            + len(pathology_statement_cases.CASES) + len(file_set_statement_cases.CASES)
            + len(pixel_structure_statement_cases.CASES)
            + len(deidentification_statement_cases.CASES) + len(parser_statement_cases.CASES)
            + len(residual_metadata_statement_cases.CASES)
            + len(residual_codestream_cases.CASES)
            + len(residual_statement_cases.CASES)
            + len(signature_statement_cases.CASES),
        )
        self.assertEqual(
            {case["case_id"] for case in manifest["core_profile_evaluation_cases"]},
            {"CP-ID-001", "CP-ID-004", "CP-CF-011"},
        )
        self.assertEqual(
            {case["case_id"] for case in manifest["candidate_gap_cases"]},
            set(CARRIED_CANDIDATE_GAPS),
        )
        self.assertEqual(
            {case["case_id"] for case in manifest["advisory_cases"]},
            {"NB-ID-005", "REQ-GENERIC-003", "REQ-GENERIC-004"},
        )
        self.assertIn(TRUE_UID_REUSE_CASE_ID,
                      {case["case_id"] for case in manifest["evaluation_cases"]})
        self.assertEqual(
            len(manifest["json_evaluation_cases"]),
            len(json_statement_cases.CASES) + len(jpip_statement_cases.CASES),
        )
        self.assertEqual(len(manifest["http_evaluation_cases"]), len(http_statement_cases.CASES))
        all_case_ids = [
            case["case_id"]
            for field in (
                "evaluation_cases", "core_profile_evaluation_cases", "candidate_gap_cases",
                "advisory_cases", "json_evaluation_cases",
                "http_evaluation_cases",
            )
            for case in manifest[field]
        ]
        self.assertEqual(len(all_case_ids), len(set(all_case_ids)))
        v7_single_source_ids = {
            control["control_id"] for control in manifest["valid_controls"]
            if len(control["original_paths"]) == 1
        }
        for case in manifest["evaluation_cases"]:
            if case["source_control_ids"][0] in v7_single_source_ids:
                self.assertIsInstance(case["source_control_sha256"], str, case["case_id"])
        self.assertNotIn("expected_results_lock", manifest)
        coverage = manifest["statement_coverage"]
        self.assertEqual(
            coverage["file_object_checked_statements"],
            coverage["directly_named_statements"]
            + coverage["duplicate_text_and_rule_mappings"]
            + coverage["uncovered_file_object_statements"],
        )
        self.assertLessEqual(
            coverage["mapped_to_existing_case_statements"], coverage["directly_named_statements"]
        )
        self.assertEqual(coverage["uncovered_file_object_statements"], 0)
        self.assertEqual(coverage["dicomweb_statements_requiring_http_cases"], 0)
        self.assertEqual(
            coverage["dicomweb_checked_statements"],
            coverage["directly_named_dicomweb_statements"]
            + coverage["dicomweb_statements_requiring_http_cases"],
        )
        self.assertEqual(
            coverage["directly_named_dicom_json_statements"],
            coverage["dicom_json_checked_statements"],
        )
        self.assertEqual(coverage["dicom_json_statements_requiring_json_cases"], 0)
        ledger = json.loads((V6_MANIFEST.parent / coverage["path"]).read_text(encoding="utf-8"))
        documented = {item["id"]: item["blocker"] for item in ledger["uncovered"]
                      if "blocker" in item}
        expected_blockers = {
            identifier: reason
            for source in (
                requirement_cases.UNCOVERED,
                pathology_statement_cases.UNCOVERED,
                residual_statement_cases.UNCOVERED,
            )
            for identifier, reason in source.items()
            if identifier in {item["id"] for item in ledger["uncovered"]}
        }
        self.assertTrue(expected_blockers.items() <= documented.items())
        evaluation_ids = {case["case_id"] for case in manifest["evaluation_cases"]}
        self.assertFalse(evaluation_ids & set(iod_statement_cases.BLOCKED_CASES))
        from wsi_dicom_bench.negative_bench.build_v7 import build_catalog, load_requirements
        catalog_rules = {rule["rule_id"] for rule in build_catalog(load_requirements())["rules"]}
        actual_unmapped = {
            rule: sorted(case["case_id"] for case in manifest["evaluation_cases"]
                         if rule in case["expected_failing_rules"])
            for rule in sorted({rule for case in manifest["evaluation_cases"]
                                for rule in case["expected_failing_rules"]
                                if rule not in catalog_rules})
        }
        self.assertEqual(manifest["carried_expectations_outside_v7_catalog"], actual_unmapped)

        carried_observations = load_carried_observations()["cases"]
        for case in manifest["evaluation_cases"]:
            if case["case_id"] not in carried_observations:
                continue
            observed = set(carried_observations[case["case_id"]]["general_failed_rules"])
            expected_intrinsic = {
                rule for rule in case["expected_failing_rules"]
                if rule.startswith("intrinsic-")
            }
            self.assertEqual(
                observed,
                expected_intrinsic | set(case.get("adjudicated_cascade_rules", [])),
                case["case_id"],
            )
        http_observations = load_http_observations()["cases"]
        for case in manifest["http_evaluation_cases"]:
            observed = http_observations[case["case_id"]]
            self.assertEqual(observed["baseline_failed_checks"], [], case["case_id"])
            if case["expected_advisory_checks"]:
                self.assertEqual(observed["observed_status"], "passed", case["case_id"])
                self.assertTrue(observed["observed_advisories"], case["case_id"])
            else:
                self.assertEqual(observed["observed_status"], "failed", case["case_id"])
            self.assertEqual(
                set(observed["failed_checks"]),
                set(case["expected_failing_checks"])
                | set(case["adjudicated_cascade_checks"]),
                case["case_id"],
            )
        for case in manifest["core_profile_evaluation_cases"]:
            observed = set(carried_observations[case["case_id"]]["core_failed_rules"])
            self.assertTrue(set(case["expected_failing_rules"]) <= observed, case["case_id"])
        statement_observations = load_statement_observations()["cases"]
        for case in manifest["evaluation_cases"]:
            if case["case_id"] not in statement_observations:
                continue
            observed = set(statement_observations[case["case_id"]]["failed_rules"])
            self.assertEqual(
                observed,
                set(case["expected_failing_rules"])
                | set(case.get("adjudicated_cascade_rules", [])),
                case["case_id"],
            )

    def test_v7_catalog_and_requirement_snapshot_are_edition_neutral_artifacts(self):
        from wsi_dicom_bench.negative_bench.build_v7 import build_catalog, load_requirements
        from wsi_dicom_bench.workbench.contract import expected_rule_set_id

        requirements = load_requirements()
        catalog = build_catalog(requirements)
        self.assertEqual(catalog["catalog_version"], "wsi-dicom-bench-rules-v7")
        self.assertEqual(catalog["dicom_edition"], "2026d")
        self.assertEqual(catalog["validation_profile"], "general")
        self.assertEqual(catalog["candidate_rule_set_id"], "wsi-dicom-general-v4")
        names = {name for rule in catalog["rules"] for name in rule["check_names"]}
        self.assertIn("intrinsic-wsi-dicom-file-set", names)
        self.assertIn("intrinsic-wsi-dicom-structured-report", names)
        self.assertNotIn("intrinsic-wsi-dicom-2026c-file-meta", names)
        self.assertEqual(requirements["dicom_edition"], "2026d")
        self.assertEqual(expected_rule_set_id(catalog, "general"), "wsi-dicom-general-v4")


if __name__ == "__main__":
    unittest.main()
