"""Bounded subprocess execution and retained document failures."""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

from wsi_dicom_bench.process_evidence import read_bounded_text, run_bounded_command


class WorkbenchError(RuntimeError):
    """A complete workbench evaluation could not be produced."""


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"non-finite JSON number: {value}")
    return number


def run_json_command(
    command: list[str],
    stdout_path: Path,
    stderr_path: Path,
    timeout_secs: int,
    max_json_bytes: int,
) -> dict:
    execution = run_bounded_command(
        command,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        timeout_secs=timeout_secs,
        max_output_bytes=max_json_bytes,
    )
    document = None
    error = None
    if execution["timed_out"]:
        error = f"command timed out after {timeout_secs}s"
    elif execution["launch_error"] is not None:
        error = f"command could not be launched: {execution['launch_error']}"
    elif execution["stdout_truncated"] or execution["stderr_truncated"]:
        error = f"command output exceeds max-json-bytes={max_json_bytes}"
    else:
        try:
            document = json.loads(
                stdout_path.read_text(encoding="utf-8"),
                parse_constant=_finite_float,
                parse_float=_finite_float,
            )
        except (UnicodeDecodeError, ValueError) as exc:
            error = f"command produced invalid JSON: {exc}"
    return {
        **execution,
        "stderr": read_bounded_text(stderr_path),
        "document": document,
        "document_error": error,
    }


def run_text_command(
    command: list[str], timeout_secs: int, max_output_bytes: int
) -> str:
    with tempfile.TemporaryDirectory(prefix="wsi-workbench-text-") as temporary:
        root = Path(temporary)
        stdout_path = root / "stdout.txt"
        stderr_path = root / "stderr.txt"
        execution = run_bounded_command(
            command,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout_secs=timeout_secs,
            max_output_bytes=max_output_bytes,
        )
        combined = stdout_path.read_bytes() + stderr_path.read_bytes()
    if execution["timed_out"]:
        raise WorkbenchError(f"command timed out after {timeout_secs}s: {command}")
    if execution["launch_error"] is not None:
        raise WorkbenchError(
            f"command could not be launched: {command}: {execution['launch_error']}"
        )
    if (
        execution["stdout_truncated"]
        or execution["stderr_truncated"]
        or execution["stdout_bytes"] + execution["stderr_bytes"] > max_output_bytes
    ):
        raise WorkbenchError(f"command output exceeds {max_output_bytes} bytes: {command}")
    text = combined.decode("utf-8", errors="replace").strip()
    if execution["returncode"] != 0 or not text:
        raise WorkbenchError(
            f"command failed to report a version: {command}; returncode={execution['returncode']}"
        )
    return text
