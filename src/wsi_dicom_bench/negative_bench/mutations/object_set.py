"""Ordered Data Set edits across a small positive multi-object control."""

from __future__ import annotations

from pathlib import Path

import pydicom

from ..model import GenerationError, MutationContext, MutationResult
from .dataset_edits import apply_operations
from .dicom import save_unvalidated, set_case_sop


def _member(root: Path, relative: object) -> Path:
    if not isinstance(relative, str):
        raise GenerationError("an object-set member path must be a string")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise GenerationError("an object-set member must stay inside its control") from error
    if not path.is_file():
        raise GenerationError(f"object-set member does not exist: {relative}")
    return path


def iod_set_edits(context: MutationContext) -> MutationResult:
    if not context.source.is_dir():
        raise GenerationError("iod_set_edits requires a multi-object control directory")
    if any(context.input_dir.iterdir()):
        raise GenerationError("object-set output directory must be empty")
    members = context.parameters.get("members")
    if not isinstance(members, list) or not members:
        raise GenerationError("iod_set_edits needs a nonempty members list")

    context.changes.clear()
    outputs = []
    edited = False
    for member in members:
        if not isinstance(member, dict):
            raise GenerationError("an object-set member must be an object")
        relative = member.get("path")
        source = _member(context.source, relative)
        destination = context.input_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        dataset = pydicom.dcmread(source)
        operations = member.get("operations")
        if operations:
            apply_operations(context, dataset, operations, str(relative))
            edited = True
        if member.get("retag"):
            before = str(dataset.SOPInstanceUID)
            after = set_case_sop(dataset, context.seed, str(relative))
            context.changes.append(
                {
                    "kind": "harness_identity",
                    "path": str(relative),
                    "attribute": "SOPInstanceUID",
                    "before": before,
                    "value": after,
                }
            )
        save_unvalidated(dataset, destination)
        outputs.append(destination)
    if not edited:
        raise GenerationError("iod_set_edits must edit at least one member")
    return MutationResult(sorted(outputs), context.changes)


HANDLERS = {"iod_set_edits": iod_set_edits}
