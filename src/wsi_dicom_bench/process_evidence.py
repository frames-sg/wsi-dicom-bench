"""One bounded subprocess owner for benchmark and workbench evidence."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import BinaryIO, Sequence


DEFAULT_MAX_OUTPUT_BYTES = 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024


class ProcessEvidenceError(RuntimeError):
    """A subprocess could not be launched under the requested evidence policy."""


def read_bounded_text(path: Path, limit: int = DEFAULT_MAX_OUTPUT_BYTES) -> str:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    suffix = "\n[truncated]" if len(data) > limit else ""
    return data[:limit].decode("utf-8", errors="replace") + suffix


def _capture_pipe(
    stream: BinaryIO,
    path: Path,
    max_output_bytes: int,
    capture: dict[str, int | bool | str],
    name: str,
) -> None:
    observed = 0
    retained = 0
    with stream, path.open("wb") as output:
        while True:
            chunk = stream.read(READ_CHUNK_BYTES)
            if not chunk:
                break
            observed += len(chunk)
            remaining = max_output_bytes - retained
            if remaining > 0:
                kept = chunk[:remaining]
                output.write(kept)
                retained += len(kept)
    capture[f"{name}_bytes"] = observed
    capture[f"{name}_truncated"] = observed > max_output_bytes


def _capture_pipe_guarded(
    stream: BinaryIO,
    path: Path,
    max_output_bytes: int,
    capture: dict[str, int | bool | str],
    name: str,
) -> None:
    try:
        _capture_pipe(stream, path, max_output_bytes, capture, name)
    except Exception as exc:  # The main thread re-raises this as policy failure.
        capture[f"{name}_capture_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        stream.close()


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            pass
        # The process-group leader may exit while a descendant ignores SIGTERM.
        # Kill the group even when the immediate child has already been reaped.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        process.kill()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired as exc:
        raise ProcessEvidenceError("timed-out process tree could not be terminated") from exc


def run_bounded_command(
    command: Sequence[str],
    *,
    stdout_path: Path,
    stderr_path: Path,
    timeout_secs: int,
    cwd: Path | None = None,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
) -> dict:
    """Run one command with capped output and retain uninterpreted lifecycle facts."""
    if not command or any(not isinstance(part, str) or not part for part in command):
        raise ProcessEvidenceError("command must contain non-empty string arguments")
    if timeout_secs <= 0:
        raise ProcessEvidenceError("timeout_secs must be positive")
    if (
        isinstance(max_output_bytes, bool)
        or not isinstance(max_output_bytes, int)
        or max_output_bytes <= 0
    ):
        raise ProcessEvidenceError("max_output_bytes must be a positive integer")
    if stdout_path == stderr_path:
        raise ProcessEvidenceError("stdout and stderr evidence paths must differ")
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_bytes(b"")
    stderr_path.write_bytes(b"")

    started = time.monotonic()
    deadline = started + timeout_secs
    timed_out = False
    launch_error: str | None = None
    returncode: int | None = None
    capture: dict[str, int | bool | str] = {
        "stdout_bytes": 0,
        "stderr_bytes": 0,
        "stdout_truncated": False,
        "stderr_truncated": False,
    }

    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=os.name == "posix",
        )
    except OSError as exc:
        launch_error = f"{type(exc).__name__}: {exc}"
        encoded = (launch_error + "\n").encode("utf-8", errors="replace")
        stderr_path.write_bytes(encoded[:max_output_bytes])
        capture["stderr_bytes"] = len(encoded)
        capture["stderr_truncated"] = len(encoded) > max_output_bytes
    else:
        assert process.stdout is not None
        assert process.stderr is not None
        readers = [
            threading.Thread(
                target=_capture_pipe_guarded,
                args=(process.stdout, stdout_path, max_output_bytes, capture, "stdout"),
                daemon=True,
            ),
            threading.Thread(
                target=_capture_pipe_guarded,
                args=(process.stderr, stderr_path, max_output_bytes, capture, "stderr"),
                daemon=True,
            ),
        ]
        for reader in readers:
            reader.start()
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
            for reader in readers:
                reader.join(timeout=max(0, deadline - time.monotonic()))
            timed_out = any(reader.is_alive() for reader in readers)
        except subprocess.TimeoutExpired:
            timed_out = True
        if timed_out:
            _terminate_process_tree(process)
            cleanup_deadline = time.monotonic() + 2
            for reader in readers:
                reader.join(timeout=max(0, cleanup_deadline - time.monotonic()))
        else:
            returncode = process.returncode
        if any(reader.is_alive() for reader in readers):
            # Closing a buffered pipe here can block on a reader's internal lock.
            raise ProcessEvidenceError("subprocess output pipes did not close")
        capture_errors = [
            str(capture[key])
            for key in ("stdout_capture_error", "stderr_capture_error")
            if key in capture
        ]
        if capture_errors:
            raise ProcessEvidenceError(
                "subprocess output capture failed: " + "; ".join(capture_errors)
            )

    return {
        "command": list(command),
        "returncode": returncode,
        "timed_out": timed_out,
        "launch_error": launch_error,
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "max_output_bytes": max_output_bytes,
        **capture,
    }
