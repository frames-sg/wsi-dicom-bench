"""Integrity of the v6 negative-bench suite: controls, catalog, profile, manifest, and mutations."""

import hashlib
import json
import re
import struct
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import pydicom

from wsi_dicom_bench.core_profile import intrinsic_rule_ids
from wsi_dicom_bench.file_digest import sha256_file
from wsi_dicom_bench.negative_bench import iod_amendment_cases, requirement_cases
from wsi_dicom_bench.negative_bench.iod_amendment_cases import full_rule_id


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "src" / "wsi_dicom_bench"
BENCH = PACKAGE_ROOT / "negative_bench"
RULES = PACKAGE_ROOT / "rules"
MANIFEST_V6 = BENCH / "manifest-v6.json"
LOCK_V6 = BENCH / "expected-results-lock-v6.json"
PROTOCOL_V6 = BENCH / "protocol-v6.md"
CONTROLS_V4 = BENCH / "controls-v4"
CONTROLS_V6 = BENCH / "controls-v6"
CATALOG_V2 = RULES / "wsi-dicom-bench-rules-2026c-v2.json"
CATALOG_V6 = RULES / "wsi-dicom-bench-rules-2026c-v6.json"
PROFILE_V4 = RULES / "wsi-dicom-core-profile-2026c-v4.json"
# `wsi-dicom requirements --json` of the frozen candidate.
REQUIREMENTS = RULES / "wsi-dicom-requirements-2026c-v1.json"
# Checked statements of REQUIREMENTS that no evaluation case names; lower it as cases
# gain requirement_ids, until every Checked statement has a case.
UNCLAIMED_CHECKED_LIMIT = 345
COHORT = "requirement-statement-evaluation-v1"
CORE_COHORT = "core-profile-evaluation-v2"
STRUCTURE_COHORT = "iod-structure-evaluation-v1"
IOD_RULES = frozenset(iod_amendment_cases.IOD_RULES)
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
ICT_CONTROLS = ("CP05-J2K-LOSSY-4F", "CP08-HTJ2K-LOSSY-4F")
# The fields that define the mutation of a case.
MUTATION_FIELDS = ("mutation_name", "mutation_parameters", "deterministic_seed", "source_control_ids",
                   "domain", "cohort", "exact_attributes_or_bytes_changed")
# SHA-256 of MUTATION_FIELDS of the 149 core-profile and IOD structure cases, in manifest order.
# They keep the mutations and seeds they were authored with, so the digest never changes.
CARRIED_MUTATIONS_SHA256 = "dc5eeae86fab367a0e3bbf56c19b705719d3fc789bad829a281174727193f4de"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def cohort(manifest: dict, name: str = COHORT) -> list[dict]:
    return [case for case in manifest["evaluation_cases"] if case["cohort"] == name]


def control_path(control: dict) -> list[Path]:
    paths = control.get("original_paths", [control.get("original_path")])
    return [BENCH / Path(path).relative_to("bench/negative_bench") for path in paths]


def dispositions(case: dict, field: str = "requirement_rule_adjudications") -> dict[str, set[str]]:
    by_disposition: dict[str, set[str]] = {}
    for item in case.get(field, []):
        by_disposition.setdefault(item["disposition"], set()).add(item["rule_id"])
    return by_disposition


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


class RuleSetSelectionTests(unittest.TestCase):
    def validation(self, catalog: dict, profile: str, rule_set_id: str) -> dict:
        return {
            "schema_version": "wsi-dicom-validation-report-v1",
            "rule_set_id": rule_set_id,
            "profile": profile,
            "files": ["one.dcm"],
            "checks": [
                {"name": name, "path": "one.dcm", "status": "passed"}
                for rule in catalog["rules"]
                if rule["rule_kind"] != "independent_decoder"
                for name in rule["check_names"]
            ],
        }

    def test_catalog_v6_and_its_contract_are_selected_together(self):
        from wsi_dicom_bench.workbench.catalog import load_catalog
        from wsi_dicom_bench.workbench.cli import expected_profile_id
        from wsi_dicom_bench.workbench.contract import expected_rule_set_id

        catalog = load_catalog(CATALOG_V6)
        self.assertEqual(expected_profile_id(catalog), load(PROFILE_V4)["profile_id"])
        self.assertEqual(expected_rule_set_id(catalog, "core-2026c"), "wsi-dicom-core-profile-2026c-v4")
        self.assertEqual(expected_rule_set_id(catalog, "general"), "wsi-dicom-general-v3")

    def test_each_catalog_accepts_only_its_own_rule_sets(self):
        from wsi_dicom_bench.workbench.catalog import load_catalog
        from wsi_dicom_bench.workbench.contract import validation_contract_errors

        for path, profile, accepted, rejected in (
            (CATALOG_V6, "core-2026c", "wsi-dicom-core-profile-2026c-v4", "wsi-dicom-general-v3"),
            (CATALOG_V6, "general", "wsi-dicom-general-v3", "wsi-dicom-general-v1"),
            (CATALOG_V2, "general", "wsi-dicom-general-v1", "wsi-dicom-general-v3"),
        ):
            catalog = load_catalog(path)
            core = profile == "core-2026c"
            with self.subTest(catalog=path.name, profile=profile):
                self.assertEqual(
                    validation_contract_errors(self.validation(catalog, profile, accepted), catalog, core), []
                )
                errors = validation_contract_errors(self.validation(catalog, profile, rejected), catalog, core)
                self.assertTrue(any("selected rule set" in error for error in errors))

    def test_unknown_catalog_versions_fail_closed(self):
        from wsi_dicom_bench.workbench.contract import validation_contract_errors

        catalog = {"catalog_version": "unreviewed-catalog", "rules": []}
        report = {
            "schema_version": "wsi-dicom-validation-report-v1",
            "rule_set_id": "wsi-dicom-general-v2",
            "profile": "general",
            "files": ["one.dcm"],
            "checks": [],
        }
        errors = validation_contract_errors(report, catalog, core=False)
        self.assertTrue(any("declares no selected rule set" in error for error in errors))

    def test_pre_iod_catalog_reports_iod_checks_as_unmapped(self):
        from wsi_dicom_bench.workbench.catalog import load_catalog
        from wsi_dicom_bench.workbench.contract import validation_contract_errors

        catalog = load_catalog(CATALOG_V2)
        report = self.validation(catalog, "general", "wsi-dicom-general-v1")
        report["checks"].append(
            {"name": "intrinsic-wsi-dicom-2026c-file-meta", "path": "one.dcm", "status": "passed"}
        )
        errors = validation_contract_errors(report, catalog, False)
        self.assertIn("binary emitted an unmapped check: intrinsic-wsi-dicom-2026c-file-meta", errors)

    def test_catalog_v6_requires_every_iod_check_on_every_instance(self):
        from wsi_dicom_bench.workbench.catalog import load_catalog
        from wsi_dicom_bench.workbench.contract import validation_contract_errors

        catalog = load_catalog(CATALOG_V6)
        report = self.validation(catalog, "core-2026c", "wsi-dicom-core-profile-2026c-v4")
        report["checks"] = [
            check for check in report["checks"] if check["name"] != "intrinsic-wsi-dicom-2026c-file-meta"
        ]
        errors = validation_contract_errors(report, catalog, True)
        self.assertTrue(any("missing required checks: intrinsic-wsi-dicom-2026c-file-meta" in e for e in errors))

    def test_workbench_rejects_a_core_profile_with_the_pre_profile_catalog(self):
        from wsi_dicom_bench.workbench.cli import WorkbenchError, parse_args, run_workbench

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dicom = root / "one.dcm"
            dicom.write_bytes(b"placeholder")
            binary = root / "binary"
            binary.write_bytes(b"placeholder")
            args = parse_args([
                str(dicom), "--output", str(root / "out"), "--wsi-dicom", str(binary),
                "--catalog", str(CATALOG_V2), "--profile", str(PROFILE_V4),
            ])
            with self.assertRaisesRegex(WorkbenchError, "profile version"):
                run_workbench(args)

    def test_workbench_pairs_no_profile_with_the_pre_profile_catalog(self):
        from wsi_dicom_bench.workbench.catalog import load_catalog
        from wsi_dicom_bench.workbench.cli import expected_profile_id

        # The contract names a core rule set for catalog v2, but v2 predates core profiles.
        self.assertIsNone(expected_profile_id(load_catalog(CATALOG_V2)))
        self.assertEqual(expected_profile_id(load_catalog(CATALOG_V6)), load(PROFILE_V4)["profile_id"])

    def test_packaged_suite_directory_resolves_to_the_v6_manifest(self):
        import importlib.resources

        from wsi_dicom_bench.challenge import _suite_manifest

        packaged = Path(str(importlib.resources.files("wsi_dicom_bench.negative_bench")))
        self.assertEqual(_suite_manifest(packaged), (packaged / "manifest-v6.json").resolve())


class CatalogAndProfileV6Tests(unittest.TestCase):
    def test_catalog_v6_has_one_rule_per_iod_and_requirement_check(self):
        from wsi_dicom_bench.workbench.catalog import load_catalog

        catalog = load_catalog(CATALOG_V6)
        self.assertEqual(catalog["catalog_version"], "wsi-dicom-bench-rules-2026c-v6")
        rules = {rule["rule_id"]: rule for rule in catalog["rules"]}
        intrinsic = intrinsic_rule_ids(catalog["rules"])
        self.assertEqual(len(intrinsic), 32)
        self.assertTrue(IOD_RULES | V6_RULES <= intrinsic)
        self.assertFalse(IOD_RULES & V6_RULES)
        for rule_id in IOD_RULES:
            rule = rules[rule_id]
            with self.subTest(rule=rule_id):
                self.assertEqual(rule["check_names"], [rule_id])
                self.assertEqual(rule["rule_kind"], "intrinsic")
                self.assertEqual(rule["primary_domain"], "conformance")
                for citation in rule["citations"]:
                    self.assertTrue(citation["url"].startswith("https://dicom.nema.org/medical/dicom/2026c/"))
        for rule_id in V6_RULES:
            rule = rules[rule_id]
            with self.subTest(rule=rule_id):
                self.assertEqual(rule["check_names"], [rule_id])
                # A rule over the evaluated set of Instances is an intrinsic set rule.
                self.assertEqual(rule["rule_kind"], "intrinsic_set" if rule_id.endswith("-set") else "intrinsic")
                for citation in rule["citations"]:
                    self.assertTrue(citation["url"].startswith("https://dicom.nema.org/medical/dicom/"))
        self.assertIn("Not covered", catalog["coverage_scope"])

    def test_per_frame_item_count_belongs_to_sequence_items_in_v6(self):
        rules = {rule["rule_id"]: rule for rule in load(CATALOG_V6)["rules"]}
        self.assertNotIn("one Item per Frame", rules[full_rule_id("iod-modules")]["summary"])
        self.assertIn("one Per-Frame Functional Groups Item per Frame", rules[full_rule_id("iod-sequence-items")]["summary"])

    def test_profile_v4_covers_every_intrinsic_rule(self):
        from wsi_dicom_bench.core_profile import load_profile, validate_profile_coverage

        v4 = load_profile(PROFILE_V4)
        self.assertEqual((v4["profile_id"], v4["profile_version"]), ("wsi-dicom-core-profile-2026c-v4", "4"))
        rows = {row["requirement_id"]: row for row in v4["requirements"]}
        # The Per-Frame Item count is enforced by iod-sequence-items, which catalog v6 assigns it to.
        self.assertEqual(rows["CP-IOD-FG-002"]["enforcement"]["rule_ids"], [full_rule_id("iod-sequence-items")])
        added = v4["requirements"][-len(requirement_cases.PROFILE_ROWS):]
        self.assertEqual([row["requirement_id"] for row in added], [row[0] for row in requirement_cases.PROFILE_ROWS])
        self.assertEqual({rule for row in added for rule in row["enforcement"]["rule_ids"]}, V6_RULES)
        mapped = {rule for row in v4["requirements"] for rule in row["enforcement"]["rule_ids"]}
        self.assertTrue(IOD_RULES <= mapped)
        for retained in ("TILED_SPARSE and other sparse-pyramid behaviors", "LABEL, OVERVIEW, and THUMBNAIL image flavors",
                         "multiple optical paths or focal planes", "concatenations",
                         "Context Group (CID) and Defined Term constraints"):
            self.assertIn(retained, v4["excluded_capabilities"])
        summary = validate_profile_coverage(v4, load(CATALOG_V6), load(MANIFEST_V6))
        self.assertEqual(summary["requirement_count"], 71)
        self.assertEqual(summary["intrinsic_rule_count"], 32)
        self.assertEqual(summary["intrinsic_rules_without_negative_cases"], [])


class ManifestV6IntegrityTests(unittest.TestCase):
    def setUp(self):
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
            "schema": {**baseline, "schema_version": "wsi-dicom-negative-bench-expected-results-lock-v3"},
            "challenge": {**baseline, "challenge_id": "wsi-dicom-negative-bench-v3"},
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
            other_profile = Path(temporary) / PROFILE_V4.name
            other_profile.write_text(json.dumps({**load(PROFILE_V4), "title": "another profile"}), encoding="utf-8")
            with self.subTest(defect="other profile"), self.assertRaises(GenerationError):
                _verify_expected_results_lock(LOCK_V6, MANIFEST_V6, PROTOCOL_V6, CATALOG_V6, other_profile)

    def test_manifest_v6_identity_points_at_v6_artifacts(self):
        self.assertEqual(self.v6["schema_version"], "wsi-dicom-negative-bench-manifest-v6")
        self.assertEqual(self.v6["rule_catalog"]["catalog_version"], self.catalog["catalog_version"])
        self.assertEqual(set(self.v6["rule_catalog"]["required_new_rule_ids"]), V6_RULES)
        self.assertEqual(self.v6["core_profile"]["profile_id"], load(PROFILE_V4)["profile_id"])
        self.assertEqual((self.v6["protocol"], self.v6["expected_results_lock"]), (PROTOCOL_V6.name, LOCK_V6.name))
        self.assertIs(self.v6["expectation_provenance"]["blinded"], False)
        self.assertRegex(self.v6["expectation_provenance"]["candidate"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertIn("not blinded", PROTOCOL_V6.read_text(encoding="utf-8").replace("\n", " "))

    def test_controls_match_their_files_and_cases_reference_them(self):
        controls = {control["control_id"]: control for control in self.v6["valid_controls"]}
        self.assertEqual(len(controls), 14)
        for control_id, control in controls.items():
            digests = control["sha256"] if isinstance(control["sha256"], list) else [control["sha256"]]
            sizes = control["size_bytes"] if isinstance(control["size_bytes"], list) else [control["size_bytes"]]
            paths = control_path(control)
            directory = CONTROLS_V6 if control_id in ICT_CONTROLS else CONTROLS_V4
            with self.subTest(control=control_id):
                self.assertEqual([sha256_file(path) for path in paths], digests)
                self.assertEqual([path.stat().st_size for path in paths], sizes)
                self.assertTrue(all(directory in path.parents for path in paths))
                self.assertEqual("YBR_ICT" in control.get("correction", ""), control_id in ICT_CONTROLS)
        for case in self.v6["evaluation_cases"]:
            (source,) = case["source_control_ids"]
            with self.subTest(case=case["case_id"]):
                self.assertEqual(case["source_control_sha256"], controls[source]["sha256"])

    def test_carried_cases_keep_their_authored_mutations(self):
        self.assertEqual(len(self.v6["development_cases"]), 10)
        carried = [case for case in self.v6["evaluation_cases"] if case["cohort"] != COHORT]
        self.assertEqual(Counter(case["cohort"] for case in carried), {CORE_COHORT: 69, STRUCTURE_COHORT: 80})
        encoded = json.dumps([{field: case[field] for field in MUTATION_FIELDS} for case in carried], sort_keys=True)
        self.assertEqual(hashlib.sha256(encoded.encode()).hexdigest(), CARRIED_MUTATIONS_SHA256)
        self.assertEqual(len({case["deterministic_seed"] for case in self.v6["evaluation_cases"]}), 352)

    def test_requirement_rule_adjudications_agree_with_the_expected_rules(self):
        counts = Counter()
        for case in self.v6["evaluation_cases"]:
            adjudications = case.get("requirement_rule_adjudications", [])
            by_disposition = dispositions(case)
            counts.update(item["disposition"] for item in adjudications)
            with self.subTest(case=case["case_id"]):
                if adjudications:
                    self.assertNotEqual(case["cohort"], COHORT)
                self.assertTrue(set(by_disposition) <= {"expected_failing_rule", "adjudicated_cascade", "superseded_expected_rule"})
                self.assertFalse(by_disposition.get("superseded_expected_rule", set()) & set(case["expected_failing_rules"]))
                self.assertTrue(by_disposition.get("expected_failing_rule", set()) <= set(case["expected_failing_rules"]))
                self.assertTrue(by_disposition.get("adjudicated_cascade", set()) <= set(case.get("adjudicated_cascade_rules", [])))
                for item in adjudications:
                    self.assertTrue(item["rationale"])
                    if item["disposition"] == "superseded_expected_rule":
                        self.assertIn(item["replacement_rule_id"], by_disposition["expected_failing_rule"])
                    else:
                        self.assertTrue(item["observed"])
                        self.assertTrue(item["citation"]["url"].startswith("https://dicom.nema.org/medical/dicom/2026c/"))
        self.assertEqual(counts, {"expected_failing_rule": 15, "adjudicated_cascade": 4, "superseded_expected_rule": 3})

    def test_structure_cases_apply_their_adjudications_to_the_authored_rules(self):
        cases = {case["case_id"]: case for case in cohort(self.v6, STRUCTURE_COHORT)}
        self.assertEqual(set(cases), {spec["case_id"] for spec in iod_amendment_cases.STRUCTURE_CASES})
        for spec in iod_amendment_cases.STRUCTURE_CASES:
            case = cases[spec["case_id"]]
            by_disposition = dispositions(case)
            authored = {full_rule_id(rule) for rule in spec["expected"]}
            with self.subTest(case=spec["case_id"]):
                self.assertEqual(case.get("requirement_rule_adjudications", []), spec.get("adjudications", []))
                self.assertEqual(
                    set(case["expected_failing_rules"]),
                    authored - by_disposition.get("superseded_expected_rule", set())
                    | by_disposition.get("expected_failing_rule", set()),
                )

    def test_iod_rule_adjudications_of_core_profile_cases_agree_with_the_expected_rules(self):
        counts = Counter()
        for case in cohort(self.v6, CORE_COHORT):
            superseded = dispositions(case).get("superseded_expected_rule", set())
            iod = dispositions(case, "iod_rule_adjudications")
            counts.update(item["disposition"] for item in case["iod_rule_adjudications"])
            with self.subTest(case=case["case_id"]):
                self.assertTrue(set(iod) <= {"expected_failing_rule", "adjudicated_cascade"})
                self.assertTrue(set().union(*iod.values()) <= IOD_RULES)
                self.assertTrue(iod.get("expected_failing_rule", set()) - superseded <= set(case["expected_failing_rules"]))
                self.assertTrue(iod.get("adjudicated_cascade", set()) <= set(case.get("adjudicated_cascade_rules", [])))
                for item in case["iod_rule_adjudications"]:
                    self.assertTrue(item["observed"] and item["rationale"])
                    self.assertTrue(item["citation"]["url"].startswith("https://dicom.nema.org/medical/dicom/2026c/"))
        self.assertEqual(counts, {"expected_failing_rule": 35, "adjudicated_cascade": 5})

    def test_expected_unaffected_rules_exclude_every_expected_and_cascade_rule(self):
        intrinsic = intrinsic_rule_ids(self.catalog["rules"])
        for case in self.v6["evaluation_cases"]:
            failing = set(case["expected_failing_rules"]) | set(case.get("adjudicated_cascade_rules", []))
            with self.subTest(case=case["case_id"]):
                self.assertTrue(failing <= intrinsic)
                self.assertEqual(set(case["expected_unaffected_rules"]), intrinsic - failing)

    def test_structure_cohort_targets_every_iod_family_with_single_file_cases(self):
        from wsi_dicom_bench.negative_bench.mutations import ALL_MUTATIONS

        controls = {control["control_id"]: control for control in self.v6["valid_controls"]}
        structure = cohort(self.v6, STRUCTURE_COHORT)
        self.assertEqual(len(structure), 80)
        families = Counter(case["target_rule_family"] for case in structure)
        self.assertEqual(set(families), IOD_RULES)
        self.assertTrue(all(count >= 8 for count in families.values()), families)
        for case in structure:
            superseded = dispositions(case).get("superseded_expected_rule", set())
            with self.subTest(case=case["case_id"]):
                # The authored target is expected unless a requirement-statement rule supersedes it.
                self.assertIn(case["target_rule_family"], set(case["expected_failing_rules"]) | superseded)
                self.assertNotIn("adjudicated_cascade_rules", case)
                self.assertEqual(case["domain"], "conformance")
                self.assertIn(case["mutation_name"], ALL_MUTATIONS)
                control = controls[case["source_control_ids"][0]]
                self.assertNotIn("package_paths", control)
                self.assertEqual(case["source_control_sha256"], control["sha256"])
                self.assertTrue(case["exact_attributes_or_bytes_changed"])
                self.assertTrue(case["dicom_citation"]["url"].startswith("https://dicom.nema.org/medical/dicom/2026c/"))

    def test_structure_cohort_reaches_top_level_nested_and_functional_group_targets(self):
        locations = Counter()
        for case in cohort(self.v6, STRUCTURE_COHORT):
            parameters = case["mutation_parameters"]
            paths = parameters.get("paths") or [parameters.get("path")]
            for path in paths:
                if path is None:
                    location = "file-meta"
                elif len(path) == 1:
                    location = "top-level"
                elif path[0] in {"SharedFunctionalGroupsSequence", "PerFrameFunctionalGroupsSequence"}:
                    location = "functional-group"
                else:
                    location = "nested"
                locations[(case["target_rule_family"], location)] += 1
        for family in IOD_RULES - {"intrinsic-wsi-dicom-2026c-file-meta"}:
            with self.subTest(family=family):
                self.assertTrue(locations[(family, "functional-group")])
                self.assertTrue(locations[(family, "top-level")] + locations[(family, "nested")])

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

    def test_every_mutation_is_used_by_the_suite(self):
        from wsi_dicom_bench.negative_bench.mutations import ALL_MUTATIONS

        used = {case["mutation_name"] for case in self.v6["evaluation_cases"]}
        self.assertEqual(set(ALL_MUTATIONS) - used, {"invalid_specimen_uid", "total_matrix_too_large"})

    def test_mutation_registries_cover_the_carried_cohorts_without_unused_handlers(self):
        from wsi_dicom_bench.negative_bench.mutations import (
            ALL_MUTATIONS,
            MUTATION_REGISTRY,
            codestream,
            encoding,
            relations,
            structure,
        )

        used = {case["mutation_name"] for case in self.v6["evaluation_cases"] if case["cohort"] != COHORT}
        requirement = {*relations.HANDLERS, *codestream.HANDLERS, *encoding.HANDLERS}
        # Beyond the core-profile inventory, every mutation of the carried cohorts is a structure
        # mutation, and no structure name shadows a core-profile one.
        self.assertEqual(set(ALL_MUTATIONS) - set(MUTATION_REGISTRY) - requirement, set(structure.HANDLERS))
        self.assertEqual(set(ALL_MUTATIONS) - used - requirement, {"invalid_specimen_uid", "total_matrix_too_large"})


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
        (source,) = control_path(control)
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

    def test_wrong_source_class_pair_lists_its_reference_with_the_true_class(self):
        case = next(case for case in load(MANIFEST_V6)["evaluation_cases"] if case["case_id"] == "NB-ID-006")
        derived, source = (pydicom.dcmread(path, stop_before_pixels=True) for path in self.generate("NB-ID-006"))
        cited = derived.SourceImageSequence[0]
        self.assertEqual(str(cited.ReferencedSOPClassUID), case["mutation_parameters"]["referenced_sop_class_uid"])
        self.assertEqual(cited.ReferencedSOPInstanceUID, source.SOPInstanceUID)
        # The Common Instance Reference listing is correct, so the wrong class is the only defect.
        (series,) = derived.ReferencedSeriesSequence
        (listed,) = series.ReferencedInstanceSequence
        self.assertEqual(series.SeriesInstanceUID, source.SeriesInstanceUID)
        self.assertEqual(
            (listed.ReferencedSOPClassUID, listed.ReferencedSOPInstanceUID),
            (source.SOPClassUID, source.SOPInstanceUID),
        )

    def test_re_encapsulated_pixel_data_ends_with_one_sequence_delimiter(self):
        delimiter = b"\xfe\xff\xdd\xe0\x00\x00\x00\x00"
        for case_id in ("REQ-CS-001", "REQ-CS-009", "REQ-CS-014"):
            (path,) = self.generate(case_id)
            data = path.read_bytes()
            with self.subTest(case=case_id):
                self.assertTrue(data.endswith(delimiter))
                self.assertFalse(data[: -len(delimiter)].endswith(delimiter))


class StructureMutationTests(unittest.TestCase):
    CONTROL = CONTROLS_V4 / "CP02-JPEG-16F.dcm"

    def generate(self, root: Path, name: str, parameters: dict) -> tuple[Path, list[dict]]:
        from wsi_dicom_bench.negative_bench.mutations import generate_case

        output = root / name
        output.mkdir()
        case = {"mutation_name": name, "mutation_parameters": parameters, "deterministic_seed": f"test:{name}"}
        paths, changes = generate_case(case, self.CONTROL, output)
        self.assertEqual(len(paths), 1)
        return paths[0], changes

    def test_paths_fail_closed_on_unknown_keywords_indices_and_shapes(self):
        from wsi_dicom_bench.negative_bench.model import GenerationError

        for path in (["NotADicomKeyword"], ["OpticalPathSequence", 5, "OpticalPathIdentifier"],
                     ["OpticalPathSequence", 0], [], ["Manufacturer", 0, "Manufacturer"]):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(GenerationError):
                    self.generate(Path(temporary), "iod_delete_attribute", {"path": path})

    def test_vr_change_keeps_the_exact_decimal_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            path, changes = self.generate(
                Path(temporary), "iod_change_vr",
                {"path": ["SharedFunctionalGroupsSequence", 0, "PixelMeasuresSequence", 0, "SliceThickness"], "vr": "LO"},
            )
            element = pydicom.dcmread(path).SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0]["SliceThickness"]
        self.assertEqual((element.VR, element.value), ("LO", "0.001"))
        self.assertEqual((changes[-1]["vr_before"], changes[-1]["vr_after"]), ("DS", "LO"))

    def test_shared_identifier_is_replaced_at_every_reference_or_not_at_all(self):
        from wsi_dicom_bench.negative_bench.model import GenerationError

        references = [["DimensionOrganizationSequence", 0, "DimensionOrganizationUID"],
                      ["DimensionIndexSequence", 0, "DimensionOrganizationUID"],
                      ["DimensionIndexSequence", 1, "DimensionOrganizationUID"]]
        with tempfile.TemporaryDirectory() as temporary:
            path, changes = self.generate(Path(temporary), "iod_set_value", {"paths": references, "value": "2.25.0123"})
            dataset = pydicom.dcmread(path)
            values = {str(dataset.DimensionOrganizationSequence[0].DimensionOrganizationUID),
                      *(str(item.DimensionOrganizationUID) for item in dataset.DimensionIndexSequence)}
            self.assertEqual(values, {"2.25.0123"})
            self.assertEqual(len([change for change in changes if change["kind"] == "defect"]), 3)
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(GenerationError, "shared Value"):
            self.generate(Path(temporary), "iod_set_value",
                          {"paths": [references[0], ["StudyInstanceUID"]], "value": "2.25.1"})

    def test_file_meta_patches_rewrite_a_consistent_group(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            removed, removal = self.generate(root, "file_meta_remove_element", {"tag": "(0002,0012)"})
            replaced, replacement = self.generate(root, "file_meta_replace_value", {"tag": "(0002,0013)", "value": "ODD-LENGTH"})
            for path, absent in ((removed, "ImplementationClassUID"), (replaced, None)):
                contents = path.read_bytes()
                group_length = struct.unpack_from("<I", contents, 140)[0]
                meta = pydicom.dcmread(path, stop_before_pixels=True).file_meta
                self.assertEqual(contents[128:132], b"DICM")
                # The rewritten Group Length ends exactly where the Data Set (group 0008) begins.
                self.assertEqual(struct.unpack_from("<H", contents, 144 + group_length)[0], 0x0008)
                self.assertEqual(int(meta.FileMetaInformationGroupLength), group_length)
                if absent:
                    self.assertNotIn(absent, meta)
            self.assertEqual(str(pydicom.dcmread(replaced, stop_before_pixels=True).file_meta.ImplementationVersionName), "ODD-LENGTH")
            self.assertEqual(removal[-1]["kind"], "raw_byte_patch")
            self.assertTrue(any(change.get("operation") == "replace_file_meta_value" for change in replacement))


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
            manifest = load(MANIFEST_V6)
            for case in cohort(manifest):
                report = load(first / "cases" / case["case_id"] / "generation.json")
                with self.subTest(case=case["case_id"]):
                    self.assertEqual(report["mutation_name"], case["mutation_name"])
                    self.assertGreater(len(report["changes"]), 1)
            for case in cohort(manifest, STRUCTURE_COHORT):
                report = load(first / "cases" / case["case_id"] / "generation.json")
                with self.subTest(case=case["case_id"]):
                    self.assertTrue(any(change["kind"] in {"defect", "raw_byte_patch"} for change in report["changes"]))
                    self.assertEqual(report["mutation_name"], case["mutation_name"])


if __name__ == "__main__":
    unittest.main()
