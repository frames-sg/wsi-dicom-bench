"""Mutations for defects that live between Attributes or between SOP Instances.

A relation defect needs more than one Data Element: an Image Laterality that disagrees
with Laterality, a Selector Attribute and its Value Number, or two Instances of one Series
that disagree. ``iod_edits`` applies an ordered list of operations to one object;
``iod_edit_pair`` copies the control as a second SOP Instance of its Series (with its own
Instance Number, so the pair is otherwise consistent) and applies operations to either.  Its
opt-in ``same_sop_instance`` mode restores the first copy's SOP and Instance identity after the
edits, for defects between two stored versions of one SOP Instance.
Each operation is ``{"operation": "insert" | "set" | "replace" | "delete", "path": [...],
"value": ..., "vr": ...}`` with paths as in ``structure``; every change is recorded. A string
``"{self.Keyword}"`` (or ``"{first.Keyword}"`` and ``"{second.Keyword}"`` in a pair) inside a
Value stands for that Instance's Value of the keyword once its case SOP Instance UID and
Instance Number are set, before any operation applies.
"""

from __future__ import annotations

import copy
import re

from pydicom.multival import MultiValue
from pydicom.valuerep import STR_VR

from ..model import GenerationError, MutationContext, MutationResult
from .dataset_edits import apply_operations as _apply, finish as _finish
from .dicom import save_unvalidated, set_case_pair, set_case_sop
PLACEHOLDER = re.compile(r"\{(self|first|second)\.(\w+)\}")


def _resolved(raw: object, instances: dict) -> object:
    """``raw`` with each placeholder replaced by the named Instance's Value."""
    if isinstance(raw, list):
        return [_resolved(item, instances) for item in raw]
    if isinstance(raw, dict):
        return {key: _resolved(item, instances) for key, item in raw.items()}
    match = PLACEHOLDER.fullmatch(raw) if isinstance(raw, str) else None
    if match is None:
        return raw
    label, keyword = match.groups()
    if label not in instances or keyword not in instances[label]:
        raise GenerationError(f"placeholder names an absent Value: {raw}")
    element = instances[label].data_element(keyword)
    if element.VR not in STR_VR:
        return element.value
    if isinstance(element.value, MultiValue):
        return [str(item) for item in element.value]
    return str(element.value)


def iod_edits(context: MutationContext) -> MutationResult:
    set_case_sop(context.dataset, context.seed)
    # Every placeholder is resolved before the first operation applies.
    operations = _resolved(context.parameters.get("operations"), {"self": context.dataset})
    _apply(context, context.dataset, operations, "")
    return _finish(context)


def iod_edit_pair(context: MutationContext) -> MutationResult:
    parameters = context.parameters
    if not parameters.get("first") and not parameters.get("second"):
        raise GenerationError("a pair edit changes the first or the second instance")
    first = context.dataset
    second = copy.deepcopy(first)
    set_case_pair(first, second, context.seed)
    instances = {"first": first, "second": second}
    # Both Instances' placeholders are resolved before either is edited.
    edits = {label: _resolved(parameters[label], instances) for label in instances if parameters.get(label)}
    for label, operations in edits.items():
        _apply(context, instances[label], operations, label)
    same_sop_instance = parameters.get("same_sop_instance", False)
    if not isinstance(same_sop_instance, bool):
        raise GenerationError("same_sop_instance must be a boolean")
    if same_sop_instance:
        before = str(second.SOPInstanceUID)
        second.SOPInstanceUID = first.SOPInstanceUID
        second.file_meta.MediaStorageSOPInstanceUID = first.SOPInstanceUID
        if "InstanceNumber" in first:
            second.InstanceNumber = first.InstanceNumber
        context.changes.append({
            "kind": "same_sop_instance_versions",
            "attribute": "SOPInstanceUID",
            "before": before,
            "after": str(first.SOPInstanceUID),
        })
    context.changes[0]["value"] = [str(first.SOPInstanceUID), str(second.SOPInstanceUID)]
    first_path = context.input_dir / "first.dcm"
    second_path = context.input_dir / "second.dcm"
    save_unvalidated(first, first_path)
    save_unvalidated(second, second_path)
    return MutationResult([first_path, second_path], context.changes)


HANDLERS = {
    "iod_edits": iod_edits,
    "iod_edit_pair": iod_edit_pair,
}
