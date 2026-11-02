"""Authored File-set defects, applied only to a separate copied output tree."""

from __future__ import annotations

import copy
import io
import shutil
from pathlib import Path

import pydicom
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence

from ..model import GenerationError, MutationContext, MutationResult
from .dataset_edits import apply_operations
from .dicom import deterministic_uid


def _write_directory(dataset, destination):
    """Keep valid graph links attached to their records when an edit changes lengths.

    Invalid offsets authored by a case remain invalid. The second write changes
    only fixed-width UL pointer Values, so the measured record positions remain
    valid. Original inputs and their directory offsets are never rewritten.
    """
    records = dataset.DirectoryRecordSequence
    old_offsets = [record.seq_item_tell for record in records]
    encoded = io.BytesIO()
    dataset.save_as(encoded, enforce_file_format=False)
    measured = pydicom.dcmread(io.BytesIO(encoded.getvalue()))
    offsets = dict(zip(old_offsets, [record.seq_item_tell for record in measured.DirectoryRecordSequence], strict=True))
    for keyword in ("OffsetOfTheFirstDirectoryRecordOfTheRootDirectoryEntity",
                    "OffsetOfTheLastDirectoryRecordOfTheRootDirectoryEntity"):
        value = int(getattr(dataset, keyword))
        setattr(dataset, keyword, offsets.get(value, value))
    for record in records:
        for keyword in ("OffsetOfTheNextDirectoryRecord", "OffsetOfReferencedLowerLevelDirectoryEntity"):
            value = int(getattr(record, keyword))
            setattr(record, keyword, offsets.get(value, value))
    dataset.save_as(destination, enforce_file_format=False)


def _icon(changes):
    icon = Dataset()
    for keyword, value in {
        "Rows": 2, "Columns": 2, "SamplesPerPixel": 1,
        "PhotometricInterpretation": "MONOCHROME2", "BitsAllocated": 8,
        "BitsStored": 8, "HighBit": 7, "PixelRepresentation": 0,
        **changes,
    }.items():
        setattr(icon, keyword, value)
    if icon.PhotometricInterpretation == "PALETTE COLOR":
        for color in ("Red", "Green", "Blue"):
            setattr(icon, color + "PaletteColorLookupTableDescriptor", [256, 0, 16])
            setattr(icon, color + "PaletteColorLookupTableData", b"\0" * 512)
    size = (int(icon.Rows) * int(icon.Columns) * int(icon.SamplesPerPixel) * int(icon.BitsAllocated) + 7) // 8
    icon.PixelData = b"\0" * (size + size % 2)
    return icon


def file_set_edits(context: MutationContext) -> MutationResult:
    source = context.source
    if source.name != "DICOMDIR" or not source.is_file():
        raise GenerationError("file_set_edits requires a DICOMDIR source")
    if any(context.input_dir.iterdir()):
        raise GenerationError("File-set output directory must be empty")
    omit = context.parameters.get("omit_file")
    empty = context.parameters.get("empty_directory", False)
    shutil.copytree(
        source.parent, context.input_dir, dirs_exist_ok=True,
        ignore=lambda folder, names: [name for name in names
                                     if (empty and Path(folder) == source.parent and name != "DICOMDIR")
                                     or (omit and str((Path(folder) / name).relative_to(source.parent)) == omit)],
    )
    dataset = context.dataset
    records = dataset.DirectoryRecordSequence
    context.changes.clear()
    if context.parameters.get("empty_directory"):
        dataset.DirectoryRecordSequence = Sequence([])
        dataset.OffsetOfTheFirstDirectoryRecordOfTheRootDirectoryEntity = 0
        dataset.OffsetOfTheLastDirectoryRecordOfTheRootDirectoryEntity = 0
    if "icon" in context.parameters:
        records[3].IconImageSequence = Sequence([_icon(context.parameters["icon"])])
    if context.parameters.get("duplicate_file"):
        duplicate = copy.deepcopy(records[3])
        duplicate.seq_item_tell = 0xFFFF_FFF0
        # Keep the original next sibling and all its file references. Only
        # the newly inserted sibling duplicates a reference.
        records[3].OffsetOfTheNextDirectoryRecord = duplicate.seq_item_tell
        records.append(duplicate)
    if "duplicate_entity" in context.parameters:
        index = {"PATIENT": 0, "STUDY": 1, "SERIES": 2}[context.parameters["duplicate_entity"]]
        original = records[index]
        duplicate = copy.deepcopy(original)
        duplicate.seq_item_tell = 0xFFFF_FFF0
        duplicate.OffsetOfReferencedLowerLevelDirectoryEntity = 0
        original.OffsetOfTheNextDirectoryRecord = duplicate.seq_item_tell
        records.append(duplicate)
        if index == 0:
            dataset.OffsetOfTheLastDirectoryRecordOfTheRootDirectoryEntity = duplicate.seq_item_tell
    if context.parameters.get("shared_child"):
        # Two distinct Series point at the same lower-level entity.
        records[5].OffsetOfReferencedLowerLevelDirectoryEntity = records[2].OffsetOfReferencedLowerLevelDirectoryEntity
    if context.parameters.get("private_record"):
        private = Dataset()
        private.seq_item_tell = 0xFFFF_FFF0
        private.DirectoryRecordType = "PRIVATE"
        private.RecordInUseFlag = 0xFFFF
        private.OffsetOfTheNextDirectoryRecord = 1 if context.parameters.get("private_bad_next") else 0
        private.OffsetOfReferencedLowerLevelDirectoryEntity = 0
        private.PrivateRecordUID = deterministic_uid(context.seed, "private-record")
        records[0].OffsetOfTheNextDirectoryRecord = private.seq_item_tell
        dataset.OffsetOfTheLastDirectoryRecordOfTheRootDirectoryEntity = private.seq_item_tell
        records.append(private)
    if context.parameters.get("unreferenced_file"):
        extra = pydicom.dcmread(source.parent / "SLIDE" / "WSI0")
        extra.SOPInstanceUID = deterministic_uid(context.seed, "unreferenced-instance")
        extra.file_meta.MediaStorageSOPInstanceUID = extra.SOPInstanceUID
        extra.SeriesInstanceUID = deterministic_uid(context.seed, "unreferenced-series")
        extra.save_as(context.input_dir / "EXTRA", enforce_file_format=True)
    for keyword, value in context.parameters.get("file_meta", {}).items():
        setattr(dataset.file_meta, keyword, value)
    operations = context.parameters.get("operations")
    if operations:
        apply_operations(context, dataset, operations, "DICOMDIR")
    _write_directory(dataset, context.input_dir / "DICOMDIR")
    context.changes.append({"kind": "authored_file_set_defect", "parameters": context.parameters})
    return MutationResult(sorted(path for path in context.input_dir.rglob("*") if path.is_file()), context.changes)


HANDLERS = {"file_set_edits": file_set_edits}
