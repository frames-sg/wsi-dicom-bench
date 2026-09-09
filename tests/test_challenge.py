from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock


BASELINE = Path(os.environ["WSI_DICOM_BENCH_EVIDENCE_ROOT"]) if os.environ.get(
    "WSI_DICOM_BENCH_EVIDENCE_ROOT"
) else None


class AcceptanceTests(unittest.TestCase):
    def test_completed_baseline_satisfies_read_only_acceptance(self):
        from wsi_dicom_bench.challenge import check_acceptance

        if BASELINE is None or not (BASELINE / "SHA256SUMS").is_file():
            self.skipTest("set WSI_DICOM_BENCH_EVIDENCE_ROOT to completed evidence")
        before = (BASELINE / "SHA256SUMS").read_bytes()
        result = check_acceptance(BASELINE)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["gate"]["controls_passing"], 14)
        self.assertEqual(result["gate"]["negative_cases_detected_and_localized"], 69)
        self.assertEqual((BASELINE / "SHA256SUMS").read_bytes(), before)

    def test_evidence_mutations_map_policy_to_one_and_infrastructure_to_two(self):
        from wsi_dicom_bench.challenge import main

        if BASELINE is None or not (BASELINE / "SHA256SUMS").is_file():
            self.skipTest("set WSI_DICOM_BENCH_EVIDENCE_ROOT to completed evidence")
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            shutil.copytree(BASELINE, evidence)
            (evidence / "SHA256SUMS").unlink()
            manifest = json.loads((evidence / "manifest.json").read_text())
            case = manifest["evaluation_cases"][0]
            report_path = (
                evidence
                / "observed-results"
                / case["case_id"]
                / "workbench"
                / "workbench-report.json"
            )
            original = report_path.read_bytes()
            report = json.loads(original)
            expected = set(case["expected_failing_rules"])
            finding = next(
                item
                for item in report["findings"]
                if item.get("rule_id") in expected and item.get("status") == "failed"
            )
            finding["status"] = "passed"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(
                main(["challenge", "check", "--evidence", str(evidence)]), 1
            )

            report_path.write_bytes(original)
            report = json.loads(original)
            report["findings"] = [
                item
                for item in report["findings"]
                if item.get("check_name") != "dciodvfy"
            ]
            report_path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(
                main(["challenge", "check", "--evidence", str(evidence)]), 2
            )

            report_path.write_text("{", encoding="utf-8")
            self.assertEqual(
                main(["challenge", "check", "--evidence", str(evidence)]), 2
            )

            report_path.write_bytes(original)
            report = json.loads(original)
            report["profile"]["id"] = "unknown-profile"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(
                main(["challenge", "check", "--evidence", str(evidence)]), 2
            )

    def test_policy_disagreement_is_distinct_from_infrastructure_failure(self):
        from wsi_dicom_bench.challenge import (
            ChallengeInfrastructureError,
            ChallengePolicyError,
            check_acceptance,
        )
        from wsi_dicom_bench.core_profile import CoreProfileError

        preflight = ({"challenge_id": "challenge"}, {"profile_id": "profile"}, {})
        with mock.patch(
            "wsi_dicom_bench.challenge._preflight_evidence", return_value=preflight
        ), mock.patch(
            "wsi_dicom_bench.challenge.validate_evidence_coverage",
            side_effect=CoreProfileError("case N was not localized to every expected rule"),
        ):
            with self.assertRaisesRegex(ChallengePolicyError, "not localized"):
                check_acceptance(Path("evidence"))

        with mock.patch(
            "wsi_dicom_bench.challenge._preflight_evidence",
            side_effect=ChallengeInfrastructureError("run summary is incompatible"),
        ):
            with self.assertRaisesRegex(ChallengeInfrastructureError, "incompatible"):
                check_acceptance(Path("evidence"))

    def test_final_seal_verification_rejects_tampering_and_symlinks(self):
        from wsi_dicom_bench.challenge import (
            ChallengeInfrastructureError,
            _verify_final_seal,
        )
        from wsi_dicom_bench.file_digest import sha256_file

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = root / "payload.json"
            payload.write_text("{}\n", encoding="utf-8")
            (root / "SHA256SUMS").write_text(
                f"{sha256_file(payload)}  payload.json\n", encoding="utf-8"
            )
            _verify_final_seal(root)
            payload.write_text('{"changed":true}\n', encoding="utf-8")
            with self.assertRaisesRegex(ChallengeInfrastructureError, "mismatch"):
                _verify_final_seal(root)

            payload.write_text("{}\n", encoding="utf-8")
            link = root / "linked.json"
            try:
                link.symlink_to(payload)
            except OSError:
                self.skipTest("symlinks are unavailable")
            with self.assertRaisesRegex(ChallengeInfrastructureError, "symlink"):
                _verify_final_seal(root)


class CommandTests(unittest.TestCase):
    def test_main_uses_documented_exit_codes_and_reports_reasons(self):
        from wsi_dicom_bench.challenge import (
            ChallengeInfrastructureError,
            ChallengePolicyError,
            main,
        )

        cases = (
            (ChallengePolicyError("locked expectation missed"), 1, "acceptance failed"),
            (ChallengeInfrastructureError("invalid JSON"), 2, "execution failed"),
        )
        for error, expected_code, message in cases:
            with self.subTest(code=expected_code), mock.patch(
                "wsi_dicom_bench.challenge.check_acceptance", side_effect=error
            ):
                stderr = StringIO()
                with redirect_stderr(stderr):
                    code = main(["challenge", "check", "--evidence", "evidence"])
                self.assertEqual(code, expected_code)
                self.assertIn(message, stderr.getvalue())
                self.assertIn(str(error), stderr.getvalue())

        with mock.patch(
            "wsi_dicom_bench.challenge.check_acceptance",
            return_value={"status": "passed"},
        ):
            stdout = StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    main(["challenge", "check", "--evidence", "evidence"]), 0
                )
            self.assertEqual(json.loads(stdout.getvalue()), {"status": "passed"})

    def test_run_requires_explicit_executable_and_protects_existing_output(self):
        from wsi_dicom_bench.challenge import ChallengeInfrastructureError, run

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "manifest.json"
            manifest.write_text("{}\n", encoding="utf-8")
            candidate = root / "wsi-dicom"
            candidate.write_text("#!/bin/sh\n", encoding="utf-8")
            candidate.chmod(candidate.stat().st_mode | 0o100)
            output = root / "evidence"
            output.mkdir()
            args = Namespace(suite=manifest, wsi_dicom=candidate, output=output)
            with self.assertRaisesRegex(ChallengeInfrastructureError, "already exists"):
                run(args)

            output.rmdir()
            candidate.chmod(0o600)
            with self.assertRaisesRegex(ChallengeInfrastructureError, "not executable"):
                run(args)

    def test_suite_directory_resolution_is_unambiguous(self):
        from wsi_dicom_bench.challenge import (
            ChallengeInfrastructureError,
            _suite_manifest,
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            versioned = root / "manifest-v4.json"
            versioned.write_text("{}\n", encoding="utf-8")
            self.assertEqual(_suite_manifest(root), versioned.resolve())
            (root / "manifest.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ChallengeInfrastructureError, "exactly one"):
                _suite_manifest(root)


class ConverterContractTests(unittest.TestCase):
    def test_versioned_contract_requires_exact_schema_and_rule_set(self):
        from wsi_dicom_bench.workbench.contract import (
            doctor_contract_errors,
            validation_contract_errors,
        )

        doctor = {"schema_version": "future-doctor", "tools": []}
        self.assertIn("unsupported doctor schema_version", doctor_contract_errors(doctor)[0])
        validation = {
            "schema_version": "wsi-dicom-validation-report-v1",
            "rule_set_id": "wrong",
            "profile": "general",
            "files": ["slide.dcm"],
            "checks": [],
        }
        errors = validation_contract_errors(validation, {"rules": []}, core=False)
        self.assertTrue(any("selected rule set" in error for error in errors))
        self.assertTrue(doctor_contract_errors({"schema_version": None, "tools": []}))

    def test_exact_unversioned_contract_remains_explicitly_compatible(self):
        from wsi_dicom_bench.workbench.contract import (
            doctor_contract_errors,
            validation_contract_errors,
        )

        self.assertEqual(doctor_contract_errors({"tools": []}), [])
        legacy = {"profile": "general", "files": ["slide.dcm"], "checks": []}
        self.assertEqual(
            validation_contract_errors(legacy, {"rules": []}, core=False), []
        )
        legacy["rule_set_id"] = "wsi-dicom-general-v1"
        self.assertTrue(validation_contract_errors(legacy, {"rules": []}, core=False))


if __name__ == "__main__":
    unittest.main()
