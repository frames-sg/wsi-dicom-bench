"""Small format-specific defects that preserve the surrounding Frame structure."""
from __future__ import annotations

import struct

from ..model import GenerationError
from .codestream import _rewrap, _segments
from .dicom import frames, set_case_sop


def null_mcc(index: int, groups: tuple[tuple[int, ...], ...]) -> bytes:
    """T.801 A.3.8/J.3: array transforms with zero array indices are identity."""
    payload = bytearray(struct.pack(">HBHH", 0, index, 0, len(groups)))
    for components in groups:
        payload += bytes([1]) + struct.pack(">H", len(components)) + bytes(components)
        payload += struct.pack(">H", len(components)) + bytes(components) + b"\0\0\0"
    return b"\xff\x75" + struct.pack(">H", len(payload) + 2) + payload


def with_identity_stage(frame: bytes) -> bytes:
    """Append one null stage after the control's single array-based ICT stage."""
    segments = _segments(frame)
    mco = [(a, b) for marker, a, b in segments if marker == 0xFF77]
    if len(mco) != 1:
        raise GenerationError("Part2 control needs one MCO marker")
    start, end = mco[0]
    original = frame[start:end]
    if len(original) != 6 or original[4] != 1:
        raise GenerationError("Part2 control needs exactly one existing transform stage")
    index = original[5]
    if index == 4:
        raise GenerationError("identity-stage index 4 is already used")
    replacement = null_mcc(4, ((0, 1, 2),)) + b"\xff\x77\x00\x05\x02" + bytes([index, 4])
    return frame[:start] + replacement + frame[end:]


def codec_statement_defect(context):
    set_case_sop(context.dataset, context.seed)
    values = frames(context.dataset)
    operation = context.parameters["operation"]
    before = values[0]
    after = bytearray(before)
    if operation.startswith("rle-"):
        if struct.unpack_from("<II", before) != (1, 64) or before[64:] != bytes([3, 11, 12, 13, 14, 253, 42, 0]):
            raise GenerationError("RLE packet control does not have the expected two rows")
        if operation == "rle-padding":
            after[-1] = 1
        elif operation == "rle-unused-offset":
            struct.pack_into("<I", after, 8, 64)
        elif operation == "rle-forbidden-run":
            after[64:64] = b"\x80\x80"
        elif operation == "rle-literal-repeat":
            after[65:68] = b"\x0b\x0b\x0b"
        elif operation == "rle-row-crossing":
            after[64:] = bytes([1, 11, 12, 2, 13, 14, 42, 254, 42, 0])
        else:
            raise GenerationError(f"unknown RLE operation {operation}")
    elif operation == "two-component-collections":
        wanted = null_mcc(4, ((0, 1, 2),))
        matches = [(a, b) for marker, a, b in _segments(before) if marker == 0xFF75 and before[a:b] == wanted]
        if len(matches) != 1:
            raise GenerationError("Part2 control needs the one-collection identity stage")
        start, end = matches[0]
        after[start:end] = null_mcc(4, ((0,), (1, 2)))
    else:
        raise GenerationError(f"unknown codec statement operation {operation}")
    values[0] = bytes(after)
    _rewrap(context.dataset, values)
    context.changes.append({"kind": operation, "frame_index": 0,
                            "before_size_bytes": len(before), "after_size_bytes": len(after)})


HANDLERS = {"codec_statement_defect": codec_statement_defect}
