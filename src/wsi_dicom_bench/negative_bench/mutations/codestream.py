"""Byte-level mutations of the codestream inside one Frame of encapsulated Pixel Data.

Marker segments are located by walking the Frame's headers (JPEG from SOI through the
first SOS, JPEG 2000 from SOC through the first SOT), never by searching the bytes, and
every edit names the bytes it expects to find, so a control without the expected marker
or Value fails closed. The edited Frames are re-encapsulated in the control's own offset
table form (Extended Offset Table, or Basic Offset Table), each Fragment padded to even
length, and every byte change is recorded.

``codestream_edit`` applies an ordered list of operations to one Frame:

``{"operation": "patch", "marker": "FF52", "offset": 8, "expect": "01", "value": "00"}``
    overwrites bytes at ``offset`` from the first byte of the marker segment;
``{"operation": "remove_segment", "marker": "FFC4", "occurrence": "all"}``
    deletes whole marker segments;
``{"operation": "insert", "marker": "FF90", "position": "before", "value": "..."}``
    inserts bytes before the marker or after its segment;
``{"operation": "insert_icc", "marker": "FFD8", "position": "after", "chunks": 2}``
    inserts APP2 ICC_PROFILE segments holding the Optical Path ICC Profile, optionally
    with one byte inverted (``invert_byte``) or one chunk left out (``omit_chunk``);
``{"operation": "truncate_end", "expect": "FFD9"}`` removes the end marker;
``{"operation": "append_copy"}`` appends a second copy of the codestream;
``{"operation": "wrap_jp2"}`` wraps a JPEG 2000 codestream in the JP2 file format.

``codestream_refragment`` splits one Frame into Fragments cut from its bytes, and
``codestream_donor_frame`` replaces one Frame with a Frame of another control.
"""

from __future__ import annotations

import hashlib
import struct

import pydicom
from pydicom.encaps import encapsulate
from pydicom.tag import Tag

from ..model import GenerationError, MutationContext
from .dataset_edits import int_in_range as _int_in_range, record_change as _record
from .dicom import frames, pack_u64, remove_extended_tables, set_case_sop


PIXEL_DATA = Tag(0x7FE0, 0x0010)
SOI = 0xFFD8
SOC = 0xFF4F
SOT = 0xFF90
SOS = 0xFFDA
JPEG_STANDALONE = frozenset({0xFF01, *range(0xFFD0, 0xFFD8)})
ITEM = b"\xfe\xff\x00\xe0"


def _hex(text: object, what: str) -> bytes:
    if not isinstance(text, str):
        raise GenerationError(f"{what} must be a hexadecimal string")
    try:
        return bytes.fromhex(text)
    except ValueError as exc:
        raise GenerationError(f"{what} is not hexadecimal: {text!r}") from exc


def _marker(text: object) -> int:
    value = _hex(text, "marker")
    if len(value) != 2 or value[0] != 0xFF:
        raise GenerationError(f"marker must be two bytes beginning FFH: {text!r}")
    return int.from_bytes(value, "big")


def _u16(data: bytes, offset: int, what: str) -> int:
    if offset + 2 > len(data):
        raise GenerationError(f"{what} at byte {offset} runs past the codestream")
    return struct.unpack_from(">H", data, offset)[0]


def _segments(codestream: bytes) -> list[tuple[int, int, int]]:
    """(marker, start, end) of each header marker segment, delimiting markers included."""
    if codestream.startswith(b"\xff\x4f\xff\x51"):
        return _header_segments(codestream, SOC, SOT, "JPEG 2000", "main header", frozenset())
    if codestream.startswith(b"\xff\xd8"):
        return _header_segments(codestream, SOI, SOS, "JPEG", "JPEG header", JPEG_STANDALONE)
    raise GenerationError("the Frame is neither a JPEG stream nor a JPEG 2000 codestream")


def _header_segments(codestream: bytes, first: int, last: int, coding: str, header: str,
                     standalone: frozenset[int]) -> list[tuple[int, int, int]]:
    """Walk the marker segments after the ``first`` marker through the ``last`` one;
    a ``standalone`` marker (one without a length) fails closed."""
    segments = [(first, 0, 2)]
    position = 2
    while True:
        marker = _u16(codestream, position, f"{coding} marker")
        if marker & 0xFF00 != 0xFF00:
            raise GenerationError(f"byte {position} of the {header} is not a marker")
        if marker in standalone:
            raise GenerationError(f"standalone marker {marker:04X}H precedes the first scan")
        end = position + 2 + _u16(codestream, position + 2, f"{coding} marker length")
        if end > len(codestream) or end < position + 4:
            raise GenerationError(f"marker {marker:04X}H at byte {position} is malformed")
        segments.append((marker, position, end))
        if marker == last:
            return segments
        position = end


def _located(codestream: bytes, operation: dict) -> list[tuple[int, int, int]]:
    marker = _marker(operation.get("marker"))
    found = [segment for segment in _segments(codestream) if segment[0] == marker]
    occurrence = operation.get("occurrence", 0)
    if occurrence == "all":
        selected = found
    elif _int_in_range(occurrence, 0, len(found)):
        selected = [found[occurrence]]
    else:
        selected = []
    if not selected:
        raise GenerationError(
            f"the Frame header has no marker {marker:04X}H occurrence {occurrence!r}"
        )
    return selected


def _content_end(codestream: bytes) -> int:
    """End of the codestream before the zero bytes that pad a Frame to even length."""
    end = len(codestream)
    while end > 0 and codestream[end - 1] == 0:
        end -= 1
    return end


def _patch(codestream: bytes, operation: dict) -> tuple[bytes, dict]:
    marker, start, end = _located(codestream, operation)[0]
    offset = operation.get("offset")
    if not _int_in_range(offset, 0):
        raise GenerationError("patch offset must be a nonnegative integer")
    expect = _hex(operation.get("expect"), "patch expect")
    value = _hex(operation.get("value"), "patch value")
    begin = start + offset
    if not expect or len(value) != len(expect) or begin + len(expect) > end:
        raise GenerationError("patch must replace expected bytes in place within one segment")
    before = codestream[begin : begin + len(expect)]
    if before != expect:
        raise GenerationError(
            f"marker {marker:04X}H byte {offset} holds {before.hex()}, not the expected {expect.hex()}"
        )
    edited = codestream[:begin] + value + codestream[begin + len(value) :]
    return edited, {"marker": f"{marker:04X}", "offset": offset, "byte": begin,
                    "before_bytes": before.hex(), "after_bytes": value.hex()}


def _remove_segment(codestream: bytes, operation: dict) -> tuple[bytes, dict]:
    segments = _located(codestream, operation)
    removed = []
    edited = codestream
    for marker, start, end in reversed(segments):
        removed.append({"marker": f"{marker:04X}", "byte": start,
                        "removed_bytes": edited[start:end].hex()})
        edited = edited[:start] + edited[end:]
    return edited, {"removed": list(reversed(removed))}


def _insertion_point(codestream: bytes, operation: dict) -> int:
    marker, start, end = _located(codestream, operation)[0]
    position = operation.get("position")
    if position not in ("before", "after"):
        raise GenerationError("insert position must be 'before' or 'after'")
    return start if position == "before" else end


def _insert(codestream: bytes, operation: dict) -> tuple[bytes, dict]:
    at = _insertion_point(codestream, operation)
    value = _hex(operation.get("value"), "insert value")
    if not value:
        raise GenerationError("insert value is empty")
    return codestream[:at] + value + codestream[at:], {
        "marker": operation["marker"], "position": operation["position"], "byte": at,
        "inserted": value.hex(),
    }


def _optical_path_profile(dataset) -> bytes:
    paths = dataset.get("OpticalPathSequence")
    if not paths or "ICCProfile" not in paths[0]:
        raise GenerationError("the control has no Optical Path ICC Profile to embed")
    profile = bytes(paths[0].ICCProfile)
    if len(profile) < 128:
        raise GenerationError("the Optical Path ICC Profile is shorter than its header")
    declared = struct.unpack_from(">I", profile, 0)[0]
    if declared > len(profile):
        raise GenerationError("the ICC Profile header size exceeds its Value")
    # The ICC header's own size excludes the pad byte of an odd-length Value.
    return profile[:declared]


def _insert_icc(codestream: bytes, operation: dict, dataset) -> tuple[bytes, dict]:
    at = _insertion_point(codestream, operation)
    profile = bytearray(_optical_path_profile(dataset))
    inverted = operation.get("invert_byte")
    if inverted is not None:
        if not _int_in_range(inverted, 0, len(profile)):
            raise GenerationError("invert_byte is outside the ICC Profile")
        profile[inverted] ^= 0xFF
    count = operation.get("chunks", 1)
    if not _int_in_range(count, 1, 256):
        raise GenerationError("chunks must be 1 to 255")
    size = -(-len(profile) // count)
    pieces = [bytes(profile[index : index + size]) for index in range(0, len(profile), size)]
    if len(pieces) != count:
        raise GenerationError("the ICC Profile does not divide into the requested chunks")
    omitted = operation.get("omit_chunk")
    if omitted is not None and not _int_in_range(omitted, 1, count + 1):
        raise GenerationError("omit_chunk must name one chunk of the sequence")
    segments = b""
    for sequence, piece in enumerate(pieces, start=1):
        if sequence == omitted:
            continue
        payload = b"ICC_PROFILE\0" + bytes([sequence, count]) + piece
        if len(payload) + 2 > 0xFFFF:
            raise GenerationError("an ICC_PROFILE chunk exceeds one APP2 segment")
        segments += b"\xff\xe2" + struct.pack(">H", len(payload) + 2) + payload
    return codestream[:at] + segments + codestream[at:], {
        "marker": operation["marker"], "position": operation["position"], "byte": at,
        "chunks": count, "omitted_chunk": omitted, "inverted_byte": inverted,
        "profile_bytes": len(profile),
        "profile_sha256": hashlib.sha256(bytes(profile)).hexdigest(),
        "inserted_bytes": len(segments),
    }


def _truncate_end(codestream: bytes, operation: dict) -> tuple[bytes, dict]:
    expect = _hex(operation.get("expect"), "truncate_end expect")
    end = _content_end(codestream)
    if not expect or codestream[end - len(expect) : end] != expect:
        raise GenerationError(f"the codestream does not end with {expect.hex()}")
    return codestream[: end - len(expect)], {
        "removed": codestream[end - len(expect) :].hex(), "byte": end - len(expect),
    }


def _append_copy(codestream: bytes, operation: dict) -> tuple[bytes, dict]:
    content = codestream[: _content_end(codestream)]
    _segments(content)
    return content + content, {"appended_bytes": len(content)}


def _wrap_jp2(codestream: bytes, operation: dict) -> tuple[bytes, dict]:
    """JP2 signature, File Type and Header boxes, then the Contiguous Codestream box."""
    content = codestream[: _content_end(codestream)]
    if not content.startswith(b"\xff\x4f\xff\x51"):
        raise GenerationError("only a JPEG 2000 codestream can be wrapped as JP2")
    width, height = struct.unpack_from(">II", content, 8)
    x_offset, y_offset = struct.unpack_from(">II", content, 16)
    components = _u16(content, 40, "SIZ Csiz")
    depth = content[42]

    def box(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", 8 + len(payload)) + kind + payload

    image_header = box(b"ihdr", struct.pack(">IIHBBBB", height - y_offset, width - x_offset,
                                            components, depth, 7, 0, 0))
    colour = box(b"colr", bytes([1, 0, 0]) + struct.pack(">I", 16 if components == 3 else 17))
    wrapped = (
        box(b"jP  ", b"\r\n\x87\n")
        + box(b"ftyp", b"jp2 " + b"\0\0\0\0" + b"jp2 ")
        + box(b"jp2h", image_header + colour)
        + box(b"jp2c", content)
    )
    return wrapped, {"prefixed_bytes": len(wrapped) - len(content)}


OPERATIONS = {
    "patch": _patch,
    "remove_segment": _remove_segment,
    "insert": _insert,
    "truncate_end": _truncate_end,
    "append_copy": _append_copy,
    "wrap_jp2": _wrap_jp2,
}


def _frame_index(parameters: dict, frame_count: int) -> int:
    index = parameters.get("frame_index")
    if not _int_in_range(index, 0, frame_count):
        raise GenerationError(f"frame_index must name one of the {frame_count} Frames")
    return index


def _record_frame(context: MutationContext, operation: str, index: int, before: bytes,
                  after: bytes, **fields) -> None:
    _record(
        context,
        operation,
        f"PixelData/Frame[{index}]",
        PIXEL_DATA,
        frame_index=index,
        before_size_bytes=len(before),
        after_size_bytes=len(after),
        before_sha256=hashlib.sha256(before).hexdigest(),
        after_sha256=hashlib.sha256(after).hexdigest(),
        **fields,
    )


def _has_basic_offsets(dataset) -> bool:
    raw = bytes(dataset.PixelData)
    if raw[:4] != ITEM:
        raise GenerationError("Pixel Data does not begin with a Basic Offset Table Item")
    return struct.unpack_from("<I", raw, 4)[0] > 0


def _padded(value: bytes) -> bytes:
    return value + b"\0" if len(value) % 2 else value


def _rewrap(dataset, frame_values: list[bytes]) -> str:
    """Re-encapsulate in the control's own offset table form; return that form.

    Extended Offset Table Lengths keep each Frame's unpadded length, as the controls
    record them, so the Frames the case does not edit stay byte-identical.
    """
    if "ExtendedOffsetTable" in dataset:
        offsets, cursor, items = [], 0, b""
        for value in frame_values:
            offsets.append(cursor)
            fragment = _padded(value)
            items += ITEM + struct.pack("<I", len(fragment)) + fragment
            cursor += 8 + len(fragment)
        dataset.PixelData = ITEM + b"\0\0\0\0" + items
        dataset["PixelData"].is_undefined_length = True
        dataset.ExtendedOffsetTable = pack_u64(offsets)
        dataset.ExtendedOffsetTableLengths = pack_u64([len(value) for value in frame_values])
        return "extended"
    dataset.PixelData = encapsulate(frame_values, has_bot=_has_basic_offsets(dataset))
    dataset["PixelData"].is_undefined_length = True
    return "basic"


def codestream_edit(context: MutationContext) -> None:
    set_case_sop(context.dataset, context.seed)
    frame_values = frames(context.dataset)
    index = _frame_index(context.parameters, len(frame_values))
    operations = context.parameters.get("operations")
    if not isinstance(operations, list) or not operations:
        raise GenerationError("codestream_edit operations must be a nonempty list")
    for operation in operations:
        if not isinstance(operation, dict):
            raise GenerationError("a codestream operation must be an object")
        kind = operation.get("operation")
        before = frame_values[index]
        if kind == "insert_icc":
            after, fields = _insert_icc(before, operation, context.dataset)
        elif kind in OPERATIONS:
            after, fields = OPERATIONS[kind](before, operation)
        else:
            raise GenerationError(f"unknown codestream operation: {kind!r}")
        frame_values[index] = after
        _record_frame(context, f"codestream_{kind}", index, before, after, **fields)
    form = _rewrap(context.dataset, frame_values)
    context.changes[-1]["offset_table"] = form


def codestream_refragment(context: MutationContext) -> None:
    """Encode one Frame as several Fragments cut from its bytes, with a Basic Offset Table."""
    set_case_sop(context.dataset, context.seed)
    frame_values = frames(context.dataset)
    index = _frame_index(context.parameters, len(frame_values))
    parts = context.parameters.get("parts")
    if not isinstance(parts, list) or len(parts) < 2:
        raise GenerationError("refragment parts must list at least two byte ranges")
    frame = frame_values[index]
    pieces = []
    for part in parts:
        if not isinstance(part, list) or len(part) != 2:
            raise GenerationError("a refragment part is [start, end] with end null for the end")
        start, end = part[0], len(frame) if part[1] is None else part[1]
        if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(frame)):
            raise GenerationError(f"refragment part {part!r} is outside the {len(frame)}-byte Frame")
        pieces.append(_padded(frame[start:end]))
    fragments = [
        pieces if position == index else [_padded(value)]
        for position, value in enumerate(frame_values)
    ]
    offsets, cursor = [], 0
    for frame_fragments in fragments:
        offsets.append(cursor)
        cursor += sum(8 + len(fragment) for fragment in frame_fragments)
    stream = ITEM + struct.pack("<I", 4 * len(offsets)) + struct.pack(f"<{len(offsets)}I", *offsets)
    for frame_fragments in fragments:
        for fragment in frame_fragments:
            stream += ITEM + struct.pack("<I", len(fragment)) + fragment
    # One Fragment per Frame is what an Extended Offset Table addresses, so the split
    # Frame is mapped by the Basic Offset Table instead.
    remove_extended_tables(context.dataset)
    context.dataset.PixelData = stream
    context.dataset["PixelData"].is_undefined_length = True
    _record_frame(context, "codestream_refragment", index, frame, b"".join(pieces),
                  parts=parts, fragment_lengths=[len(piece) for piece in pieces],
                  offset_table="basic")


def codestream_donor_frame(context: MutationContext) -> None:
    """Replace one Frame with a Frame of another control of the same Image Pixel shape."""
    set_case_sop(context.dataset, context.seed)
    parameters = context.parameters
    donor_id = parameters.get("donor_control")
    if not isinstance(donor_id, str) or "/" in donor_id or not donor_id:
        raise GenerationError("donor_control must name a sibling control")
    donor_path = context.source.with_name(f"{donor_id}.dcm")
    if not donor_path.is_file():
        raise GenerationError(f"donor control is absent: {donor_path.name}")
    donor = pydicom.dcmread(donor_path)
    for keyword in ("Rows", "Columns", "SamplesPerPixel", "BitsAllocated", "BitsStored"):
        if int(donor[keyword].value) != int(context.dataset[keyword].value):
            raise GenerationError(f"donor control differs in {keyword}")
    if donor.file_meta.TransferSyntaxUID == context.dataset.file_meta.TransferSyntaxUID:
        raise GenerationError("donor control has the same Transfer Syntax")
    frame_values = frames(context.dataset)
    donor_frames = frames(donor)
    index = _frame_index(parameters, len(frame_values))
    donor_index = parameters.get("donor_frame_index", index)
    if not _int_in_range(donor_index, 0, len(donor_frames)):
        raise GenerationError("donor_frame_index is outside the donor's Frames")
    before = frame_values[index]
    frame_values[index] = donor_frames[donor_index]
    form = _rewrap(context.dataset, frame_values)
    _record_frame(context, "codestream_donor_frame", index, before, frame_values[index],
                  donor_control=donor_id, donor_frame_index=donor_index,
                  donor_transfer_syntax=str(donor.file_meta.TransferSyntaxUID),
                  offset_table=form)


HANDLERS = {
    "codestream_edit": codestream_edit,
    "codestream_refragment": codestream_refragment,
    "codestream_donor_frame": codestream_donor_frame,
}
