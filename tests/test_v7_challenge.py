import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class V7ChallengeRunTests(unittest.TestCase):
    def test_input_report_digest_file_binds_exact_ids_and_contents(self):
        from wsi_dicom_bench.negative_bench.model import GenerationError
        from wsi_dicom_bench.negative_bench.v7_challenge import (
            _verify_input_report_sums,
            _write_input_report_sums,
        )

        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            reports = package / "observed-results" / "inputs"
            reports.mkdir(parents=True)
            report = reports / "ONE.json"
            report.write_text('{"id":"ONE"}\n')
            run = {"input_report_sums": _write_input_report_sums(package, reports)}
            _verify_input_report_sums(package, run, {"ONE"})

            report.write_text('{"id":"CHANGED"}\n')
            with self.assertRaisesRegex(GenerationError, "digest differs"):
                _verify_input_report_sums(package, run, {"ONE"})

    def test_public_check_maps_malformed_v7_evidence_to_infrastructure_error(self):
        from wsi_dicom_bench.challenge import (
            ChallengeInfrastructureError,
            check_acceptance,
        )
        from wsi_dicom_bench.negative_bench.model import GenerationError

        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary)
            (evidence / "manifest.json").write_text(json.dumps({
                "schema_version": "wsi-dicom-negative-bench-manifest-v7",
            }))
            with patch(
                "wsi_dicom_bench.challenge._require_distribution_payload"
            ), patch(
                "wsi_dicom_bench.negative_bench.v7_challenge.check_v7_acceptance",
                side_effect=GenerationError("broken retained evidence"),
            ), self.assertRaisesRegex(
                ChallengeInfrastructureError, "broken retained evidence"
            ):
                check_acceptance(evidence)

    def test_locked_run_summary_keeps_its_schema_over_diagnostic_schema(self):
        from wsi_dicom_bench.negative_bench.v7_challenge import run_v7_challenge

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "package"
            (package / "observed-results").mkdir(parents=True)
            (package / "manifest.json").write_text(json.dumps({
                "schema_version": "wsi-dicom-negative-bench-manifest-v7",
                "challenge_id": "example-v7",
            }))
            candidate = root / "wsi-dicom"
            candidate.write_bytes(b"candidate")
            diagnostic = {
                "schema_version": "wsi-dicom-v7-draft-diagnostic-v1",
                "challenge_id": "example-v7",
                "status": "passed",
                "counts": {},
                "contracts": {},
                "failures": [],
            }

            def run_diagnostic(_manifest, _candidate, output, **_kwargs):
                output.write_text(json.dumps(diagnostic))
                return diagnostic

            with patch(
                "wsi_dicom_bench.negative_bench.v7_challenge.run_diagnostic",
                side_effect=run_diagnostic,
            ), patch(
                "wsi_dicom_bench.negative_bench.v7_challenge.run_file_evaluation",
                return_value={
                    "schema_version": "wsi-dicom-negative-bench-v7-file-evaluation-v1",
                    "status": "complete",
                    "execution_count": 769,
                },
            ):
                result = run_v7_challenge(package, candidate)

        self.assertEqual(
            result["schema_version"],
            "wsi-dicom-negative-bench-v7-run-summary-v1",
        )
        self.assertEqual(result["challenge_id"], "example-v7")
        self.assertEqual(
            result["candidate_sha256_before"], result["candidate_sha256_after"]
        )
        self.assertEqual(
            result["file_evaluation"],
            "observed-results/file-evaluation/summary.json",
        )
        self.assertEqual(
            result["input_report_sums"]["path"],
            "observed-results/input-report-SHA256SUMS",
        )
        self.assertEqual(len(result["diagnostic_sha256"]), 64)

    def test_acceptance_requires_the_offline_file_evaluation(self):
        from wsi_dicom_bench.negative_bench.v7_challenge import check_v7_acceptance

        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            inputs = package / "observed-results" / "inputs"
            inputs.mkdir(parents=True)
            manifest = {
                "schema_version": "wsi-dicom-negative-bench-manifest-v7",
                "challenge_id": "example-v7",
                "valid_controls": [],
                "evaluation_cases": [],
                "core_profile_evaluation_cases": [],
                "advisory_cases": [],
                "json_evaluation_cases": [{
                    "case_id": "JSON",
                    "expected_failing_rules": [],
                }],
                "http_evaluation_cases": [],
                "candidate_gap_cases": [],
                "freeze_gate": {"known_policy_failure": False},
            }
            (package / "manifest.json").write_text(json.dumps(manifest))
            (inputs / "JSON.json").write_text(json.dumps({
                "id": "JSON",
                "cohort": "json",
                "report": {
                    "schema_version": "wsi-dicom-json-validation-report-v1",
                    "dicom_edition": "2026d",
                    "rule_set_id": "wsi-dicom-general-v4",
                    "checks": [],
                    "optional": [],
                },
            }))
            digest = "a" * 64
            run = {
                "schema_version": "wsi-dicom-negative-bench-v7-run-summary-v1",
                "challenge_id": "example-v7",
                "status": "passed",
                "counts": {
                    "valid_controls": 0,
                    "general_cases": 0,
                    "core_cases": 0,
                    "advisory_cases": 0,
                    "json_cases": 1,
                    "http_cases": 0,
                    "candidate_gap_cases": 0,
                    "failures": 0,
                },
                "contracts": {
                    "general": [["2026d", "wsi-dicom-general-v4"]],
                    "core": [["2026d", "wsi-dicom-core-profile-v5"]],
                    "json": [["2026d", "wsi-dicom-general-v4"]],
                    "http": [["2026d", "wsi-dicom-dicomweb-report-v1"]],
                },
                "failures": [],
                "candidate_sha256_before": digest,
                "candidate_sha256_after": digest,
                "file_evaluation": "observed-results/file-evaluation/summary.json",
            }
            (package / "observed-results" / "run-summary.json").write_text(
                json.dumps(run)
            )

            with patch(
                "wsi_dicom_bench.negative_bench.v7_challenge._verify_generation_sums"
            ), patch(
                "wsi_dicom_bench.negative_bench.v7_challenge._verify_packaged_lock"
            ), patch(
                "wsi_dicom_bench.negative_bench.v7_challenge._verify_input_report_sums"
            ), patch(
                "wsi_dicom_bench.negative_bench.v7_challenge._verify_diagnostic"
            ), patch(
                "wsi_dicom_bench.negative_bench.v7_challenge.validate_file_evaluation"
            ) as validate:
                result = check_v7_acceptance(package)

        self.assertEqual(result["checked_evaluation"], "passed")
        validate.assert_called_once_with(
            package.resolve(),
            package.resolve() / "observed-results" / "file-evaluation",
            digest,
        )

    def test_completed_candidate_mismatch_is_policy_failure_bound_to_report(self):
        from wsi_dicom_bench.negative_bench.model import GenerationError
        from wsi_dicom_bench.negative_bench.v7_challenge import check_v7_acceptance

        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            inputs = package / "observed-results" / "inputs"
            inputs.mkdir(parents=True)
            manifest = {
                "schema_version": "wsi-dicom-negative-bench-manifest-v7",
                "challenge_id": "example-v7",
                "valid_controls": [{"control_id": "CONTROL"}],
                "evaluation_cases": [],
                "core_profile_evaluation_cases": [],
                "advisory_cases": [],
                "json_evaluation_cases": [],
                "http_evaluation_cases": [],
                "candidate_gap_cases": [],
                "freeze_gate": {"known_policy_failure": False},
            }
            (package / "manifest.json").write_text(json.dumps(manifest))
            report = {
                "schema_version": "wsi-dicom-validation-report-v1",
                "dicom_edition": "2026d",
                "rule_set_id": "wsi-dicom-general-v4",
                "checks": [{
                    "name": "intrinsic-unexpected",
                    "status": "failed",
                }],
            }
            (inputs / "CONTROL.json").write_text(json.dumps({
                "id": "CONTROL",
                "cohort": "valid-control",
                "report": report,
            }))
            digest = "b" * 64
            failure = {
                "id": "CONTROL",
                "profile": "general-control",
                "unexpected_rules": ["intrinsic-unexpected"],
            }
            run = {
                "schema_version": "wsi-dicom-negative-bench-v7-run-summary-v1",
                "challenge_id": "example-v7",
                "status": "failed",
                "counts": {
                    "valid_controls": 1,
                    "general_cases": 0,
                    "core_cases": 0,
                    "advisory_cases": 0,
                    "json_cases": 0,
                    "http_cases": 0,
                    "candidate_gap_cases": 0,
                    "failures": 1,
                },
                "contracts": {
                    "general": [["2026d", "wsi-dicom-general-v4"]],
                    "core": [["2026d", "wsi-dicom-core-profile-v5"]],
                    "json": [["2026d", "wsi-dicom-general-v4"]],
                    "http": [["2026d", "wsi-dicom-dicomweb-report-v1"]],
                },
                "failures": [failure],
                "candidate_sha256_before": digest,
                "candidate_sha256_after": digest,
                "file_evaluation": "observed-results/file-evaluation/summary.json",
            }
            summary_path = package / "observed-results" / "run-summary.json"
            summary_path.write_text(json.dumps(run))

            with patch(
                "wsi_dicom_bench.negative_bench.v7_challenge._verify_generation_sums"
            ), patch(
                "wsi_dicom_bench.negative_bench.v7_challenge._verify_packaged_lock"
            ), patch(
                "wsi_dicom_bench.negative_bench.v7_challenge._verify_input_report_sums"
            ), patch(
                "wsi_dicom_bench.negative_bench.v7_challenge._verify_diagnostic"
            ), patch(
                "wsi_dicom_bench.negative_bench.v7_challenge.validate_file_evaluation"
            ):
                result = check_v7_acceptance(package)
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["checked_evaluation"], "failed")
                self.assertEqual(result["checked_failures"], [failure])

                run["failures"] = []
                summary_path.write_text(json.dumps(run))
                with self.assertRaisesRegex(GenerationError, "incomplete or failed"):
                    check_v7_acceptance(package)

                run["failures"] = [failure]
                summary_path.write_text(json.dumps(run))
                report["checks"] = [None]
                (inputs / "CONTROL.json").write_text(json.dumps({
                    "id": "CONTROL",
                    "cohort": "valid-control",
                    "report": report,
                }))
                with self.assertRaisesRegex(GenerationError, "validation checks"):
                    check_v7_acceptance(package)


if __name__ == "__main__":
    unittest.main()
