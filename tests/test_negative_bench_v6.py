"""Integrity of the v6 requirement-statement amendment and its separation from frozen v5."""

import json
import re
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import pydicom

from wsi_dicom_bench.core_profile import intrinsic_rule_ids
from wsi_dicom_bench.file_digest import sha256_file
from wsi_dicom_bench.negative_bench import requirement_cases
from wsi_dicom_bench.negative_bench.iod_amendment_cases import full_rule_id


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "src" / "wsi_dicom_bench"
BENCH = PACKAGE_ROOT / "negative_bench"
RULES = PACKAGE_ROOT / "rules"
MANIFEST_V5 = BENCH / "manifest-v5.json"
MANIFEST_V6 = BENCH / "manifest-v6.json"
LOCK_V5 = BENCH / "expected-results-lock-v5.json"
LOCK_V6 = BENCH / "expected-results-lock-v6.json"
PROTOCOL_V6 = BENCH / "protocol-v6.md"
CONTROLS_V4 = BENCH / "controls-v4"
CONTROLS_V6 = BENCH / "controls-v6"
CATALOG_V5 = RULES / "wsi-dicom-bench-rules-2026c-v5.json"
CATALOG_V6 = RULES / "wsi-dicom-bench-rules-2026c-v6.json"
PROFILE_V3 = RULES / "wsi-dicom-core-profile-2026c-v3.json"
PROFILE_V4 = RULES / "wsi-dicom-core-profile-2026c-v4.json"
# `wsi-dicom requirements --json` of the frozen candidate.
REQUIREMENTS = RULES / "wsi-dicom-requirements-2026c-v1.json"
# Checked statements of REQUIREMENTS that no evaluation case names; lower it as cases
# gain requirement_ids, until every Checked statement has a case.
UNCLAIMED_CHECKED_LIMIT = 345
COHORT = "requirement-statement-evaluation-v1"
V6_RULES = frozenset(
    full_rule_id(name)
    for name in (
        "iod-value-sets",
        "wsi-image",
        "attribute-relations",
        "series-set",
        "pixel-attributes",
        "codestream",
        "encoding",
    )
)
# The two catalog-v5 rules whose summaries v6 changes: the Per-Frame Item count moves
# from iod-modules to iod-sequence-items.
MOVED_COUNT = frozenset(full_rule_id(name) for name in ("iod-modules", "iod-sequence-items"))
ICT_CONTROLS = ("CP05-J2K-LOSSY-4F", "CP08-HTJ2K-LOSSY-4F")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def cohort(manifest: dict) -> list[dict]:
    return [case for case in manifest["evaluation_cases"] if case["cohort"] == COHORT]


class FrozenV5ArtifactTests(unittest.TestCase):
    def test_v5_lock_still_binds_the_unchanged_v5_artifacts(self):
        lock = load(LOCK_V5)
        sources = {
            "bench/negative_bench/protocol-v5.md": BENCH / "protocol-v5.md",
            "bench/negative_bench/manifest-v5.json": MANIFEST_V5,
            "rules/wsi-dicom-bench-rules-2026c-v5.json": CATALOG_V5,
            "rules/wsi-dicom-core-profile-2026c-v3.json": PROFILE_V3,
        }
        self.assertEqual({item["path"] for item in lock["files"]}, set(sources))
        for item in lock["files"]:
            with self.subTest(path=item["path"]):
                self.assertEqual(sha256_file(sources[item["path"]]), item["sha256"])

    def test_v5_catalog_and_contract_remain_selectable(self):
        from wsi_dicom_bench.workbench.catalog import load_catalog
        from wsi_dicom_bench.workbench.cli import expected_profile_id
        from wsi_dicom_bench.workbench.contract import expected_rule_set_id

        catalog = load_catalog(CATALOG_V5)
        self.assertEqual(expected_profile_id(catalog), load(PROFILE_V3)["profile_id"])
        self.assertEqual(expected_rule_set_id(catalog, "core-2026c"), "wsi-dicom-core-profile-2026c-v3")
        self.assertFalse(V6_RULES & {rule["rule_id"] for rule in catalog["rules"]})


class CorrectedControlTests(unittest.TestCase):
    def test_controls_v6_change_only_the_photometric_declaration_and_identity(self):
        for control_id in ICT_CONTROLS:
            v4 = pydicom.dcmread(CONTROLS_V4 / f"{control_id}.dcm")
            v6 = pydicom.dcmread(CONTROLS_V6 / f"{control_id}.dcm")
            with self.subTest(control=control_id):
                self.assertEqual((v4.PhotometricInterpretation, v6.PhotometricInterpretation), ("YBR_RCT", "YBR_ICT"))
                self.assertNotEqual(v6.SOPInstanceUID, v4.SOPInstanceUID)
                self.assertEqual(v6.file_meta.MediaStorageSOPInstanceUID, v6.SOPInstanceUID)
                self.assertEqual(v6.PixelData, v4.PixelData)
                for keyword in ("StudyInstanceUID", "SeriesInstanceUID", "FrameOfReferenceUID", "PyramidUID"):
                    self.assertEqual(v6.data_element(keyword).value, v4.data_element(keyword).value)
                changed = {
                    element.keyword
                    for element in v6
                    if element.keyword not in {"PixelData"} and v4.get(element.tag) != element
                }
                self.assertEqual(changed, {"PhotometricInterpretation", "SOPInstanceUID", "DimensionOrganizationSequence",
                                           "DimensionIndexSequence"})

    def test_controls_v6_are_reproduced_by_their_builder(self):
        from wsi_dicom_bench.negative_bench.build_core_profile_controls import correct_lossy_photometric

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "controls-v6"
            correct_lossy_photometric(CONTROLS_V4, output)
            self.assertEqual(
                {path.name: sha256_file(path) for path in output.iterdir()},
                {path.name: sha256_file(path) for path in CONTROLS_V6.iterdir()},
            )


class CatalogAndProfileV6Tests(unittest.TestCase):
    def test_catalog_v6_is_catalog_v5_plus_one_rule_per_new_check(self):
        from wsi_dicom_bench.workbench.catalog import load_catalog

        v5 = load_catalog(CATALOG_V5)
        v6 = load_catalog(CATALOG_V6)
        self.assertEqual(v6["catalog_version"], "wsi-dicom-bench-rules-2026c-v6")
        old = {rule["rule_id"]: rule for rule in v5["rules"]}
        new = {rule["rule_id"]: rule for rule in v6["rules"]}
        self.assertEqual(set(new) - set(old), V6_RULES)
        self.assertEqual(set(old) - set(new), set())
        for rule_id, rule in old.items():
            with self.subTest(rule=rule_id):
                if rule_id in MOVED_COUNT:
                    self.assertNotEqual(new[rule_id]["summary"], rule["summary"])
                    self.assertEqual(new[rule_id]["check_names"], rule["check_names"])
                else:
                    self.assertEqual(new[rule_id], rule)
        for rule_id in V6_RULES:
            rule = new[rule_id]
            with self.subTest(rule=rule_id):
                self.assertEqual(rule["check_names"], [rule_id])
                # A rule over the evaluated set of Instances is an intrinsic set rule.
                self.assertEqual(rule["rule_kind"], "intrinsic_set" if rule_id.endswith("-set") else "intrinsic")
                for citation in rule["citations"]:
                    self.assertTrue(citation["url"].startswith("https://dicom.nema.org/medical/dicom/"))

    def test_per_frame_item_count_belongs_to_sequence_items_in_v6(self):
        rules = {rule["rule_id"]: rule for rule in load(CATALOG_V6)["rules"]}
        self.assertNotIn("one Item per Frame", rules[full_rule_id("iod-modules")]["summary"])
        self.assertIn("one Per-Frame Functional Groups Item per Frame", rules[full_rule_id("iod-sequence-items")]["summary"])

    def test_profile_v4_extends_v3_and_covers_every_intrinsic_rule(self):
        from wsi_dicom_bench.core_profile import load_profile, validate_profile_coverage

        v3 = load_profile(PROFILE_V3)
        v4 = load_profile(PROFILE_V4)
        self.assertEqual((v4["profile_id"], v4["profile_version"]), ("wsi-dicom-core-profile-2026c-v4", "4"))
        carried = v4["requirements"][: len(v3["requirements"])]
        for old, new in zip(v3["requirements"], carried, strict=True):
            with self.subTest(row=old["requirement_id"]):
                if old["requirement_id"] in requirement_cases.PROFILE_REMAPS:
                    replacement = full_rule_id(requirement_cases.PROFILE_REMAPS[old["requirement_id"]])
                    self.assertEqual(new, {**old, "enforcement": {**old["enforcement"], "rule_ids": [replacement]}})
                else:
                    self.assertEqual(new, old)
        added = v4["requirements"][len(v3["requirements"]):]
        self.assertEqual({rule for row in added for rule in row["enforcement"]["rule_ids"]}, V6_RULES)
        summary = validate_profile_coverage(v4, load(CATALOG_V6), load(MANIFEST_V6))
        self.assertEqual(summary["intrinsic_rule_count"], 32)
        self.assertEqual(summary["intrinsic_rules_without_negative_cases"], [])


class ManifestV6IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.v5 = load(MANIFEST_V5)
        self.v6 = load(MANIFEST_V6)
        self.catalog = load(CATALOG_V6)

    def test_committed_profile_manifest_and_lock_match_the_builder(self):
        from wsi_dicom_bench.negative_bench.build_requirement_manifest import (
            build_lock,
            build_manifest,
            build_profile,
            main,
        )

        self.assertEqual(build_profile(), load(PROFILE_V4))
        self.assertEqual(build_manifest(), self.v6)
        self.assertEqual(build_lock(), load(LOCK_V6))
        self.assertEqual(main([]), 0)

    def test_lock_v6_binds_protocol_manifest_catalog_and_profile(self):
        from wsi_dicom_bench.negative_bench.generate import GenerationError, _verify_expected_results_lock

        _verify_expected_results_lock(LOCK_V6, MANIFEST_V6, PROTOCOL_V6, CATALOG_V6, PROFILE_V4)
        baseline = load(LOCK_V6)
        self.assertEqual(
            baseline["expected_counts"],
            {"development_cases": 10, "evaluation_cases": 352, "valid_controls": 14, "compound_cases": 0},
        )
        broken = {
            "schema": {**baseline, "schema_version": "wsi-dicom-negative-bench-expected-results-lock-v5"},
            "counts": {**baseline, "expected_counts": {**baseline["expected_counts"], "evaluation_cases": 149}},
            "digest": {**baseline, "files": [{**baseline["files"][0], "sha256": "0" * 64}, *baseline["files"][1:]]},
            "profile": {**baseline, "core_profile": {**baseline["core_profile"], "version": "3"}},
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "expected-results-lock-v6.json"
            for name, document in broken.items():
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.subTest(defect=name), self.assertRaises(GenerationError):
                    _verify_expected_results_lock(path, MANIFEST_V6, PROTOCOL_V6, CATALOG_V6, PROFILE_V4)

    def test_manifest_v6_identity_points_at_v6_artifacts(self):
        self.assertEqual(self.v6["schema_version"], "wsi-dicom-negative-bench-manifest-v6")
        self.assertEqual(self.v6["rule_catalog"]["catalog_version"], self.catalog["catalog_version"])
        self.assertEqual(set(self.v6["rule_catalog"]["required_new_rule_ids"]), V6_RULES)
        self.assertEqual(self.v6["core_profile"]["profile_id"], load(PROFILE_V4)["profile_id"])
        self.assertEqual((self.v6["protocol"], self.v6["expected_results_lock"]), (PROTOCOL_V6.name, LOCK_V6.name))
        self.assertIs(self.v6["expectation_provenance"]["blinded"], False)
        self.assertRegex(self.v6["expectation_provenance"]["candidate"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertIn("not blinded", PROTOCOL_V6.read_text(encoding="utf-8").replace("\n", " "))

    def test_only_the_ict_controls_change_and_their_cases_are_rebased(self):
        old = {control["control_id"]: control for control in self.v5["valid_controls"]}
        new = {control["control_id"]: control for control in self.v6["valid_controls"]}
        self.assertEqual(set(new), set(old))
        for control_id, control in new.items():
            with self.subTest(control=control_id):
                if control_id in ICT_CONTROLS:
                    path = BENCH / Path(control["original_path"]).relative_to("bench/negative_bench")
                    self.assertEqual(path.parent, CONTROLS_V6)
                    self.assertEqual(control["sha256"], sha256_file(path))
                    self.assertIn("YBR_ICT", control["correction"])
                else:
                    self.assertEqual(control, old[control_id])
        for case in self.v6["evaluation_cases"]:
            (source,) = case["source_control_ids"]
            with self.subTest(case=case["case_id"]):
                self.assertEqual(case["source_control_sha256"], new[source]["sha256"])

    def test_every_v5_entry_is_carried_forward_with_the_same_mutation(self):
        self.assertEqual(self.v6["development_cases"], self.v5["development_cases"])
        carried = {case["case_id"]: case for case in self.v6["evaluation_cases"]}
        fields = ("mutation_name", "mutation_parameters", "deterministic_seed", "source_control_ids",
                  "domain", "cohort", "exact_attributes_or_bytes_changed")
        for old in self.v5["evaluation_cases"]:
            new = carried[old["case_id"]]
            adjudications = new.get("requirement_rule_adjudications", [])
            with self.subTest(case=old["case_id"]):
                self.assertEqual({field: new[field] for field in fields}, {field: old[field] for field in fields})
                superseded = {item["rule_id"] for item in adjudications if item["disposition"] == "superseded_expected_rule"}
                added = {item["rule_id"] for item in adjudications if item["disposition"] == "expected_failing_rule"}
                cascades = {item["rule_id"] for item in adjudications if item["disposition"] == "adjudicated_cascade"}
                self.assertEqual(len(adjudications), len(superseded) + len(added) + len(cascades))
                self.assertEqual(set(new["expected_failing_rules"]),
                                 set(old["expected_failing_rules"]) - superseded | added)
                self.assertEqual(set(new.get("adjudicated_cascade_rules", [])),
                                 set(old.get("adjudicated_cascade_rules", [])) | cascades)
                for item in adjudications:
                    self.assertTrue(item["rationale"])
                    if item["disposition"] == "superseded_expected_rule":
                        self.assertIn(item["replacement_rule_id"], added)
                    else:
                        self.assertTrue(item["observed"])
                        self.assertTrue(item["citation"]["url"].startswith("https://dicom.nema.org/medical/dicom/2026c/"))

    def test_expected_unaffected_rules_exclude_every_expected_and_cascade_rule(self):
        intrinsic = intrinsic_rule_ids(self.catalog["rules"])
        for case in self.v6["evaluation_cases"]:
            failing = set(case["expected_failing_rules"]) | set(case.get("adjudicated_cascade_rules", []))
            with self.subTest(case=case["case_id"]):
                self.assertTrue(failing <= intrinsic)
                self.assertEqual(set(case["expected_unaffected_rules"]), intrinsic - failing)

    def test_requirement_cohort_targets_every_v6_rule_with_single_file_cases(self):
        from wsi_dicom_bench.negative_bench.mutations import ALL_MUTATIONS

        rules = {rule["rule_id"]: rule for rule in self.catalog["rules"]}
        controls = {control["control_id"]: control for control in self.v6["valid_controls"]}
        cases = cohort(self.v6)
        self.assertEqual(len(cases), 203)
        self.assertEqual(len(self.v6["evaluation_cases"]), 352)
        families = Counter(case["target_rule_family"] for case in cases)
        self.assertEqual(set(families), V6_RULES)
        for case in cases:
            with self.subTest(case=case["case_id"]):
                self.assertIn(case["target_rule_family"], case["expected_failing_rules"])
                self.assertNotIn("adjudicated_cascade_rules", case)
                self.assertEqual(case["domain"], rules[case["target_rule_family"]]["primary_domain"])
                self.assertIn(case["likely_fix_owner"], rules[case["target_rule_family"]]["likely_fix_owners"])
                # Context Group and Template bindings are table rows, which have no statement id.
                self.assertEqual(bool(case["requirement_ids"]), case["target_rule_family"] != full_rule_id("iod-value-sets"))
                self.assertTrue(all(re.fullmatch(r"Ps\d+_[A-Za-z0-9_]+_[0-9a-f]{6}", item) for item in case["requirement_ids"]))
                self.assertIn(case["mutation_name"], ALL_MUTATIONS)
                self.assertNotIn("package_paths", controls[case["source_control_ids"][0]])
                self.assertTrue(case["exact_attributes_or_bytes_changed"])
                self.assertTrue(case["dicom_citation"]["url"].startswith("https://dicom.nema.org/medical/dicom/2026c/"))

    def test_uncovered_statements_are_not_claimed_by_any_case(self):
        claimed = {item for case in cohort(self.v6) for item in case["requirement_ids"]}
        self.assertFalse(claimed & set(requirement_cases.UNCOVERED))

    def test_every_mutation_is_used_by_a_suite(self):
        from wsi_dicom_bench.negative_bench.mutations import ALL_MUTATIONS

        used = {
            case["mutation_name"]
            for manifest in (load(BENCH / "manifest-v4.json"), self.v5, self.v6)
            for case in manifest["evaluation_cases"]
        }
        self.assertEqual(set(ALL_MUTATIONS) - used, {"invalid_specimen_uid", "total_matrix_too_large"})


class RequirementCoverageTests(unittest.TestCase):
    def setUp(self):
        snapshot = load(REQUIREMENTS)
        self.assertEqual(snapshot["schema_version"], "wsi-dicom-requirements-v1")
        self.statements = {item["id"]: item for item in snapshot["requirements"] if item["id"]}
        self.rule_of = {name: rule["rule_id"] for rule in load(CATALOG_V6)["rules"] for name in rule["check_names"]}
        self.manifest = load(MANIFEST_V6)

    def checking_rule(self, statement: str) -> str | None:
        disposition = self.statements[statement]["disposition"]
        return self.rule_of[disposition["detail"]] if disposition["kind"] == "checked" else None

    def test_named_statements_are_checked_by_an_expected_rule(self):
        for case in self.manifest["evaluation_cases"]:
            for statement in case.get("requirement_ids", []):
                with self.subTest(case=case["case_id"], statement=statement):
                    self.assertIn(statement, self.statements)
                    self.assertIn(self.checking_rule(statement), case["expected_failing_rules"])

    def test_uncovered_statements_are_checked_and_unclaimed(self):
        for statement in requirement_cases.UNCOVERED:
            with self.subTest(statement=statement):
                self.assertIsNotNone(self.checking_rule(statement))

    def test_unclaimed_checked_statements_only_fall(self):
        claimed = {item for case in self.manifest["evaluation_cases"] for item in case.get("requirement_ids", [])}
        unclaimed = {statement for statement in self.statements if self.checking_rule(statement)} - claimed
        self.assertEqual(len(unclaimed), UNCLAIMED_CHECKED_LIMIT, f"lower UNCLAIMED_CHECKED_LIMIT to {len(unclaimed)}")
        v6 = {statement for statement in unclaimed if self.checking_rule(statement) in V6_RULES}
        self.assertEqual(v6, {statement for statement in requirement_cases.UNCOVERED if self.checking_rule(statement) in V6_RULES})


class HarnessCorrectionTests(unittest.TestCase):
    def generate(self, case_id: str) -> list[Path]:
        from wsi_dicom_bench.negative_bench.mutations import generate_case

        case = next(case for case in load(MANIFEST_V6)["evaluation_cases"] if case["case_id"] == case_id)
        control = next(c for c in load(MANIFEST_V6)["valid_controls"] if c["control_id"] == case["source_control_ids"][0])
        source = BENCH / Path(control["original_path"]).relative_to("bench/negative_bench")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        outputs, _ = generate_case(case, source, Path(self.temporary.name))
        return outputs

    def test_instance_pairs_of_one_series_have_distinct_instance_numbers(self):
        for case_id in ("NB-ID-003", "NB-ID-006", "NB-GE-008", "CP-GE-005", "CP-ID-001", "REQ-SET-002"):
            datasets = [pydicom.dcmread(path, stop_before_pixels=True) for path in self.generate(case_id)]
            with self.subTest(case=case_id):
                self.assertEqual(len({dataset.SeriesInstanceUID for dataset in datasets}), 1)
                self.assertEqual(len({int(dataset.InstanceNumber) for dataset in datasets}), len(datasets))

    def test_re_encapsulated_pixel_data_ends_with_one_sequence_delimiter(self):
        delimiter = b"\xfe\xff\xdd\xe0\x00\x00\x00\x00"
        for case_id in ("REQ-CS-001", "REQ-CS-009", "REQ-CS-014"):
            (path,) = self.generate(case_id)
            data = path.read_bytes()
            with self.subTest(case=case_id):
                self.assertTrue(data.endswith(delimiter))
                self.assertFalse(data[: -len(delimiter)].endswith(delimiter))


class GenerationV6Tests(unittest.TestCase):
    def test_complete_v6_generation_is_deterministic(self):
        from wsi_dicom_bench.negative_bench.finalize import _verify_generation_sums
        from wsi_dicom_bench.negative_bench.generate import generate_challenge

        with tempfile.TemporaryDirectory() as temporary:
            first, second = Path(temporary) / "first", Path(temporary) / "second"
            generate_challenge(MANIFEST_V6, first)
            generate_challenge(MANIFEST_V6, second)
            _verify_generation_sums(first)
            self.assertEqual(len(list((first / "cases").iterdir())), 352)
            self.assertEqual(len(list((first / "controls").rglob("*.dcm"))), 15)
            self.assertEqual(
                [sha256_file(path) for path in sorted(first.rglob("*.dcm"))],
                [sha256_file(path) for path in sorted(second.rglob("*.dcm"))],
            )
            for case in cohort(load(MANIFEST_V6)):
                report = load(first / "cases" / case["case_id"] / "generation.json")
                with self.subTest(case=case["case_id"]):
                    self.assertEqual(report["mutation_name"], case["mutation_name"])
                    self.assertGreater(len(report["changes"]), 1)


if __name__ == "__main__":
    unittest.main()
