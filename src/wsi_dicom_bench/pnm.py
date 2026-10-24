"""Bounded parsing for binary PGM and PPM decoder output."""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


MAX_PNM_TOKEN_BYTES = 64
MAX_PNM_HEADER_BYTES = 4096


@dataclass(frozen=True)
class PnmInfo:
    magic: str
    width: int
    height: int
    maximum: int
    components: int
    payload_offset: int
    payload_bytes: int


def _read_token(stream: BinaryIO) -> str:
    token = bytearray()
    in_comment = False
    while True:
        byte = stream.read(1)
        if stream.tell() > MAX_PNM_HEADER_BYTES:
            raise ValueError(
                f"decoder output PNM header exceeds {MAX_PNM_HEADER_BYTES} bytes"
            )
        if not byte:
            if not token:
                raise ValueError("decoder output ended inside the PNM header")
            break
        if in_comment:
            in_comment = byte != b"\n"
            continue
        if not token and byte == b"#":
            in_comment = True
            continue
        if byte.isspace():
            if not token:
                continue
            break
        token += byte
        if len(token) > MAX_PNM_TOKEN_BYTES:
            raise ValueError(
                f"decoder output PNM header token exceeds {MAX_PNM_TOKEN_BYTES} bytes"
            )
    try:
        return token.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError(f"decoder output PNM header is not ASCII: {exc}") from exc


def _parse_int(stream: BinaryIO, field: str) -> int:
    token = _read_token(stream)
    if not token.isdigit():
        raise ValueError(f"decoder output has invalid PNM {field} {token!r}")
    return int(token)


def _inspect(stream: BinaryIO, file_len: int) -> PnmInfo:
    magic = _read_token(stream)
    components = {"P5": 1, "P6": 3}.get(magic)
    if components is None:
        raise ValueError(f"decoder output uses unsupported PNM magic {magic!r}")
    width = _parse_int(stream, "width")
    height = _parse_int(stream, "height")
    maximum = _parse_int(stream, "maximum sample value")
    if width <= 0 or height <= 0 or not 0 < maximum <= 65535:
        raise ValueError("decoder output has unsupported PNM geometry or sample range")
    payload_offset = stream.tell()
    if payload_offset > MAX_PNM_HEADER_BYTES:
        raise ValueError(
            f"decoder output PNM header exceeds {MAX_PNM_HEADER_BYTES} bytes"
        )
    payload_bytes = width * height * components * (2 if maximum > 255 else 1)
    actual = max(file_len - payload_offset, 0)
    if actual != payload_bytes:
        raise ValueError(
            f"decoder output payload has {actual} bytes, expected {payload_bytes}"
        )
    return PnmInfo(
        magic,
        width,
        height,
        maximum,
        components,
        payload_offset,
        payload_bytes,
    )


def _read_path(
    path: Path, max_bytes: int, *, include_payload: bool
) -> tuple[PnmInfo, bytes | None]:
    try:
        stream = path.open("rb")
    except OSError as exc:
        raise ValueError(f"decoder did not create readable output {path}: {exc}") from exc
    with stream:
        file_len = os.fstat(stream.fileno()).st_size
        if file_len > max_bytes:
            raise ValueError(
                f"decoder output {path} exceeds {max_bytes} byte validation limit"
            )
        info = _inspect(stream, file_len)
        if not include_payload:
            return info, None
        payload = stream.read(info.payload_bytes)
        if len(payload) != info.payload_bytes:
            raise ValueError(
                f"decoder output payload has {len(payload)} bytes, expected {info.payload_bytes}"
            )
        return info, payload


def inspect_pnm(path: Path, max_bytes: int) -> PnmInfo:
    """Inspect a PNM header and size without loading its pixel payload."""
    info, _ = _read_path(path, max_bytes, include_payload=False)
    return info


def read_pnm(path: Path, max_bytes: int) -> tuple[str, int, int, int, bytes]:
    """Read one bounded PNM file and return its canonical header fields and payload."""
    info, payload = _read_path(path, max_bytes, include_payload=True)
    assert payload is not None
    return info.magic, info.width, info.height, info.maximum, payload


def parse_pnm_bytes(data: bytes) -> tuple[str, int, int, int, bytes]:
    """Parse an already bounded in-memory PNM document."""
    stream = io.BytesIO(data)
    info = _inspect(stream, len(data))
    return info.magic, info.width, info.height, info.maximum, data[info.payload_offset :]
