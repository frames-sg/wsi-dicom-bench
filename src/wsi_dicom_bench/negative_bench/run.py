"""Run every frozen negative-bench case and control through the workbench."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path

from wsi_dicom_bench.file_digest import sha256_file
from wsi_dicom_bench.negative_bench.identifiers import manifest_identifier_items
from wsi_dicom_bench.process_evidence import run_bounded_command


class ChallengeRunError(RuntimeError):
    """The locked challenge could not be executed completely."""


def run_challenge(package: Path, wsi_dicom: Path) -> dict:
    package = package.resolve()
    wsi_dicom = wsi_dicom.resolve()
    manifest_path = package / "manifest.json"
    if not manifest_path.is_file():
        raise ChallengeRunError(f"package manifest does not exist: {manifest_path}")
    if not wsi_dicom.is_file():
        raise ChallengeRunError(f"wsi-dicom binary does not exist: {wsi_dicom}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    try:
        controls, cases = manifest_identifier_items(manifest)
    except ValueError as exc:
        raise ChallengeRunError(str(exc)) from exc
    limits = manifest.get("resource_limits")
    if not isinstance(limits, dict):
        raise ChallengeRunError("challenge manifest resource_limits must be an object")
    for key in (
        "max_command_output_bytes",
        "max_pixel_frames",
        "command_timeout_secs",
        "case_timeout_secs",
    ):
        value = limits.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ChallengeRunError(
                f"challenge manifest resource_limits.{key} must be a positive integer"
            )
    catalog_name = Path(
        manifest.get("rule_catalog", {}).get(
            "path", "rules/wsi-dicom-bench-rules-2026c-v4.json"
        )
    ).name
    profile_path = None
    core_profile = manifest.get("core_profile")
    if core_profile is not None:
        profile_name = Path(core_profile["path"]).name
        profile_path = package / "expected-results" / profile_name
        if not profile_path.is_file():
            raise ChallengeRunError(f"core profile does not exist: {profile_path}")
    summary_path = package / "observed-results" / "run-summary.json"
    if summary_path.exists():
        raise ChallengeRunError(f"run summary already exists: {summary_path}")

    inputs = [
        (
            control["control_id"],
            "valid-controls-v1",
            (
                package / "controls" / control["control_id"]
                if "package_paths" in control
                else package / "controls" / f"{control['control_id']}.dcm"
            ),
        )
        for control in controls
    ]
    inputs.extend(
        (
            case["case_id"],
            "evaluation-v1",
            package / "cases" / case["case_id"] / "input",
        )
        for case in cases
    )
    executions = []
    for identifier, cohort, dicom_input in inputs:
        executions.append(
            _run_one_input(
                package,
                wsi_dicom,
                package / "expected-results" / catalog_name,
                profile_path,
                limits,
                identifier,
                cohort,
                dicom_input,
            )
        )

    summary = {
        "schema_version": "wsi-dicom-negative-bench-run-summary-v1",
        "challenge_id": manifest.get("challenge_id"),
        "environment": {
            "python": sys.version,
            "operating_system": platform.platform(),
            "machine": platform.machine(),
            "wsi_dicom_path": wsi_dicom.name,
            "wsi_dicom_sha256": sha256_file(wsi_dicom),
            "workbench_module": "wsi_dicom_bench.workbench.cli",
        },
        "resource_limits": limits,
        "executions": executions,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = summary_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, summary_path)
    return summary


def _run_one_input(
    package: Path,
    wsi_dicom: Path,
    catalog_path: Path,
    profile_path: Path | None,
    limits: dict,
    identifier: str,
    cohort: str,
    dicom_input: Path,
) -> dict:
    if not dicom_input.exists():
        raise ChallengeRunError(f"challenge input does not exist: {dicom_input}")
    evidence = package / "observed-results" / identifier / "workbench"
    raw_dir = package / "validator-results" / identifier
    if evidence.exists() or raw_dir.exists():
        raise ChallengeRunError(f"result path already exists for {identifier}")
    raw_dir.mkdir(parents=True)
    command = [
        sys.executable,
        "-m",
        "wsi_dicom_bench.workbench.cli",
        str(dicom_input),
        "--output",
        str(evidence),
        "--wsi-dicom",
        str(wsi_dicom),
        "--catalog",
        str(catalog_path),
        "--max-pixel-frames",
        str(limits["max_pixel_frames"]),
        "--command-timeout-secs",
        str(limits["command_timeout_secs"]),
        "--evaluation-timeout-secs",
        str(limits["case_timeout_secs"]),
    ]
    if profile_path is not None:
        command.extend(["--profile", str(profile_path)])
    stdout_path = raw_dir / "launcher.stdout.json"
    stderr_path = raw_dir / "launcher.stderr.txt"
    execution = run_bounded_command(
        command,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        timeout_secs=int(limits["case_timeout_secs"]),
        max_output_bytes=int(limits["max_command_output_bytes"]),
    )
    timed_out = execution["timed_out"]
    returncode = execution["returncode"]
    runtime = execution["elapsed_seconds"]
    if execution["stdout_truncated"] or execution["stderr_truncated"]:
        raise ChallengeRunError(
            f"launcher output exceeds max_command_output_bytes for {identifier}"
        )
    report_path = evidence / "workbench-report.json"
    report_present = report_path.is_file()
    if (
        returncode not in {0, 1}
        or timed_out
        or execution["launch_error"] is not None
        or not report_present
    ):
        raise ChallengeRunError(
            f"workbench execution failed for {identifier}: returncode={returncode}, "
            f"timed_out={timed_out}, report_present={report_present}"
        )
    sanitize = _evidence_sanitizer(package, wsi_dicom)
    _sanitize_public_evidence((evidence, raw_dir), sanitize)
    return {
        "id": identifier,
        "cohort": cohort,
        "input": str(dicom_input.relative_to(package)),
        "command": [sanitize(argument) for argument in command],
        "returncode": returncode,
        "timed_out": timed_out,
        "runtime_seconds": runtime,
        "workbench_report": str(report_path.relative_to(package)),
        "launcher_stdout": str(stdout_path.relative_to(package)),
        "launcher_stderr": str(stderr_path.relative_to(package)),
    }


def _evidence_sanitizer(package: Path, wsi_dicom: Path):
    replacements = {
        str(wsi_dicom): wsi_dicom.name,
        sys.executable: "python",
        str(Path(sys.executable).resolve()): "python",
        str(package): ".",
    }
    home = str(Path.home())
    if home not in {"", "/"}:
        replacements[home] = "<home>"
    ordered = sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True)

    def sanitize(value):
        if isinstance(value, dict):
            return {sanitize(key): sanitize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        if isinstance(value, str):
            for sensitive, portable in ordered:
                value = value.replace(sensitive, portable)
        return value

    return sanitize


def _sanitize_public_evidence(roots: tuple[Path, ...], sanitize) -> None:
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".json", ".md", ".txt"}:
                continue
            if path.suffix == ".json":
                try:
                    document = json.loads(path.read_text(encoding="utf-8"))
                except (UnicodeError, json.JSONDecodeError):
                    document = None
                if document is not None:
                    path.write_text(
                        json.dumps(sanitize(document), indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    continue
            text = path.read_text(encoding="utf-8", errors="replace")
            path.write_text(sanitize(text), encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--wsi-dicom", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = run_challenge(args.package, args.wsi_dicom)
    except (ChallengeRunError, OSError, ValueError) as exc:
        print(f"challenge run failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {"status": "complete", "executions": len(summary["executions"])},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
