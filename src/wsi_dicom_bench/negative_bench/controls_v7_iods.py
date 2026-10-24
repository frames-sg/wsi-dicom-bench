"""Build the controls-v7 non-WSI pathology IOD controls (DICOM 2026d).

Every control here is a valid object derived from the existing VL WSI control
``controls-v4/CP12-PYRAMID-2L`` (a two-level pyramid: ``level-0.dcm``, 4x4 pixels in four
2x2 RGB tiles, and ``level-1.dcm``, its 2x2 nearest-neighbor reduction). Each control
joins that slide's Patient, Study and Specimen, and uses its Frame of Reference wherever
the IOD places the object in the slide coordinate system. Each control is its own Series.

Derivation. ``build(output)`` reads only the two CP12 files and writes every control in
one pass. Pixel content is a fixed function of the source raster (no random numbers), all
new UIDs are ``2.25`` UIDs hashed from ``UID_NAMESPACE``, the control id and a role, and
every date and time is the source's 1970-01-01 00:00:00. The objects are written by
highdicom (``HIGHDICOM_VERSION``), which is not a dependency of this package: run the
builder from a throwaway environment that has it, with this package on ``PYTHONPATH``::

    <venv-with-highdicom>/bin/python -m wsi_dicom_bench.negative_bench.controls_v7_iods \\
        build <empty-output-dir>

The File-set control ``V7-FILESET`` is written by dcmtk ``dcmmkdir`` (on PATH, 3.7.0) from
byte copies of the CP12 pyramid and of the 2D and 3D annotations and the BINARY SEG built
here. Out of scope by the owner's decision: VL Microscopic, VL Slide-Coordinates
Microscopic, and both Confocal Microscopy IODs.

``verify`` re-hashes the committed files against ``CONTROLS`` and needs only the standard
library.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = PACKAGE_DIR / "controls-v4" / "CP12-PYRAMID-2L"
CONTROLS_DIR = PACKAGE_DIR / "controls-v7" / "iods"
UID_NAMESPACE = "wsi-dicom-bench-controls-v7-iods"
HIGHDICOM_VERSION = "0.28.2"
FIXED_DATE = "19700101"
FIXED_TIME = "000000"
MANUFACTURER = "wsi-dicom-bench"
MODEL = "controls-v7-iods"
SOFTWARE_VERSION = "1"
DEVICE_SERIAL = "RESEARCH"

SOURCE = {
    "id": "CP12-PYRAMID-2L",
    "paths": ("controls-v4/CP12-PYRAMID-2L/level-0.dcm", "controls-v4/CP12-PYRAMID-2L/level-1.dcm"),
}

# Tool limits recorded once and named by each control's ``external`` results.
TOOL_LIMITS = {
    "validate_iods-functional-groups": (
        "validate_iods 2026d reports every Functional Group Macro of the Segmentation and "
        "Parametric Map IODs as 'Tag ... is unexpected' in the Shared and Per-Frame Functional "
        "Groups Sequences: it does not load those IODs' Functional Group tables "
        "(PS3.3 A.51.5, A.75.5). The tags it names are the Macros the IOD requires."
    ),
    "validate_iods-no-ann": (
        "validate_iods 2026d prints 'Unknown or retired SOP Class UID: "
        "1.2.840.10008.5.1.4.1.1.91.1' and exits 1: it has no Microscopy Bulk Simple "
        "Annotations IOD (PS3.3 A.87), so it gives no verdict."
    ),
    "dcentvfy-accession-ie": (
        "dcentvfy on a set holding a Key Object Selection or SR document and a VL WSI image "
        "warns 'Different information entities for attribute - Element=<AccessionNumber> "
        "IE <Study> versus <Series>' (dicom3tools places it in the Series IE of the VL WSI "
        "image). Accession Number (0008,0050) is in the General Study Module of both IODs "
        "(PS3.3 C.7.2.1) and its Value is identical (RESEARCH); dcentvfy exits 0."
    ),
    "candidate-no-kos-sr-rules": (
        "the frozen candidate predates KOS and SR support: iod-modules is 'skipped' with "
        "'... is not a SOP Class of the pathology-slide IODs ...; no IOD rules apply'."
    ),
    "dciodvfy-dicomdir-annotation": (
        "dciodvfy on the DICOMDIR reports 'Error - </DirectoryRecordSequence(0004,1220)[9]/"
        "DirectoryRecordType(0004,1430)[1]> - Unrecognized enumerated value = <ANNOTATION>' "
        "(and [11]): ANNOTATION is an Enumerated Value of Directory Record Type in PS3.3 "
        "2026d F.3.2.2, with the record defined in F.5.47. Its warnings 'Attribute is not "
        "present in standard DICOM IOD' name Image Type in IMAGE records and Content Date, "
        "Content Time and Content Identification keys in ANNOTATION records, which F.5.4 and "
        "F.5.47 allow ('Any other Attribute of the ... IE Modules', Type 3; Table 10-12)."
    ),
    "validate_iods-dicomdir": (
        "validate_iods on the File-set directory prints 'Missing SOP Class UID' for the "
        "DICOMDIR (it has no Basic Directory IOD), the validate_iods-no-ann line for each "
        "annotation, and validate_iods-functional-groups for the SEG."
    ),
    "candidate-no-fileset": (
        "the frozen candidate's directory mode only reads '*.dcm' files ('DICOM validation "
        "failed: no .dcm files found under .../fileset'), and File IDs cannot carry an "
        "extension (PS3.10 8.2), so it cannot validate a File-set as a set; given the DICOMDIR "
        "file it reports iod-modules 'skipped' for SOP Class 1.2.840.10008.1.3.10 ('no IOD "
        "rules apply') and runs no File-set checks."
    ),
    "dcentvfy-single-file": (
        "dcentvfy on a derived object alone reports 'Missing SOPInstanceUID that was "
        "referenced' for its source; it is run on the set of the object and CP12 instead."
    ),
}

# The registry. ``sha256`` maps each path (relative to controls-v7/iods) to its digest.
# ``external`` and ``candidate`` record the results on the file alone and, for objects that
# reference CP12, on the set {CP12 level-0, level-1, control}.
CONTROLS: tuple[dict, ...] = (
    {
        "id": "V7-SEG-BINARY",
        "paths": ("seg-binary.dcm",),
        "sop_class_uid": "1.2.840.10008.5.1.4.1.1.66.4",
        "iod": "Segmentation (BINARY)",
        "exercises": (
            "Segmentation IOD, Segmentation Type BINARY, one segment, 1-bit Pixel Data packed "
            "contiguously across Frames; four 2x2 Frames on the four CP12 level-0 tiles, "
            "TILED_SPARSE with Plane Position (Slide) and Derivation Image per Frame; "
            "Explicit VR Little Endian"
        ),
        "references": SOURCE["paths"][:1],
        "built_with": (
            "highdicom 0.28.2 Segmentation from CP12 level-0; mask = mean RGB < 64; Pixel Data "
            "re-packed without per-Frame byte padding"
        ),
        "sha256": {"seg-binary.dcm": "d50b81ae5c99b4ad0350608253bab8afcbaa33022f7a752a60a37f879e89bc42"},
        "external": {
            "dciodvfy": "no errors, no warnings",
            "dcentvfy": "set: no errors",
            "validate_iods": "tool limit validate_iods-functional-groups (rc 5)",
        },
        "candidate": "general: every intrinsic check passed; set: every intrinsic check passed",
    },
    {
        "id": "V7-SEG-FRACTIONAL",
        "paths": ("seg-fractional.dcm",),
        "sop_class_uid": "1.2.840.10008.5.1.4.1.1.66.4",
        "iod": "Segmentation (FRACTIONAL, PROBABILITY)",
        "exercises": (
            "Segmentation IOD, Segmentation Type FRACTIONAL, Segmentation Fractional Type "
            "PROBABILITY, Maximum Fractional Value 255, 8-bit; four 2x2 Frames on the CP12 "
            "level-0 tiles, TILED_SPARSE; Explicit VR Little Endian"
        ),
        "references": SOURCE["paths"][:1],
        "built_with": "highdicom 0.28.2 Segmentation from CP12 level-0; p = (255 - mean RGB) / 255",
        "sha256": {"seg-fractional.dcm": "f672b51762102c72754b86a7f3d9a061be9a7e97ad311f20052b4747e70f25ae"},
        "external": {
            "dciodvfy": "no errors, no warnings",
            "dcentvfy": "set: no errors",
            "validate_iods": "tool limit validate_iods-functional-groups (rc 5)",
        },
        "candidate": "general: every intrinsic check passed; set: every intrinsic check passed",
    },
    {
        "id": "V7-SEG-LABELMAP",
        "paths": ("seg-labelmap.dcm",),
        "sop_class_uid": "1.2.840.10008.5.1.4.1.1.66.7",
        "iod": "Label Map Segmentation",
        "exercises": (
            "Label Map Segmentation SOP Class, Segmentation Type LABELMAP, two segments and "
            "background 0 as Pixel Padding Value, 8-bit MONOCHROME2; four 2x2 Frames on the "
            "CP12 level-0 tiles, TILED_SPARSE, no Segment Identification group; Explicit VR "
            "Little Endian"
        ),
        "references": SOURCE["paths"][:1],
        "built_with": (
            "highdicom 0.28.2 Segmentation (LABELMAP) from CP12 level-0; label 1 if mean RGB < "
            "64, 2 if < 128, else 0; empty Patient Orientation added"
        ),
        "sha256": {"seg-labelmap.dcm": "5fa1b8a5db00f0b1d29738dc1186e739117be085331e332bf7027868124b8a5c"},
        "external": {
            "dciodvfy": (
                "no errors, no warnings (without Patient Orientation: 'Error - "
                "</PatientOrientation(0020,0020)> - Missing attribute for Type 2C Conditional - "
                "Module=<GeneralImage>', which it does not report for the BINARY and FRACTIONAL "
                "class)"
            ),
            "dcentvfy": "set: no errors",
            "validate_iods": "tool limit validate_iods-functional-groups (rc 4)",
        },
        "candidate": "general: every intrinsic check passed; set: every intrinsic check passed",
    },
    {
        "id": "V7-PM-FLOAT",
        "paths": ("pm-float.dcm",),
        "sop_class_uid": "1.2.840.10008.5.1.4.1.1.30",
        "iod": "Parametric Map",
        "exercises": (
            "Parametric Map IOD, 32-bit Float Pixel Data (7FE0,0008) with the Floating Point "
            "Image Pixel Module, shared Real World Value Mapping (double-float first/last value "
            "mapped, slope 1, intercept 0, UCUM unit 1), Frame VOI LUT, Parametric Map Frame "
            "Type DERIVED\\PRIMARY\\VOLUME\\QUANTITY; four 2x2 Frames on the CP12 level-0 tiles, "
            "TILED_SPARSE; Explicit VR Little Endian"
        ),
        "references": SOURCE["paths"][:1],
        "built_with": (
            "highdicom 0.28.2 ParametricMap from CP12 level-0; OD = -log10((mean RGB + 1) / 256)"
        ),
        "sha256": {"pm-float.dcm": "ab8670b0fc896935705591eccc2543b0b27f627773a0cc6ef30eb2061453ac60"},
        "external": {
            "dciodvfy": "no errors, no warnings",
            "dcentvfy": "set: no errors",
            "validate_iods": "tool limit validate_iods-functional-groups (rc 8)",
        },
        "candidate": "general: every intrinsic check passed; set: every intrinsic check passed",
    },
    {
        "id": "V7-ANN-2D",
        "paths": ("ann-2d.dcm",),
        "sop_class_uid": "1.2.840.10008.5.1.4.1.1.91.1",
        "iod": "Microscopy Bulk Simple Annotations (2D)",
        "exercises": (
            "Microscopy Bulk Simple Annotations IOD, Annotation Coordinate Type 2D, Pixel Origin "
            "Interpretation VOLUME on CP12 level-0; group 1 POINT (2 nuclei, MANUAL) with a "
            "Diameter measurement in um; group 2 POLYGON (2 open 4-vertex polygons, AUTOMATIC "
            "with Algorithm Identification) with an Area measurement in um2; float Point "
            "Coordinates Data and Long Primitive Point Index List; Explicit VR Little Endian"
        ),
        "references": SOURCE["paths"][:1],
        "built_with": "highdicom 0.28.2 MicroscopyBulkSimpleAnnotations from CP12 level-0",
        "sha256": {"ann-2d.dcm": "4800f018c177b754fd3780846b2fca1d489ac694089d18bcd2e0602932de8a13"},
        "external": {
            "dciodvfy": "no errors, no warnings",
            "dcentvfy": "set: no errors",
            "validate_iods": "tool limit validate_iods-no-ann (rc 1)",
        },
        "candidate": "general: every intrinsic check passed; set: every intrinsic check passed",
    },
    {
        "id": "V7-ANN-3D",
        "paths": ("ann-3d.dcm",),
        "sop_class_uid": "1.2.840.10008.5.1.4.1.1.91.1",
        "iod": "Microscopy Bulk Simple Annotations (3D)",
        "exercises": (
            "Microscopy Bulk Simple Annotations IOD, Annotation Coordinate Type 3D on the CP12 "
            "slide Frame of Reference (Frame of Reference Module present); one POLYGON group "
            "(MANUAL) in slide coordinates (mm) as Double Point Coordinates Data with Common Z "
            "Coordinate Value 0, with an Area measurement in um2; "
            "Explicit VR Little Endian"
        ),
        "references": SOURCE["paths"][:1],
        "built_with": "highdicom 0.28.2 MicroscopyBulkSimpleAnnotations from CP12 level-0",
        "sha256": {"ann-3d.dcm": "71e805e73d5a9afa99d2bb0f2eaedb6e3771884e5444ef4201b9bb8b0144208c"},
        "external": {
            "dciodvfy": "no errors, no warnings",
            "dcentvfy": "set: no errors",
            "validate_iods": "tool limit validate_iods-no-ann (rc 1)",
        },
        "candidate": "general: every intrinsic check passed; set: every intrinsic check passed",
    },
    {
        "id": "V7-KOS-ACQ-COMPLETE",
        "paths": ("kos-acquisition-complete.dcm",),
        "sop_class_uid": "1.2.840.10008.5.1.4.1.1.88.59",
        "iod": "Key Object Selection Document (acquisition complete)",
        "exercises": (
            "Key Object Selection Document IOD, TID 2010 titled (113034, DCM, \"Complete "
            "Acquisition Content\") per CP-LAB-281, referencing every instance of the CP12 WSI "
            "Series (level-0 and level-1) as IMAGE items, with the Current Requested Procedure "
            "Evidence Sequence listing the same two; Explicit VR Little Endian"
        ),
        "references": SOURCE["paths"],
        "built_with": "highdicom 0.28.2 KeyObjectSelectionDocument; Study Description copied from CP12",
        "sha256": {
            "kos-acquisition-complete.dcm": "5c63dca5e05dcb7f9a983227178338a537d45958147a377e1dcc854ee4cb1868"
        },
        "external": {
            "dciodvfy": "no errors, no warnings",
            "dcentvfy": "set: rc 0, tool limit dcentvfy-accession-ie (one warning)",
            "validate_iods": "no errors (rc 0)",
        },
        "candidate": (
            "general: every intrinsic check passed, iod-modules skipped "
            "(candidate-no-kos-sr-rules); set: same, rc 0"
        ),
    },
    {
        "id": "V7-KOS-REJECTED-QUALITY",
        "paths": ("kos-rejected-quality.dcm",),
        "sop_class_uid": "1.2.840.10008.5.1.4.1.1.88.59",
        "iod": "Key Object Selection Document (quality rejection)",
        "exercises": (
            "Key Object Selection Document IOD, TID 2010 titled (113001, DCM, \"Rejected for "
            "Quality Reasons\") with a Document Title Modifier (111219, DCM, \"Inappropriate "
            "image processing\") from CID 7011, rejecting CP12 level-1; Explicit VR Little Endian"
        ),
        "references": SOURCE["paths"][1:],
        "built_with": (
            "highdicom 0.28.2 KeyObjectSelectionDocument, Document Title Modifier item inserted "
            "first; Study Description copied from CP12"
        ),
        "sha256": {
            "kos-rejected-quality.dcm": "7d3707c5d83b24313ce381f498452ed43919b12d680ca60883a7ebe34fcd7765"
        },
        "external": {
            "dciodvfy": "no errors, no warnings",
            "dcentvfy": "set: rc 0, tool limit dcentvfy-accession-ie (one warning)",
            "validate_iods": "no errors (rc 0)",
        },
        "candidate": (
            "general: every intrinsic check passed, iod-modules skipped "
            "(candidate-no-kos-sr-rules); set: same, rc 0"
        ),
    },
    {
        "id": "V7-SR-TID1500",
        "paths": ("sr-tid1500.dcm",),
        "sop_class_uid": "1.2.840.10008.5.1.4.1.1.88.33",
        "iod": "Comprehensive SR (TID 1500)",
        "exercises": (
            "Comprehensive SR IOD with a TID 1500 Imaging Measurement Report: device observer, "
            "specimen subject context (CP12 Specimen UID, Identifier and Container Identifier), "
            "Procedure Reported (112703, DCM, \"Whole Slide Imaging\"), one TID 1410 Planar ROI "
            "group whose Image Region is a closed SCOORD POLYLINE on CP12 level-0 with Pixel "
            "Origin Interpretation VOLUME, and an Area measurement in um2; Explicit VR Little "
            "Endian"
        ),
        "references": SOURCE["paths"][:1],
        "built_with": "highdicom 0.28.2 ComprehensiveSR + MeasurementReport; Study Description copied",
        "sha256": {"sr-tid1500.dcm": "3a15cb86b70e8a216107e0f7a5f8fd3e1a113ca74c7289d9819e62a5c1fa6f10"},
        "external": {
            "dciodvfy": "no errors, no warnings",
            "dcentvfy": "set: rc 0, tool limit dcentvfy-accession-ie (two warnings)",
            "validate_iods": "no errors (rc 0)",
        },
        "candidate": (
            "general: every intrinsic check passed, iod-modules skipped "
            "(candidate-no-kos-sr-rules); set: same, rc 0"
        ),
    },
    {
        "id": "V7-SR-3D",
        "paths": ("sr-3d.dcm",),
        "sop_class_uid": "1.2.840.10008.5.1.4.1.1.88.34",
        "iod": "Comprehensive 3D SR (TID 1500)",
        "exercises": (
            "Comprehensive 3D SR IOD with a TID 1500 Imaging Measurement Report whose TID 1410 "
            "Planar ROI is a closed SCOORD3D POLYGON at Z 0 in slide coordinates (mm), "
            "Referenced Frame of Reference UID = the CP12 slide Frame of Reference, with an "
            "Area measurement in um2 and the specimen subject context; Explicit VR Little Endian"
        ),
        "references": SOURCE["paths"][:1],
        "built_with": "highdicom 0.28.2 Comprehensive3DSR + MeasurementReport; Study Description copied",
        "sha256": {"sr-3d.dcm": "e5bd068f4c0ae807cd00bcf42f7abf8c28b31aadd67667b30f47249636380e35"},
        "external": {
            "dciodvfy": "no errors, no warnings",
            "dcentvfy": "set: rc 0, tool limit dcentvfy-accession-ie (two warnings)",
            "validate_iods": "no errors (rc 0)",
        },
        "candidate": (
            "general: every intrinsic check passed, iod-modules skipped "
            "(candidate-no-kos-sr-rules); set: same, rc 0"
        ),
    },
    {
        "id": "V7-FILESET",
        "paths": (
            "fileset/DICOMDIR",
            "fileset/SLIDE/WSI0",
            "fileset/SLIDE/WSI1",
            "fileset/SLIDE/ANN2D",
            "fileset/SLIDE/ANN3D",
            "fileset/SLIDE/SEG",
        ),
        "sop_class_uid": "1.2.840.10008.1.3.10",
        "iod": "Basic Directory (DICOMDIR File-set)",
        "exercises": (
            "Media Storage Directory (Basic Directory IOD), General Purpose profile "
            "STD-GEN-CD/DVD-RAM/BD, File-set ID CP12SLIDE: one PATIENT, one STUDY, four SERIES; "
            "IMAGE records for the CP12 pyramid (WSI0 = level-0, WSI1 = level-1, byte copies) "
            "and the BINARY SEG, ANNOTATION records (F.5.47) for the 2D and 3D Bulk "
            "Annotations; every Referenced File ID exists and its SOP Class, SOP Instance and "
            "Transfer Syntax UIDs match the record"
        ),
        "references": SOURCE["paths"],
        "built_with": (
            "dcmmkdir 3.7.0 -Pgp +F CP12SLIDE -I with the File IDs in FILESET_MEMBERS order; "
            "then the invented Media Storage SOP Instance UID replaced by uid(V7-FILESET, "
            "dicomdir) with every record offset moved to the record's new position (pydicom)"
        ),
        "sha256": {
            "fileset/DICOMDIR": "4dfac6397116c567696baf999b230e977d7e1fae1932c6e8e174307039ed0c85",
            "fileset/SLIDE/WSI0": "218b2b6f6904bf12630a718713b692d1ff26112f4a9af295252117d3f4ec69c0",
            "fileset/SLIDE/WSI1": "5b7ae5d4613196d008f629d74595147b98ee193951e2d0e9df9ea8d8425cd0a4",
            "fileset/SLIDE/ANN2D": "4800f018c177b754fd3780846b2fca1d489ac694089d18bcd2e0602932de8a13",
            "fileset/SLIDE/ANN3D": "71e805e73d5a9afa99d2bb0f2eaedb6e3771884e5444ef4201b9bb8b0144208c",
            "fileset/SLIDE/SEG": "d50b81ae5c99b4ad0350608253bab8afcbaa33022f7a752a60a37f879e89bc42",
        },
        "external": {
            "dciodvfy": "DICOMDIR: rc 1, tool limit dciodvfy-dicomdir-annotation (2 errors, 15 warnings)",
            "dcmdump": "DICOMDIR parses (rc 0); every offset lands on a record",
            "dcentvfy": "the five member files: no errors (rc 0)",
            "validate_iods": "tool limit validate_iods-dicomdir (rc 8)",
            "referenced_files": "all 5 exist; SOP Class, SOP Instance and Transfer Syntax UIDs match",
        },
        "candidate": (
            "tool limit candidate-no-fileset; each member file alone: every intrinsic check passed"
        ),
    },
)


def uid(control_id: str, role: str) -> str:
    digest = hashlib.sha256(f"{UID_NAMESPACE}:{control_id}:{role}".encode()).digest()[:16]
    return f"2.25.{int.from_bytes(digest, 'big')}"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_highdicom():
    try:
        import highdicom
    except ImportError as error:  # pragma: no cover - build-time only
        raise RuntimeError(
            "controls_v7_iods build needs highdicom; run it from a throwaway venv"
        ) from error
    if highdicom.__version__ != HIGHDICOM_VERSION:
        raise RuntimeError(
            f"controls_v7_iods was derived with highdicom {HIGHDICOM_VERSION}, "
            f"found {highdicom.__version__}"
        )
    return highdicom


def _load_sources():
    import pydicom

    level_zero = pydicom.dcmread(SOURCE_DIR / "level-0.dcm")
    level_one = pydicom.dcmread(SOURCE_DIR / "level-1.dcm")
    if level_zero.pixel_array.shape != (4, 2, 2, 3):
        raise RuntimeError("CP12 level-0 is no longer four 2x2 RGB tiles")
    return level_zero, level_one


GENERATED_UID_ROOTS = ("1.2.826.0.1.3680043.10.511.", "1.2.826.0.1.3680043.8.498.")


def _determinize(dataset, control_id: str) -> None:
    """Make highdicom's output a function of its inputs alone.

    Every non-empty DA, TM and DT becomes the source's 1970-01-01 00:00:00 (highdicom stamps
    Content, Series and Contribution dates with the build time), and every UID highdicom or
    pydicom generated at random (their UID roots) becomes ``uid(control_id, generated-N)``,
    numbered in traversal order and replaced consistently at every reference.
    """
    mapping: dict[str, str] = {}
    fixed = {"DA": FIXED_DATE, "TM": FIXED_TIME, "DT": FIXED_DATE + FIXED_TIME}

    def visit(ds) -> None:
        for element in ds:
            if element.VR == "SQ":
                for item in element.value:
                    visit(item)
            elif element.VR in fixed and element.value not in (None, ""):
                element.value = fixed[element.VR]
            elif element.VR == "UI" and element.value:
                values = element.value if element.VM > 1 else [element.value]
                replaced = []
                for value in values:
                    if str(value).startswith(GENERATED_UID_ROOTS):
                        if value not in mapping:
                            mapping[value] = uid(control_id, f"generated-{len(mapping) + 1}")
                        value = mapping[value]
                    replaced.append(value)
                element.value = replaced if element.VM > 1 else replaced[0]

    visit(dataset)
    if "SOPInstanceUID" in dataset:
        dataset.file_meta.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID


def _equipment(control_id: str, series_number: int) -> dict:
    return {
        "series_instance_uid": uid(control_id, "series"),
        "series_number": series_number,
        "sop_instance_uid": uid(control_id, "instance"),
        "instance_number": 1,
        "manufacturer": MANUFACTURER,
        "manufacturer_model_name": MODEL,
        "software_versions": SOFTWARE_VERSION,
        "device_serial_number": DEVICE_SERIAL,
    }


def _tissue_mask(level_zero):
    """Binary tissue mask of level-0 as four 2x2 frames: pixels darker than mid-gray."""
    import numpy as np

    luminance = level_zero.pixel_array.astype(np.uint16).sum(axis=-1) // 3
    return (luminance < 64).astype(np.uint8)


def _segment_description(hd, number: int, label: str, algorithm: str):
    from pydicom.sr.codedict import codes

    return hd.seg.SegmentDescription(
        segment_number=number,
        segment_label=label,
        segmented_property_category=codes.SCT.Tissue,
        segmented_property_type=codes.SCT.Tissue,
        algorithm_type=hd.seg.SegmentAlgorithmTypeValues.AUTOMATIC,
        algorithm_identification=hd.AlgorithmIdentificationSequence(
            name=algorithm, version="1", family=codes.cid7162.ArtificialIntelligence
        ),
    )


def _repack_binary_frames(seg, mask) -> None:
    """Write BINARY Pixel Data as one contiguous bit stream (PS3.5 2026d 8.1.1).

    highdicom 0.28.2 pads every Frame to a whole byte; a 2x2 Frame holds 4 bits, so four
    Frames must share 2 bytes, with no padding between Frames.
    """
    from pydicom.pixels import pack_bits

    if int(seg.NumberOfFrames) != mask.shape[0]:
        raise RuntimeError("BINARY SEG frame count no longer matches its source tiles")
    packed = pack_bits(mask.reshape(-1), pad=True)
    seg.PixelData = packed
    seg["PixelData"].VR = "OB"


def _build_seg_binary(hd, level_zero, level_one):
    control_id = "V7-SEG-BINARY"
    mask = _tissue_mask(level_zero)
    seg = hd.seg.Segmentation(
        source_images=[level_zero],
        pixel_array=mask,
        segmentation_type=hd.seg.SegmentationTypeValues.BINARY,
        segment_descriptions=[_segment_description(hd, 1, "Tissue", "luminance-threshold-64")],
        omit_empty_frames=False,
        **_equipment(control_id, 101),
    )
    _repack_binary_frames(seg, mask)
    _determinize(seg, control_id)
    return control_id, {"seg-binary.dcm": seg}


def _luminance(level_zero):
    import numpy as np

    return level_zero.pixel_array.astype(np.uint16).sum(axis=-1) // 3


def _build_seg_fractional(hd, level_zero, level_one):
    import numpy as np

    control_id = "V7-SEG-FRACTIONAL"
    # Tissue probability falls linearly with luminance: 1.0 at 0, 0.0 at 255.
    probability = (255 - _luminance(level_zero)).astype(np.float32) / 255.0
    seg = hd.seg.Segmentation(
        source_images=[level_zero],
        pixel_array=probability,
        segmentation_type=hd.seg.SegmentationTypeValues.FRACTIONAL,
        fractional_type=hd.seg.SegmentationFractionalTypeValues.PROBABILITY,
        max_fractional_value=255,
        segment_descriptions=[_segment_description(hd, 1, "Tissue", "inverse-luminance")],
        omit_empty_frames=False,
        **_equipment(control_id, 102),
    )
    _determinize(seg, control_id)
    return control_id, {"seg-fractional.dcm": seg}


def _build_seg_labelmap(hd, level_zero, level_one):
    import numpy as np

    control_id = "V7-SEG-LABELMAP"
    luminance = _luminance(level_zero)
    labels = np.where(luminance < 64, 1, np.where(luminance < 128, 2, 0)).astype(np.uint8)
    seg = hd.seg.Segmentation(
        source_images=[level_zero],
        pixel_array=labels,
        segmentation_type=hd.seg.SegmentationTypeValues.LABELMAP,
        segment_descriptions=[
            _segment_description(hd, 1, "Dense tissue", "luminance-bands-64-128"),
            _segment_description(hd, 2, "Light tissue", "luminance-bands-64-128"),
        ],
        omit_empty_frames=False,
        **_equipment(control_id, 103),
    )
    # General Image Patient Orientation is Type 2C; highdicom omits it. Its 2026d condition
    # ("does not require Image Orientation (Patient) and Image Position (Patient) or ... does
    # not require Image Orientation (Slide)") is read by dciodvfy as requiring it for the
    # Label Map class, and an empty Value is permitted under every reading.
    seg.PatientOrientation = ""
    _determinize(seg, control_id)
    return control_id, {"seg-labelmap.dcm": seg}


def _optical_density(level_zero):
    import numpy as np

    # OD = -log10((I + 1) / 256) of the mean RGB intensity I, per tile.
    return (-np.log10((_luminance(level_zero).astype(np.float64) + 1.0) / 256.0)).astype(
        np.float32
    )


def _build_pm(hd, level_zero, level_one):
    from highdicom.sr.coding import CodedConcept

    control_id = "V7-PM-FLOAT"
    density = _optical_density(level_zero)
    mapping = hd.pm.RealWorldValueMapping(
        lut_label="OD",
        lut_explanation="Optical density of mean RGB intensity",
        unit=CodedConcept("1", "UCUM", "no units"),
        value_range=(float(density.min()), float(density.max())),
        slope=1.0,
        intercept=0.0,
    )
    pm = hd.pm.ParametricMap(
        source_images=[level_zero],
        pixel_array=density,
        contains_recognizable_visual_features=False,
        real_world_value_mappings=[mapping],
        voi_lut_transformations=[
            hd.VOILUTTransformation(
                window_center=float(density.mean()),
                window_width=float(density.max() - density.min()),
            )
        ],
        content_label="OPTICALDENSITY",
        **_equipment(control_id, 104),
    )
    _determinize(pm, control_id)
    return control_id, {"pm-float.dcm": pm}


def _pixel_spacing_um(level_zero) -> tuple[float, float]:
    """(row spacing, column spacing) of level-0 in micrometers."""
    spacing = level_zero.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0].PixelSpacing
    return float(spacing[0]) * 1000.0, float(spacing[1]) * 1000.0


def _build_ann_2d(hd, level_zero, level_one):
    import numpy as np
    from pydicom.sr.codedict import codes

    control_id = "V7-ANN-2D"
    row_um, column_um = _pixel_spacing_um(level_zero)
    # Nuclei marked by hand at two pixel centers of the 4x4 Total Pixel Matrix (column, row),
    # whose top left corner is 0\\0.
    points = [np.array([[1.5, 1.5]]), np.array([[3.5, 2.5]])]
    nuclei = hd.ann.AnnotationGroup(
        number=1,
        uid=uid(control_id, "group-1"),
        label="Nuclei",
        annotated_property_category=codes.SCT.AnatomicalStructure,
        annotated_property_type=codes.SCT.Nucleus,
        graphic_type=hd.ann.GraphicTypeValues.POINT,
        graphic_data=points,
        algorithm_type=hd.ann.AnnotationGroupGenerationTypeValues.MANUAL,
        measurements=[
            hd.ann.Measurements(
                name=codes.SCT.Diameter,
                values=np.array([0.5, 0.75], dtype=np.float32),
                unit=codes.UCUM.Micrometer,
            )
        ],
    )
    # Two tissue regions: the left and right halves of the matrix, open polygons in
    # (column, row) Total Pixel Matrix coordinates, where the top left corner of the top left
    # pixel is 0\\0 and the bottom right corner of the matrix is 4\\4 (the sub-pixel
    # convention of PS3.3 C.18.6 and C.37); area from the level-0 Pixel Spacing.
    regions = [
        np.array([[0.0, 0.0], [2.0, 0.0], [2.0, 4.0], [0.0, 4.0]]),
        np.array([[2.0, 0.0], [4.0, 0.0], [4.0, 4.0], [2.0, 4.0]]),
    ]
    areas = np.array([2.0 * column_um * 4.0 * row_um] * 2, dtype=np.float32)
    tissue = hd.ann.AnnotationGroup(
        number=2,
        uid=uid(control_id, "group-2"),
        label="Tissue regions",
        annotated_property_category=codes.SCT.Tissue,
        annotated_property_type=codes.SCT.Tissue,
        graphic_type=hd.ann.GraphicTypeValues.POLYGON,
        graphic_data=regions,
        algorithm_type=hd.ann.AnnotationGroupGenerationTypeValues.AUTOMATIC,
        algorithm_identification=hd.AlgorithmIdentificationSequence(
            name="half-split", version="1", family=codes.cid7162.ArtificialIntelligence
        ),
        measurements=[
            hd.ann.Measurements(name=codes.SCT.Area, values=areas, unit=codes.UCUM.SquareMicrometer)
        ],
    )
    ann = hd.ann.MicroscopyBulkSimpleAnnotations(
        source_images=[level_zero],
        annotation_coordinate_type=hd.ann.AnnotationCoordinateTypeValues.SCOORD,
        annotation_groups=[nuclei, tissue],
        pixel_origin_interpretation=hd.ann.PixelOriginInterpretationValues.VOLUME,
        content_label="ANN2D",
        **_equipment(control_id, 105),
    )
    _determinize(ann, control_id)
    return control_id, {"ann-2d.dcm": ann}


def _build_ann_3d(hd, level_zero, level_one):
    import numpy as np
    from pydicom.sr.codedict import codes

    control_id = "V7-ANN-3D"
    # A tissue outline on the slide surface (Z 0) inside the CP12 imaged volume
    # (0.001 mm wide, 0.002 mm high from the origin at X 0, Y 0), in slide coordinates (mm).
    outline = np.array(
        [[0.0001, 0.0002, 0.0], [0.0009, 0.0002, 0.0], [0.0009, 0.0018, 0.0], [0.0001, 0.0018, 0.0]]
    )
    area_um2 = (0.0008 * 1000.0) * (0.0016 * 1000.0)
    group = hd.ann.AnnotationGroup(
        number=1,
        uid=uid(control_id, "group-1"),
        label="Tissue outline",
        annotated_property_category=codes.SCT.Tissue,
        annotated_property_type=codes.SCT.Tissue,
        graphic_type=hd.ann.GraphicTypeValues.POLYGON,
        graphic_data=[outline],
        algorithm_type=hd.ann.AnnotationGroupGenerationTypeValues.MANUAL,
        measurements=[
            hd.ann.Measurements(
                name=codes.SCT.Area,
                values=np.array([area_um2], dtype=np.float32),
                unit=codes.UCUM.SquareMicrometer,
            )
        ],
    )
    ann = hd.ann.MicroscopyBulkSimpleAnnotations(
        source_images=[level_zero],
        annotation_coordinate_type=hd.ann.AnnotationCoordinateTypeValues.SCOORD3D,
        annotation_groups=[group],
        content_label="ANN3D",
        **_equipment(control_id, 106),
    )
    _determinize(ann, control_id)
    return control_id, {"ann-3d.dcm": ann}


STUDY_KEYWORDS = ("StudyDescription",)


def _copy_study(dataset, source) -> None:
    """Give a document the source's Study attributes that highdicom leaves out."""
    for keyword in STUDY_KEYWORDS:
        if keyword in source and keyword not in dataset:
            setattr(dataset, keyword, getattr(source, keyword))


def _kos(hd, control_id: str, series_number: int, title, references, modifier=None):
    content = hd.ko.KeyObjectSelection(document_title=title, referenced_objects=references)
    if modifier is not None:
        # TID 2010 row 2: Document Title Modifier from CID 7011, allowed when the title is
        # (113001, DCM, "Rejected for Quality Reasons"); it precedes the references.
        from pydicom.sr.codedict import codes

        item = hd.sr.CodeContentItem(
            name=codes.DCM.DocumentTitleModifier,
            value=modifier,
            relationship_type=hd.sr.RelationshipTypeValues.HAS_CONCEPT_MOD,
        )
        content[0].ContentSequence.insert(0, item)
    kos = hd.ko.KeyObjectSelectionDocument(
        evidence=references,
        content=content,
        series_instance_uid=uid(control_id, "series"),
        series_number=series_number,
        sop_instance_uid=uid(control_id, "instance"),
        instance_number=1,
        manufacturer=MANUFACTURER,
    )
    _copy_study(kos, references[0])
    _determinize(kos, control_id)
    return kos


def _build_kos_acquisition_complete(hd, level_zero, level_one):
    from pydicom.sr.codedict import codes

    control_id = "V7-KOS-ACQ-COMPLETE"
    kos = _kos(hd, control_id, 107, codes.DCM.CompleteAcquisitionContent, [level_zero, level_one])
    return control_id, {"kos-acquisition-complete.dcm": kos}


def _build_kos_rejected_quality(hd, level_zero, level_one):
    from pydicom.sr.codedict import codes

    control_id = "V7-KOS-REJECTED-QUALITY"
    kos = _kos(
        hd,
        control_id,
        108,
        codes.DCM.RejectedForQualityReasons,
        [level_one],
        modifier=codes.DCM.InappropriateImageProcessing,
    )
    return control_id, {"kos-rejected-quality.dcm": kos}


def _observation_context(hd, control_id: str, level_zero):
    from pydicom.sr.codedict import codes

    specimen = level_zero.SpecimenDescriptionSequence[0]
    return hd.sr.ObservationContext(
        observer_device_context=hd.sr.ObserverContext(
            observer_type=codes.DCM.Device,
            observer_identifying_attributes=hd.sr.DeviceObserverIdentifyingAttributes(
                uid=uid(control_id, "observer-device"), name=MODEL, manufacturer_name=MANUFACTURER
            ),
        ),
        subject_context=hd.sr.SubjectContext(
            subject_class=codes.DCM.Specimen,
            subject_class_specific_context=hd.sr.SubjectContextSpecimen(
                uid=specimen.SpecimenUID,
                identifier=specimen.SpecimenIdentifier,
                container_identifier=level_zero.ContainerIdentifier,
            ),
        ),
    )


def _measurement_report(hd, control_id: str, level_zero, region, area_um2: float):
    from pydicom.sr.codedict import codes

    roi = hd.sr.PlanarROIMeasurementsAndQualitativeEvaluations(
        tracking_identifier=hd.sr.TrackingIdentifier(
            uid=uid(control_id, "tracking"), identifier="Tissue region 1"
        ),
        referenced_region=region,
        finding_type=codes.SCT.Tissue,
        measurements=[
            hd.sr.Measurement(
                name=codes.SCT.Area, value=area_um2, unit=codes.UCUM.SquareMicrometer
            )
        ],
    )
    return hd.sr.MeasurementReport(
        observation_context=_observation_context(hd, control_id, level_zero),
        procedure_reported=codes.DCM.WholeSlideImaging,
        imaging_measurements=[roi],
    )


def _sr(hd, cls, control_id: str, series_number: int, report, level_zero):
    sr = cls(
        evidence=[level_zero],
        content=report,
        series_instance_uid=uid(control_id, "series"),
        series_number=series_number,
        sop_instance_uid=uid(control_id, "instance"),
        instance_number=1,
        manufacturer=MANUFACTURER,
        is_complete=True,
    )
    _copy_study(sr, level_zero)
    _determinize(sr, control_id)
    return sr


def _build_sr_tid1500(hd, level_zero, level_one):
    import numpy as np

    control_id = "V7-SR-TID1500"
    row_um, column_um = _pixel_spacing_um(level_zero)
    # The left half of the level-0 Total Pixel Matrix, (column, row): a closed POLYLINE, the
    # SCOORD form of a region (PS3.3 C.18.6.1.1).
    outline = np.array([[0.0, 0.0], [2.0, 0.0], [2.0, 4.0], [0.0, 4.0], [0.0, 0.0]])
    region = hd.sr.ImageRegion(
        graphic_type=hd.sr.GraphicTypeValues.POLYLINE,
        graphic_data=outline,
        source_image=hd.sr.SourceImageForRegion(
            referenced_sop_class_uid=level_zero.SOPClassUID,
            referenced_sop_instance_uid=level_zero.SOPInstanceUID,
        ),
        pixel_origin_interpretation=hd.sr.PixelOriginInterpretationValues.VOLUME,
    )
    report = _measurement_report(hd, control_id, level_zero, region, 2.0 * column_um * 4.0 * row_um)
    sr = _sr(hd, hd.sr.ComprehensiveSR, control_id, 109, report, level_zero)
    return control_id, {"sr-tid1500.dcm": sr}


def _build_sr_3d(hd, level_zero, level_one):
    import numpy as np

    control_id = "V7-SR-3D"
    # The V7-ANN-3D outline, closed, in slide coordinates (mm) on the CP12 Frame of Reference.
    outline = np.array(
        [
            [0.0001, 0.0002, 0.0],
            [0.0009, 0.0002, 0.0],
            [0.0009, 0.0018, 0.0],
            [0.0001, 0.0018, 0.0],
            [0.0001, 0.0002, 0.0],
        ]
    )
    region = hd.sr.ImageRegion3D(
        graphic_type=hd.sr.GraphicTypeValues3D.POLYGON,
        graphic_data=outline,
        frame_of_reference_uid=level_zero.FrameOfReferenceUID,
    )
    report = _measurement_report(hd, control_id, level_zero, region, 0.8 * 1.6)
    sr = _sr(hd, hd.sr.Comprehensive3DSR, control_id, 110, report, level_zero)
    return control_id, {"sr-3d.dcm": sr}


BUILDERS = (
    _build_seg_binary,
    _build_seg_fractional,
    _build_seg_labelmap,
    _build_pm,
    _build_ann_2d,
    _build_ann_3d,
    _build_kos_acquisition_complete,
    _build_kos_rejected_quality,
    _build_sr_tid1500,
    _build_sr_3d,
)


FILESET_ID = "V7-FILESET"
FILESET_DIR = "fileset"
FILESET_ID_VALUE = "CP12SLIDE"
# File IDs (PS3.10 8.2: up to 8 components of up to 8 of A-Z, 0-9 and _) and their sources:
# the CP12 pyramid, then the annotations and segmentation built here.
FILESET_MEMBERS = (
    ("SLIDE/WSI0", "source:level-0.dcm"),
    ("SLIDE/WSI1", "source:level-1.dcm"),
    ("SLIDE/ANN2D", "built:ann-2d.dcm"),
    ("SLIDE/ANN3D", "built:ann-3d.dcm"),
    ("SLIDE/SEG", "built:seg-binary.dcm"),
)
OFFSET_TAGS = (0x00041200, 0x00041202, 0x00041400, 0x00041420)


def _remap_offsets(dicomdir, mapping: dict[int, int]) -> None:
    for tag in OFFSET_TAGS[:2]:
        if dicomdir[tag].value:
            dicomdir[tag].value = mapping[dicomdir[tag].value]
    for record in dicomdir.DirectoryRecordSequence:
        for tag in OFFSET_TAGS[2:]:
            if tag in record and record[tag].value:
                record[tag].value = mapping[record[tag].value]


def _determinize_dicomdir(path: Path) -> None:
    """Give the dcmmkdir DICOMDIR a deterministic SOP Instance UID.

    dcmmkdir invents the Media Storage SOP Instance UID; replacing it changes the File Meta
    length, so every record offset (PS3.3 F.3.2.1) is moved by mapping each record's old
    file position to its new one, and the result is re-read to prove each offset lands on a
    record.
    """
    import io

    import pydicom

    dicomdir = pydicom.dcmread(path)
    old_tells = [record.seq_item_tell for record in dicomdir.DirectoryRecordSequence]
    dicomdir.file_meta.MediaStorageSOPInstanceUID = uid(FILESET_ID, "dicomdir")
    buffer = io.BytesIO()
    dicomdir.save_as(buffer, enforce_file_format=True)
    reread = pydicom.dcmread(io.BytesIO(buffer.getvalue()))
    new_tells = [record.seq_item_tell for record in reread.DirectoryRecordSequence]
    # pydicom's seq_item_tell is the file position of the Item tag, which is what each
    # offset names.
    mapping = dict(zip(old_tells, new_tells, strict=True))
    _remap_offsets(dicomdir, mapping)
    dicomdir.save_as(path, enforce_file_format=True)
    check = pydicom.dcmread(path)
    starts = {record.seq_item_tell for record in check.DirectoryRecordSequence}
    offsets = [check[tag].value for tag in OFFSET_TAGS[:2]] + [
        record[tag].value
        for record in check.DirectoryRecordSequence
        for tag in OFFSET_TAGS[2:]
        if tag in record
    ]
    stray = [offset for offset in offsets if offset and offset not in starts]
    if stray:
        raise RuntimeError(f"DICOMDIR offsets {stray} do not start a Directory Record")


def _build_fileset(staging: Path) -> dict[str, str]:
    """Write the File-set with dcmmkdir (General Purpose profile) in a fixed member order."""
    import subprocess

    root = staging / FILESET_DIR
    for file_id, source in FILESET_MEMBERS:
        kind, name = source.split(":")
        origin = SOURCE_DIR / name if kind == "source" else staging / name
        destination = root / file_id
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, destination)
    command = ["dcmmkdir", "-Pgp", "+F", FILESET_ID_VALUE, "-I"] + [
        file_id for file_id, _ in FILESET_MEMBERS
    ]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"dcmmkdir failed ({result.returncode}): {result.stderr.strip()}")
    _determinize_dicomdir(root / "DICOMDIR")
    relatives = ["DICOMDIR"] + [file_id for file_id, _ in FILESET_MEMBERS]
    return {f"{FILESET_DIR}/{relative}": _sha256(root / relative) for relative in relatives}


def build(output: Path) -> dict[str, dict[str, str]]:
    """Write every control into ``output`` (which must not exist); return path digests."""
    if output.exists():
        raise RuntimeError(f"output already exists: {output}")
    hd = _require_highdicom()
    level_zero, level_one = _load_sources()
    output.parent.mkdir(parents=True, exist_ok=True)
    digests: dict[str, dict[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent) as temporary:
        staging = Path(temporary) / "out"
        staging.mkdir()
        for builder in BUILDERS:
            control_id, objects = builder(hd, copy.deepcopy(level_zero), copy.deepcopy(level_one))
            digests[control_id] = {}
            for relative, dataset in objects.items():
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                dataset.save_as(destination, enforce_file_format=True)
                digests[control_id][relative] = _sha256(destination)
        digests[FILESET_ID] = _build_fileset(staging)
        shutil.move(staging, output)
    return digests


def verify(directory: Path = CONTROLS_DIR) -> list[str]:
    """Return a problem per registered file whose digest differs or that is missing."""
    problems = []
    for control in CONTROLS:
        for relative, expected in control["sha256"].items():
            path = directory / relative
            if not path.is_file():
                problems.append(f"{control['id']}: missing {relative}")
            elif _sha256(path) != expected:
                problems.append(f"{control['id']}: sha256 mismatch for {relative}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build")
    build_parser.add_argument("output", type=Path)
    sub.add_parser("verify")
    args = parser.parse_args(argv)
    if args.command == "build":
        for control_id, files in build(args.output).items():
            for relative, digest in files.items():
                print(f"{control_id}\t{relative}\t{digest}")
        return 0
    problems = verify()
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
