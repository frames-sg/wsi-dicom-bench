"""Shared DICOM Data Set paths, Values, change records, and ordered edits."""

from __future__ import annotations

import re

from pydicom import config
from pydicom.datadict import dictionary_VR, tag_for_keyword
from pydicom.dataelem import DataElement
from pydicom.dataset import Dataset
from pydicom.multival import MultiValue
from pydicom.sequence import Sequence
from pydicom.tag import Tag
from pydicom.valuerep import STR_VR

from ..model import GenerationError, MutationContext, MutationResult
from .dicom import save_unvalidated


TAG_TEXT = re.compile(r"\(([0-9A-F]{4}),([0-9A-F]{4})\)")
MAX_LOGGED_TEXT = 96
BINARY_VRS = frozenset({"OB", "OD", "OF", "OL", "OV", "OW", "UN"})
OPERATIONS = ("insert", "set", "replace", "delete")


def tag_for_path(keyword: object) -> Tag:
    if not isinstance(keyword, str):
        raise GenerationError(f"mutation path keyword must be a string: {keyword!r}")
    explicit = TAG_TEXT.fullmatch(keyword)
    if explicit:
        return Tag(int(explicit[1], 16), int(explicit[2], 16))
    tag = tag_for_keyword(keyword)
    if tag is None:
        raise GenerationError(f"mutation path names an unknown DICOM keyword: {keyword}")
    return Tag(tag)


def int_in_range(value: object, low: int, high: int | None = None) -> bool:
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return low <= value and (high is None or value < high)


def item_index(index: object, items: list, what: str, sequence: str) -> int:
    if not int_in_range(index, 0, len(items)):
        raise GenerationError(f"{what} Item index is out of range: {sequence}[{index}]")
    return index


def resolve_path(dataset: Dataset, path: object) -> tuple[Dataset, Tag, str]:
    if not isinstance(path, list) or not path or len(path) % 2 == 0:
        raise GenerationError(
            "mutation path must alternate Sequence keywords and Item indices and end in a keyword"
        )
    current = dataset
    printable = []
    for keyword, index in zip(path[:-1:2], path[1:-1:2]):
        tag = tag_for_path(keyword)
        if tag not in current or current[tag].VR != "SQ":
            raise GenerationError(f"mutation path Sequence is absent: {keyword}")
        items = current[tag].value
        current = items[item_index(index, items, "mutation path", keyword)]
        printable.append(f"{keyword}[{index}]")
    printable.append(path[-1])
    return current, tag_for_path(path[-1]), "/".join(printable)


def logged_value(element: DataElement | None):
    if element is None:
        return None
    if element.VR == "SQ":
        return f"{len(element.value)} Item(s)"
    value = element.value
    if value is None or value == "":
        return ""
    if isinstance(value, (bytes, bytearray)):
        return f"{len(value)} bytes"
    if isinstance(value, (list, tuple, MultiValue)):
        return [_bounded(str(item)) for item in value]
    return _bounded(str(value))


def _bounded(text: str) -> str:
    return text if len(text) <= MAX_LOGGED_TEXT else text[:MAX_LOGGED_TEXT] + "..."


def record_change(
    context: MutationContext, operation: str, path: str, tag: Tag, **fields
) -> None:
    context.changes.append(
        {"kind": "defect", "operation": operation, "path": path, "tag": str(tag), **fields}
    )


def finish(context: MutationContext) -> MutationResult:
    context.changes[0]["value"] = str(context.dataset.SOPInstanceUID)
    save_unvalidated(context.dataset, context.default_output)
    return MutationResult([context.default_output], context.changes)


def require_element(parent: Dataset, tag: Tag, path: str) -> DataElement:
    if tag not in parent:
        raise GenerationError(f"mutation target is absent from the control: {path}")
    return parent[tag]


def manifest_value(raw: object, vr: str):
    if vr == "SQ":
        if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
            raise GenerationError("a Sequence Value must be a list of Item objects")
        items = []
        for item in raw:
            dataset = Dataset()
            for keyword, item_value in sorted(item.items()):
                item_tag = tag_for_path(keyword)
                item_vr = dictionary_VR(item_tag)
                if isinstance(item_value, dict):
                    if set(item_value) != {"vr", "value"} or not isinstance(
                        item_value["vr"], str
                    ):
                        raise GenerationError(
                            f"an explicit-VR Item entry needs only vr and value: {keyword}"
                        )
                    item_vr, item_value = item_value["vr"], item_value["value"]
                dataset.add(DataElement(item_tag, item_vr, manifest_value(item_value, item_vr)))
            items.append(dataset)
        return Sequence(items)
    if raw is None:
        return None
    if vr in BINARY_VRS:
        if not isinstance(raw, str):
            raise GenerationError(f"a {vr} Value must be a hexadecimal string")
        try:
            return bytes.fromhex(raw)
        except ValueError as exc:
            raise GenerationError(f"a {vr} Value must be a hexadecimal string: {exc}") from exc
    if vr in STR_VR:
        if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
            return list(raw)
        if isinstance(raw, str):
            return raw
        raise GenerationError(f"a {vr} Value must be a string or a list of strings")
    if isinstance(raw, bool) or not isinstance(raw, (int, float, list)):
        raise GenerationError(f"a {vr} Value must be numeric")
    return raw


def apply_operations(
    context: MutationContext, dataset: Dataset, operations: object, label: str
) -> None:
    if not isinstance(operations, list) or not operations:
        raise GenerationError(f"{label} operations must be a nonempty list")
    for operation in operations:
        if not isinstance(operation, dict) or operation.get("operation") not in OPERATIONS:
            raise GenerationError(f"{label} operation must name one of {OPERATIONS}")
        kind = operation["operation"]
        parent, tag, path = resolve_path(dataset, operation.get("path"))
        path = f"{label}:{path}" if label else path
        present = tag in parent
        if kind == "insert" and present:
            raise GenerationError(f"inserted attribute is already present: {path}")
        if kind in ("set", "delete"):
            require_element(parent, tag, path)
        before = logged_value(parent[tag]) if present else None
        if kind == "delete":
            vr = parent[tag].VR
            del parent[tag]
            record_change(
                context, "delete_attribute", path, tag, vr=vr, before=before, after=None
            )
            continue
        vr = operation.get("vr") or (parent[tag].VR if present else dictionary_VR(tag))
        with config.disable_value_validation():
            parent[tag] = DataElement(tag, vr, manifest_value(operation.get("value"), vr))
        record_change(
            context,
            f"{kind}_attribute",
            path,
            tag,
            vr=vr,
            before=before,
            after=logged_value(parent[tag]),
        )
