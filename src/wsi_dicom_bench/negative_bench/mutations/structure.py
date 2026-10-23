"""Single-defect structural mutations for the DICOM 2026c VL WSI IOD requirement families.

Each handler changes one Data Element, one Sequence Item, or one File Meta Information
element of a frozen control and records the exact path, tag, VR, and Values before and
after. Data Set paths alternate DICOM keywords and zero-based Sequence Item indices and
end in a keyword, for example
``["SharedFunctionalGroupsSequence", 0, "PixelMeasuresSequence"]``.
"""

from __future__ import annotations

import copy
import re
import struct

from pydicom import config
from pydicom.datadict import dictionary_VR, tag_for_keyword
from pydicom.dataelem import DataElement
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence
from pydicom.tag import Tag

from ..model import GenerationError, MutationContext, MutationResult
from .dicom import save, set_case_sop


PREAMBLE_AND_PREFIX = 132
FILE_META_PREFIX = b"DICM"
# PS3.5 Table 7.1-1: VRs with a reserved field and a 4-byte Value Length.
LONG_LENGTH_VRS = {
    b"OB", b"OD", b"OF", b"OL", b"OV", b"OW", b"SQ", b"SV", b"UC", b"UN", b"UR", b"UT", b"UV",
}
FILE_META_TAG = re.compile(r"\(0002,([0-9A-F]{4})\)\Z")
STRING_VRS = {
    "AE", "AS", "CS", "DA", "DS", "DT", "IS", "LO", "LT", "PN", "SH", "ST", "TM", "UC",
    "UI", "UR", "UT",
}
MAX_LOGGED_TEXT = 96


def _tag(keyword: object) -> Tag:
    if not isinstance(keyword, str):
        raise GenerationError(f"mutation path keyword must be a string: {keyword!r}")
    tag = tag_for_keyword(keyword)
    if tag is None:
        raise GenerationError(f"mutation path names an unknown DICOM keyword: {keyword}")
    return Tag(tag)


def _tag_text(tag: Tag) -> str:
    return f"({tag.group:04X},{tag.element:04X})"


def _resolve(dataset: Dataset, path: object) -> tuple[Dataset, Tag, str]:
    """Return the Data Set that holds the final path keyword, its tag, and a printable path."""
    if not isinstance(path, list) or not path or len(path) % 2 == 0:
        raise GenerationError(
            "mutation path must alternate Sequence keywords and Item indices and end in a keyword"
        )
    current = dataset
    printable = []
    for keyword, index in zip(path[:-1:2], path[1:-1:2]):
        tag = _tag(keyword)
        if tag not in current or current[tag].VR != "SQ":
            raise GenerationError(f"mutation path Sequence is absent: {keyword}")
        items = current[tag].value
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 0 <= index < len(items)
        ):
            raise GenerationError(f"mutation path Item index is out of range: {keyword}[{index}]")
        current = items[index]
        printable.append(f"{keyword}[{index}]")
    printable.append(path[-1])
    return current, _tag(path[-1]), "/".join(printable)


def _logged_value(element: DataElement | None):
    """A bounded JSON-friendly rendering of one element Value."""
    if element is None:
        return None
    if element.VR == "SQ":
        return f"{len(element.value)} Item(s)"
    value = element.value
    if value is None or value == "":
        return ""
    if isinstance(value, (bytes, bytearray)):
        return f"{len(value)} bytes"
    if isinstance(value, (list, tuple)) or type(value).__name__ == "MultiValue":
        return [_bounded(str(item)) for item in value]
    return _bounded(str(value))


def _bounded(text: str) -> str:
    return text if len(text) <= MAX_LOGGED_TEXT else text[:MAX_LOGGED_TEXT] + "..."


def _record(context: MutationContext, operation: str, path: str, tag: Tag, **fields) -> None:
    context.changes.append(
        {"kind": "defect", "operation": operation, "path": path, "tag": _tag_text(tag), **fields}
    )


def _finish(context: MutationContext) -> MutationResult:
    context.changes[0]["value"] = str(context.dataset.SOPInstanceUID)
    with config.disable_value_validation():
        save(context.dataset, context.default_output)
    return MutationResult([context.default_output], context.changes)


def _require(parent: Dataset, tag: Tag, path: str) -> DataElement:
    if tag not in parent:
        raise GenerationError(f"mutation target is absent from the control: {path}")
    return parent[tag]


def _value(raw: object, vr: str):
    """Convert one manifest Value to the form pydicom encodes for the VR."""
    if vr == "SQ":
        if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
            raise GenerationError("a Sequence Value must be a list of Item objects")
        items = []
        for item in raw:
            dataset = Dataset()
            for keyword, item_value in sorted(item.items()):
                item_tag = _tag(keyword)
                item_vr = dictionary_VR(item_tag)
                dataset.add(DataElement(item_tag, item_vr, _value(item_value, item_vr)))
            items.append(dataset)
        return Sequence(items)
    if raw is None:
        return None
    if vr in STRING_VRS:
        if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
            return list(raw)
        if isinstance(raw, str):
            return raw
        raise GenerationError(f"a {vr} Value must be a string or a list of strings")
    if isinstance(raw, bool) or not isinstance(raw, (int, float, list)):
        raise GenerationError(f"a {vr} Value must be numeric")
    return raw


def iod_delete_attribute(context: MutationContext) -> MutationResult:
    set_case_sop(context.dataset, context.seed)
    parent, tag, path = _resolve(context.dataset, context.parameters["path"])
    element = _require(parent, tag, path)
    _record(context, "delete_attribute", path, tag, vr=element.VR,
            before=_logged_value(element), after=None)
    del parent[tag]
    return _finish(context)


def iod_empty_attribute(context: MutationContext) -> MutationResult:
    set_case_sop(context.dataset, context.seed)
    parent, tag, path = _resolve(context.dataset, context.parameters["path"])
    element = _require(parent, tag, path)
    before = _logged_value(element)
    with config.disable_value_validation():
        element.value = Sequence([]) if element.VR == "SQ" else None
    _record(context, "empty_attribute", path, tag, vr=element.VR,
            before=before, after=_logged_value(element), value_length_after=0)
    return _finish(context)


def iod_set_value(context: MutationContext) -> MutationResult:
    """Replace one Value; ``paths`` replaces one shared identifier at every reference."""
    set_case_sop(context.dataset, context.seed)
    parameters = context.parameters
    if ("path" in parameters) == ("paths" in parameters):
        raise GenerationError("set_value requires exactly one of path or paths")
    paths = parameters["paths"] if "paths" in parameters else [parameters["path"]]
    if not isinstance(paths, list) or not paths:
        raise GenerationError("set_value paths must be a nonempty list")
    targets = []
    for raw_path in paths:
        parent, tag, path = _resolve(context.dataset, raw_path)
        element = _require(parent, tag, path)
        if element.VR == "SQ":
            raise GenerationError(f"set_value does not replace Sequences: {path}")
        targets.append((element, tag, path))
    if len({str(element.value) for element, _, _ in targets}) != 1:
        raise GenerationError("set_value paths must hold one shared Value before the change")
    for element, tag, path in targets:
        before = _logged_value(element)
        with config.disable_value_validation():
            element.value = _value(parameters["value"], element.VR)
        _record(context, "set_value", path, tag, vr=element.VR,
                before=before, after=_logged_value(element))
    return _finish(context)


def iod_insert_attribute(context: MutationContext) -> MutationResult:
    set_case_sop(context.dataset, context.seed)
    parent, tag, path = _resolve(context.dataset, context.parameters["path"])
    if tag in parent:
        raise GenerationError(f"inserted attribute is already present: {path}")
    vr = context.parameters.get("vr", dictionary_VR(tag))
    with config.disable_value_validation():
        parent.add(DataElement(tag, vr, _value(context.parameters["value"], vr)))
    _record(context, "insert_attribute", path, tag, vr=vr,
            before=None, after=_logged_value(parent[tag]))
    return _finish(context)


def iod_change_vr(context: MutationContext) -> MutationResult:
    set_case_sop(context.dataset, context.seed)
    parent, tag, path = _resolve(context.dataset, context.parameters["path"])
    element = _require(parent, tag, path)
    vr = context.parameters["vr"]
    if element.VR not in STRING_VRS or vr not in STRING_VRS or vr == element.VR:
        raise GenerationError(f"VR change must replace one string VR with another: {path}")
    # DS and IS Values are held as numbers; re-encode their exact text unchanged.
    value = element.value
    if element.VM > 1:
        value = [str(item) for item in value]
    elif value is not None:
        value = str(value)
    with config.disable_value_validation():
        parent[tag] = DataElement(tag, vr, value)
    _record(context, "change_vr", path, tag, vr_before=element.VR, vr_after=vr,
            before=_logged_value(element), after=_logged_value(parent[tag]))
    return _finish(context)


def _sequence(context: MutationContext) -> tuple[list, str, Tag]:
    parent, tag, path = _resolve(context.dataset, context.parameters["path"])
    element = _require(parent, tag, path)
    if element.VR != "SQ":
        raise GenerationError(f"Item mutation target is not a Sequence: {path}")
    return element.value, path, tag


def iod_duplicate_sequence_item(context: MutationContext) -> MutationResult:
    set_case_sop(context.dataset, context.seed)
    items, path, tag = _sequence(context)
    index = context.parameters["item_index"]
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(items):
        raise GenerationError(f"duplicated Item index is out of range: {path}[{index}]")
    before = len(items)
    items.append(copy.deepcopy(items[index]))
    _record(context, "duplicate_sequence_item", path, tag, vr="SQ",
            copied_item_index=index, before=f"{before} Item(s)", after=f"{len(items)} Item(s)")
    return _finish(context)


def iod_append_sequence_item(context: MutationContext) -> MutationResult:
    set_case_sop(context.dataset, context.seed)
    items, path, tag = _sequence(context)
    before = len(items)
    with config.disable_value_validation():
        items.append(_value([context.parameters["item"]], "SQ")[0])
    _record(context, "append_sequence_item", path, tag, vr="SQ",
            appended_item=context.parameters["item"],
            before=f"{before} Item(s)", after=f"{len(items)} Item(s)")
    return _finish(context)


def iod_remove_sequence_item(context: MutationContext) -> MutationResult:
    set_case_sop(context.dataset, context.seed)
    items, path, tag = _sequence(context)
    index = context.parameters["item_index"]
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(items):
        raise GenerationError(f"removed Item index is out of range: {path}[{index}]")
    before = len(items)
    del items[index]
    _record(context, "remove_sequence_item", path, tag, vr="SQ",
            removed_item_index=index, before=f"{before} Item(s)", after=f"{len(items)} Item(s)")
    return _finish(context)


def _file_meta_tag(value: object) -> int:
    match = FILE_META_TAG.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise GenerationError(f"File Meta tag must be written (0002,xxxx): {value!r}")
    return int(match.group(1), 16)


def _file_meta_elements(contents: bytes) -> list[dict]:
    """Parse the explicit VR Little Endian File Meta Information group as written."""
    if contents[128:PREAMBLE_AND_PREFIX] != FILE_META_PREFIX:
        raise GenerationError("written control lacks the DICM prefix")
    elements = []
    offset = PREAMBLE_AND_PREFIX
    end = None
    while end is None or offset < end:
        group, element = struct.unpack_from("<HH", contents, offset)
        if group != 0x0002:
            break
        vr = bytes(contents[offset + 4 : offset + 6])
        if vr in LONG_LENGTH_VRS:
            length = struct.unpack_from("<I", contents, offset + 8)[0]
            header = 12
        else:
            length = struct.unpack_from("<H", contents, offset + 6)[0]
            header = 8
        elements.append(
            {
                "element": element,
                "vr": vr,
                "offset": offset,
                "header": header,
                "length": length,
                "value": bytes(contents[offset + header : offset + header + length]),
            }
        )
        if element == 0x0000:
            end = offset + header + length + struct.unpack_from("<I", contents, offset + header)[0]
        offset += header + length
    if not elements or elements[0]["element"] != 0x0000:
        raise GenerationError("written control lacks File Meta Information Group Length")
    if offset != end:
        raise GenerationError("written File Meta Information Group Length is inconsistent")
    return elements


def _encode_file_meta_element(element: int, vr: bytes, value: bytes) -> bytes:
    tag = struct.pack("<HH", 0x0002, element)
    if vr in LONG_LENGTH_VRS:
        return tag + vr + b"\0\0" + struct.pack("<I", len(value)) + value
    return tag + vr + struct.pack("<H", len(value)) + value


def _rewrite_file_meta(context: MutationContext, transform) -> MutationResult:
    """Save the Data Set, then replace its File Meta group with ``transform(elements)``."""
    set_case_sop(context.dataset, context.seed)
    result = _finish(context)
    path = context.default_output
    contents = path.read_bytes()
    elements = _file_meta_elements(contents)
    group_start = elements[1]["offset"] if len(elements) > 1 else None
    group_end = elements[-1]["offset"] + elements[-1]["header"] + elements[-1]["length"]
    before_length = struct.unpack_from("<I", elements[0]["value"])[0]
    retained = transform(elements[1:])
    group = b"".join(
        _encode_file_meta_element(item["element"], item["vr"], item["value"]) for item in retained
    )
    length_element = _encode_file_meta_element(0x0000, b"UL", struct.pack("<I", len(group)))
    path.write_bytes(
        contents[:PREAMBLE_AND_PREFIX] + length_element + group + contents[group_end:]
    )
    context.changes.append(
        {
            "kind": "raw_byte_patch",
            "attribute": "FileMetaInformationGroupLength",
            "tag": "(0002,0000)",
            "byte_offset": PREAMBLE_AND_PREFIX + 8,
            "group_start_offset": group_start,
            "offsets_refer_to": "the serialization before this patch",
            "before": before_length,
            "after": len(group),
        }
    )
    return result


def _find_file_meta(elements: list[dict], element: int) -> dict:
    matches = [item for item in elements if item["element"] == element]
    if len(matches) != 1:
        raise GenerationError(f"expected one File Meta element (0002,{element:04X})")
    return matches[0]


def file_meta_remove_element(context: MutationContext) -> MutationResult:
    element = _file_meta_tag(context.parameters["tag"])
    if element == 0x0000:
        raise GenerationError("the File Meta Information Group Length cannot be removed")

    def transform(elements: list[dict]) -> list[dict]:
        removed = _find_file_meta(elements, element)
        context.changes.append(
            {
                "kind": "raw_byte_patch",
                "operation": "remove_file_meta_element",
                "tag": context.parameters["tag"],
                "vr": removed["vr"].decode("ascii"),
                "byte_offset": removed["offset"],
                "removed_bytes": removed["header"] + removed["length"],
                "before": removed["value"].hex(),
                "after": None,
            }
        )
        return [item for item in elements if item is not removed]

    return _rewrite_file_meta(context, transform)


def file_meta_replace_value(context: MutationContext) -> MutationResult:
    element = _file_meta_tag(context.parameters["tag"])
    if element == 0x0000:
        raise GenerationError("use a dedicated mutation for the File Meta Group Length")
    if "value_hex" in context.parameters:
        replacement = bytes.fromhex(context.parameters["value_hex"])
    else:
        text = context.parameters["value"]
        if not isinstance(text, str):
            raise GenerationError("File Meta replacement value must be a string")
        replacement = text.encode("ascii")

    def transform(elements: list[dict]) -> list[dict]:
        target = _find_file_meta(elements, element)
        padded = replacement
        if len(padded) % 2:
            padded += b"\0" if target["vr"] == b"UI" else b" "
        context.changes.append(
            {
                "kind": "raw_byte_patch",
                "operation": "replace_file_meta_value",
                "tag": context.parameters["tag"],
                "vr": target["vr"].decode("ascii"),
                "byte_offset": target["offset"] + target["header"],
                "before": target["value"].hex(),
                "after": padded.hex(),
            }
        )
        return [
            {**item, "value": padded} if item is target else item for item in elements
        ]

    return _rewrite_file_meta(context, transform)


HANDLERS = {
    "iod_delete_attribute": iod_delete_attribute,
    "iod_empty_attribute": iod_empty_attribute,
    "iod_set_value": iod_set_value,
    "iod_insert_attribute": iod_insert_attribute,
    "iod_change_vr": iod_change_vr,
    "iod_duplicate_sequence_item": iod_duplicate_sequence_item,
    "iod_append_sequence_item": iod_append_sequence_item,
    "iod_remove_sequence_item": iod_remove_sequence_item,
    "file_meta_remove_element": file_meta_remove_element,
    "file_meta_replace_value": file_meta_replace_value,
}
