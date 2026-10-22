"""Bounded reads of encapsulated Pixel Data frames for independent decoding.

Only item headers are scanned; fragment payloads are read for the selected
frames alone. Frame mapping follows PS3.5 A.4: a Basic or Extended Offset Table
locates frames, and without one each fragment is a frame unless the image has
a single frame.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from typing import BinaryIO


ITEM_TAG = b"\xfe\xff\x00\xe0"
SEQUENCE_DELIMITER_TAG = b"\xfe\xff\xdd\xe0"
ITEM_HEADER_BYTES = 8
UNDEFINED_LENGTH = 0xFFFFFFFF
MAX_BASIC_OFFSET_TABLE_BYTES = 64 * 1024 * 1024


class FrameAssemblyError(ValueError):
    """Encapsulated Pixel Data cannot be mapped to the declared frames."""


@dataclass(frozen=True)
class Fragment:
    """One fragment payload located by its absolute file offset."""

    offset: int
    length: int


@dataclass(frozen=True)
class FrameSpan:
    """Fragments ``start:end`` hold the frame; ``length`` payload bytes are used."""

    start: int
    end: int
    length: int


def read_item_stream(stream: BinaryIO, value_offset: int) -> tuple[list[int], list[Fragment]]:
    """Return the Basic Offset Table and fragment locations after ``value_offset``."""
    stream.seek(0, os.SEEK_END)
    file_size = stream.tell()
    stream.seek(value_offset)
    tag, length = _read_item_header(stream)
    if tag != ITEM_TAG:
        raise FrameAssemblyError("Pixel Data does not start with a Basic Offset Table item")
    if length == UNDEFINED_LENGTH or length % 4:
        raise FrameAssemblyError("Basic Offset Table length is not a multiple of 4")
    if length > MAX_BASIC_OFFSET_TABLE_BYTES:
        raise FrameAssemblyError(
            f"Basic Offset Table exceeds the {MAX_BASIC_OFFSET_TABLE_BYTES}-byte limit"
        )
    table = stream.read(length)
    if len(table) != length:
        raise FrameAssemblyError("Basic Offset Table is truncated")
    basic_offsets = list(struct.unpack(f"<{length // 4}I", table))

    fragments = []
    while True:
        tag, length = _read_item_header(stream)
        if tag == SEQUENCE_DELIMITER_TAG:
            return basic_offsets, fragments
        if tag != ITEM_TAG:
            raise FrameAssemblyError(f"Pixel Data item stream has unexpected tag {tag.hex()}")
        if length == UNDEFINED_LENGTH:
            raise FrameAssemblyError("Pixel Data fragment has an undefined length")
        offset = stream.tell()
        if offset + length > file_size:
            raise FrameAssemblyError("Pixel Data fragment extends past the end of the file")
        fragments.append(Fragment(offset, length))
        stream.seek(length, os.SEEK_CUR)


def _read_item_header(stream: BinaryIO) -> tuple[bytes, int]:
    header = stream.read(ITEM_HEADER_BYTES)
    if len(header) != ITEM_HEADER_BYTES:
        raise FrameAssemblyError("Pixel Data ends before its Sequence Delimitation Item")
    return header[:4], struct.unpack("<I", header[4:])[0]


def frame_spans(
    fragments: list[Fragment],
    frame_count: int,
    basic_offsets: list[int],
    extended_offsets: list[int] | None,
    extended_lengths: list[int] | None,
    max_frame_bytes: int,
) -> list[FrameSpan]:
    """Map every declared frame to its fragments, rejecting inconsistent tables."""
    if not fragments:
        raise FrameAssemblyError("Pixel Data has no fragments")
    offsets = extended_offsets or basic_offsets
    lengths = extended_lengths or None
    if lengths is not None and not extended_offsets:
        raise FrameAssemblyError("Extended Offset Table Lengths requires an Extended Offset Table")
    if lengths is not None and len(lengths) != frame_count:
        raise FrameAssemblyError(
            f"Extended Offset Table Lengths has {len(lengths)} entries for {frame_count} frames"
        )

    if not offsets:
        if frame_count == 1:
            ranges = [(0, len(fragments))]
        elif frame_count != len(fragments):
            raise FrameAssemblyError(
                f"cannot map {len(fragments)} Pixel Data fragments to {frame_count} frames "
                "without an offset table"
            )
        else:
            ranges = [(index, index + 1) for index in range(frame_count)]
    else:
        ranges = _offset_table_ranges(fragments, frame_count, offsets)
    return [
        _validated_span(fragments, lengths, max_frame_bytes, frame_index, start, end)
        for frame_index, (start, end) in enumerate(ranges)
    ]


def _offset_table_ranges(
    fragments: list[Fragment], frame_count: int, offsets: list[int]
) -> list[tuple[int, int]]:
    if len(offsets) != frame_count:
        raise FrameAssemblyError(
            f"Pixel Data offset table has {len(offsets)} entries for {frame_count} frames"
        )
    if offsets[0] != 0 or any(
        offsets[index - 1] >= offsets[index] for index in range(1, frame_count)
    ):
        raise FrameAssemblyError("Pixel Data frame offsets are not strictly increasing from zero")
    ranges = []
    fragment_index = 0
    fragment_offset = 0
    for frame_index in range(frame_count):
        if fragment_offset != offsets[frame_index]:
            raise FrameAssemblyError(
                f"Pixel Data frame offset {offsets[frame_index]} does not identify a fragment boundary"
            )
        start = fragment_index
        expected_end = offsets[frame_index + 1] if frame_index + 1 < frame_count else None
        while fragment_index < len(fragments) and (
            expected_end is None or fragment_offset < expected_end
        ):
            fragment_offset += ITEM_HEADER_BYTES + fragments[fragment_index].length
            fragment_index += 1
        if expected_end is not None and fragment_offset != expected_end:
            raise FrameAssemblyError(
                f"Pixel Data frame offset {expected_end} does not identify a fragment boundary"
            )
        ranges.append((start, fragment_index))
    if fragment_index != len(fragments):
        raise FrameAssemblyError("Pixel Data offset table does not map all fragments")
    return ranges


def _validated_span(
    fragments: list[Fragment],
    lengths: list[int] | None,
    max_frame_bytes: int,
    frame_index: int,
    start: int,
    end: int,
) -> FrameSpan:
    if start >= end or end > len(fragments):
        raise FrameAssemblyError(f"Pixel Data frame {frame_index} has an empty or invalid fragment span")
    assembled = sum(fragment.length for fragment in fragments[start:end])
    length = lengths[frame_index] if lengths is not None else assembled
    if length == 0:
        raise FrameAssemblyError(f"Pixel Data frame {frame_index} is empty")
    if length > assembled:
        if end == start + 1 and length - assembled == ITEM_HEADER_BYTES:
            raise FrameAssemblyError(
                f"Pixel Data frame {frame_index} Extended Offset Table Lengths entry includes "
                "the 8-byte Item header; DICOM requires only Frame payload bytes"
            )
        raise FrameAssemblyError(
            f"Pixel Data frame {frame_index} declares {length} bytes but only {assembled} are available"
        )
    if length > max_frame_bytes:
        raise FrameAssemblyError(
            f"Pixel Data frame {frame_index} exceeds {max_frame_bytes} byte validation limit"
        )
    return FrameSpan(start, end, length)


def read_frame(stream: BinaryIO, fragments: list[Fragment], span: FrameSpan) -> bytes:
    """Concatenate the span's fragment payloads, truncated to its frame length."""
    parts = []
    remaining = span.length
    for fragment in fragments[span.start:span.end]:
        if remaining == 0:
            break
        stream.seek(fragment.offset)
        part = stream.read(min(fragment.length, remaining))
        if len(part) != min(fragment.length, remaining):
            raise FrameAssemblyError("Pixel Data fragment is truncated")
        parts.append(part)
        remaining -= len(part)
    return b"".join(parts)
