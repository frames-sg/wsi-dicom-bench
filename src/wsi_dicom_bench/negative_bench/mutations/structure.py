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
from pydicom.datadict import dictionary_VR
from pydicom.dataelem import DataElement
from pydicom.sequence import Sequence
from pydicom.tag import Tag
from pydicom.valuerep import STR_VR

from ..model import GenerationError, MutationContext, MutationResult
from .dataset_edits import (
    finish as _finish,
    item_index as _item_index,
    logged_value as _logged_value,
    manifest_value as _value,
    record_change as _record,
    require_element as _require,
    resolve_path as _resolve,
)
from .dicom import set_case_sop
from .encoded_file import LONG_LENGTH_VRS, PREAMBLE_AND_PREFIX


FILE_META_PREFIX = b"DICM"
FILE_META_TAG = re.compile(r"\(0002,([0-9A-F]{4})\)\Z")


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
    if element.VR not in STR_VR or vr not in STR_VR or vr == element.VR:
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
    index = _item_index(context.parameters["item_index"], items, "duplicated", path)
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
    index = _item_index(context.parameters["item_index"], items, "removed", path)
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
