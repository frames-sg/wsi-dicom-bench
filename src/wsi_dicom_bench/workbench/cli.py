"""Single entry point for a complete WSI-DICOM Bench DICOM evaluation."""

from __future__ import annotations

import argparse
import importlib.resources
import json
import os
import sys
import tempfile
from pathlib import Path

from wsi_dicom_bench.cli_values import positive_int
from wsi_dicom_bench.core_profile import CoreProfileError, load_profile
from wsi_dicom_bench.json_document import write_json

from .catalog import CatalogError, load_catalog
from .execution import WorkbenchError, run_json_command
from .report import build_report, render_summary


DEFAULT_CATALOG = (
    Path(str(importlib.resources.files("wsi_dicom_bench.rules")))
    / "wsi-dicom-bench-rules-2026c-v4.json"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run intrinsic, decoder, and independent-validator checks and emit one unified per-slide report."
    )
    parser.add_argument("dicom", type=Path, help="DICOM file or directory to evaluate")
    parser.add_argument("--output", type=Path, required=True, help="new evidence directory")
    parser.add_argument(
        "--wsi-dicom",
        type=Path,
        required=True,
        help="wsi-dicom executable",
    )
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument(
        "--profile",
        type=Path,
        help="machine-readable VL WSI core profile; required by versioned core-profile benchmark runs",
    )
    parser.add_argument("--allow-missing-tools", action="store_true")
    parser.add_argument("--dcmvalidate-iod", type=Path)
    parser.add_argument("--htj2k-decoder")
    parser.add_argument("--max-pixel-frames", type=positive_int, default=1)
    parser.add_argument("--command-timeout-secs", type=positive_int, default=300)
    parser.add_argument("--evaluation-timeout-secs", type=positive_int, default=3600)
    parser.add_argument("--max-json-bytes", type=positive_int, default=256 * 1024 * 1024)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        result = run_workbench(args)
    except (WorkbenchError, CatalogError, CoreProfileError, OSError, ValueError) as exc:
        print(f"workbench failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return {"passed": 0, "failed": 1, "execution_error": 2}[result["status"]]


def run_workbench(args: argparse.Namespace) -> dict:
    if args.output.exists():
        raise WorkbenchError(f"output path already exists: {args.output}")
    if not args.dicom.exists():
        raise WorkbenchError(f"DICOM input does not exist: {args.dicom}")
    if not args.wsi_dicom.is_file():
        raise WorkbenchError(f"wsi-dicom executable does not exist: {args.wsi_dicom}")
    catalog = load_catalog(args.catalog)
    if (
        any("intrinsic-wsi-dicom-2026c-core-image-profile" in rule["check_names"] for rule in catalog["rules"])
        and args.profile is None
    ):
        raise WorkbenchError("--profile is required for the DICOM 2026c core-profile catalog")
    profile = load_profile(args.profile) if args.profile else None
    expected_profile = {
        "wsi-dicom-bench-rules-2026c-v4": "wsi-dicom-core-profile-2026c-v2",
    }.get(catalog["catalog_version"])
    if profile and profile["profile_id"] != expected_profile:
        raise WorkbenchError("catalog and selected profile version are incompatible")
    if profile and profile["dicom_edition"] != catalog["dicom_edition"]:
        raise WorkbenchError("profile and rule catalog use different DICOM editions")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{args.output.name}.staging-", dir=args.output.parent
    ) as temporary:
        staging = Path(temporary)
        doctor_execution, validation_execution = _run_evaluations(args, staging)
        doctor = doctor_execution.pop("document")
        validation = validation_execution.pop("document")
        for execution in (doctor_execution, validation_execution):
            for field in ("stdout_path", "stderr_path"):
                execution[field] = str(args.output / Path(execution[field]).relative_to(staging))
        report = build_report(
            args,
            catalog,
            profile,
            doctor,
            validation,
            doctor_execution,
            validation_execution,
        )
        write_json(staging / "doctor.json", doctor)
        write_json(staging / "validation.json", validation)
        write_json(staging / "workbench-report.json", report)
        (staging / "summary.md").write_text(render_summary(report), encoding="utf-8")
        os.replace(staging, args.output)
    return {
        "status": report["status"],
        "output": str(args.output),
        "report": str(args.output / "workbench-report.json"),
        "summary": str(args.output / "summary.md"),
    }


def _run_evaluations(
    args: argparse.Namespace, staging: Path
) -> tuple[dict, dict]:
    doctor_execution = run_json_command(
        build_doctor_command(args),
        staging / "doctor.stdout.json",
        staging / "doctor.stderr.txt",
        args.evaluation_timeout_secs,
        args.max_json_bytes,
    )
    validation_execution = run_json_command(
        build_validation_command(args),
        staging / "validation.stdout.json",
        staging / "validation.stderr.txt",
        args.evaluation_timeout_secs,
        args.max_json_bytes,
    )
    return doctor_execution, validation_execution


def build_doctor_command(args: argparse.Namespace) -> list[str]:
    command = [str(args.wsi_dicom), "doctor", "--json"]
    if not args.allow_missing_tools:
        command.append("--strict")
    append_validator_options(command, args)
    return command


def build_validation_command(args: argparse.Namespace) -> list[str]:
    command = [
        str(args.wsi_dicom),
        "validate",
        str(args.dicom),
        "--profile",
        "core-2026c" if args.profile else "general",
        "--json",
        "--max-pixel-frames",
        str(args.max_pixel_frames),
        "--command-timeout-secs",
        str(args.command_timeout_secs),
    ]
    if not args.allow_missing_tools:
        command.append("--strict")
    append_validator_options(command, args)
    return command


def append_validator_options(command: list[str], args: argparse.Namespace) -> None:
    if args.dcmvalidate_iod:
        command.extend(["--dcmvalidate-iod", str(args.dcmvalidate_iod)])
    if args.htj2k_decoder:
        command.extend(["--htj2k-decoder", args.htj2k_decoder])


if __name__ == "__main__":
    raise SystemExit(main())
