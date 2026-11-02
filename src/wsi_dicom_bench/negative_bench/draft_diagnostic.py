"""Run the unfrozen v7 draft directly against a candidate.

This is a development diagnostic, not locked benchmark evidence.  It materializes
inputs in a temporary directory, checks the manifest's current expectations, and
writes only a compact JSON summary.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from wsi_dicom_bench.file_digest import sha256_file
from wsi_dicom_bench.negative_bench import jpip_statement_cases, json_statement_cases
from wsi_dicom_bench.negative_bench import http_statement_runner
from wsi_dicom_bench.negative_bench.model import GenerationError
from wsi_dicom_bench.negative_bench.mutations import generate_case


PACKAGE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = PACKAGE / "manifest-v7-draft.json"
JSON_BUILDERS = {
    "json_statement_cases.build_document": json_statement_cases.build_document,
    "jpip_statement_cases.build_document": jpip_statement_cases.build_document,
}


class DiagnosticError(RuntimeError):
    """The draft could not be materialized or the candidate did not execute."""


def _source_paths(control: dict, manifest_path: Path) -> list[Path]:
    originals = control.get("original_paths") or [control.get("original_path")]
    packaged = control.get("package_paths") or [control.get("package_path")]
    paths = []
    for index, original in enumerate(originals):
        if not isinstance(original, str):
            raise DiagnosticError(f"invalid source path for {control['control_id']}")
        path = Path(original)
        if not path.is_file():
            try:
                path = manifest_path.parent / path.relative_to("bench/negative_bench")
            except ValueError:
                path = manifest_path.parent / path
        if not path.is_file() and index < len(packaged) and isinstance(packaged[index], str):
            path = manifest_path.parent / packaged[index]
        if not path.is_file():
            raise DiagnosticError(f"source does not exist: {path}")
        paths.append(path)
    return paths


def _source_target(paths: list[Path]) -> Path:
    if len(paths) == 1:
        return paths[0]
    common = Path(os.path.commonpath(paths))
    return common if common.is_dir() else common.parent


def _generation_source(case: dict, paths: list[Path]) -> Path:
    return _source_target(paths) if case["mutation_name"] == "iod_set_edits" else paths[0]


def _normalize_rule(name: str) -> str:
    return "intrinsic-wsi-dicom-pixel-structure" if name == "intrinsic-pixel-structure" else name


def _run_report(command: list[str]) -> dict:
    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if result.returncode not in {0, 1}:
        raise DiagnosticError(
            f"candidate command failed ({result.returncode}): {' '.join(command[:4])}: "
            f"{result.stderr}"
        )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise DiagnosticError(f"candidate emitted invalid JSON: {error}") from error
    if not isinstance(report, dict) or not isinstance(report.get("checks"), list):
        raise DiagnosticError("candidate report is incomplete")
    return report


def _intrinsic_failed(report: dict) -> set[str]:
    return {
        _normalize_rule(check["name"])
        for check in report["checks"]
        if check.get("status") == "failed"
        and isinstance(check.get("name"), str)
        and check["name"].startswith("intrinsic-")
    }


def _validate_file(candidate: Path, path: Path, profile: str) -> tuple[dict, set[str]]:
    report = _run_report([
        str(candidate), "validate", "--profile", profile, "--json", "--optional", str(path),
    ])
    return report, _intrinsic_failed(report)


def _validate_json(candidate: Path, path: Path, transfer_syntax: str) -> tuple[dict, set[str]]:
    report = _run_report([
        str(candidate), "validate-json", str(path), "--json",
        "--transfer-syntax", transfer_syntax,
    ])
    return report, _intrinsic_failed(report)


def _check_source_digest(case: dict, paths: list[Path]) -> None:
    expected = case["source_control_sha256"]
    actual = [sha256_file(path) for path in paths]
    if isinstance(expected, str):
        actual_value: str | list[str] = actual[0]
    else:
        actual_value = actual
    if actual_value != expected:
        raise DiagnosticError(f"source digest differs for {case['case_id']}")


def _case_failure(case: dict, report: dict, observed: set[str], profile: str) -> dict | None:
    expected = {
        rule for rule in case.get("expected_failing_rules", [])
        if rule.startswith("intrinsic-")
    }
    cascades = set(case.get("adjudicated_cascade_rules", []))
    missing = expected - observed
    unexpected = observed - expected - cascades
    missing_cascades = cascades - observed
    advisory_fragment = case.get("expected_advisory_contains")
    advisories = [
        advisory
        for item in report.get("optional", [])
        for advisory in item.get("advisories", [])
    ]
    missing_advisory = (
        advisory_fragment is not None
        and not any(advisory_fragment in advisory for advisory in advisories)
    )
    if not (missing or unexpected or missing_cascades or missing_advisory):
        return None
    return {
        "id": case["case_id"],
        "profile": profile,
        "missing_expected_rules": sorted(missing),
        "missing_cascade_rules": sorted(missing_cascades),
        "unexpected_rules": sorted(unexpected),
        "observed_rules": sorted(observed),
        **({"missing_advisory_fragment": advisory_fragment} if missing_advisory else {}),
    }


def run_diagnostic(manifest_path: Path, candidate: Path, output: Path,
                   workers: int = 4, reports_dir: Path | None = None) -> dict:
    manifest_path = manifest_path.resolve()
    candidate = candidate.resolve()
    output = output.resolve()
    if output.exists():
        raise DiagnosticError(f"output already exists: {output}")
    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise DiagnosticError(f"candidate is not executable: {candidate}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DiagnosticError(f"cannot read manifest: {error}") from error
    if manifest.get("schema_version") not in {
        "wsi-dicom-negative-bench-manifest-v7-draft",
        "wsi-dicom-negative-bench-manifest-v7",
    }:
        raise DiagnosticError("diagnostic needs the v7 draft manifest")
    packaged = manifest.get("schema_version") == "wsi-dicom-negative-bench-manifest-v7"
    controls = {
        control["control_id"]: control
        for control in [*manifest["mutation_sources"], *manifest["valid_controls"]]
    }
    failures = []
    contracts: dict[str, set[tuple[str | None, str | None]]] = {}

    def retain(identifier: str, cohort: str, report: dict) -> None:
        if reports_dir is None:
            return
        reports_dir.mkdir(parents=True, exist_ok=True)
        destination = reports_dir / f"{identifier}.json"
        destination.write_text(
            json.dumps({"id": identifier, "cohort": cohort, "report": report},
                       indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def remember(profile: str, report: dict) -> None:
        contracts.setdefault(profile, set()).add(
            (report.get("dicom_edition"), report.get("rule_set_id"))
        )

    valid_controls = manifest["valid_controls"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for control in valid_controls:
            paths = _source_paths(control, manifest_path)
            future = pool.submit(_validate_file, candidate, _source_target(paths), "general")
            futures[future] = control["control_id"]
        for future in concurrent.futures.as_completed(futures):
            identifier = futures[future]
            report, observed = future.result()
            remember("general", report)
            retain(identifier, "valid-control", report)
            if observed:
                failures.append({
                    "id": identifier,
                    "profile": "general-control",
                    "unexpected_rules": sorted(observed),
                })

    collections = (
        (manifest["evaluation_cases"], "general"),
        (manifest.get("core_profile_evaluation_cases", []), "core"),
        (manifest.get("advisory_cases", []), "general"),
    )
    generated: list[tuple[dict, str, Path]] = []
    with tempfile.TemporaryDirectory(prefix="wsi-dicom-v7-diagnostic-") as temporary:
        root = Path(temporary)
        for cases, profile in collections:
            for case in cases:
                source_paths = _source_paths(controls[case["source_control_ids"][0]], manifest_path)
                _check_source_digest(case, source_paths)
                if packaged:
                    case_dir = manifest_path.parent / "cases" / case["case_id"] / "input"
                    if not case_dir.is_dir():
                        raise DiagnosticError(f"packaged case input is missing: {case['case_id']}")
                else:
                    case_dir = root / profile / case["case_id"]
                    case_dir.mkdir(parents=True)
                    outputs, _ = generate_case(
                        case, _generation_source(case, source_paths), case_dir
                    )
                    if not outputs:
                        raise DiagnosticError(f"case generated no output: {case['case_id']}")
                generated.append((case, profile, case_dir))

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_validate_file, candidate, case_dir, profile): (case, profile)
                for case, profile, case_dir in generated
            }
            for future in concurrent.futures.as_completed(futures):
                case, profile = futures[future]
                report, observed = future.result()
                remember(profile, report)
                retain(case["case_id"], f"{profile}-file", report)
                failure = _case_failure(case, report, observed, profile)
                if failure is not None:
                    failures.append(failure)

        json_cases = manifest.get("json_evaluation_cases", [])
        json_inputs = []
        for case in json_cases:
            source_paths = _source_paths(controls[case["source_control_ids"][0]], manifest_path)
            _check_source_digest(case, source_paths)
            if packaged:
                path = manifest_path.parent / "cases" / case["case_id"] / "input/document.json"
                if not path.is_file():
                    raise DiagnosticError(f"packaged JSON input is missing: {case['case_id']}")
            else:
                path = root / "json" / f"{case['case_id']}.json"
                path.parent.mkdir(exist_ok=True)
                builder_name = case.get("document_builder")
                builder = JSON_BUILDERS.get(builder_name)
                if builder is None:
                    raise DiagnosticError(
                        f"unsupported JSON document builder for {case['case_id']}: {builder_name}"
                    )
                path.write_bytes(builder(case["case_id"], source_paths[0]))
            json_inputs.append((case, path))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_validate_json, candidate, path, case["transfer_syntax"]): case
                for case, path in json_inputs
            }
            for future in concurrent.futures.as_completed(futures):
                case = futures[future]
                report, observed = future.result()
                remember("json", report)
                retain(case["case_id"], "json", report)
                failure = _case_failure(case, report, observed, "json")
                if failure is not None:
                    failures.append(failure)

    http_cases = manifest.get("http_evaluation_cases", [])
    if http_cases:
        http_observations = http_statement_runner.observe_cases(candidate, http_cases)
        contracts.setdefault("http", set()).add((
            http_observations.get("dicom_edition"),
            http_observations.get("candidate_report_schema_version"),
        ))
        for case in http_cases:
            observed = http_observations["cases"][case["case_id"]]
            retain(case["case_id"], "http", observed)
            expected = set(case["expected_failing_checks"])
            expected_advisory = set(case.get("expected_advisory_checks", []))
            cascades = set(case.get("adjudicated_cascade_checks", []))
            failed = set(observed["failed_checks"])
            advisory_fragment = case.get("expected_advisory_contains")
            baseline_advisories = observed.get("baseline_advisories", [])
            target_advisory = bool(observed["observed_advisories"]) and (
                advisory_fragment is None
                or (
                    any(advisory_fragment in message
                        for message in observed["observed_advisories"])
                    and not any(advisory_fragment in message
                                for message in baseline_advisories)
                )
            )
            localized = (
                observed["observed_status"] == "passed"
                and target_advisory
                if expected_advisory else
                observed["observed_status"] == "failed"
            )
            if (
                observed["baseline_status"] != "passed"
                or observed["baseline_failed_checks"]
                or not localized
                or failed != expected | cascades
            ):
                failures.append({
                    "id": case["case_id"],
                    "profile": "http",
                    "missing_expected_checks": sorted(expected - failed),
                    "missing_cascade_checks": sorted(cascades - failed),
                    "unexpected_checks": sorted(failed - expected - cascades),
                })

    inconsistent = {
        profile: sorted([list(identity) for identity in identities], key=str)
        for profile, identities in contracts.items() if len(identities) != 1
    }
    if inconsistent:
        failures.append({"id": "candidate-contract", "inconsistent": inconsistent})
    candidate_gaps = manifest.get("candidate_gap_cases", [])
    if candidate_gaps:
        failures.append({
            "id": "candidate-gap-cases",
            "cases": sorted(case["case_id"] for case in candidate_gaps),
        })
    summary = {
        "schema_version": "wsi-dicom-v7-draft-diagnostic-v1",
        "challenge_id": manifest["challenge_id"],
        "status": "passed" if not failures else "failed",
        "counts": {
            "valid_controls": len(valid_controls),
            "general_cases": len(manifest["evaluation_cases"]),
            "core_cases": len(manifest.get("core_profile_evaluation_cases", [])),
            "advisory_cases": len(manifest.get("advisory_cases", [])),
            "json_cases": len(manifest.get("json_evaluation_cases", [])),
            "http_cases": len(http_cases),
            "candidate_gap_cases": len(candidate_gaps),
            "failures": len(failures),
        },
        "contracts": {
            profile: [list(identity) for identity in sorted(identities, key=str)]
            for profile, identities in sorted(contracts.items())
        },
        "failures": sorted(failures, key=lambda item: item["id"]),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output.with_suffix(output.suffix + ".tmp")
    temporary_output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary_output, output)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    if args.workers < 1 or args.workers > 32:
        parser.error("--workers must be from 1 to 32")
    try:
        summary = run_diagnostic(args.manifest, args.candidate, args.output, args.workers)
    except (DiagnosticError, GenerationError, OSError, ValueError) as error:
        print(f"v7 draft diagnostic failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"status": summary["status"], **summary["counts"]}, sort_keys=True))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
