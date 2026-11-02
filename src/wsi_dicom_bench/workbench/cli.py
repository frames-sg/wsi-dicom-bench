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
from wsi_dicom_bench.process_evidence import run_bounded_command

from .catalog import CatalogError, load_catalog
from .contract import expected_rule_set_id
from .execution import WorkbenchError, run_json_command
from .pixel_decode import DecodePolicy, run_pixel_decode_checks
from .report import build_report, render_summary


RULES_DIR = Path(str(importlib.resources.files("wsi_dicom_bench.rules")))
DEFAULT_CATALOG = RULES_DIR / "wsi-dicom-bench-rules-2026c-v6.json"
# The catalogs that pair with a core profile.
PROFILE_CATALOGS = frozenset({"wsi-dicom-bench-rules-2026c-v6"})


def expected_profile_id(catalog: dict) -> str | None:
    """Return the core profile ID a catalog pairs with (its core rule set), or None."""
    if catalog.get("catalog_version") not in PROFILE_CATALOGS:
        return None
    return expected_rule_set_id(catalog, "core-2026c")


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
        "--validation-profile",
        choices=("general", "core"),
        default="general",
        help="candidate validation profile; independent of the legacy --profile definition file",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        help="machine-readable VL WSI core profile; required by versioned core-profile benchmark runs",
    )
    parser.add_argument("--allow-missing-tools", action="store_true")
    parser.add_argument("--dcmvalidate-iod", type=Path)
    parser.add_argument(
        "--dicom-validator-standard-path",
        type=Path,
        help="task-specific dicom-validator definition root used for provenance",
    )
    parser.add_argument(
        "--htj2k-decoder",
        help="absolute HTJ2K decoder command template with {input} and {output}; "
        "grk_decompress on PATH is used when omitted",
    )
    parser.add_argument(
        "--max-pixel-frames",
        type=positive_int,
        default=1,
        help="frames per instance that the bench decodes with independent decoders",
    )
    parser.add_argument(
        "--max-input-bytes",
        type=positive_int,
        help="per-file input limit forwarded to wsi-dicom validate; its own default applies when omitted",
    )
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
    if profile and getattr(args, "validation_profile", "general") != "general":
        raise WorkbenchError("--validation-profile cannot be combined with --profile")
    expected_profile = expected_profile_id(catalog)
    if profile and profile["profile_id"] != expected_profile:
        raise WorkbenchError("catalog and selected profile version are incompatible")
    if profile and profile["dicom_edition"] != catalog["dicom_edition"]:
        raise WorkbenchError("profile and rule catalog use different DICOM editions")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{args.output.name}.staging-", dir=args.output.parent
    ) as temporary:
        staging = Path(temporary)
        legacy = wsi_dicom_runs_pixel_decode(args.wsi_dicom, args.command_timeout_secs)
        doctor_execution, validation_execution = _run_evaluations(args, staging, legacy)
        doctor = doctor_execution.pop("document")
        validation = validation_execution.pop("document")
        for execution in (doctor_execution, validation_execution):
            for field in ("stdout_path", "stderr_path"):
                execution[field] = str(args.output / Path(execution[field]).relative_to(staging))
        candidate_unreadable_files = _candidate_unreadable_files(validation)
        unreadable_paths = {item["path"] for item in candidate_unreadable_files}
        decoding = run_pixel_decode_checks(
            [path for path in _validated_files(validation) if path not in unreadable_paths],
            DecodePolicy(
                max_frames=args.max_pixel_frames,
                strict=not args.allow_missing_tools,
                timeout_secs=args.command_timeout_secs,
                htj2k_decoder=args.htj2k_decoder,
            ),
        )
        decoding["wsi_dicom_pixel_decode"] = (
            "disabled_with_max_pixel_frames_0" if legacy else "not_supported"
        )
        decoding["candidate_unreadable_files"] = candidate_unreadable_files
        report = build_report(
            args,
            catalog,
            profile,
            doctor,
            validation,
            decoding,
            doctor_execution,
            validation_execution,
        )
        write_json(staging / "doctor.json", doctor)
        write_json(staging / "validation.json", validation)
        write_json(staging / "pixel-decode.json", decoding)
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
    args: argparse.Namespace, staging: Path, legacy: bool
) -> tuple[dict, dict]:
    doctor_execution = run_json_command(
        build_doctor_command(args, legacy),
        staging / "doctor.stdout.json",
        staging / "doctor.stderr.txt",
        args.evaluation_timeout_secs,
        args.max_json_bytes,
    )
    validation_execution = run_json_command(
        build_validation_command(args, legacy),
        staging / "validation.stdout.json",
        staging / "validation.stderr.txt",
        args.evaluation_timeout_secs,
        args.max_json_bytes,
    )
    return doctor_execution, validation_execution


def wsi_dicom_runs_pixel_decode(wsi_dicom: Path, timeout_secs: int) -> bool:
    """Whether this wsi-dicom still decodes frames itself (releases through 0.8.0).

    Those releases accept ``--max-pixel-frames``; the bench passes 0 so that only
    its own decoder stage runs. A failed probe is treated as a current release.
    """
    with tempfile.TemporaryDirectory(prefix="wsi-workbench-probe-") as temporary:
        root = Path(temporary)
        execution = run_bounded_command(
            [str(wsi_dicom), "validate", "--help"],
            stdout_path=root / "stdout.txt",
            stderr_path=root / "stderr.txt",
            timeout_secs=min(timeout_secs, 30),
            max_output_bytes=256 * 1024,
        )
        help_text = (root / "stdout.txt").read_text(encoding="utf-8", errors="replace")
    return execution["returncode"] == 0 and "--max-pixel-frames" in help_text


def _validated_files(validation: object) -> list[str]:
    files = validation.get("files") if isinstance(validation, dict) else None
    if not isinstance(files, list) or not all(isinstance(path, str) and path for path in files):
        return []
    return files


def _candidate_unreadable_files(validation: object) -> list[dict[str, str]]:
    """Return files the candidate could not parse, bounded to one mapped check shape."""
    files = set(_validated_files(validation))
    checks = validation.get("checks") if isinstance(validation, dict) else None
    if not isinstance(checks, list):
        return []
    unreadable = []
    seen = set()
    for check in checks:
        if not isinstance(check, dict):
            continue
        path = check.get("path")
        reason = check.get("message")
        if (
            check.get("name") != "intrinsic-pixel-structure"
            or check.get("status") != "failed"
            or path not in files
            or path in seen
            or not isinstance(reason, str)
            or not reason.startswith("failed to read DICOM file:")
        ):
            continue
        unreadable.append({"path": path, "reason": reason})
        seen.add(path)
    return unreadable


def build_doctor_command(args: argparse.Namespace, legacy: bool = False) -> list[str]:
    command = [str(args.wsi_dicom), "doctor", "--json"]
    if not args.allow_missing_tools:
        command.append("--strict")
    append_validator_options(command, args)
    if legacy and args.htj2k_decoder:
        # Releases through 0.8.0 probe the HTJ2K decoder in strict doctor runs.
        command.extend(["--htj2k-decoder", args.htj2k_decoder])
    return command


def build_validation_command(args: argparse.Namespace, legacy: bool = False) -> list[str]:
    validation_profile = (
        "core-2026c" if args.profile else getattr(args, "validation_profile", "general")
    )
    command = [
        str(args.wsi_dicom),
        "validate",
        str(args.dicom),
        "--profile",
        validation_profile,
        "--json",
        "--command-timeout-secs",
        str(args.command_timeout_secs),
    ]
    if legacy:
        command.extend(["--max-pixel-frames", "0"])
    if args.max_input_bytes is not None:
        command.extend(["--max-input-bytes", str(args.max_input_bytes)])
    if not args.allow_missing_tools:
        command.append("--strict")
    append_validator_options(command, args)
    return command


def append_validator_options(command: list[str], args: argparse.Namespace) -> None:
    if args.dcmvalidate_iod:
        command.extend(["--dcmvalidate-iod", str(args.dcmvalidate_iod)])


if __name__ == "__main__":
    raise SystemExit(main())
