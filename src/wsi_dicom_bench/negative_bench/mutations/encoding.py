"""Single-defect mutations of the encoded bytes of a Data Set (PS3.5 6, 7 and Annex A).

pydicom, like the DICOM parser of the checked tool, sorts Data Elements, keeps one of
each tag, writes reserved bytes and delimiter lengths as zero and re-encodes text from
decoded strings, so these defects are written into the bytes after pydicom saves the
control. ``encoding_rewrite`` saves the control, optionally after pydicom ``edits``
(the operations of ``iod_edits``), Sequence length forms and a Transfer Syntax change,
then applies ``operations`` to the encoded Data Set in order.

An operation locates its target by a path as in ``structure``: keywords, or
``"(gggg,eeee)"`` for private tags, alternating with zero-based Item indices. It fails
closed when the target is absent or the change would misframe the stream for the
parser, keeps the Explicit Lengths of the Items and Sequences around it consistent, and
records its byte offset with the bytes before and after.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

from pydicom.datadict import dictionary_VR
from pydicom.tag import Tag
from pydicom.uid import (
    DeflatedExplicitVRLittleEndian,
    ExplicitVRBigEndian,
    ExplicitVRLittleEndian,
    ImplicitVRLittleEndian,
)

from ..model import GenerationError, MutationContext, MutationResult
from .dataset_edits import (
    apply_operations as _apply,
    finish as _finish,
    item_index as _item_index,
    record_change as _record,
    resolve_path as _resolve,
    tag_for_path as _tag,
)
from .dicom import set_case_sop
from .encoded_file import LONG_LENGTH_VRS, PREAMBLE_AND_PREFIX


UNDEFINED = 0xFFFFFFFF
ITEM = 0xFFFEE000
ITEM_DELIMITATION = 0xFFFEE00D
SEQUENCE_DELIMITATION = 0xFFFEE0DD
PIXEL_DATA = 0x7FE00010
# The parser gives VR bytes it does not know the 32-bit Value Length of the PS3.5 Table
# 7.1-1 VRs (PS3.5 6.2), so an unknown or lower-case VR keeps that form.
KNOWN_VRS = frozenset(
    vr.encode("ascii")
    for vr in (
        "AE AS AT CS DA DS DT FL FD IS LO LT OB OD OF OL OV OW PN SH SL SQ SS ST SV TM "
        "UC UI UL UN UR US UT UV"
    ).split()
)
TRANSFER_SYNTAXES = (str(ImplicitVRLittleEndian), str(DeflatedExplicitVRLittleEndian))
MAX_LOGGED_BYTES = 64


def _long_form(vr: bytes) -> bool:
    return vr in LONG_LENGTH_VRS or vr not in KNOWN_VRS


def _hex(data: bytes) -> str:
    text = data.hex()
    return text if len(data) <= MAX_LOGGED_BYTES else text[: 2 * MAX_LOGGED_BYTES] + "..."


@dataclass
class Element:
    tag: int
    vr: bytes | None
    start: int
    header: int
    length: int
    end: int
    length_field: tuple[int, int]
    items: list["Item"] | None = None
    # Offset of the Sequence Delimitation Item of an Undefined Length Value.
    delimiter: int | None = None

    @property
    def value(self) -> int:
        return self.start + self.header


@dataclass
class Item:
    start: int
    length: int
    elements: list[Element]
    # Where the Item's Data Set ends: its Item Delimitation Item, if undefined.
    content_end: int
    end: int

    @property
    def length_field(self) -> tuple[int, int]:
        return self.start + 4, 4


@dataclass
class Frame:
    """The Data Set an operation addresses, with the defined-length containers around it."""

    elements: list[Element]
    content_end: int
    containers: list[Element | Item] = field(default_factory=list)


class Encoded:
    """A Little Endian Data Set as written, element by element."""

    def __init__(self, data: bytes, start: int, explicit: bool):
        self.data = data
        self.explicit = explicit
        elements, content_end, _ = self._data_set(start, len(data), until_delimiter=False)
        self.root = Frame(elements, content_end)

    def _u16(self, offset: int) -> int:
        return struct.unpack_from("<H", self.data, offset)[0]

    def _u32(self, offset: int) -> int:
        return struct.unpack_from("<I", self.data, offset)[0]

    def _tag(self, offset: int) -> int:
        if offset + 4 > len(self.data):
            raise GenerationError(f"the encoded Data Set ends inside a tag at byte {offset}")
        return self._u16(offset) << 16 | self._u16(offset + 2)

    def _data_set(self, offset: int, end: int, until_delimiter: bool, explicit=None):
        explicit = self.explicit if explicit is None else explicit
        elements = []
        while offset < end:
            tag = self._tag(offset)
            if tag == ITEM_DELIMITATION and until_delimiter:
                return elements, offset, offset + 8
            if tag >> 16 == 0xFFFE:
                raise GenerationError(f"control holds tag {tag:08X} at byte {offset} in a Data Set")
            element = self._element(offset, explicit)
            elements.append(element)
            offset = element.end
        if until_delimiter:
            raise GenerationError("an Item of Undefined Length lacks its Item Delimitation Item")
        if offset != end:
            raise GenerationError(f"elements overrun their Data Set by {offset - end} bytes")
        return elements, end, end

    def _element(self, offset: int, explicit: bool) -> Element:
        tag = self._tag(offset)
        if explicit:
            vr = self.data[offset + 4 : offset + 6]
            if _long_form(vr):
                header, length_field = 12, (offset + 8, 4)
                length = self._u32(offset + 8)
            else:
                header, length_field = 8, (offset + 6, 2)
                length = self._u16(offset + 6)
        else:
            vr = None
            header, length_field = 8, (offset + 4, 4)
            length = self._u32(offset + 4)
        value = offset + header
        element = Element(tag, vr, offset, header, length, value + length, length_field)
        sequence = vr == b"SQ" if explicit else self._implicit_sequence(tag, length)
        if length == UNDEFINED:
            if tag == PIXEL_DATA:
                element.delimiter = self._fragments(value)
                element.end = element.delimiter + 8
                return element
            # PS3.5 6.2.2: the Items of an undefined-length UN stay Implicit VR.
            nested = explicit and vr != b"UN"
            element.items, element.delimiter, element.end = self._items(value, None, nested)
        elif sequence:
            element.items, _, _ = self._items(value, value + length, explicit)
        if element.end > len(self.data):
            raise GenerationError(f"element {tag:08X} at byte {offset} extends beyond the file")
        return element

    @staticmethod
    def _implicit_sequence(tag: int, length: int) -> bool:
        if length == UNDEFINED:
            return True
        try:
            return dictionary_VR(Tag(tag)) == "SQ"
        except KeyError:
            return False

    def _items(self, offset: int, end: int | None, explicit: bool):
        items = []
        while end is None or offset < end:
            tag, length = self._tag(offset), self._u32(offset + 4)
            if tag == SEQUENCE_DELIMITATION and end is None:
                return items, offset, offset + 8
            if tag != ITEM:
                raise GenerationError(f"tag {tag:08X} at byte {offset} where an Item is expected")
            value = offset + 8
            if length == UNDEFINED:
                elements, content_end, after = self._data_set(value, len(self.data), True, explicit)
            else:
                elements, content_end, after = self._data_set(value, value + length, False, explicit)
            items.append(Item(offset, length, elements, content_end, after))
            offset = after
        return items, None, offset

    def _fragments(self, offset: int) -> int:
        while True:
            tag, length = self._tag(offset), self._u32(offset + 4)
            if tag == SEQUENCE_DELIMITATION:
                return offset
            if tag != ITEM or length == UNDEFINED:
                raise GenerationError(f"encapsulated Pixel Data holds tag {tag:08X} at byte {offset}")
            offset += 8 + length

    def frame(self, path: list) -> Frame:
        """The Data Set at ``path``: ``[]`` or alternating Sequence keys and Item indices."""
        if len(path) % 2:
            raise GenerationError("a Data Set path alternates Sequence keys and Item indices")
        frame = self.root
        for key, index in zip(path[::2], path[1::2]):
            sequence = self.find(frame, key)
            items = sequence.items
            if items is None:
                raise GenerationError(f"encoding path element is not a Sequence: {key}")
            item = items[_item_index(index, items, "encoding path", key)]
            containers = [*frame.containers]
            if sequence.length != UNDEFINED:
                containers.append(sequence)
            if item.length != UNDEFINED:
                containers.append(item)
            frame = Frame(item.elements, item.content_end, containers)
        return frame

    @staticmethod
    def find(frame: Frame, key: object) -> Element:
        tag = _tag(key)
        matches = [element for element in frame.elements if element.tag == tag]
        if len(matches) != 1:
            raise GenerationError(f"expected one encoded element {key}, found {len(matches)}")
        return matches[0]

    def element(self, path: list) -> tuple[Frame, Element]:
        if not path or len(path) % 2 == 0:
            raise GenerationError("an element path ends in a key")
        frame = self.frame(path[:-1])
        return frame, self.find(frame, path[-1])


def _printable(path: list) -> str:
    parts = []
    for key, index in zip(path[::2], path[1::2]):
        parts.append(f"{key}[{index}]")
    if len(path) % 2:
        parts.append(str(path[-1]))
    return "/".join(parts) or "(top level)"


def _resize(data: bytearray, containers: list, delta: int) -> list[dict]:
    """Adds ``delta`` to each Explicit Length around an inserted or removed span."""
    patches = []
    for container in containers:
        offset, size = container.length_field
        if size != 4:
            raise GenerationError("a resized container has a 16-bit Value Length")
        before = struct.unpack_from("<I", data, offset)[0]
        struct.pack_into("<I", data, offset, before + delta)
        patches.append({"byte_offset": offset, "before": before, "after": before + delta})
    return patches


def _encode(spec: dict, explicit: bool) -> bytes:
    """One element as written: ``tag``, ``vr``, and ``text``, ``value_hex`` or ``items``."""
    tag = _tag(spec.get("tag"))
    vr = spec.get("vr")
    if not isinstance(vr, str) or len(vr.encode("ascii")) != 2:
        raise GenerationError(f"an encoded element needs a two-character VR: {spec!r}")
    vr_bytes = vr.encode("ascii")
    undefined = spec.get("length") == "undefined"
    if "items" in spec:
        items = b""
        for item in spec["items"]:
            content = b"".join(_encode(child, explicit) for child in item)
            if spec.get("item_length") == "undefined":
                items += struct.pack("<HHI", 0xFFFE, 0xE000, UNDEFINED) + content
                items += struct.pack("<HHI", 0xFFFE, 0xE00D, 0)
            else:
                items += struct.pack("<HHI", 0xFFFE, 0xE000, len(content)) + content
        value = items + (struct.pack("<HHI", 0xFFFE, 0xE0DD, 0) if undefined else b"")
    elif "text" in spec:
        value = spec["text"].encode(spec.get("encoding", "ascii"))
        if len(value) % 2:
            value += b"\0" if vr == "UI" else b" "
    elif "value_hex" in spec:
        value = bytes.fromhex(spec["value_hex"])
    else:
        raise GenerationError(f"an encoded element needs text, value_hex or items: {spec!r}")
    if len(value) % 2:
        raise GenerationError(f"an encoded Value has odd length {len(value)}: {spec!r}")
    length = UNDEFINED if undefined else len(value)
    head = struct.pack("<HH", tag >> 16, tag & 0xFFFF)
    if not explicit:
        return head + struct.pack("<I", length) + value
    if _long_form(vr_bytes):
        reserved = bytes.fromhex(spec.get("reserved_hex", "0000"))
        return head + vr_bytes + reserved + struct.pack("<I", length) + value
    if undefined or length > 0xFFFF:
        raise GenerationError(f"VR {vr} has a 16-bit Value Length: {spec!r}")
    return head + vr_bytes + struct.pack("<H", length) + value


class Rewrite:
    """The saved file and the encoded Data Set its operations change."""

    def __init__(self, context: MutationContext, explicit: bool, raw: bool):
        self.context = context
        self.path = context.default_output
        self.data = bytearray(self.path.read_bytes())
        self.explicit = explicit
        self.raw = raw
        self.start = self._data_set_start()

    def _data_set_start(self) -> int:
        if self.data[128:PREAMBLE_AND_PREFIX] != b"DICM":
            raise GenerationError("saved control lacks the DICM prefix")
        group_length = struct.unpack_from("<I", self.data, PREAMBLE_AND_PREFIX + 8)[0]
        return PREAMBLE_AND_PREFIX + 12 + group_length

    def encoded(self) -> Encoded:
        if not self.raw:
            raise GenerationError("element operations need a Little Endian Data Set as written")
        return Encoded(bytes(self.data), self.start, self.explicit)

    def record(self, operation: str, path: list, tag: int, **fields) -> None:
        _record(self.context, operation, _printable(path), Tag(tag), **fields)

    def replace(self, start: int, end: int, replacement: bytes, containers: list) -> list[dict]:
        delta = len(replacement) - (end - start)
        self.data[start:end] = replacement
        return _resize(self.data, containers, delta) if delta else []

    def swap(self, operation: dict) -> None:
        path = operation["path"]
        frame, first = self.encoded().element(path)
        second = Encoded.find(frame, operation["with"])
        if second.start <= first.start:
            raise GenerationError("swap names the later element in path and the earlier in with")
        a, b = bytes(self.data[first.start : first.end]), bytes(self.data[second.start : second.end])
        between = bytes(self.data[first.end : second.start])
        self.data[first.start : second.end] = b + between + a
        self.record("swap_elements", path, first.tag, swapped_with=f"{second.tag:08X}",
                    byte_offset=first.start, before=f"{first.tag:08X} then {second.tag:08X}",
                    after=f"{second.tag:08X} then {first.tag:08X}")

    def duplicate(self, operation: dict) -> None:
        path = operation["path"]
        frame, element = self.encoded().element(path)
        copy = bytes(self.data[element.start : element.end])
        lengths = self.replace(element.end, element.end, copy, frame.containers)
        self.record("duplicate_element", path, element.tag, byte_offset=element.end,
                    inserted=_hex(copy), container_lengths=lengths)

    def set_vr(self, operation: dict) -> None:
        path = operation["path"]
        _, element = self.encoded().element(path)
        vr = operation["vr"].encode("ascii")
        if not self.explicit or len(vr) != 2:
            raise GenerationError("set_vr needs an Explicit VR Data Set and a two-byte VR")
        if _long_form(vr) != _long_form(element.vr):
            raise GenerationError("set_vr would change the Value Length form the parser reads")
        self.data[element.start + 4 : element.start + 6] = vr
        self.record("set_vr", path, element.tag, byte_offset=element.start + 4,
                    before=element.vr.decode("latin-1"), after=vr.decode("latin-1"))

    def set_reserved(self, operation: dict) -> None:
        path = operation["path"]
        _, element = self.encoded().element(path)
        reserved = bytes.fromhex(operation["hex"])
        if not self.explicit or element.header != 12 or len(reserved) != 2:
            raise GenerationError("set_reserved needs a 32-bit Value Length element and two bytes")
        before = bytes(self.data[element.start + 6 : element.start + 8])
        self.data[element.start + 6 : element.start + 8] = reserved
        self.record("set_reserved_bytes", path, element.tag, byte_offset=element.start + 6,
                    before=before.hex(), after=reserved.hex())

    def set_delimiter_length(self, operation: dict) -> None:
        path = operation["path"]
        _, sequence = self.encoded().element(path)
        index = operation.get("item")
        # Encapsulated Pixel Data ends with a Sequence Delimitation Item but has no Items here.
        if sequence.items is None and (sequence.delimiter is None or index is not None):
            raise GenerationError(f"delimiter target is not a Sequence: {_printable(path)}")
        if index is None:
            if sequence.delimiter is None:
                raise GenerationError("the Sequence has an Explicit Length and no delimiter")
            offset, tag = sequence.delimiter, SEQUENCE_DELIMITATION
        else:
            if not 0 <= index < len(sequence.items):
                raise GenerationError(f"delimiter Item index is out of range: {index}")
            item = sequence.items[index]
            if item.length != UNDEFINED:
                raise GenerationError("the Item has an Explicit Length and no delimiter")
            offset, tag = item.content_end, ITEM_DELIMITATION
        before = struct.unpack_from("<I", self.data, offset + 4)[0]
        struct.pack_into("<I", self.data, offset + 4, int(operation["length"]))
        self.record("set_delimiter_length", path, tag, item_index=index, byte_offset=offset + 4,
                    before=before, after=int(operation["length"]))

    def insert(self, operation: dict) -> None:
        into = operation.get("into", [])
        specs = operation.get("elements")
        if not isinstance(specs, list) or not specs:
            raise GenerationError("insert needs a nonempty list of elements")
        frame = self.encoded().frame(into)
        encoded = b"".join(_encode(spec, self.explicit) for spec in specs)
        first = _tag(specs[0]["tag"])
        if any(element.tag == first for element in frame.elements):
            raise GenerationError(f"inserted element {first:08X} is already present")
        if operation.get("at", "sorted") == "end":
            offset = frame.content_end
        else:
            later = [element.start for element in frame.elements if element.tag > first]
            offset = later[0] if later else frame.content_end
        lengths = self.replace(offset, offset, encoded, frame.containers)
        self.record("insert_encoded_elements", into, first, byte_offset=offset,
                    elements=[dict(spec) for spec in specs],
                    inserted=_hex(encoded), container_lengths=lengths)

    def set_value(self, operation: dict) -> None:
        path = operation["path"]
        frame, element = self.encoded().element(path)
        if element.items is not None or element.length == UNDEFINED:
            raise GenerationError("set_value replaces a primitive Value of Explicit Length")
        if "value_hex" in operation:
            value = bytes.fromhex(operation["value_hex"])
        else:
            value = operation["text"].encode(operation.get("encoding", "ascii"))
        if len(value) % 2:
            raise GenerationError(f"replacement Value has odd length {len(value)}")
        offset, size = element.length_field
        if size == 2 and len(value) > 0xFFFF:
            raise GenerationError("replacement Value exceeds the 16-bit Value Length")
        before = bytes(self.data[element.value : element.end])
        lengths = self.replace(element.value, element.end, value, frame.containers)
        struct.pack_into("<H" if size == 2 else "<I", self.data, offset, len(value))
        self.record("set_encoded_value", path, element.tag, byte_offset=element.value,
                    before=_hex(before), after=_hex(value), container_lengths=lengths)

    def patch_value(self, operation: dict) -> None:
        path = operation["path"]
        _, element = self.encoded().element(path)
        patch = bytes.fromhex(operation["hex"])
        start = element.value + int(operation["offset"])
        if element.items is not None or start + len(patch) > element.end or start < element.value:
            raise GenerationError("patch_value overwrites bytes inside one primitive Value")
        before = bytes(self.data[start : start + len(patch)])
        self.data[start : start + len(patch)] = patch
        self.record("patch_encoded_value", path, element.tag, byte_offset=start,
                    before=before.hex(), after=patch.hex())

    def _pixel_data(self) -> Element:
        """Top-level encapsulated Pixel Data, which ends the file."""
        _, pixel_data = self.encoded().element(["PixelData"])
        if pixel_data.delimiter is None or pixel_data.end != len(self.data):
            raise GenerationError("the operation needs encapsulated Pixel Data that ends the file")
        return pixel_data

    def drop_pixel_delimiter(self, operation: dict) -> None:
        """Ends the file after the last Fragment, without the Sequence Delimitation Item."""
        pixel_data = self._pixel_data()
        removed = bytes(self.data[pixel_data.delimiter :])
        del self.data[pixel_data.delimiter :]
        self.record("drop_pixel_delimiter", ["PixelData"], PIXEL_DATA,
                    byte_offset=pixel_data.delimiter, before=removed.hex(), after=None)

    def insert_fragment(self, operation: dict) -> None:
        """Adds a Fragment Item holding ``hex`` after the last Fragment, where it moves no
        offset that the offset tables record."""
        pixel_data = self._pixel_data()
        value = bytes.fromhex(operation.get("hex", ""))
        item = struct.pack("<HHI", ITEM >> 16, ITEM & 0xFFFF, len(value)) + value
        self.data[pixel_data.delimiter : pixel_data.delimiter] = item
        self.record("insert_fragment", ["PixelData"], PIXEL_DATA,
                    byte_offset=pixel_data.delimiter, before=None, after=item.hex())

    def append(self, operation: dict) -> None:
        appended = bytes.fromhex(operation["hex"])
        offset = len(self.data)
        self.data += appended
        tag = struct.unpack_from("<HH", appended) if len(appended) >= 4 else (0, 0)
        self.record("append_bytes", [], tag[0] << 16 | tag[1],
                    byte_offset=offset, before=None, after=appended.hex())

    def break_deflate_padding(self, operation: dict) -> None:
        """Gives the deflated bit stream the wrong PS3.5 A.5 padding for its length."""
        compressed = bytes(self.data[self.start :])
        inflater = zlib.decompressobj(-15)
        inflater.decompress(compressed)
        if not inflater.eof:
            raise GenerationError("the saved Data Set is not one complete deflated bit stream")
        stream = len(compressed) - len(inflater.unused_data)
        trailing = inflater.unused_data
        if stream % 2 == 1 and trailing == b"\0":
            del self.data[-1]
            change = {"before": "00", "after": None, "removed": "the NULL pad byte of an odd-length stream"}
        elif stream % 2 == 0 and trailing == b"":
            self.data += b"\0"
            change = {"before": None, "after": "00", "added": "a NULL byte after an even-length stream"}
        else:
            raise GenerationError(f"saved deflated stream already ends in {trailing.hex()!r}")
        self.record("break_deflate_padding", [], 0, byte_offset=self.start + stream,
                    deflated_stream_bytes=stream, **change)

    def write(self) -> None:
        self.path.write_bytes(bytes(self.data))


OPERATIONS = {
    "swap": Rewrite.swap,
    "duplicate": Rewrite.duplicate,
    "set_vr": Rewrite.set_vr,
    "set_reserved": Rewrite.set_reserved,
    "set_delimiter_length": Rewrite.set_delimiter_length,
    "insert": Rewrite.insert,
    "set_value": Rewrite.set_value,
    "patch_value": Rewrite.patch_value,
    "append": Rewrite.append,
    "break_deflate_padding": Rewrite.break_deflate_padding,
    "drop_pixel_delimiter": Rewrite.drop_pixel_delimiter,
    "insert_fragment": Rewrite.insert_fragment,
}
FILE_LEVEL = frozenset({"append", "break_deflate_padding"})


def _set_lengths(context: MutationContext, forms: object) -> None:
    """Sets the encoded length form of Sequences and their Items before the save."""
    if not isinstance(forms, list):
        raise GenerationError("lengths must be a list")
    for form in forms:
        parent, tag, path = _resolve(context.dataset, form.get("path"))
        if tag not in parent or parent[tag].VR != "SQ":
            raise GenerationError(f"length form target is not a present Sequence: {path}")
        element = parent[tag]
        sequence, items = form.get("sequence"), form.get("items")
        if sequence not in (None, "defined", "undefined") or items not in (None, "defined", "undefined"):
            raise GenerationError("a length form is defined or undefined")
        if sequence is not None:
            element.is_undefined_length = sequence == "undefined"
        if items is not None:
            for item in element.value:
                item.is_undefined_length_sequence_item = items == "undefined"
        context.changes.append({"kind": "encoding_form", "path": path, "tag": str(tag),
                                "sequence_length": sequence, "item_length": items})


def encoding_rewrite(context: MutationContext) -> MutationResult:
    parameters = context.parameters
    operations = parameters.get("operations", [])
    if not isinstance(operations, list) or not (operations or parameters.get("edits")):
        raise GenerationError("encoding_rewrite needs edits or operations")
    set_case_sop(context.dataset, context.seed)
    if parameters.get("edits"):
        _apply(context, context.dataset, parameters["edits"], "")
    if "lengths" in parameters:
        _set_lengths(context, parameters["lengths"])
    syntax = parameters.get("transfer_syntax")
    if syntax is not None:
        if syntax not in TRANSFER_SYNTAXES:
            raise GenerationError(f"encoding_rewrite re-encodes only as {TRANSFER_SYNTAXES}")
        before = str(context.dataset.file_meta.TransferSyntaxUID)
        if before != ExplicitVRLittleEndian:
            raise GenerationError("a re-encoded control must be Explicit VR Little Endian")
        context.dataset.file_meta.TransferSyntaxUID = syntax
        context.changes.append({"kind": "transfer_syntax", "tag": "(0002,0010)",
                                "before": before, "after": syntax})
    result = _finish(context)
    syntax = str(context.dataset.file_meta.TransferSyntaxUID)
    raw = syntax not in (str(DeflatedExplicitVRLittleEndian), str(ExplicitVRBigEndian))
    rewrite = Rewrite(context, explicit=syntax != str(ImplicitVRLittleEndian), raw=raw)
    for operation in operations:
        name = operation.get("op") if isinstance(operation, dict) else None
        if name not in OPERATIONS:
            raise GenerationError(f"encoding operation must name one of {sorted(OPERATIONS)}")
        if not raw and name not in FILE_LEVEL:
            raise GenerationError(f"{name} needs a Data Set encoded as elements")
        OPERATIONS[name](rewrite, operation)
    rewrite.write()
    return result


HANDLERS = {
    "encoding_rewrite": encoding_rewrite,
}
