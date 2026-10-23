"""Integrity of the v5 IOD amendment and its separation from the frozen v4 artifacts."""

import hashlib
import json
import struct
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import pydicom


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "src" / "wsi_dicom_bench"
BENCH = PACKAGE_ROOT / "negative_bench"
RULES = PACKAGE_ROOT / "rules"
MANIFEST_V4 = BENCH / "manifest-v4.json"
MANIFEST_V5 = BENCH / "manifest-v5.json"
LOCK_V4 = BENCH / "expected-results-lock-v4.json"
LOCK_V5 = BENCH / "expected-results-lock-v5.json"
PROTOCOL_V5 = BENCH / "protocol-v5.md"
CATALOG_V4 = RULES / "wsi-dicom-bench-rules-2026c-v4.json"
CATALOG_V5 = RULES / "wsi-dicom-bench-rules-2026c-v5.json"
PROFILE_V2 = RULES / "wsi-dicom-core-profile-2026c-v2.json"
PROFILE_V3 = RULES / "wsi-dicom-core-profile-2026c-v3.json"
IOD_RULES = {
    f"intrinsic-wsi-dicom-2026c-{name}"
    for name in (
        "iod-modules",
        "iod-attribute-presence",
        "iod-enumerated-values",
        "iod-vr-vm",
        "iod-value-format",
        "iod-sequence-items",
        "file-meta",
    )
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def intrinsic_rules(catalog: dict) -> set[str]:
    return {rule["rule_id"] for rule in catalog["rules"] if rule["rule_kind"] != "independent_validator"}


class FrozenV4ArtifactTests(unittest.TestCase):
    def test_v4_lock_still_binds_the_unchanged_v4_artifacts(self):
        lock = load(LOCK_V4)
        sources = {
            "bench/negative_bench/protocol-v4.md": BENCH / "protocol-v4.md",
            "bench/negative_bench/manifest-v4.json": MANIFEST_V4,
            "rules/wsi-dicom-bench-rules-2026c-v4.json": CATALOG_V4,
            "rules/wsi-dicom-core-profile-2026c-v2.json": PROFILE_V2,
        }
        self.assertEqual({item["path"] for item in lock["files"]}, set(sources))
        for item in lock["files"]:
            with self.subTest(path=item["path"]):
                self.assertEqual(sha256_file(sources[item["path"]]), item["sha256"])

    def test_v4_controls_still_match_their_manifest_digests(self):
        for control in load(MANIFEST_V4)["valid_controls"]:
            paths = control.get("original_paths", [control.get("original_path")])
            digests = control["sha256"] if isinstance(control["sha256"], list) else [control["sha256"]]
            for path, digest in zip(paths, digests, strict=True):
                source = BENCH / Path(path).relative_to("bench/negative_bench")
                with self.subTest(path=path):
                    self.assertEqual(sha256_file(source), digest)

    def test_v4_catalog_and_contract_remain_selectable(self):
        from wsi_dicom_bench.workbench.catalog import load_catalog
        from wsi_dicom_bench.workbench.cli import CATALOG_PROFILES
        from wsi_dicom_bench.workbench.contract import expected_rule_set_id

        catalog = load_catalog(CATALOG_V4)
        self.assertEqual(CATALOG_PROFILES[catalog["catalog_version"]], load(PROFILE_V2)["profile_id"])
        self.assertEqual(expected_rule_set_id(catalog, "core-2026c"), "wsi-dicom-core-profile-2026c-v2")
        self.assertEqual(expected_rule_set_id(catalog, "general"), "wsi-dicom-general-v1")
        self.assertFalse(IOD_RULES & {rule["rule_id"] for rule in catalog["rules"]})


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

    def test_each_catalog_accepts_only_its_own_rule_sets(self):
        from wsi_dicom_bench.workbench.catalog import load_catalog
        from wsi_dicom_bench.workbench.contract import validation_contract_errors

        pairs = {
            CATALOG_V4: {"core-2026c": "wsi-dicom-core-profile-2026c-v2", "general": "wsi-dicom-general-v1"},
            CATALOG_V5: {"core-2026c": "wsi-dicom-core-profile-2026c-v3", "general": "wsi-dicom-general-v2"},
        }
        for path, accepted in pairs.items():
            catalog = load_catalog(path)
            other = pairs[CATALOG_V5 if path == CATALOG_V4 else CATALOG_V4]
            for profile, rule_set_id in accepted.items():
                core = profile == "core-2026c"
                with self.subTest(catalog=path.name, profile=profile):
                    self.assertEqual(
                        validation_contract_errors(self.validation(catalog, profile, rule_set_id), catalog, core),
                        [],
                    )
                    errors = validation_contract_errors(
                        self.validation(catalog, profile, other[profile]), catalog, core
                    )
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

    def test_v4_catalog_reports_new_iod_checks_as_unmapped(self):
        from wsi_dicom_bench.workbench.catalog import load_catalog
        from wsi_dicom_bench.workbench.contract import validation_contract_errors

        catalog = load_catalog(CATALOG_V4)
        report = self.validation(catalog, "core-2026c", "wsi-dicom-core-profile-2026c-v2")
        report["checks"].append(
            {"name": "intrinsic-wsi-dicom-2026c-file-meta", "path": "one.dcm", "status": "passed"}
        )
        errors = validation_contract_errors(report, catalog, True)
        self.assertIn("binary emitted an unmapped check: intrinsic-wsi-dicom-2026c-file-meta", errors)

    def test_v5_catalog_requires_every_iod_check_on_every_instance(self):
        from wsi_dicom_bench.workbench.catalog import load_catalog
        from wsi_dicom_bench.workbench.contract import validation_contract_errors

        catalog = load_catalog(CATALOG_V5)
        report = self.validation(catalog, "core-2026c", "wsi-dicom-core-profile-2026c-v3")
        report["checks"] = [
            check for check in report["checks"] if check["name"] != "intrinsic-wsi-dicom-2026c-file-meta"
        ]
        errors = validation_contract_errors(report, catalog, True)
        self.assertTrue(any("missing required checks: intrinsic-wsi-dicom-2026c-file-meta" in e for e in errors))

    def test_workbench_pairs_catalog_v5_with_profile_v3_only(self):
        from wsi_dicom_bench.workbench.cli import WorkbenchError, parse_args, run_workbench

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dicom = root / "one.dcm"
            dicom.write_bytes(b"placeholder")
            binary = root / "binary"
            binary.write_bytes(b"placeholder")
            for catalog, profile in ((CATALOG_V5, PROFILE_V2), (CATALOG_V4, PROFILE_V3)):
                args = parse_args([
                    str(dicom), "--output", str(root / "out"), "--wsi-dicom", str(binary),
                    "--catalog", str(catalog), "--profile", str(profile),
                ])
                with self.subTest(catalog=catalog.name), self.assertRaisesRegex(WorkbenchError, "profile version"):
                    run_workbench(args)

    def test_suite_directory_with_one_versioned_v5_manifest_resolves(self):
        from wsi_dicom_bench.challenge import ChallengeInfrastructureError, _suite_manifest

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "manifest-v5.json").write_text("{}\n", encoding="utf-8")
            self.assertEqual(_suite_manifest(root), (root / "manifest-v5.json").resolve())
            (root / "manifest-v4.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ChallengeInfrastructureError, "exactly one"):
                _suite_manifest(root)


class CatalogAndProfileV5Tests(unittest.TestCase):
    def test_catalog_v5_is_catalog_v4_plus_one_rule_per_iod_check(self):
        from wsi_dicom_bench.workbench.catalog import load_catalog

        v4 = load_catalog(CATALOG_V4)
        v5 = load_catalog(CATALOG_V5)
        self.assertEqual(v5["catalog_version"], "wsi-dicom-bench-rules-2026c-v5")
        old = {rule["rule_id"]: rule for rule in v4["rules"]}
        new = {rule["rule_id"]: rule for rule in v5["rules"]}
        self.assertEqual(set(new) - set(old), IOD_RULES)
        for rule_id, rule in old.items():
            self.assertEqual(new[rule_id], rule)
        for rule_id in IOD_RULES:
            rule = new[rule_id]
            with self.subTest(rule=rule_id):
                self.assertEqual(rule["check_names"], [rule_id])
                self.assertEqual(rule["rule_kind"], "intrinsic")
                self.assertEqual(rule["primary_domain"], "conformance")
                for citation in rule["citations"]:
                    self.assertTrue(citation["url"].startswith("https://dicom.nema.org/medical/dicom/2026c/"))
        self.assertIn("Not covered", v5["coverage_scope"])
        self.assertIn("Context Group (CID)", v5["coverage_scope"])

    def test_profile_v3_extends_v2_and_covers_every_iod_rule(self):
        from wsi_dicom_bench.core_profile import load_profile, validate_profile_coverage

        v2 = load_profile(PROFILE_V2)
        v3 = load_profile(PROFILE_V3)
        self.assertEqual((v3["profile_id"], v3["profile_version"]), ("wsi-dicom-core-profile-2026c-v3", "3"))
        self.assertEqual(v3["requirements"][: len(v2["requirements"])], v2["requirements"])
        added = v3["requirements"][len(v2["requirements"]):]
        self.assertEqual({rule for row in added for rule in row["enforcement"]["rule_ids"]} & IOD_RULES, IOD_RULES)
        removed = set(v2["excluded_capabilities"]) - set(v3["excluded_capabilities"])
        self.assertEqual(removed, {"concatenations and exhaustive normative attribute/condition coverage"})
        for retained in ("TILED_SPARSE and other sparse-pyramid behaviors", "LABEL, OVERVIEW, and THUMBNAIL image flavors",
                         "multiple optical paths or focal planes", "concatenations",
                         "Context Group (CID) and Defined Term constraints"):
            self.assertIn(retained, v3["excluded_capabilities"])
        summary = validate_profile_coverage(v3, load(CATALOG_V5), load(MANIFEST_V5))
        self.assertEqual(summary["intrinsic_rule_count"], 25)
        self.assertEqual(summary["intrinsic_rules_without_negative_cases"], [])


class ManifestV5IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.v4 = load(MANIFEST_V4)
        self.v5 = load(MANIFEST_V5)
        self.catalog = load(CATALOG_V5)

    def test_committed_manifest_and_lock_match_the_builder(self):
        from wsi_dicom_bench.negative_bench.build_iod_structure_manifest import (
            build_lock,
            build_manifest,
            main,
        )

        self.assertEqual(build_manifest(), self.v5)
        self.assertEqual(build_lock(), load(LOCK_V5))
        self.assertEqual(main([]), 0)

    def test_lock_v5_binds_protocol_manifest_catalog_and_profile(self):
        from wsi_dicom_bench.negative_bench.generate import GenerationError, _verify_expected_results_lock

        _verify_expected_results_lock(LOCK_V5, MANIFEST_V5, PROTOCOL_V5, CATALOG_V5, PROFILE_V3)
        baseline = load(LOCK_V5)
        self.assertEqual(
            baseline["expected_counts"],
            {"development_cases": 10, "evaluation_cases": 149, "valid_controls": 14, "compound_cases": 0},
        )
        broken = {
            "schema": {**baseline, "schema_version": "wsi-dicom-negative-bench-expected-results-lock-v4"},
            "challenge": {**baseline, "challenge_id": "wsi-dicom-negative-bench-v3"},
            "counts": {**baseline, "expected_counts": {**baseline["expected_counts"], "evaluation_cases": 69}},
            "digest": {**baseline, "files": [{**baseline["files"][0], "sha256": "0" * 64}, *baseline["files"][1:]]},
            "profile": {**baseline, "core_profile": {**baseline["core_profile"], "version": "2"}},
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "expected-results-lock-v5.json"
            for name, document in broken.items():
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.subTest(defect=name), self.assertRaises(GenerationError):
                    _verify_expected_results_lock(path, MANIFEST_V5, PROTOCOL_V5, CATALOG_V5, PROFILE_V3)
            with self.subTest(defect="v4 profile"), self.assertRaises(GenerationError):
                _verify_expected_results_lock(LOCK_V5, MANIFEST_V5, PROTOCOL_V5, CATALOG_V5, PROFILE_V2)

    def test_manifest_v5_identity_points_at_v5_artifacts(self):
        self.assertEqual(self.v5["schema_version"], "wsi-dicom-negative-bench-manifest-v5")
        self.assertEqual(self.v5["rule_catalog"]["catalog_version"], self.catalog["catalog_version"])
        self.assertEqual(set(self.v5["rule_catalog"]["required_new_rule_ids"]), IOD_RULES)
        self.assertEqual(self.v5["core_profile"]["profile_id"], load(PROFILE_V3)["profile_id"])
        self.assertEqual(self.v5["protocol"], PROTOCOL_V5.name)
        self.assertEqual(self.v5["expected_results_lock"], LOCK_V5.name)
        self.assertIs(self.v5["expectation_provenance"]["blinded"], False)
        self.assertIn("not blinded", PROTOCOL_V5.read_text(encoding="utf-8").replace("\n", " "))

    def test_every_v4_entry_is_carried_forward_with_the_same_mutation(self):
        self.assertEqual(self.v5["valid_controls"], self.v4["valid_controls"])
        self.assertEqual(self.v5["development_cases"], self.v4["development_cases"])
        carried = {case["case_id"]: case for case in self.v5["evaluation_cases"]}
        fields = ("mutation_name", "mutation_parameters", "deterministic_seed", "source_control_ids",
                  "source_control_sha256", "domain", "cohort", "exact_attributes_or_bytes_changed")
        for old in self.v4["evaluation_cases"]:
            new = carried[old["case_id"]]
            with self.subTest(case=old["case_id"]):
                self.assertEqual({field: new[field] for field in fields}, {field: old[field] for field in fields})
                self.assertEqual(new["expected_failing_rules"][: len(old["expected_failing_rules"])], old["expected_failing_rules"])
                self.assertTrue(set(old.get("adjudicated_cascade_rules", [])) <= set(new.get("adjudicated_cascade_rules", [])))
                added = set(new["expected_failing_rules"]) - set(old["expected_failing_rules"])
                cascades = set(new.get("adjudicated_cascade_rules", [])) - set(old.get("adjudicated_cascade_rules", []))
                self.assertTrue((added | cascades) <= IOD_RULES)
                adjudicated = {
                    (item["rule_id"], item["disposition"]) for item in new["iod_rule_adjudications"]
                }
                self.assertEqual(
                    adjudicated,
                    {(rule, "expected_failing_rule") for rule in added}
                    | {(rule, "adjudicated_cascade") for rule in cascades},
                )
                for item in new["iod_rule_adjudications"]:
                    self.assertTrue(item["observed"] and item["rationale"])
                    self.assertTrue(item["citation"]["url"].startswith("https://dicom.nema.org/medical/dicom/2026c/"))

    def test_expected_unaffected_rules_exclude_every_expected_and_cascade_rule(self):
        intrinsic = intrinsic_rules(self.catalog)
        for case in self.v5["evaluation_cases"]:
            failing = set(case["expected_failing_rules"]) | set(case.get("adjudicated_cascade_rules", []))
            with self.subTest(case=case["case_id"]):
                self.assertTrue(failing <= intrinsic)
                self.assertEqual(set(case["expected_unaffected_rules"]), intrinsic - failing)

    def test_structure_cohort_targets_every_iod_family_with_single_file_cases(self):
        from wsi_dicom_bench.negative_bench.mutations import ALL_MUTATIONS

        controls = {control["control_id"]: control for control in self.v5["valid_controls"]}
        structure = [case for case in self.v5["evaluation_cases"] if case["cohort"] == "iod-structure-evaluation-v1"]
        self.assertEqual(len(structure), 80)
        self.assertEqual(len(self.v5["evaluation_cases"]), 149)
        families = Counter(case["target_rule_family"] for case in structure)
        self.assertEqual(set(families), IOD_RULES)
        self.assertTrue(all(count >= 8 for count in families.values()), families)
        for case in structure:
            with self.subTest(case=case["case_id"]):
                self.assertIn(case["target_rule_family"], case["expected_failing_rules"])
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
        for case in self.v5["evaluation_cases"]:
            if case["cohort"] != "iod-structure-evaluation-v1":
                continue
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

    def test_mutation_registries_cover_v4_and_v5_without_new_unused_handlers(self):
        from wsi_dicom_bench.negative_bench.mutations import (
            ALL_MUTATIONS,
            MUTATION_REGISTRY,
            STRUCTURE_MUTATION_REGISTRY,
        )

        used = {case["mutation_name"] for manifest in (self.v4, self.v5) for case in manifest["evaluation_cases"]}
        self.assertEqual(set(ALL_MUTATIONS), set(MUTATION_REGISTRY) | set(STRUCTURE_MUTATION_REGISTRY))
        self.assertFalse(set(MUTATION_REGISTRY) & set(STRUCTURE_MUTATION_REGISTRY))
        self.assertEqual(set(ALL_MUTATIONS) - used, {"invalid_specimen_uid", "total_matrix_too_large"})


class StructureMutationTests(unittest.TestCase):
    CONTROL = BENCH / "controls-v4" / "CP02-JPEG-16F.dcm"

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

    def test_complete_v5_generation_is_deterministic(self):
        from wsi_dicom_bench.negative_bench.finalize import _verify_generation_sums
        from wsi_dicom_bench.negative_bench.generate import generate_challenge

        with tempfile.TemporaryDirectory() as temporary:
            first, second = Path(temporary) / "first", Path(temporary) / "second"
            generate_challenge(MANIFEST_V5, first)
            generate_challenge(MANIFEST_V5, second)
            _verify_generation_sums(first)
            self.assertEqual(len(list((first / "cases").iterdir())), 149)
            self.assertEqual(len(list((first / "controls").rglob("*.dcm"))), 15)
            self.assertEqual(
                [sha256_file(path) for path in sorted(first.rglob("*.dcm"))],
                [sha256_file(path) for path in sorted(second.rglob("*.dcm"))],
            )
            for case in load(MANIFEST_V5)["evaluation_cases"]:
                if case["cohort"] != "iod-structure-evaluation-v1":
                    continue
                report = load(first / "cases" / case["case_id"] / "generation.json")
                with self.subTest(case=case["case_id"]):
                    self.assertTrue(any(change["kind"] in {"defect", "raw_byte_patch"} for change in report["changes"]))
                    self.assertEqual(report["mutation_name"], case["mutation_name"])


if __name__ == "__main__":
    unittest.main()
