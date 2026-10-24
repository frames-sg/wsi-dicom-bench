"""Independent-decoder frame checks owned by the bench.

wsi-dicom never runs external codecs. The bench decodes a bounded sample of
each instance's encapsulated frames with decoders that wsi-dicom does not use
(libjpeg-turbo ``djpeg``, OpenJPEG ``opj_decompress``, and an HTJ2K decoder),
then checks the decoded matrix against Rows, Columns, Samples per Pixel and
Bits Allocated. Checks keep the names and record shape that the rule catalog
maps to ``pixel-decode-wsi-dicom-2026c-frame-geometry``.
"""

from __future__ import annotations

import os
import shlex
import shutil
import struct
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import Path

from wsi_dicom_bench.file_digest import sha256_file
from wsi_dicom_bench.pnm import inspect_pnm
from wsi_dicom_bench.process_evidence import read_bounded_text, run_bounded_command

from .encapsulated_frames import FrameAssemblyError, frame_spans, read_frame, read_item_stream


BENCH_OWNED_CHECKS = frozenset({"pixel-decode", "pixel-djpeg", "pixel-opj-decompress", "pixel-htj2k"})
AUTO_HTJ2K_DECODER_COMMAND = "grk_decompress"
DEFAULT_MAX_PIXEL_FRAME_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_DECODER_OUTPUT_BYTES = 4 * 1024 * 1024
DEFER_METADATA_VALUES_ABOVE = "1 KB"
JPEG_BASELINE_8BIT = "1.2.840.10008.1.2.4.50"
JPEG_2000_LOSSLESS = "1.2.840.10008.1.2.4.90"
JPEG_2000 = "1.2.840.10008.1.2.4.91"
HTJ2K_LOSSLESS = "1.2.840.10008.1.2.4.201"
HTJ2K_LOSSLESS_RPCL = "1.2.840.10008.1.2.4.202"
HTJ2K = "1.2.840.10008.1.2.4.203"


@dataclass(frozen=True)
class DecodePolicy:
    """Bounds and tool requirements for one decode stage."""

    max_frames: int
    strict: bool
    timeout_secs: int
    htj2k_decoder: str | None = None
    max_frame_bytes: int = DEFAULT_MAX_PIXEL_FRAME_BYTES
    max_output_bytes: int = DEFAULT_MAX_DECODER_OUTPUT_BYTES


@dataclass(frozen=True)
class Decoder:
    """An external decoder resolved for one transfer syntax family."""

    check_name: str
    command_name: str
    executable: str | None
    arguments: tuple[str, ...]
    input_suffix: str


@dataclass(frozen=True)
class FrameExpectation:
    columns: int
    rows: int
    samples_per_pixel: int | None
    bits_allocated: int | None


class DecoderConfigurationError(ValueError):
    """The configured HTJ2K decoder template cannot be executed."""


def run_pixel_decode_checks(files: list[str], policy: DecodePolicy) -> dict:
    """Decode sampled frames of every file; return checks and decoder provenance."""
    decoders: dict[str, Decoder | None] = {}
    checks = []
    with tempfile.TemporaryDirectory(prefix="wsi-dicom-bench-decode-") as temporary:
        root = Path(temporary)
        for file_index, path in enumerate(files):
            checks.extend(_file_checks(file_index, path, policy, root, decoders))
    return {
        "schema_version": "wsi-dicom-bench-pixel-decode-v1",
        "policy": {
            "max_frames_per_file": policy.max_frames,
            "max_frame_bytes": policy.max_frame_bytes,
            "strict_decoders": policy.strict,
            "command_timeout_secs": policy.timeout_secs,
        },
        "decoders": [
            _decoder_provenance(family, decoder) for family, decoder in sorted(decoders.items())
        ],
        "checks": checks,
    }


def _file_checks(
    file_index: int,
    path: str,
    policy: DecodePolicy,
    root: Path,
    decoders: dict[str, Decoder | None],
) -> list[dict]:
    import pydicom

    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            dataset = pydicom.dcmread(path, defer_size=DEFER_METADATA_VALUES_ABOVE)
    except OSError as exc:
        return [_execution_failed_check("pixel-decode", path, f"cannot read {path}: {exc}", "io")]
    except Exception as exc:  # pydicom raises many exception types for malformed files
        message = f"cannot parse DICOM metadata: {type(exc).__name__}: {exc}"
        return [_failed_check("pixel-decode", path, message)]
    if len(dataset) == 0:
        # pydicom returns an empty Data Set, with only a warning, for some malformed
        # streams, such as encapsulated Pixel Data that ends the file without its delimiter.
        reason = "; ".join(str(warning.message) for warning in caught) or "no Data Element was read"
        return [_failed_check("pixel-decode", path, f"cannot parse DICOM metadata: {reason}")]
    file_meta = getattr(dataset, "file_meta", None) or {}
    transfer_syntax = str(file_meta.get("TransferSyntaxUID", "")).rstrip("\0")
    family = _decoder_family(transfer_syntax)
    if family is None:
        return [
            _skipped_check(
                "pixel-decode", path, f"pixel decode not needed for transfer syntax {transfer_syntax}"
            )
        ]
    if family not in decoders:
        try:
            decoders[family] = _resolve_decoder(family, policy)
        except DecoderConfigurationError as exc:
            return [_execution_failed_check("pixel-htj2k", path, str(exc), "configuration")]
    decoder = decoders[family]
    if decoder is None:
        return [_unconfigured_htj2k_check(path, policy.strict)]
    try:
        expected = _frame_expectation(dataset)
        frames = _selected_frames(path, dataset, policy)
    except FrameAssemblyError as exc:
        return [_failed_check("pixel-decode", path, str(exc))]
    except OSError as exc:
        return [_execution_failed_check("pixel-decode", path, f"cannot read Pixel Data: {exc}", "io")]
    return [
        _decode_frame(decoder, path, root / f"file-{file_index:04d}-frame-{frame_index:06d}", frame, expected, policy)
        for frame_index, frame in enumerate(frames)
    ]


def _decoder_family(transfer_syntax: str) -> str | None:
    if transfer_syntax == JPEG_BASELINE_8BIT:
        return "jpeg"
    if transfer_syntax in {JPEG_2000, JPEG_2000_LOSSLESS}:
        return "jpeg2000"
    if transfer_syntax in {HTJ2K, HTJ2K_LOSSLESS, HTJ2K_LOSSLESS_RPCL}:
        return "htj2k"
    return None


def _resolve_decoder(family: str, policy: DecodePolicy) -> Decoder | None:
    if family == "jpeg":
        return Decoder("pixel-djpeg", "djpeg", shutil.which("djpeg"), ("-outfile", "{output}", "{input}"), ".jpg")
    if family == "jpeg2000":
        return Decoder(
            "pixel-opj-decompress",
            "opj_decompress",
            shutil.which("opj_decompress"),
            ("-i", "{input}", "-o", "{output}"),
            ".j2k",
        )
    template = policy.htj2k_decoder or _auto_htj2k_template()
    if template is None:
        return None
    command, arguments = htj2k_decoder_command(template)
    executable = command if Path(command).is_file() else None
    return Decoder("pixel-htj2k", command, executable, arguments, ".j2k")


def _auto_htj2k_template() -> str | None:
    found = shutil.which(AUTO_HTJ2K_DECODER_COMMAND)
    if found is None or not Path(found).is_absolute():
        return None
    return f"{shlex.quote(found)} -i {{input}} -o {{output}}"


def htj2k_decoder_command(template: str) -> tuple[str, tuple[str, ...]]:
    """Split an HTJ2K template into an absolute command and placeholder arguments."""
    try:
        parts = shlex.split(template)
    except ValueError as exc:
        raise DecoderConfigurationError("HTJ2K decoder command has invalid quoting") from exc
    if not parts or not parts[0].strip():
        raise DecoderConfigurationError("HTJ2K decoder command is empty")
    command, arguments = parts[0], parts[1:]
    if not Path(command).is_absolute():
        raise DecoderConfigurationError(
            "HTJ2K decoder command must start with an absolute executable path"
        )
    if not any("{input}" in part or "{output}" in part for part in arguments):
        arguments.append("{input}")
    return command, tuple(arguments)


def _frame_expectation(dataset) -> FrameExpectation:
    columns = _required_positive_int(dataset, "Columns")
    rows = _required_positive_int(dataset, "Rows")
    return FrameExpectation(
        columns=columns,
        rows=rows,
        samples_per_pixel=_optional_int(dataset, "SamplesPerPixel"),
        bits_allocated=_optional_int(dataset, "BitsAllocated"),
    )


def _required_positive_int(dataset, keyword: str) -> int:
    if keyword not in dataset:
        raise FrameAssemblyError(f"DICOM {_label(keyword)} is missing")
    value = _optional_int(dataset, keyword)
    if value is None or value <= 0:
        raise FrameAssemblyError(f"DICOM {_label(keyword)} must be greater than zero")
    return value


def _optional_int(dataset, keyword: str) -> int | None:
    if keyword not in dataset or dataset[keyword].value in (None, ""):
        return None
    try:
        return int(dataset[keyword].value)
    except (TypeError, ValueError) as exc:
        raise FrameAssemblyError(f"failed to read DICOM {_label(keyword)}: {exc}") from exc


def _label(keyword: str) -> str:
    return {
        "Columns": "Columns",
        "Rows": "Rows",
        "SamplesPerPixel": "Samples per Pixel",
        "BitsAllocated": "Bits Allocated",
        "NumberOfFrames": "Number of Frames",
    }.get(keyword, keyword)


def _selected_frames(path: str, dataset, policy: DecodePolicy) -> list[bytes]:
    frame_count = _required_positive_int(dataset, "NumberOfFrames")
    pixel_data = dataset.get_item("PixelData", keep_deferred=True)
    if pixel_data is None:
        raise FrameAssemblyError("failed to read Pixel Data: element is missing")
    if getattr(pixel_data, "length", None) != 0xFFFFFFFF:
        raise FrameAssemblyError("compressed Pixel Data is not encapsulated")
    extended_offsets = _optional_u64_values(dataset, "ExtendedOffsetTable")
    extended_lengths = _optional_u64_values(dataset, "ExtendedOffsetTableLengths")
    with open(path, "rb") as stream:
        basic_offsets, fragments = read_item_stream(stream, pixel_data.value_tell)
        spans = frame_spans(
            fragments, frame_count, basic_offsets, extended_offsets, extended_lengths, policy.max_frame_bytes
        )
        return [read_frame(stream, fragments, span) for span in spans[: policy.max_frames]]


def _optional_u64_values(dataset, keyword: str) -> list[int] | None:
    if keyword not in dataset:
        return None
    value = dataset[keyword].value
    if value is None:
        return []
    if not isinstance(value, bytes) or len(value) % 8:
        raise FrameAssemblyError(f"failed to read DICOM element {keyword}: not a 64-bit value list")
    return list(struct.unpack(f"<{len(value) // 8}Q", value))


def _decode_frame(
    decoder: Decoder,
    path: str,
    stem: Path,
    frame: bytes,
    expected: FrameExpectation,
    policy: DecodePolicy,
) -> dict:
    source = stem.with_suffix(decoder.input_suffix)
    output = stem.with_suffix(".ppm")
    try:
        _write_private_file(source, frame)
    except OSError as exc:
        return _execution_failed_check("pixel-decode", path, f"failed to write temporary codestream: {exc}", "io")
    arguments = [
        argument.replace("{input}", str(source)).replace("{output}", str(output))
        for argument in decoder.arguments
    ]
    check = _command_check(decoder, path, arguments, stem, policy)
    if check["status"] != "passed":
        return check
    try:
        inspect_pnm_output(output, expected, policy.max_frame_bytes)
    except ValueError as exc:
        check["status"] = "failed"
        check["message"] = str(exc)
        if not output.is_file():
            check["execution"]["failure"] = "io"
    return check


def _command_check(decoder: Decoder, path: str, arguments: list[str], stem: Path, policy: DecodePolicy) -> dict:
    check = _check(decoder.check_name, path, "failed", "", [decoder.command_name, *arguments])
    check["execution"] = {"return_code": None, "elapsed_millis": 0, "failure": None}
    if decoder.executable is None:
        check["status"] = "failed" if policy.strict else "skipped"
        check["message"] = f"{decoder.command_name} not found"
        check["execution"]["failure"] = "unavailable"
        return check
    evidence = run_bounded_command(
        [decoder.executable, *arguments],
        stdout_path=stem.with_suffix(".stdout.txt"),
        stderr_path=stem.with_suffix(".stderr.txt"),
        timeout_secs=policy.timeout_secs,
        max_output_bytes=policy.max_output_bytes,
    )
    check["stdout"] = read_bounded_text(Path(evidence["stdout_path"]), policy.max_output_bytes)
    check["stderr"] = read_bounded_text(Path(evidence["stderr_path"]), policy.max_output_bytes)
    check["execution"].update(
        return_code=evidence["returncode"],
        elapsed_millis=int(evidence["elapsed_seconds"] * 1000),
    )
    name = decoder.command_name
    if evidence["launch_error"] is not None:
        check["execution"]["failure"] = "launch"
        check["message"] = f"failed to start {name}: {evidence['launch_error']}"
    elif evidence["timed_out"]:
        check["execution"]["failure"] = "timeout"
        check["message"] = f"{name} timed out after {policy.timeout_secs}s"
    elif evidence["stdout_truncated"] or evidence["stderr_truncated"]:
        check["execution"]["failure"] = "output_limit"
        check["message"] = f"{name} output exceeded {policy.max_output_bytes} byte capture limit"
    elif evidence["returncode"] is None:
        check["execution"]["failure"] = "terminated"
        check["message"] = f"{name} did not complete"
    elif evidence["returncode"] == 0:
        check["status"] = "passed"
        check["message"] = f"{name} passed"
    else:
        check["message"] = f"{name} failed"
    return check


def inspect_pnm_output(output: Path, expected: FrameExpectation, max_decoded_bytes: int) -> None:
    """Require a binary PGM/PPM whose header and payload match the DICOM frame."""
    info = inspect_pnm(output, max_decoded_bytes)
    columns, rows = info.width, info.height
    components, max_value = info.components, info.maximum
    if (columns, rows) != (expected.columns, expected.rows):
        raise ValueError(
            f"decoder output dimensions {columns}x{rows} do not match DICOM "
            f"{expected.columns}x{expected.rows}"
        )
    if expected.samples_per_pixel is not None and expected.samples_per_pixel != components:
        raise ValueError(
            f"decoder output has {components} component(s), expected {expected.samples_per_pixel}"
        )
    if max_value not in {255, 65535}:
        raise ValueError(f"decoder output maximum sample value {max_value} is unsupported")
    if expected.bits_allocated is not None:
        expected_max = {8: 255, 16: 65535}.get(expected.bits_allocated)
        if expected_max is None:
            raise ValueError(
                f"DICOM Bits Allocated {expected.bits_allocated} is unsupported for PNM validation"
            )
        if max_value != expected_max:
            raise ValueError(
                f"decoder output maximum sample value {max_value} does not match "
                f"{expected.bits_allocated}-bit DICOM pixels"
            )


def _write_private_file(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)


def _decoder_provenance(family: str, decoder: Decoder | None) -> dict:
    if decoder is None:
        return {"family": family, "command": None, "path": None, "sha256": None}
    executable = Path(decoder.executable) if decoder.executable else None
    return {
        "family": family,
        "command": decoder.command_name,
        "path": decoder.executable,
        "sha256": sha256_file(executable) if executable and executable.is_file() else None,
    }


def _unconfigured_htj2k_check(path: str, strict: bool) -> dict:
    check = _check("pixel-htj2k", path, "failed" if strict else "skipped", "HTJ2K decoder command is not configured")
    check["execution"] = {"return_code": None, "elapsed_millis": 0, "failure": "unavailable"}
    return check


def _execution_failed_check(name: str, path: str, message: str, failure: str) -> dict:
    check = _check(name, path, "failed", message)
    check["execution"] = {"return_code": None, "elapsed_millis": 0, "failure": failure}
    return check


def _failed_check(name: str, path: str, message: str) -> dict:
    return _check(name, path, "failed", message)


def _skipped_check(name: str, path: str, message: str) -> dict:
    return _check(name, path, "skipped", message)


def _check(name: str, path: str, status: str, message: str, command: list[str] | None = None) -> dict:
    return {
        "name": name,
        "path": path,
        "status": status,
        "command": command or [],
        "message": message,
        "stdout": "",
        "stderr": "",
    }
