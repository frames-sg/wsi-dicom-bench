"""Shared validation of completed negative-bench run summaries."""

from __future__ import annotations

from dataclasses import dataclass

from wsi_dicom_bench.negative_bench.identifiers import manifest_identifier_items
from wsi_dicom_bench.path_identifiers import require_portable_identifier


class CompletedEvidenceError(ValueError):
    """A run summary does not describe one complete execution per challenge input."""


@dataclass(frozen=True)
class CompletedRunEvidence:
    controls: list[dict]
    cases: list[dict]
    expected: dict[str, str]
    candidate_sha256: str | None


def require_candidate_sha256(evidence: CompletedRunEvidence) -> str:
    if evidence.candidate_sha256 is None:
        raise CompletedEvidenceError("run summary lacks the evaluated wsi-dicom SHA-256")
    return evidence.candidate_sha256


def validate_completed_run(manifest: dict, run: dict) -> CompletedRunEvidence:
    """Validate run identity, coverage, process completion, and candidate identity."""
    try:
        controls, cases = manifest_identifier_items(manifest)
    except ValueError as exc:
        raise CompletedEvidenceError(str(exc)) from exc
    challenge_id = manifest.get("challenge_id")
    if not isinstance(challenge_id, str) or not challenge_id:
        raise CompletedEvidenceError("manifest challenge_id must be a non-empty string")

    executions = run.get("executions")
    if (
        run.get("schema_version") != "wsi-dicom-negative-bench-run-summary-v1"
        or run.get("challenge_id") != challenge_id
        or not isinstance(executions, list)
    ):
        raise CompletedEvidenceError("run summary schema or challenge does not match manifest")
    expected = {
        **{control["control_id"]: "valid-controls-v1" for control in controls},
        **{case["case_id"]: "evaluation-v1" for case in cases},
    }
    if not expected:
        raise CompletedEvidenceError("completed package must contain at least one challenge input")

    observed: dict[str, str] = {}
    for index, execution in enumerate(executions):
        if not isinstance(execution, dict):
            raise CompletedEvidenceError(f"run summary execution {index} must be an object")
        try:
            identifier = require_portable_identifier(
                execution.get("id"), f"run summary execution {index} id"
            )
        except ValueError as exc:
            raise CompletedEvidenceError(str(exc)) from exc
        if identifier in observed:
            raise CompletedEvidenceError(f"run summary duplicates execution: {identifier}")
        observed[identifier] = execution.get("cohort")
        if (
            execution.get("timed_out") is not False
            or execution.get("launch_error") is not None
            or type(execution.get("returncode")) is not int
            or execution["returncode"] not in {0, 1}
        ):
            raise CompletedEvidenceError(f"{identifier} has incomplete execution evidence")
    if observed != expected:
        raise CompletedEvidenceError("run summary executions do not match manifest inputs")

    candidate_sha256 = run.get("environment", {}).get("wsi_dicom_sha256")
    if candidate_sha256 is not None:
        if (
            not isinstance(candidate_sha256, str)
            or len(candidate_sha256) != 64
            or any(character not in "0123456789abcdef" for character in candidate_sha256)
        ):
            raise CompletedEvidenceError("run summary lacks the evaluated wsi-dicom SHA-256")
    return CompletedRunEvidence(controls, cases, expected, candidate_sha256)
