"""Generate, execute and evaluate the locked v7 multi-cohort challenge."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from wsi_dicom_bench.file_digest import sha256_file

from . import jpip_statement_cases, json_statement_cases
from .draft_diagnostic import (
    DiagnosticError,
    _case_failure,
    _intrinsic_failed,
    run_diagnostic,
)
from .finalize import FinalizationError, _verify_generation_sums
from .freeze_v7 import LOCK, PROTOCOL
from .generate import (
    _copy_packaged_runtime,
    _materialize_cases,
    _materialize_controls,
    _write_generation_sums,
)
from .model import GenerationError
from .v7_file_evaluation import (
    FileEvaluationError,
    run_file_evaluation,
    validate_file_evaluation,
)


SCHEMA = "wsi-dicom-negative-bench-manifest-v7"
JSON_BUILDERS = {
    "json_statement_cases.build_document": json_statement_cases.build_document,
    "jpip_statement_cases.build_document": jpip_statement_cases.build_document,
}


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise GenerationError(f"v7 challenge JSON must be an object: {path}")
    return value


def verify_v7_lock(manifest_path: Path) -> None:
    manifest = _read(manifest_path)
    lock_path = manifest_path.with_name(manifest["expected_results_lock"])
    lock = _read(lock_path)
    if (
        manifest.get("schema_version") != SCHEMA
        or lock.get("schema_version")
        != "wsi-dicom-negative-bench-expected-results-lock-v7"
        or lock.get("challenge_id") != manifest.get("challenge_id")
    ):
        raise GenerationError("v7 manifest and expected-results lock are incompatible")
    package = manifest_path.parent
    rules = package.parent / "rules"
    actual_paths = {
        f"bench/negative_bench/{PROTOCOL.name}": package / PROTOCOL.name,
        f"bench/negative_bench/{manifest_path.name}": manifest_path,
        f"rules/{Path(manifest['rule_catalog']['path']).name}":
            rules / Path(manifest["rule_catalog"]["path"]).name,
        f"rules/{Path(manifest['requirement_catalog']['path']).name}":
            rules / Path(manifest["requirement_catalog"]["path"]).name,
        f"bench/negative_bench/{Path(manifest['statement_coverage']['path']).name}":
            package / Path(manifest["statement_coverage"]["path"]).name,
    }
    expected = {item["path"]: item["sha256"] for item in lock.get("files", [])}
    actual = {name: sha256_file(path) for name, path in actual_paths.items()}
    if expected != actual:
        raise GenerationError("v7 expected-results lock differs from its artifacts")


def _verify_packaged_lock(package: Path, manifest: dict) -> None:
    expected_dir = package / "expected-results"
    lock = _read(expected_dir / manifest["expected_results_lock"])
    sources = {
        f"bench/negative_bench/{Path(manifest['protocol']).name}": package / "protocol.md",
        "bench/negative_bench/manifest-v7.json": package / "manifest.json",
        manifest["rule_catalog"]["path"]:
            expected_dir / Path(manifest["rule_catalog"]["path"]).name,
        manifest["requirement_catalog"]["path"]:
            expected_dir / Path(manifest["requirement_catalog"]["path"]).name,
        f"bench/negative_bench/{Path(manifest['statement_coverage']['path']).name}":
            expected_dir / Path(manifest["statement_coverage"]["path"]).name,
    }
    expected = {item["path"]: item["sha256"] for item in lock.get("files", [])}
    actual = {name: sha256_file(path) for name, path in sources.items()}
    if expected != actual or lock.get("known_policy_failure") != manifest.get("freeze_gate"):
        raise GenerationError("packaged v7 expected-results lock differs")


def _write_input_report_sums(package: Path, reports_dir: Path) -> dict:
    destination = package / "observed-results" / "input-report-SHA256SUMS"
    paths = sorted(path for path in reports_dir.glob("*.json") if path.is_file())
    lines = [f"{sha256_file(path)}  inputs/{path.name}" for path in paths]
    destination.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return {
        "path": str(destination.relative_to(package)),
        "sha256": sha256_file(destination),
    }


def _verify_input_report_sums(package: Path, run: dict, expected_ids: set[str]) -> None:
    identity = run.get("input_report_sums")
    if not isinstance(identity, dict) or identity.get("path") != (
        "observed-results/input-report-SHA256SUMS"
    ):
        raise GenerationError("v7 input-report digest identity is missing")
    sums = package / identity["path"]
    if (
        not sums.is_file()
        or not isinstance(identity.get("sha256"), str)
        or sha256_file(sums) != identity["sha256"]
    ):
        raise GenerationError("v7 input-report digest file differs")
    entries = {}
    ordered = []
    for line in sums.read_text(encoding="utf-8").splitlines():
        if len(line) < 67 or line[64:66] != "  ":
            raise GenerationError("v7 input-report digest entry is invalid")
        digest, relative = line[:64], line[66:]
        if (
            any(character not in "0123456789abcdef" for character in digest)
            or not relative.startswith("inputs/")
            or not relative.endswith(".json")
            or "/" in relative[len("inputs/"):]
            or relative in entries
        ):
            raise GenerationError("v7 input-report digest entry is unsafe or duplicated")
        entries[relative] = digest
        ordered.append(relative)
    if ordered != sorted(ordered):
        raise GenerationError("v7 input-report digest paths are not sorted")
    expected_paths = {f"inputs/{identifier}.json" for identifier in expected_ids}
    if set(entries) != expected_paths:
        raise GenerationError("v7 input-report digest IDs differ from the frozen manifest")
    for relative, digest in entries.items():
        path = package / "observed-results" / relative
        if path.is_symlink() or not path.is_file() or sha256_file(path) != digest:
            raise GenerationError(f"v7 input-report digest differs: {relative}")


def _verify_diagnostic(
    package: Path,
    run: dict,
    expected_counts: dict,
    expected_contracts: dict,
    checked_failures: list[dict],
) -> None:
    relative = run.get("diagnostic")
    expected_relative = "observed-results/v7-diagnostic.json"
    if relative != expected_relative:
        raise GenerationError("v7 diagnostic path differs")
    path = package / expected_relative
    digest = run.get("diagnostic_sha256")
    if (
        path.is_symlink()
        or not path.is_file()
        or not isinstance(digest, str)
        or sha256_file(path) != digest
    ):
        raise GenerationError("v7 diagnostic digest differs")
    diagnostic = _read(path)
    if (
        diagnostic.get("schema_version") != "wsi-dicom-v7-draft-diagnostic-v1"
        or diagnostic.get("challenge_id") != run.get("challenge_id")
        or diagnostic.get("status") != ("passed" if not checked_failures else "failed")
        or diagnostic.get("counts") != expected_counts
        or diagnostic.get("contracts") != expected_contracts
        or diagnostic.get("failures") != checked_failures
    ):
        raise GenerationError("v7 diagnostic differs from retained input reports")


def _http_case_failure(case: dict, observed: dict) -> dict | None:
    expected = set(case["expected_failing_checks"])
    expected_advisory = set(case.get("expected_advisory_checks", []))
    cascades = set(case.get("adjudicated_cascade_checks", []))
    failed = set(observed["failed_checks"])
    advisory_fragment = case.get("expected_advisory_contains")
    baseline_advisories = observed.get("baseline_advisories", [])
    target_advisory = bool(observed["observed_advisories"]) and (
        advisory_fragment is None
        or (
            any(advisory_fragment in message for message in observed["observed_advisories"])
            and not any(advisory_fragment in message for message in baseline_advisories)
        )
    )
    localized = (
        observed["observed_status"] == "passed" and target_advisory
        if expected_advisory else observed["observed_status"] == "failed"
    )
    if (
        observed["baseline_status"] == "passed"
        and not observed["baseline_failed_checks"]
        and localized
        and failed == expected | cascades
    ):
        return None
    return {
        "id": case["case_id"],
        "profile": "http",
        "missing_expected_checks": sorted(expected - failed),
        "missing_cascade_checks": sorted(cascades - failed),
        "unexpected_checks": sorted(failed - expected - cascades),
    }


def _validate_candidate_report_shape(identifier: str, report: dict) -> None:
    checks = report.get("checks")
    if not isinstance(checks, list) or any(
        not isinstance(check, dict)
        or not isinstance(check.get("name"), str)
        or check.get("status") not in {"passed", "failed", "skipped"}
        for check in checks
    ):
        raise GenerationError(f"invalid retained validation checks: {identifier}")
    optional = report.get("optional", [])
    if not isinstance(optional, list) or any(
        not isinstance(item, dict)
        or not isinstance(item.get("advisories", []), list)
        or any(not isinstance(message, str) for message in item.get("advisories", []))
        for item in optional
    ):
        raise GenerationError(f"invalid retained validation advisories: {identifier}")


def _recompute_checked_failures(manifest: dict, records: dict[str, dict]) -> list[dict]:
    failures = []
    for control in manifest["valid_controls"]:
        identifier = control["control_id"]
        observed = _intrinsic_failed(records[identifier]["report"])
        if observed:
            failures.append({
                "id": identifier,
                "profile": "general-control",
                "unexpected_rules": sorted(observed),
            })
    for field, profile in (
        ("evaluation_cases", "general"),
        ("core_profile_evaluation_cases", "core"),
        ("advisory_cases", "general"),
        ("json_evaluation_cases", "json"),
    ):
        for case in manifest.get(field, []):
            report = records[case["case_id"]]["report"]
            failure = _case_failure(case, report, _intrinsic_failed(report), profile)
            if failure is not None:
                failures.append(failure)
    for case in manifest.get("http_evaluation_cases", []):
        failure = _http_case_failure(case, records[case["case_id"]]["report"])
        if failure is not None:
            failures.append(failure)
    candidate_gaps = manifest.get("candidate_gap_cases", [])
    if candidate_gaps:
        failures.append({
            "id": "candidate-gap-cases",
            "cases": sorted(case["case_id"] for case in candidate_gaps),
        })
    return sorted(failures, key=lambda item: item["id"])


def generate_v7_challenge(manifest_path: Path, output: Path) -> None:
    manifest_path = manifest_path.resolve()
    output = output.resolve()
    if output.exists():
        raise GenerationError(f"output path already exists: {output}")
    verify_v7_lock(manifest_path)
    manifest = _read(manifest_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{output.name}.staging-", dir=output.parent) as td:
        staging = Path(td)
        for relative in (
            "controls", "cases", "expected-results", "observed-results",
            "validator-results", "generator", "analysis",
        ):
            (staging / relative).mkdir(parents=True, exist_ok=True)
        controls = _materialize_controls(
            manifest_path, manifest, staging / "controls",
            int(manifest["resource_limits"]["max_file_bytes"]),
        )
        file_cases = [
            *manifest["evaluation_cases"],
            *manifest.get("core_profile_evaluation_cases", []),
            *manifest.get("advisory_cases", []),
        ]
        _materialize_cases(
            {**manifest, "evaluation_cases": file_cases}, controls, staging / "cases",
            int(manifest["resource_limits"]["max_file_bytes"]),
        )
        for case in manifest.get("json_evaluation_cases", []):
            builder = JSON_BUILDERS.get(case.get("document_builder"))
            if builder is None:
                raise GenerationError(f"unsupported JSON builder: {case.get('document_builder')}")
            source = controls[case["source_control_ids"][0]][0]
            destination = staging / "cases" / case["case_id"] / "input" / "document.json"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(builder(case["case_id"], source))
        shutil.copyfile(manifest_path, staging / "manifest.json")
        shutil.copyfile(PROTOCOL, staging / "protocol.md")
        for reference in (
            manifest["rule_catalog"]["path"], manifest["requirement_catalog"]["path"],
            manifest["statement_coverage"]["path"], manifest["expected_results_lock"],
        ):
            name = Path(reference).name
            source = (
                manifest_path.parent.parent / "rules" / name
                if reference.startswith("rules/") else manifest_path.parent / name
            )
            shutil.copyfile(source, staging / "expected-results" / name)
        _copy_packaged_runtime(manifest_path, staging)
        _write_generation_sums(staging)
        os.replace(staging, output)


def run_v7_challenge(package: Path, candidate: Path) -> dict:
    package = package.resolve()
    manifest = _read(package / "manifest.json")
    if manifest.get("schema_version") != SCHEMA:
        raise GenerationError("run_v7_challenge needs a frozen v7 manifest")
    candidate_before = sha256_file(candidate)
    output = package / "observed-results" / "v7-diagnostic.json"
    reports = package / "observed-results" / "inputs"
    try:
        summary = run_diagnostic(
            package / "manifest.json", candidate, output, workers=4, reports_dir=reports
        )
        file_evaluation_dir = package / "observed-results" / "file-evaluation"
        run_file_evaluation(package, candidate, file_evaluation_dir)
    except (DiagnosticError, FileEvaluationError) as error:
        raise GenerationError(f"v7 candidate execution failed: {error}") from error
    candidate_after = sha256_file(candidate)
    if candidate_after != candidate_before:
        raise GenerationError("candidate binary changed during the v7 run")
    input_report_sums = _write_input_report_sums(package, reports)
    run = {
        **summary,
        "schema_version": "wsi-dicom-negative-bench-v7-run-summary-v1",
        "challenge_id": manifest["challenge_id"],
        "candidate_sha256_before": candidate_before,
        "candidate_sha256_after": candidate_after,
        "diagnostic": str(output.relative_to(package)),
        "diagnostic_sha256": sha256_file(output),
        "file_evaluation": str(
            (file_evaluation_dir / "summary.json").relative_to(package)
        ),
        "input_report_sums": input_report_sums,
    }
    (package / "observed-results" / "run-summary.json").write_text(
        json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return run


def check_v7_acceptance(package: Path) -> dict:
    package = package.resolve()
    try:
        _verify_generation_sums(package)
    except FinalizationError as error:
        raise GenerationError(f"v7 generated package integrity failed: {error}") from error
    manifest = _read(package / "manifest.json")
    run = _read(package / "observed-results" / "run-summary.json")
    _verify_packaged_lock(package, manifest)
    expected_base_counts = {
        "valid_controls": len(manifest["valid_controls"]),
        "general_cases": len(manifest["evaluation_cases"]),
        "core_cases": len(manifest.get("core_profile_evaluation_cases", [])),
        "advisory_cases": len(manifest.get("advisory_cases", [])),
        "json_cases": len(manifest.get("json_evaluation_cases", [])),
        "http_cases": len(manifest.get("http_evaluation_cases", [])),
        "candidate_gap_cases": len(manifest.get("candidate_gap_cases", [])),
    }
    expected_contracts = {
        "general": [["2026d", "wsi-dicom-general-v4"]],
        "core": [["2026d", "wsi-dicom-core-profile-v5"]],
        "json": [["2026d", "wsi-dicom-general-v4"]],
        "http": [["2026d", "wsi-dicom-dicomweb-report-v1"]],
    }
    expected_ids = {
        *(control["control_id"] for control in manifest["valid_controls"]),
        *(case["case_id"] for field in (
            "evaluation_cases", "core_profile_evaluation_cases", "advisory_cases",
            "json_evaluation_cases", "http_evaluation_cases",
        ) for case in manifest.get(field, [])),
    }
    reports_dir = package / "observed-results" / "inputs"
    report_paths = list(reports_dir.glob("*.json"))
    actual_ids = {path.stem for path in report_paths}
    if actual_ids != expected_ids:
        raise GenerationError("v7 retained input report IDs differ from the frozen manifest")
    _verify_input_report_sums(package, run, expected_ids)
    expected_cohorts = {
        **{control["control_id"]: "valid-control" for control in manifest["valid_controls"]},
        **{case["case_id"]: "general-file" for case in manifest["evaluation_cases"]},
        **{case["case_id"]: "core-file"
           for case in manifest.get("core_profile_evaluation_cases", [])},
        **{case["case_id"]: "general-file"
           for case in manifest.get("advisory_cases", [])},
        **{case["case_id"]: "json" for case in manifest.get("json_evaluation_cases", [])},
        **{case["case_id"]: "http" for case in manifest.get("http_evaluation_cases", [])},
    }
    records = {}
    for path in report_paths:
        record = _read(path)
        cohort, report = record.get("cohort"), record.get("report")
        if (
            not isinstance(report, dict)
            or record.get("id") != path.stem
            or cohort != expected_cohorts.get(path.stem)
        ):
            raise GenerationError(f"invalid retained v7 input report: {path.name}")
        if cohort == "http":
            contract = report.get("candidate_contract", {})
            if contract != {
                "schema_version": "wsi-dicom-dicomweb-report-v1", "dicom_edition": "2026d",
            }:
                raise GenerationError(f"invalid HTTP report contract: {path.name}")
        else:
            expected_rule = (
                "wsi-dicom-core-profile-v5" if cohort == "core-file"
                else "wsi-dicom-general-v4"
            )
            expected_schema = (
                "wsi-dicom-json-validation-report-v1"
                if cohort == "json" else "wsi-dicom-validation-report-v1"
            )
            if (
                report.get("schema_version") != expected_schema
                or report.get("dicom_edition") != "2026d"
                or report.get("rule_set_id") != expected_rule
            ):
                raise GenerationError(f"invalid validation report contract: {path.name}")
            _validate_candidate_report_shape(path.stem, report)
        records[path.stem] = record
    try:
        checked_failures = _recompute_checked_failures(manifest, records)
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise GenerationError(f"invalid retained v7 result fields: {error}") from error
    expected_counts = {**expected_base_counts, "failures": len(checked_failures)}
    _verify_diagnostic(
        package, run, expected_counts, expected_contracts, checked_failures
    )
    candidate_sha256 = run.get("candidate_sha256_before")
    if (
        manifest.get("schema_version") != SCHEMA
        or run.get("schema_version")
        != "wsi-dicom-negative-bench-v7-run-summary-v1"
        or run.get("challenge_id") != manifest.get("challenge_id")
        or run.get("status") != ("passed" if not checked_failures else "failed")
        or run.get("failures") != checked_failures
        or run.get("counts") != expected_counts
        or run.get("contracts") != expected_contracts
        or not isinstance(candidate_sha256, str)
        or len(candidate_sha256) != 64
        or any(character not in "0123456789abcdef" for character in candidate_sha256)
        or candidate_sha256 != run.get("candidate_sha256_after")
        or run.get("file_evaluation")
        != "observed-results/file-evaluation/summary.json"
    ):
        raise GenerationError("v7 run is incomplete or failed its locked checked expectations")
    try:
        validate_file_evaluation(
            package,
            package / "observed-results" / "file-evaluation",
            candidate_sha256,
        )
    except FileEvaluationError as error:
        raise GenerationError(f"v7 independent file evaluation failed: {error}") from error
    gaps = manifest.get("freeze_gate", {})
    result = {
        "schema_version": "wsi-dicom-negative-bench-v7-acceptance-v1",
        "challenge_id": manifest["challenge_id"],
        "status": (
            "failed" if checked_failures or gaps.get("known_policy_failure") else "passed"
        ),
        "checked_evaluation": "failed" if checked_failures else "passed",
        "checked_failures": checked_failures,
        "known_policy_failure": gaps,
    }
    return result
