"""Run locked challenges and apply their acceptance policy."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path, PurePosixPath

from .core_profile import (
    CoreProfileError,
    _validate_report_evidence,
    load_profile,
    validate_evidence_coverage,
    validate_profile_coverage,
)
from .file_digest import sha256_file
from .negative_bench.finalize import (
    FinalizationError,
    _verify_generation_sums,
    finalize_package,
)
from .negative_bench.identifiers import manifest_identifier_items
from .negative_bench.model import GenerationError


class ChallengeInfrastructureError(RuntimeError):
    """Challenge execution, integrity, or compatibility is incomplete."""


class ChallengePolicyError(RuntimeError):
    """Complete evidence does not satisfy the locked acceptance policy."""


def _read_object(path: Path, description: str) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ChallengeInfrastructureError(f"cannot read {description} {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ChallengeInfrastructureError(f"{description} must be a JSON object: {path}")
    return document


def _suite_manifest(suite: Path) -> Path:
    suite = suite.resolve()
    if suite.is_file():
        return suite
    if not suite.is_dir():
        raise ChallengeInfrastructureError(f"suite does not exist: {suite}")
    candidates = [suite / "manifest.json", suite / "manifest-v4.json"]
    existing = [path for path in candidates if path.is_file()]
    if len(existing) != 1:
        raise ChallengeInfrastructureError(
            f"suite directory must contain exactly one supported manifest: {suite}"
        )
    return existing[0]


def _require_distribution_payload(evidence: Path) -> None:
    metadata = _read_object(
        evidence / "reproduction" / "benchmark-distribution.json",
        "benchmark distribution payload",
    )
    wheel = metadata.get("wheel")
    if (
        metadata.get("schema_version") != "wsi-dicom-bench-distribution-payload-v1"
        or not isinstance(wheel, dict)
        or not isinstance(wheel.get("path"), str)
        or not isinstance(wheel.get("sha256"), str)
    ):
        raise ChallengeInfrastructureError(
            "challenge run requires an exact retained benchmark wheel payload"
        )
    relative = PurePosixPath(wheel["path"])
    if (
        relative.is_absolute()
        or "\\" in wheel["path"]
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ChallengeInfrastructureError("retained benchmark wheel path is unsafe")
    path = evidence / "reproduction" / relative
    if not path.is_file() or sha256_file(path) != wheel["sha256"]:
        raise ChallengeInfrastructureError("retained benchmark wheel SHA-256 differs")
    lock = evidence / "reproduction" / "requirements.lock"
    if not lock.is_file() or "pydicom==3.0.2 --hash=sha256:" not in lock.read_text(
        encoding="utf-8"
    ):
        raise ChallengeInfrastructureError("reproduction dependency lock is incomplete")


def _verify_final_seal(evidence: Path) -> None:
    seal = evidence / "SHA256SUMS"
    if not seal.exists():
        return
    try:
        text = seal.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ChallengeInfrastructureError(f"cannot read final checksum seal: {exc}") from exc
    if not text or not text.endswith("\n"):
        raise ChallengeInfrastructureError("SHA256SUMS must be nonempty and newline-terminated")
    entries: dict[str, str] = {}
    paths: list[str] = []
    for line in text.splitlines():
        if len(line) < 67 or line[64:66] != "  ":
            raise ChallengeInfrastructureError("SHA256SUMS contains an invalid entry")
        digest, raw_path = line[:64], line[66:]
        relative = PurePosixPath(raw_path)
        if (
            any(character not in "0123456789abcdef" for character in digest)
            or "\\" in raw_path
            or relative.is_absolute()
            or relative.as_posix() != raw_path
            or any(part in {"", ".", ".."} for part in relative.parts)
            or raw_path in entries
        ):
            raise ChallengeInfrastructureError("SHA256SUMS contains an unsafe or duplicate entry")
        entries[raw_path] = digest
        paths.append(raw_path)
    if paths != sorted(paths):
        raise ChallengeInfrastructureError("SHA256SUMS paths are not sorted")
    actual: dict[str, Path] = {}
    for path in sorted(evidence.rglob("*")):
        if path.is_symlink():
            raise ChallengeInfrastructureError(
                f"sealed evidence contains a symlink: {path.relative_to(evidence)}"
            )
        if path.is_file() and path != seal:
            actual[path.relative_to(evidence).as_posix()] = path
    if set(entries) != set(actual):
        raise ChallengeInfrastructureError("SHA256SUMS file set differs from sealed evidence")
    for relative, expected in entries.items():
        if sha256_file(actual[relative]) != expected:
            raise ChallengeInfrastructureError(f"final SHA-256 mismatch: {relative}")


def _preflight_evidence(evidence: Path) -> tuple[dict, dict, dict]:
    evidence = evidence.resolve()
    if not evidence.is_dir():
        raise ChallengeInfrastructureError(f"evidence directory does not exist: {evidence}")
    _verify_final_seal(evidence)
    try:
        _verify_generation_sums(evidence)
    except (FinalizationError, OSError) as exc:
        raise ChallengeInfrastructureError(f"generated suite integrity failed: {exc}") from exc

    manifest = _read_object(evidence / "manifest.json", "challenge manifest")
    try:
        controls, cases = manifest_identifier_items(manifest)
    except ValueError as exc:
        raise ChallengeInfrastructureError(str(exc)) from exc
    challenge_id = manifest.get("challenge_id")
    run = _read_object(
        evidence / "observed-results" / "run-summary.json", "run summary"
    )
    if (
        run.get("schema_version") != "wsi-dicom-negative-bench-run-summary-v1"
        or run.get("challenge_id") != challenge_id
        or not isinstance(run.get("executions"), list)
    ):
        raise ChallengeInfrastructureError("run summary schema or challenge is incompatible")
    expected = {
        **{item["control_id"]: "valid-controls-v1" for item in controls},
        **{item["case_id"]: "evaluation-v1" for item in cases},
    }
    observed: dict[str, str] = {}
    for index, execution in enumerate(run["executions"]):
        if not isinstance(execution, dict) or not isinstance(execution.get("id"), str):
            raise ChallengeInfrastructureError(f"run summary execution {index} is invalid")
        identifier = execution["id"]
        if identifier in observed:
            raise ChallengeInfrastructureError(f"run summary duplicates execution: {identifier}")
        observed[identifier] = execution.get("cohort")
        if (
            execution.get("timed_out")
            or execution.get("launch_error")
            or execution.get("returncode") not in {0, 1}
        ):
            raise ChallengeInfrastructureError(f"{identifier} has incomplete execution evidence")
    if observed != expected:
        raise ChallengeInfrastructureError("run summary executions do not match manifest inputs")

    profile_ref = manifest.get("core_profile", {}).get("path")
    catalog_ref = manifest.get("rule_catalog", {}).get("path")
    if not isinstance(profile_ref, str) or not isinstance(catalog_ref, str):
        raise ChallengeInfrastructureError("challenge lacks an explicit core profile or rule catalog")
    profile_path = evidence / "expected-results" / Path(profile_ref).name
    catalog_path = evidence / "expected-results" / Path(catalog_ref).name
    protocol_path = evidence / "protocol.md"
    lock_name = Path(manifest.get("expected_results_lock", "expected-results-lock-v1.json")).name
    lock_path = evidence / "expected-results" / lock_name
    try:
        profile = load_profile(profile_path)
        catalog = _read_object(catalog_path, "rule catalog")
        from .negative_bench.generate import _verify_expected_results_lock

        _verify_expected_results_lock(
            lock_path, evidence / "manifest.json", protocol_path, catalog_path, profile_path
        )
        validate_profile_coverage(profile, catalog, manifest)
        candidate_digest = run.get("environment", {}).get("wsi_dicom_sha256")
        if (
            not isinstance(candidate_digest, str)
            or len(candidate_digest) != 64
            or any(character not in "0123456789abcdef" for character in candidate_digest)
        ):
            raise ChallengeInfrastructureError(
                "run summary lacks the evaluated wsi-dicom SHA-256"
            )
        for identifier in expected:
            report_path = (
                evidence
                / "observed-results"
                / identifier
                / "workbench"
                / "workbench-report.json"
            )
            report = _read_object(report_path, f"workbench report for {identifier}")
            if report.get("schema_version") not in {
                "wsi-dicom-bench-workbench-report-v1",
                "wsi-dicom-bench-workbench-report-v2",
            }:
                raise ChallengeInfrastructureError(
                    f"workbench report schema is incompatible: {identifier}"
                )
            if report.get("profile", {}).get("id") != profile.get("profile_id"):
                raise ChallengeInfrastructureError(
                    f"{identifier} records an incompatible core-profile identity"
                )
            if report.get("profile", {}).get("sha256") != sha256_file(profile_path):
                raise ChallengeInfrastructureError(
                    f"{identifier} records the wrong core-profile digest"
                )
            if report.get("software", {}).get("wsi_dicom", {}).get("sha256") != candidate_digest:
                raise ChallengeInfrastructureError(
                    f"{identifier} records a different wsi-dicom executable SHA-256"
                )
            _validate_report_evidence(identifier, report, catalog, manifest, evidence)
    except (CoreProfileError, GenerationError) as exc:
        raise ChallengeInfrastructureError(f"evidence compatibility failed: {exc}") from exc
    return manifest, profile, catalog


def check_acceptance(evidence: Path) -> dict:
    """Apply the locked acceptance gate without modifying evidence."""
    evidence = evidence.resolve()
    manifest, profile, catalog = _preflight_evidence(evidence)
    try:
        gate = validate_evidence_coverage(profile, catalog, manifest, evidence)
    except CoreProfileError as exc:
        raise ChallengePolicyError(str(exc)) from exc
    return {
        "schema_version": "wsi-dicom-bench-acceptance-v1",
        "status": "passed",
        "challenge_id": manifest["challenge_id"],
        "evidence": str(evidence),
        "gate": gate,
    }


def run(args: argparse.Namespace) -> dict:
    manifest = _suite_manifest(args.suite)
    candidate = args.wsi_dicom.resolve()
    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise ChallengeInfrastructureError(
            f"wsi-dicom executable is missing or not executable: {candidate}"
        )
    output = args.output.resolve()
    if output.exists():
        raise ChallengeInfrastructureError(f"output path already exists: {output}")

    from .negative_bench.analyze import AnalysisError, analyze_challenge
    from .negative_bench.generate import generate_challenge
    from .negative_bench.run import ChallengeRunError, run_challenge

    try:
        generate_challenge(manifest, output)
        _require_distribution_payload(output)
        run_challenge(output, candidate)
        analyze_challenge(output)
    except ChallengeInfrastructureError:
        raise
    except (GenerationError, ChallengeRunError, AnalysisError, OSError, ValueError) as exc:
        raise ChallengeInfrastructureError(str(exc)) from exc
    result = check_acceptance(output)
    try:
        result["finalization"] = finalize_package(output)
    except (FinalizationError, OSError) as exc:
        raise ChallengeInfrastructureError(f"finalization failed: {exc}") from exc
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    challenge = commands.add_parser("challenge")
    actions = challenge.add_subparsers(dest="action", required=True)
    run_parser = actions.add_parser("run")
    run_parser.add_argument("--suite", type=Path, required=True)
    run_parser.add_argument("--wsi-dicom", type=Path, required=True)
    run_parser.add_argument("--output", type=Path, required=True)
    check_parser = actions.add_parser("check")
    check_parser.add_argument("--evidence", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        result = run(args) if args.action == "run" else check_acceptance(args.evidence)
    except ChallengePolicyError as exc:
        print(f"challenge acceptance failed: {exc}", file=sys.stderr)
        return 1
    except (ChallengeInfrastructureError, OSError, ValueError) as exc:
        print(f"challenge execution failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
