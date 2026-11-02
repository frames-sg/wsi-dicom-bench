"""Small statement families left after the pathology and File-set cohorts."""

from __future__ import annotations

from .iod_amendment_cases import _case as _spec, _cite, _edits, _op


def _case(case_id, control, mutation, parameters, expected, requirements, changed,
          citation, rationale):
    return _spec(
        case_id, control, mutation, parameters, expected, changed, citation, rationale,
        requirement_ids=list(requirements),
    )


def _edit(case_id, control, operations, expected, requirements, changed, citation, rationale):
    return _case(
        case_id, control, "iod_edits", _edits(*operations), expected, requirements,
        changed, citation, rationale,
    )


def _set(case_id, control, members, expected, requirements, changed, citation, rationale):
    return _case(
        case_id, control, "iod_set_edits", {"members": members}, expected, requirements,
        changed, citation, rationale,
    )


def _fileset(case_id, parameters, expected, requirements, changed, citation, rationale):
    return _case(
        case_id, "V7-FILESET", "file_set_edits", parameters, expected, requirements,
        changed, citation, rationale,
    )


CASES = (
    _set(
        "REQ-RES-001", "W7-SET-PYRAMID-3L-LOT",
        [{"path": "label.dcm", "operations": [
            _op("set", ["SpecimenLabelInImage"], "NO")
        ]}],
        ("wsi-image",), ("Ps3_C_8_12_4_1_SpecimenLabelInImage_fd0f41",),
        "Set Specimen Label in Image to NO in the LABEL image.",
        _cite("PS3.3", "C.8.12.4.1 Table C.8.12.4-1", "part03/sect_C.8.12.4.html"),
        "LABEL and OVERVIEW images include the physical specimen label, so the indicator is YES.",
    ),
    _edit(
        "REQ-RES-002", "V7-SEG-FRACTIONAL",
        [_op("delete", ["SegmentationFractionalType"])],
        ("iod-attribute-presence",), ("Ps3_C_8_20_2_3_2_f2ea4d",),
        "Remove Segmentation Fractional Type from the FRACTIONAL Segmentation.",
        _cite("PS3.3", "C.8.20.2.3.2", "part03/sect_C.8.20.2.html"),
        "A FRACTIONAL Segmentation specifies its fractional type.",
    ),
    _edit(
        "REQ-RES-003", "CP10-EVRLE-16F",
        [_op("insert", ["FloatPixelData"], "00" * 768, vr="OF")],
        ("iod-attribute-presence",), ("Ps5_8_2_ed0a1a",),
        "Add Float Pixel Data while retaining the top-level Pixel Data.",
        _cite("PS3.5", "8.2", "part05/sect_8.2.html"),
        "A top-level Data Set contains only one Pixel Data representation.",
    ),
    _edit(
        "REQ-RES-004", "V7-SR-TID1500",
        [_op("delete", ["ConceptNameCodeSequence"])],
        ("iod-attribute-presence",), ("Ps3_C_17_3_1_c9b830",),
        "Remove the root Content Item's Concept Name Code Sequence.",
        _cite("PS3.3", "C.17.3.1", "part03/sect_C.17.3.html"),
        "The root Content Item names the SR Document title.",
    ),
    _edit(
        "REQ-RES-005", "W7-TS-J2K-PART1-ICT",
        [_op("set", ["LossyImageCompressionMethod"],
             ["ISO_15444_1", "ISO_18181_1"])],
        ("lossy-history",),
        ("Ps3_C_7_6_1_1_5_1_f408e9", "Ps3_C_7_6_1_1_5_2_a81e8a"),
        "Give Lossy Image Compression Method two Values while the Ratio retains one Value.",
        _cite("PS3.3", "C.7.6.1.1.5.1 and C.7.6.1.1.5.2",
              "part03/sect_C.7.6.html"),
        "Successive compression methods and ratios form ordered pairs with matching multiplicity.",
    ),
    _edit(
        "REQ-RES-006", "W7-TS-J2K-PART1-ICT",
        [_op("set", ["LossyImageCompression"], "00")],
        ("lossy-history",), ("Ps3_C_7_6_1_1_5_dfc992",),
        "Set Lossy Image Compression to 00 in the lossy JPEG 2000 image.",
        _cite("PS3.3", "C.7.6.1.1.5", "part03/sect_C.7.6.html"),
        "A multi-frame object with lossy-compressed Frames declares Lossy Image Compression 01.",
    ),
    _fileset(
        "REQ-RES-007", {"operations": [
            _op("set", ["FileSetConsistencyFlag"], 0xFFFF)
        ]},
        ("iod-enumerated-values",), ("Ps3_F_3_3_FileSetConsistencyFlag_343323",),
        "Set File-set Consistency Flag to FFFFH.",
        _cite("PS3.3", "F.3.3", "part03/sect_F.3.html"),
        "A File-set Creator never writes the reserved FFFFH consistency flag.",
    ),
    _fileset(
        "REQ-RES-008", {"operations": [
            _op("set", ["DirectoryRecordSequence", 3, "RecordInUseFlag"], 1)
        ]},
        ("iod-enumerated-values",), ("Ps3_F_3_3_RecordInUseFlag_a50813",),
        "Set one Directory Record's Record In-use Flag to reserved Value 0001H.",
        _cite("PS3.3", "F.3.3", "part03/sect_F.3.html"),
        "A File-set Creator does not write a reserved Record In-use Flag Value.",
    ),
    _fileset(
        "REQ-RES-009", {"operations": [
            _op("set", ["DirectoryRecordSequence", 3, "RecordInUseFlag"], 0)
        ]},
        ("iod-enumerated-values",), ("Ps3_F_3_3_RecordInUseFlag_cb4e2b",),
        "Set one Directory Record's Record In-use Flag to 0000H.",
        _cite("PS3.3", "F.3.3", "part03/sect_F.3.html"),
        "The retired inactive-record Value 0000H is never present.",
    ),
    _fileset(
        "REQ-RES-010", {
            "private_record": True,
            "operations": [
                _op("delete", ["DirectoryRecordSequence", 11, "PrivateRecordUID"])
            ],
        },
        ("iod-attribute-presence",), ("Ps3_F_3_3_DirectoryRecordType_45a11c",),
        "Add a PRIVATE Directory Record and remove its Private Record UID.",
        _cite("PS3.3", "F.3.3", "part03/sect_F.3.html"),
        "Private Record UID defines the type of a PRIVATE Directory Record.",
    ),
    _case(
        "REQ-RES-011", "W7-TS-J2K-PART1-ICT", "encoding_rewrite",
        {"preserve_source_encoding": True,
         "operations": [{"op": "remove_pixel_fragments"}]},
        ("pixel-structure",), ("Ps5_A_4_2_6687ec", "Ps5_A_4_2_c5d6d5"),
        "Remove every JPEG 2000 Frame Fragment while retaining the Basic Offset Table.",
        _cite("PS3.5", "A.4.2", "part05/sect_A.4.html"),
        "Each multi-frame JPEG 2000 Frame is encoded in exactly one Fragment.",
    ),
    _case(
        "REQ-RES-012", "W7-TS-JXL-LOSSLESS-RGB", "encoding_rewrite",
        {"preserve_source_encoding": True,
         "operations": [{"op": "remove_pixel_fragments"}]},
        ("pixel-structure",), ("Ps5_A_4_12_a741e8",),
        "Remove every JPEG XL Frame Fragment while retaining the Basic Offset Table.",
        _cite("PS3.5", "A.4.12", "part05/sect_A.4.html"),
        "Each JPEG XL Frame is encoded separately in one Fragment.",
    ),
    _case(
        "REQ-RES-013", "W7-TS-HTJ2K-RPCL-128", "encoding_rewrite",
        {"preserve_source_encoding": True,
         "operations": [{"op": "remove_pixel_fragments"}]},
        ("pixel-structure",), ("Ps5_A_4_4_72c08f",),
        "Remove every HTJ2K Frame Fragment while retaining the Basic Offset Table.",
        _cite("PS3.5", "A.4.4", "part05/sect_A.4.html"),
        "Each HTJ2K Frame is encoded separately in one Fragment.",
    ),
    _case(
        "REQ-RES-014", "W7-TS-DEFLATED-IMAGE-FRAME", "encoding_rewrite",
        {"preserve_source_encoding": True,
         "operations": [{"op": "remove_pixel_fragments"}]},
        ("pixel-structure",), ("Ps5_A_4_13_14f644", "Ps5_A_4_13_7626f4"),
        "Remove every Deflated Image Frame Fragment while retaining the Basic Offset Table.",
        _cite("PS3.5", "A.4.13", "part05/sect_A.4.html"),
        "Each multi-frame Deflated Image Frame is encoded separately in one Fragment.",
    ),
    _case(
        "REQ-RES-015", "W7-TS-ENCAPSULATED-UNCOMPRESSED", "encoding_rewrite",
        {"preserve_source_encoding": True,
         "operations": [{"op": "remove_pixel_fragments"}]},
        ("pixel-structure",), ("Ps5_A_4_11_dd388a", "Ps5_A_4_11_f1cc7f"),
        "Remove every Encapsulated Uncompressed Frame Fragment while retaining the Basic Offset Table.",
        _cite("PS3.5", "A.4.11", "part05/sect_A.4.html"),
        "Each multi-frame uncompressed Frame is encoded separately in one Fragment.",
    ),
)


UNCOVERED = {
    "Ps5_7_5_379e6d": (
        "An SQ Data Element encodes one Sequence Value containing Items; a second Sequence with "
        "the same Tag is instead the separate duplicate-Data-Element defect."
    ),
}
