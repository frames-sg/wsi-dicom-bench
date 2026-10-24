import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wsi_dicom_bench.file_digest import sha256_file
from wsi_dicom_bench.negative_bench import v7_file_evaluation as file_eval


ROOT = Path(__file__).resolve().parents[1]
V7_CATALOG = ROOT / "src/wsi_dicom_bench/rules/wsi-dicom-bench-rules-v7.json"


class V7FileEvaluationTests(unittest.TestCase):
    def test_core_catalog_is_exactly_the_two_rule_extension(self):
        from wsi_dicom_bench.workbench.contract import validation_contract_errors

        base = json.loads(V7_CATALOG.read_text())
        derived = file_eval.derive_core_catalog(base)
        self.assertEqual(derived["catalog_version"], file_eval.CORE_CATALOG_VERSION)
        self.assertEqual(derived["candidate_rule_set_id"], "wsi-dicom-core-profile-v5")
        self.assertEqual(len(derived["rules"]), len(base["rules"]) - 6 + 4)
        self.assertEqual(
            {rule["rule_id"] for rule in derived["rules"]} -
            {rule["rule_id"] for rule in base["rules"]},
            set(file_eval.CORE_RULES.values()),
        )
        self.assertEqual(
            {rule["rule_id"] for rule in base["rules"]} -
            {rule["rule_id"] for rule in derived["rules"]},
            set(derived["core_derivation"]["removed_rule_ids"]),
        )
        self.assertEqual(
            len(derived["core_derivation"]["supplemental_rules"]), 4
        )
        checks = []
        for rule in derived["rules"]:
            if rule["rule_kind"] == "intrinsic":
                checks.extend({"name": name, "path": "one.dcm", "status": "passed"}
                              for name in rule["check_names"])
        report = {
            "schema_version": "wsi-dicom-validation-report-v1",
            "rule_set_id": "wsi-dicom-core-profile-v5",
            "profile": "core",
            "files": ["one.dcm"],
            "checks": checks,
        }
        self.assertEqual(
            validation_contract_errors(
                report, derived, False, validation_profile="core"
            ),
            [],
        )

    def test_validation_profile_selection_preserves_legacy_profile_files(self):
        from wsi_dicom_bench.workbench.cli import build_validation_command, parse_args

        base = ["slide", "--output", "evidence", "--wsi-dicom", "wsi-dicom"]
        general = build_validation_command(parse_args(base))
        self.assertEqual(general[general.index("--profile") + 1], "general")
        core = build_validation_command(parse_args([*base, "--validation-profile", "core"]))
        self.assertEqual(core[core.index("--profile") + 1], "core")
        legacy = build_validation_command(parse_args([*base, "--profile", "profile.json"]))
        self.assertEqual(legacy[legacy.index("--profile") + 1], "core-2026c")

    def test_adapter_retains_all_769_profiles_and_validates_their_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "challenge"
            (package / "expected-results").mkdir(parents=True)
            (package / "validator-results").mkdir()
            (package / "observed-results").mkdir()
            shutil.copyfile(V7_CATALOG, package / "expected-results" / V7_CATALOG.name)
            manifest = {
                "schema_version": file_eval.MANIFEST_SCHEMA,
                "challenge_id": "wsi-dicom-negative-bench-v7",
                "rule_catalog": {"path": "rules/" + V7_CATALOG.name},
                "resource_limits": {
                    "max_command_output_bytes": 1024,
                    "max_pixel_frames": 1,
                    "command_timeout_secs": 1,
                    "case_timeout_secs": 2,
                },
                "tool_limits": {"known": "independent tool limit"},
                "valid_controls": [
                    {"control_id": f"CONTROL-{index:03d}", "package_paths": ["unused"]}
                    for index in range(66)
                ],
                "evaluation_cases": [
                    {"case_id": f"GENERAL-{index:03d}"} for index in range(697)
                ],
                "core_profile_evaluation_cases": [
                    {"case_id": f"CORE-{index:03d}"} for index in range(3)
                ],
                "advisory_cases": [
                    {"case_id": f"ADVISORY-{index:03d}"} for index in range(3)
                ],
            }
            (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            candidate = package / "wsi-dicom"
            candidate.write_text("#!/bin/sh\n", encoding="utf-8")
            candidate.chmod(0o700)
            candidate_digest = sha256_file(candidate)
            standard = package / "dicom-standard"
            standard.mkdir()

            validator_runtime = {
                "packages": {
                    "dicom-validator": {"version": "0.8.3"},
                    "pydicom": {"version": "3.0.2"},
                },
                "definitions": {
                    "edition": "2026d",
                    "standard_path": str(standard),
                    "files": [
                        {"path": f"2026d/json/{name}", "sha256": "a" * 64}
                        for name in (
                            "dict_info.json", "iod_info.json", "module_info.json",
                            "uid_info.json", "version",
                        )
                    ],
                },
            }

            def run_one(package_arg, candidate_arg, catalog, _profile_path, _limits,
                        identifier, cohort, dicom, validation_profile="general",
                        dicom_validator_standard_path=None):
                report_path = (package_arg / "observed-results" / identifier / "workbench" /
                               "workbench-report.json")
                report_path.parent.mkdir(parents=True)
                raw = package_arg / "validator-results" / identifier
                raw.mkdir()
                stdout = raw / "launcher.stdout.json"
                stderr = raw / "launcher.stderr.txt"
                stdout.write_text("{}\n", encoding="utf-8")
                stderr.write_text("", encoding="utf-8")
                report = {
                    "schema_version": "wsi-dicom-bench-workbench-report-v2",
                    "contract_errors": [],
                    "status": "passed",
                    "catalog": {"sha256": sha256_file(catalog)},
                    "evaluation_policy": {"validation_profile": validation_profile},
                    "software": {
                        "wsi_dicom": {"sha256": candidate_digest},
                        "bench_decoders": [],
                        "validators_and_decoders": [
                            {"name": "dciodvfy", "runtime": None},
                            {"name": "dcentvfy", "runtime": None},
                            {"name": "validate_iods", "runtime": validator_runtime},
                        ],
                    },
                    "doctor": {"tools": [
                        {"name": name, "status": "available", "required": True}
                        for name in ("dciodvfy", "dcentvfy", "validate_iods")
                    ]},
                    "validator_comparison": {"external": {"dciodvfy": "passed"}},
                    "limitations": {"unavailable_tools": []},
                }
                report_path.write_text(json.dumps(report), encoding="utf-8")
                return {
                    "id": identifier,
                    "cohort": cohort,
                    "input": str(dicom.relative_to(package_arg)),
                    "command": ["workbench"],
                    "returncode": 0,
                    "timed_out": False,
                    "runtime_seconds": 0.0,
                    "workbench_report": str(report_path.relative_to(package_arg)),
                    "launcher_stdout": str(stdout.relative_to(package_arg)),
                    "launcher_stderr": str(stderr.relative_to(package_arg)),
                }

            reports = package / "observed-results" / "file-evaluation"
            with mock.patch.object(file_eval, "_run_one_input", side_effect=run_one) as runner:
                summary = file_eval.run_file_evaluation(
                    package, candidate, reports, standard
                )
            self.assertEqual(runner.call_count, 769)
            self.assertEqual(summary["execution_count"], 769)
            self.assertEqual(summary["cohorts"]["valid-control"]["count"], 66)
            self.assertEqual(summary["cohorts"]["general-file"]["count"], 697)
            self.assertEqual(summary["cohorts"]["core-file"]["count"], 3)
            self.assertEqual(summary["cohorts"]["advisory-file"]["count"], 3)
            file_eval.validate_file_evaluation(package, reports, candidate_digest)

            changed = reports / "inputs" / "CORE-000.json"
            document = json.loads(changed.read_text())
            document["validation_profile"] = "general"
            changed.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(file_eval.FileEvaluationError, "report differs"):
                file_eval.validate_file_evaluation(package, reports, candidate_digest)


if __name__ == "__main__":
    unittest.main()
