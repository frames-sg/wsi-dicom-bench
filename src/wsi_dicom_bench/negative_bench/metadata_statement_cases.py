"""Single-defect metadata cases for the v7 ``requirement-statement-evaluation-v2`` cohort.

The cases name the checked statements of the ``file-meta``, ``dimension-order`` and
``icc-profile`` rules, and the ``series-set`` statements on localizer references and
shared Dimension Organization UIDs, that no earlier case names. File Meta defects that a
DICOM writer would normalize away are written into the File Meta group with the
``encoding_rewrite`` File Meta operations, which rewrite its Group Length; the rest use
``iod_edits`` and ``iod_edit_pair``. Every Attribute a case adds around its defect is
otherwise conformant. Expectations are set as for the rest of the cohort: by running the
candidate and adjudicating each result against DICOM 2026d.

``NAMED_BY_EXISTING`` lists the statements that carried-forward cases already break, by
the observed failure message of their expected rule. ``UNCOVERED`` gives, for the
statements of these rules that no single-defect case can hold, the concrete blocker.
``CONTROLS`` is empty: no structural control the statements need (a Concatenation, a LABEL
or OVERVIEW image, a second optical path) can be derived from the controls and pass the
general profile; ``UNCOVERED`` records why for each.
"""

from __future__ import annotations

from .iod_amendment_cases import SHARED, _case as _spec, _cite, _code, _edits, _op


PS310_META = _cite("PS3.10", "7.1", "part10/chapter_7.html#sect_7.1")
PS310_ADDRESS = _cite("PS3.10", "7.1.1.1", "part10/chapter_7.html#sect_7.1.1.1")
PS35_JPIP = _cite("PS3.5", "10.8", "part05/sect_10.8.html")
PS33_ICC = _cite("PS3.3", "C.11.15.1.1 and C.8.12.5.1.4", "part03/sect_C.11.15.html#sect_C.11.15.1.1")
PS33_INDICES = _cite("PS3.3", "C.7.6.17.1", "part03/sect_C.7.6.17.html#sect_C.7.6.17.1")
PS33_INDEX_VALUES = _cite("PS3.3", "C.7.6.16.2.2 Table C.7.6.16-3", "part03/sect_C.7.6.16.2.2.html")
PS33_DIMENSION_ORGANIZATION = _cite("PS3.3", "C.7.6.17.2", "part03/sect_C.7.6.17.2.html")
PS33_LOCALIZER = _cite("PS3.3", "C.7.6.16.2.5.1", "part03/sect_C.7.6.16.2.5.html#sect_C.7.6.16.2.5.1")

WSI_CLASS = "1.2.840.10008.5.1.4.1.1.77.1.6"
JPIP_REFERENCED = "1.2.840.10008.1.2.4.94"
LOCALIZER_SERIES = "1.2.826.0.1.3680043.10.999.947"
OTHER_FRAME_OF_REFERENCE = "1.2.826.0.1.3680043.10.999.948"
MONO = "CP11-MONO-EVRLE-4F"
# The Dimension Organization UID of MONO, which its two Dimension Index Items share.
MONO_DIMENSIONS = "2.25.133903666094689810433027391371163936962"
# MONO's Dimension Index Values (row, column) of Frames 1 to 4 of its 2 x 2 tiling.
MONO_INDICES = ([1, 1], [1, 2], [2, 1], [2, 2])

# Data Element Tags that Attribute Tag Values name.
ROW_POSITION = 0x0048_021F
COLUMN_POSITION = 0x0048_021E
TOTAL_PIXEL_MATRIX_COLUMNS = 0x0048_0006
PLANE_POSITION = 0x0048_021A
X_OFFSET = 0x0040_072A
FRAME_CONTENT = 0x0020_9111
DIMENSION_INDEX_VALUES = 0x0020_9157
FRAME_LABEL = 0x0020_9453
# A private block ACME of group 0029: a LO Value and a Sequence that holds one.
PRIVATE_CREATOR = "(0029,0010)"
PRIVATE_VALUE = "(0029,1002)"
PRIVATE_GROUP = "(0029,1003)"
PRIVATE_VALUE_TAG = 0x0029_1002
PRIVATE_GROUP_TAG = 0x0029_1003

PER_FRAME = "PerFrameFunctionalGroupsSequence"
ONLY = "Only the {rule} rule reports this defect."


def _case(case_id, control, mutation, parameters, expected, requirements, changed, citation,
          rationale) -> dict:
    return {**_spec(case_id, control, mutation, parameters, list(expected), changed, citation, rationale),
            "requirement_ids": list(requirements)}


def _edit(case_id, control, operations, requirements, changed, citation, rationale,
          expected=("dimension-order",)) -> dict:
    """An ``iod_edits`` case."""
    return _case(case_id, control, "iod_edits", _edits(*operations), expected, requirements,
                 changed, citation, rationale)


def _rewrite(case_id, control, operations, requirements, changed, citation, rationale,
             expected=("file-meta",), **before) -> dict:
    """An ``encoding_rewrite`` case; ``edits`` apply before the encoded-byte ``operations``."""
    return _case(case_id, control, "encoding_rewrite", {**before, "operations": operations},
                 expected, requirements, changed, citation, rationale)


def _pair(case_id, control, first, second, requirements, changed, citation, rationale) -> dict:
    parameters = {key: value for key, value in (("first", first), ("second", second)) if value}
    return _case(case_id, control, "iod_edit_pair", parameters, ("series-set",), requirements,
                 changed, citation, rationale)


def _meta_insert(tag: str, vr: str, **value) -> dict:
    """Insert a File Meta element holding ``text`` (padded to even length) or ``value_hex``."""
    return {"op": "file_meta_insert", "tag": tag, "vr": vr, **value}


def _meta_set(tag: str, **change) -> dict:
    """Set the ``vr``, ``text`` or exact ``value_hex`` of a File Meta element as written."""
    return {"op": "file_meta_set", "tag": tag, **change}


def _content(frame: int) -> list:
    """The Frame Content Item of zero-based ``frame``."""
    return [PER_FRAME, frame, "FrameContentSequence", 0]


def _index(pointer: int, group: int | None = None, **fields) -> dict:
    """A Dimension Index Item of MONO's Dimension Organization."""
    item = {"DimensionOrganizationUID": MONO_DIMENSIONS, "DimensionIndexPointer": pointer, **fields}
    if group is not None:
        item["FunctionalGroupPointer"] = group
    return item


def _third_index(item: dict, values: list[int]) -> list[dict]:
    """Append ``item`` to MONO's row and column Dimension Index Items, and give each Frame its
    third Dimension Index Value from ``values``."""
    return [
        _op("replace", ["DimensionIndexSequence"],
            [_index(ROW_POSITION, PLANE_POSITION), _index(COLUMN_POSITION, PLANE_POSITION), item]),
        *(_op("set", [*_content(frame), "DimensionIndexValues"], [*MONO_INDICES[frame], value])
          for frame, value in enumerate(values)),
    ]


def _private_value(path: list) -> list[dict]:
    """Insert the ACME Private Creator and its LO Value A into the Item at ``path``."""
    return [_op("insert", [*path, PRIVATE_CREATOR], "ACME", vr="LO"),
            _op("insert", [*path, PRIVATE_VALUE], "A", vr="LO")]


def _private_group(frame: int) -> list[dict]:
    """Insert the private Functional Group Sequence (0029,1003), holding the ACME Value, into
    the Per-Frame Functional Groups Item of zero-based ``frame``."""
    item = [PER_FRAME, frame]
    return [_op("insert", [*item, PRIVATE_CREATOR], "ACME", vr="LO"),
            _op("insert", [*item, PRIVATE_GROUP], [{}], vr="SQ"),
            *_private_value([*item, PRIVATE_GROUP, 0])]


DIMENSION_CASES = (
    _edit("REQ-MET-001", MONO,
        [_op("set", [*_content(1), "DimensionIndexValues"], [1, 2, 1])],
        ("Ps3_C_7_6_16_3_DimensionIndexValues_e56fe8",),
        "Give Frame 2 the three Dimension Index Values 1\\2\\1 for the two Dimension Index Sequence Items.",
        PS33_INDEX_VALUES, "Dimension Index Values has one Value per Dimension Index Sequence Item. "
        + ONLY.format(rule="dimension-order")),
    _edit("REQ-MET-002", MONO,
        [_op("set", ["DimensionIndexSequence", 1, "DimensionIndexPointer"], TOTAL_PIXEL_MATRIX_COLUMNS)],
        ("Ps3_C_7_6_17_1_da4366",),
        "Set the column Dimension Index Pointer to Total Pixel Matrix Columns (0048,0006), which the Plane Position (Slide) Functional Group does not hold.",
        PS33_INDICES, "The Dimension Index Pointer contains the Tag of the Attribute the index values index. "
        + ONLY.format(rule="dimension-order")),
    _edit("REQ-MET-003", MONO, [
        _op("set", ["DimensionIndexSequence", 1, "DimensionIndexPointer"], DIMENSION_INDEX_VALUES),
        _op("set", ["DimensionIndexSequence", 1, "FunctionalGroupPointer"], FRAME_CONTENT),
    ],
        ("Ps3_C_7_6_17_1_849d42",),
        "Point the column Dimension Index Item at Dimension Index Values (0020,9157) in the Frame Content Sequence.",
        PS33_INDICES, "The Dimension Index Pointer does not name Dimension Index Values. "
        + ONLY.format(rule="dimension-order")),
    _edit("REQ-MET-004", MONO, _third_index(_index(PLANE_POSITION, PLANE_POSITION), [1, 2, 3, 4]),
        ("Ps3_C_7_6_17_1_83308f",),
        "Add a third Dimension Index Item indexing the Plane Position (Slide) Sequence (0048,021A) with a Functional Group Pointer, each Frame its own index.",
        PS33_INDICES, "A Dimension Index Pointer that names a Functional Group Sequence has no Functional "
        "Group Pointer; the index values follow the distinct Plane Positions. " + ONLY.format(rule="dimension-order")),
    _edit("REQ-MET-005", MONO, [
        *_third_index(_index(FRAME_LABEL, FRAME_CONTENT), [1, 1, 2, 3]),
        *(_op("insert", [*_content(frame), "FrameLabel"], "A") for frame in (0, 1)),
    ],
        ("Ps3_C_7_6_17_1_97159c",),
        "Index Frame Label (0020,9453), present in Frames 1 and 2, with a third Dimension Index Item, and give Frames 3 and 4, which lack it, the indices 2 and 3.",
        PS33_INDICES, "Frames that lack the indexed Attribute share one index of their own. "
        + ONLY.format(rule="dimension-order")),
    _edit("REQ-MET-006", MONO, [
        *_third_index(_index(PRIVATE_VALUE_TAG, FRAME_CONTENT, DimensionIndexPrivateCreator="OTHER"),
                      [1, 1, 1, 1]),
        *(op for frame in range(4) for op in _private_value(_content(frame))),
    ],
        ("Ps3_C_7_6_17_1_0f809b",),
        "Index the private ACME Value (0029,1002) of each Frame Content Item with a third Dimension Index Item whose Dimension Index Private Creator (0020,9213) is OTHER.",
        PS33_INDICES, "The Dimension Index Private Creator is the Private Creator of the indexed element's block, ACME. "
        + ONLY.format(rule="dimension-order")),
    _edit("REQ-MET-007", MONO, [
        *_third_index(_index(PRIVATE_VALUE_TAG, PRIVATE_GROUP_TAG, DimensionIndexPrivateCreator="ACME",
                             FunctionalGroupPrivateCreator="OTHER"), [1, 1, 1, 1]),
        *(op for frame in range(4) for op in _private_group(frame)),
    ],
        ("Ps3_C_7_6_17_1_39ce9a",),
        "Index the ACME Value of a private Functional Group Sequence (0029,1003) in each Per-Frame Item with a third Dimension Index Item whose Functional Group Private Creator (0020,9238) is OTHER.",
        PS33_INDICES, "The Functional Group Private Creator is the Private Creator of the private Functional Group's block, ACME. "
        + ONLY.format(rule="dimension-order")),
)


ICC_CASES = (
    _rewrite("REQ-MET-008", "CP02-JPEG-16F",
        [{"op": "patch_value", "path": ["OpticalPathSequence", 0, "ICCProfile"], "offset": 20,
          "hex": "4c757620"}],
        ("Ps3_C_11_15_1_1_efa57f", "Ps3_C_11_15_1_1_4ea599", "Ps3_C_8_12_5_1_4_b19588"),
        "Patch Profile Connection Space bytes 20 to 23 of the Optical Path ICC Profile from 'XYZ ' to 'Luv '.",
        PS33_ICC, "The PCS of the Input Device profile is CIELab or CIEXYZ. " + ONLY.format(rule="icc-profile"),
        expected=("icc-profile",)),
)


PAIR_CASES = (
    _pair("REQ-MET-009", "CP02-JPEG-16F", [
        _op("insert", [*SHARED, "ReferencedImageSequence"], [{
            "ReferencedSOPClassUID": WSI_CLASS, "ReferencedSOPInstanceUID": "{second.SOPInstanceUID}",
            "PurposeOfReferenceCodeSequence": [_code("DCM", "121311", "Localizer")],
        }]),
        _op("insert", ["ReferencedSeriesSequence"], [{
            "SeriesInstanceUID": LOCALIZER_SERIES,
            "ReferencedInstanceSequence": [
                {"ReferencedSOPClassUID": WSI_CLASS, "ReferencedSOPInstanceUID": "{second.SOPInstanceUID}"}],
        }]),
    ], [
        _op("set", ["SeriesInstanceUID"], LOCALIZER_SERIES),
        _op("set", ["FrameOfReferenceUID"], OTHER_FRAME_OF_REFERENCE),
    ],
        ("Ps3_C_7_6_16_2_5_1_17ac5a",),
        "Reference the second Instance, in its own Series with another Frame of Reference UID, as the first Instance's Localizer (121311, DCM) in the shared Referenced Image Sequence, listed in the Referenced Series Sequence.",
        PS33_LOCALIZER, "An Instance referenced to plan the acquisition has this image's Frame of Reference UID."),
    _pair("REQ-MET-010", "CP02-JPEG-16F", None, [
        _op("set", ["DimensionIndexSequence", 1, "DimensionIndexPointer"], X_OFFSET),
    ],
        ("Ps3_C_7_6_17_2_4ebae3",),
        "Index the second Instance's columns by X Offset in Slide Coordinate System (0040,072A) instead of Column Position, under the Dimension Organization UID the first Instance uses for Column Position.",
        PS33_DIMENSION_ORGANIZATION, "Instances sharing a Dimension Organization UID give equivalent indices the same meaning; "
        "the second Instance's own indices follow its X Offsets."),
)


CASES = (
    *DIMENSION_CASES,
    *ICC_CASES,
    *PAIR_CASES,
)

# Carried-forward cases whose expected rule's observed message shows the statements' violation.
NAMED_BY_EXISTING: dict[str, tuple[str, ...]] = {}

UNCOVERED: dict[str, str] = {}

# Structural controls derived from controls-v4 and controls-v6 that pass every intrinsic rule
# and the external validators; none could be (see UNCOVERED).
CONTROLS: dict[str, dict] = {}
