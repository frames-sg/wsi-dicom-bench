"""Negative statement cases for the non-WSI pathology object families.

The controls are the valid v7 SEG, Parametric Map, Microscopy Bulk Simple
Annotations, KOS and SR objects and their small referenced-object sets.  Cases
use ordered Data Set edits, set edits, pair edits or one encoded-value rewrite
and name only statements that the resulting defect actually violates.
"""

from __future__ import annotations

import struct

from .iod_amendment_cases import _case as _spec, _cite, _edits, _op


SEG = ("segmentation",)
PM = ("parametric-map",)
ANN = ("bulk-annotations",)
SR = ("structured-report",)
KOS = ("key-object-selection",)
SYNC = ("synchronization",)

PS33_SEG = _cite("PS3.3", "A.51 and C.8.20", "part03/sect_A.51.html")
PS33_PM = _cite("PS3.3", "A.75 and C.8.32", "part03/sect_A.75.html")
PS33_ANN = _cite("PS3.3", "C.37.1.2", "part03/sect_C.37.html#sect_C.37.1.2")
PS33_SR = _cite("PS3.3", "A.35, C.17 and C.18", "part03/sect_A.35.html")
PS33_SYNC = _cite("PS3.3", "C.7.4.2", "part03/sect_C.7.4.html#sect_C.7.4.2")
PS35_FLOAT = _cite("PS3.5", "8.2", "part05/chapter_8.html#sect_8.2")

SHARED = ["SharedFunctionalGroupsSequence", 0]
VOI = [*SHARED, "FrameVOILUTSequence", 0]
FRAME_TYPE = [*SHARED, "ParametricMapFrameTypeSequence", 0, "FrameType"]
NUM = ["ContentSequence", 10, "ContentSequence", 0, "ContentSequence", 3]
SCOORD = ["ContentSequence", 10, "ContentSequence", 0, "ContentSequence", 4]
SCOORD3D = ["ContentSequence", 10, "ContentSequence", 0, "ContentSequence", 4]
MEASURED = [*NUM, "MeasuredValueSequence", 0]
ANN0 = ["AnnotationGroupSequence", 0]
ANN1 = ["AnnotationGroupSequence", 1]
WSI_CLASS = "1.2.840.10008.5.1.4.1.1.77.1.6"
KOS_CLASS = "1.2.840.10008.5.1.4.1.1.88.59"
COMPREHENSIVE_SR_CLASS = "1.2.840.10008.5.1.4.1.1.88.33"
CONCATENATION_MEMBER = "2.25.272749449541853938306599290835500864878"
SOURCE_STUDY = "2.25.91377140152254719573571000013980927017"
SOURCE_SERIES = "2.25.98616610931348373385257471081082330290"
SOURCE_IMAGE_1 = "2.25.52012031790397401411496663953142193882"
SOURCE_IMAGE_2 = "2.25.46906494363476203538132861256865639328"
OTHER_STUDY = "1.2.826.0.1.3680043.10.999.980"
OTHER_SERIES = "1.2.826.0.1.3680043.10.999.981"


def _case(case_id, control, operations, expected, requirements, changed, citation, rationale):
    return _spec(
        case_id,
        control,
        "iod_edits",
        _edits(*operations),
        expected,
        changed,
        citation,
        rationale,
        requirement_ids=list(requirements),
    )


def _encoding_case(
    case_id, control, operations, expected, requirements, changed, citation, rationale
):
    return _spec(
        case_id,
        control,
        "encoding_rewrite",
        {"operations": operations},
        expected,
        changed,
        citation,
        rationale,
        requirement_ids=list(requirements),
    )


def _set_case(case_id, control, members, expected, requirements, changed, citation, rationale):
    return _spec(
        case_id,
        control,
        "iod_set_edits",
        {"members": members},
        expected,
        changed,
        citation,
        rationale,
        requirement_ids=list(requirements),
    )


def _pair(case_id, control, first, second, requirements, changed, rationale):
    parameters = {key: value for key, value in (("first", first), ("second", second)) if value}
    return _spec(
        case_id,
        control,
        "iod_edit_pair",
        parameters,
        SYNC,
        changed,
        PS33_SYNC,
        rationale,
        requirement_ids=list(requirements),
    )


def _document_pair(case_id, first, second, requirements, changed, rationale):
    return _spec(
        case_id,
        "V7-KOS-ACQ-COMPLETE",
        "iod_edit_pair",
        {"first": first, "second": second},
        KOS,
        changed,
        PS33_SR,
        rationale,
        requirement_ids=list(requirements),
    )


def _evidence(study: str, series: str, *instances: str, sop_class: str = WSI_CLASS) -> dict:
    return {
        "StudyInstanceUID": study,
        "ReferencedSeriesSequence": [{
            "SeriesInstanceUID": series,
            "ReferencedSOPSequence": [
                {"ReferencedSOPClassUID": sop_class, "ReferencedSOPInstanceUID": instance}
                for instance in instances
            ],
        }],
    }


def _packed(code: str, values) -> str:
    values = tuple(values)
    return struct.pack(f"<{len(values)}{code}", *values).hex()


def _od(*values: float) -> str:
    return _packed("d", values)


def _of(*values: float) -> str:
    return _packed("f", values)


def _ol(*values: int) -> str:
    return _packed("I", values)


def _plane(orientation: list[float]) -> dict:
    return _op(
        "insert",
        [*SHARED, "PlaneOrientationSequence"],
        [{"ImageOrientationPatient": {"vr": "DS", "value": [str(value) for value in orientation]}}],
    )


def _lut(descriptor_vr: str, entries: int, bits: int, data_bytes: int) -> dict:
    return _op(
        "insert",
        [*VOI, "VOILUTSequence"],
        [{
            "LUTDescriptor": {"vr": descriptor_vr, "value": [entries, 0, bits]},
            "LUTData": {"vr": "OB", "value": "00" * data_bytes},
        }],
    )


SEGMENTATION_CASES = (
    _set_case("REQ-PATH-095", "V7-SEG-FOR-SET", [
        {
            "path": "segmentation.dcm",
            "retag": True,
            "operations": [_op("set", ["FrameOfReferenceUID"],
                               "1.2.826.0.1.3680043.10.999.995")],
        },
        {"path": "source-image.dcm"},
    ], SEG, ("Ps3_A_51_1_68d35f",),
        "Give the Segmentation a different Frame of Reference UID while retaining its referenced WSI image.",
        PS33_SEG,
        "A Segmentation and every referenced image with a Frame of Reference share its UID."),
    _set_case("REQ-PATH-096", "V7-SEG-NO-FOR-SET", [
        {"path": "segmentation.dcm"},
        {
            "path": "source-image.dcm",
            "operations": [
                _op("set", ["Rows"], 3),
                _op("set", ["PixelData"], "00" * 72, vr="OB"),
            ],
        },
    ], SEG, ("Ps3_A_51_1_34d27f",),
        "Change the referenced no-Frame-of-Reference image from 2x2 to 3x2 pixels per Frame and resize its Pixel Data.",
        PS33_SEG,
        "Without a Frame of Reference, the Segmentation has the referenced image's sampling and extent."),
    _case("REQ-PATH-001", "V7-SEG-BINARY",
          [_op("set", ["ImageType"], ["DERIVED", "PRIMARY", "VOLUME"])], SEG,
          ("Ps3_C_8_20_2_ImageType_e16bb7",),
          "Append VOLUME as Image Type Value 3.", PS33_SEG,
          "A Segmentation Image Type has DERIVED and PRIMARY only; no other Value is present."),
    _case("REQ-PATH-002", "V7-SEG-LABELMAP",
          [_op("set", ["SegmentSequence", 2, "SegmentNumber"], 1)], SEG,
          ("Ps3_C_8_20_2_4_75482d", "Ps3_C_8_20_4_SegmentNumber_9ad373"),
          "Change Segment Sequence Item 3's Segment Number from 2 to 1.", PS33_SEG,
          "Two Segment Items then identify Segment 1, violating both statements that require uniqueness."),
    _case("REQ-PATH-003", "V7-SEG-BINARY",
          [_op("set", ["SegmentSequence", 0, "SegmentNumber"], 2)], SEG,
          ("Ps3_C_8_20_2_4_517b9d",),
          "Change the only Segment Number from 1 to 2.", PS33_SEG,
          "BINARY Segment Numbers start at 1 and increase by one."),
    _case("REQ-PATH-004", "V7-SEG-LABELMAP",
          [_op("set", ["SegmentsOverlap"], "YES")], SEG,
          ("Ps3_C_8_20_2_SegmentsOverlap_c35c89",),
          "Set Segments Overlap to YES on a LABELMAP.", PS33_SEG,
          "Segments Overlap, when present for LABELMAP, is NO."),
    _case("REQ-PATH-005", "V7-SEG-BINARY",
          [_op("set", [*SHARED, "SegmentIdentificationSequence", 0,
                        "ReferencedSegmentNumber"], [1, 1])], SEG,
          ("Ps3_C_8_20_3_ReferencedSegmentNumber_36aaef",),
          "Give Referenced Segment Number two Values.", PS33_SEG,
          "Referenced Segment Number is single-valued."),
    _case("REQ-PATH-006", "V7-SEG-FRACTIONAL",
          [_op("set", ["MaximumFractionalValue"], 1)], SEG,
          ("Ps3_C_8_20_2_MaximumFractionalValue_8e2125",),
          "Lower Maximum Fractional Value from 255 to 1 while retaining the pixels.", PS33_SEG,
          "The retained Pixel Data contains many Values greater than 1."),
    _case("REQ-PATH-007", "V7-SEG-LABELMAP",
          [_op("set", ["PixelData"], "03010101010102020102020202020200", vr="OB")], SEG,
          ("Ps3_C_8_20_2_3_3_3dd2ed",),
          "Change the first label pixel from 1 to undescribed label 3.", PS33_SEG,
          "Every encoded LABELMAP value is described by a Segment Sequence Item."),
    _case("REQ-PATH-008", "V7-SEG-BINARY",
          [_op("set", ["PixelData"], "01000100", vr="OB")],
          ("segmentation", "pixel-structure"),
          ("Ps3_C_8_20_2_1_672661", "Ps5_8_1_1_018c03", "Ps5_8_1_1_b26202"),
          "Store four bytes for sixteen one-bit pixels instead of two.", PS33_SEG,
          "Single-bit pixels are packed eight to a byte across Frames."),
    _case("REQ-PATH-009", "V7-SEG-BINARY",
          [_op("delete", ["PerFrameFunctionalGroupsSequence", 0,
                           "PlanePositionSlideSequence"])], SEG,
          ("Ps3_A_51_5_1_1767c6",),
          "Remove Frame 1's Plane Position (Slide) Functional Group.", PS33_SEG,
          "With a Frame of Reference, every segment Frame is located by Pixel Measures and a plane position."),
    _case("REQ-PATH-010", "V7-SEG-BINARY",
          [_op("delete", ["FrameOfReferenceUID"]),
           _op("delete", ["PerFrameFunctionalGroupsSequence", 0, "DerivationImageSequence"])], SEG,
          ("Ps3_A_51_5_1_6b8f76",),
          "Remove the Frame of Reference UID and Frame 1's Derivation Image Functional Group.",
          PS33_SEG,
          "Without a Frame of Reference, each segmentation pixel corresponds to a referenced image pixel through Derivation Image."),
    _case("REQ-PATH-082", "V7-SEG-LABELMAP-PALETTE",
          [_op("set", ["RedPaletteColorLookupTableDescriptor"], [3, 0, 12])], SEG,
          ("Ps3_C_7_6_3_1_5_1d78b7",),
          "Change the Red Palette Color Lookup Table Descriptor depth from 8 to 12 bits.",
          PS33_SEG,
          "A Segmentation Palette Color LUT Descriptor specifies 8 or 16 bits per entry."),
    _case("REQ-PATH-083", "V7-SEG-LABELMAP-PALETTE",
          [_op("insert", ["SegmentedRedPaletteColorLookupTableData"], "000100", vr="OW")], SEG,
          ("Ps3_C_7_9_0dab54",),
          "Add Segmented Red Palette Color LUT Data while retaining ordinary Red Palette Data.",
          PS33_SEG,
          "The Palette Color Lookup Table Module conditions take precedence: a Segmentation uses ordinary LUT Data alone."),
)


PARAMETRIC_MAP_CASES = (
    _case("REQ-PATH-011", "V7-PM-FLOAT", [_op("set", [*VOI, "WindowWidth"], "0.5")], PM,
          ("Ps3_C_11_2_1_2_1_2b93d6",), "Set LINEAR Window Width to 0.5.", PS33_PM,
          "The LINEAR Window Width is at least 1."),
    _case("REQ-PATH-012", "V7-PM-FLOAT",
          [_op("set", [*VOI, "WindowWidth"], "0"),
           _op("insert", [*VOI, "VOILUTFunction"], "SIGMOID")], PM,
          ("Ps3_C_11_2_1_3_1_18115e",), "Set SIGMOID Window Width to 0.", PS33_PM,
          "The SIGMOID Window Width is greater than 0."),
    _case("REQ-PATH-013", "V7-PM-FLOAT",
          [_op("set", [*VOI, "WindowWidth"], "0"),
           _op("insert", [*VOI, "VOILUTFunction"], "LINEAR_EXACT")], PM,
          ("Ps3_C_11_2_1_3_2_05afe8",), "Set LINEAR_EXACT Window Width to 0.", PS33_PM,
          "The LINEAR_EXACT Window Width is greater than 0."),
    _case("REQ-PATH-014", "V7-PM-FLOAT",
          [_op("set", [*VOI, "WindowCenter"], ["0.5", "2"])], PM,
          ("Ps3_C_11_2_1_2_2_4dae85",),
          "Give Window Center two Values while Window Width retains one.", PS33_PM,
          "Multiple Window Centers and Widths have matching multiplicity and form pairs."),
    _case("REQ-PATH-015", "V7-PM-FLOAT",
          [_op("set", ["PhotometricInterpretation"], "RGB")], PM,
          ("Ps3_C_11_2_1_2_2_1336e7",),
          "Set Photometric Interpretation to RGB while retaining Window Center and Width.", PS33_PM,
          "Window Center and Width are used only for MONOCHROME1 and MONOCHROME2."),
    _case("REQ-PATH-016", "V7-PM-FLOAT", [_lut("US", 4, 16, 8)], PM,
          ("Ps3_C_11_2_1_1_ed95f2",),
          "Insert a four-entry VOI LUT with a US Descriptor for floating-point input.", PS33_PM,
          "Floating-point input can be signed, so the Descriptor's second Value is represented by SS."),
    _case("REQ-PATH-017", "V7-PM-FLOAT", [_lut("SS", 4, 12, 8)], PM,
          ("Ps3_C_11_2_1_1_9b32b3",),
          "Insert a VOI LUT whose Descriptor specifies 12 bits per entry.", PS33_PM,
          "A VOI LUT in an Image IOD specifies 8 or 16 bits."),
    _case("REQ-PATH-018", "V7-PM-FLOAT", [_lut("SS", 4, 8, 8)], PM,
          ("Ps3_C_11_2_1_1_88b85b",),
          "Insert a four-entry 8-bit VOI LUT stored in eight bytes instead of four.", PS33_PM,
          "Eight-bit LUT entries are stored in an eight-bit-equivalent representation."),
    _case("REQ-PATH-019", "V7-PM-FLOAT",
          [_op("set", ["ImageType"], ["DERIVED", "PRIMARY", "", "QUANTITY"])], PM,
          ("Ps3_C_8_16_1_3_66c2ea", "Ps3_C_8_32_2_ImageType_06ce58"),
          "Make Image Type Value 3 zero length.", PS33_PM,
          "Value 3 is a nonempty Image Flavor."),
    _case("REQ-PATH-020", "V7-PM-FLOAT",
          [_op("set", ["ImageType"], ["DERIVED", "PRIMARY", "MIXED", "QUANTITY"])], PM,
          ("Ps3_C_8_16_1_3_6f1c70",), "Set Image Type Value 3 to MIXED.", PS33_PM,
          "Image Type Value 3 summarizes the primary purpose and may not be MIXED."),
    _case("REQ-PATH-021", "V7-PM-FLOAT",
          [_op("set", ["ImageType"], ["ORIGINAL", "PRIMARY", "VOLUME", "QUANTITY"])], PM,
          ("Ps3_C_8_16_1_4_0067a1",),
          "Set Image Type Value 1 to ORIGINAL while Value 4 remains QUANTITY.", PS33_PM,
          "Value 4 is NONE when Value 1 is ORIGINAL."),
    _case("REQ-PATH-022", "V7-PM-FLOAT",
          [_op("set", ["ImageType"], ["DERIVED", "PRIMARY", "VOLUME", ""])], PM,
          ("Ps3_C_8_16_1_4_e1a716", "Ps3_C_8_32_2_ImageType_c7ce98"),
          "Make Image Type Value 4 zero length.", PS33_PM,
          "Value 4 is a nonempty Derived Pixel Contrast."),
    _case("REQ-PATH-024", "V7-PM-FLOAT",
          [_op("set", FRAME_TYPE, ["DERIVED", "PRIMARY", "MIXED", "NONE"])], PM,
          ("Ps3_C_8_32_3_FrameType_4a0dab",), "Set Frame Type Value 3 to MIXED.", PS33_PM,
          "MIXED is not allowed in Parametric Map Frame Type."),
    _case("REQ-PATH-025", "V7-PM-FLOAT", [_op("set", ["BitsAllocated"], 64)], PM,
          ("Ps5_8_2_18602a",), "Set Bits Allocated to 64 with Float Pixel Data.", PS35_FLOAT,
          "Float Pixel Data uses OF with Bits Allocated 32."),
    _case("REQ-PATH-027", "V7-PM-FLOAT",
          [_op("delete", ["FloatPixelData"]), _op("set", ["BitsAllocated"], 64),
           _op("insert", ["DoubleFloatPixelData"], "00" * 128, vr="OD"),
           _op("insert", ["BitsStored"], 64)], PM,
          ("Ps5_8_2_4bcda5",),
          "Replace Float Pixel Data with native Double Float Pixel Data and add forbidden Bits Stored.",
          PS35_FLOAT, "Bits Stored is absent with Double Float Pixel Data."),
    _case("REQ-PATH-028", "V7-PM-FLOAT", [_plane([1, 0, 0, 1, 0, 0])], PM,
          ("Ps3_C_7_6_2_1_1_34cf77",),
          "Insert equal patient row and column direction cosine vectors.", PS33_PM,
          "The row and column direction vectors are orthogonal."),
    _case("REQ-PATH-029", "V7-PM-FLOAT", [_plane([1, 0, 0, 0, 0.5, 0])], PM,
          ("Ps3_C_7_6_2_1_1_29ac83",),
          "Insert a patient column direction vector of length 0.5.", PS33_PM,
          "Each patient direction cosine vector is normal."),
    _case("REQ-PATH-030", "V7-PM-FLOAT", [_plane([1, 0, 0, 0, 1, 0])], PM,
          ("Ps3_C_7_6_2_1_1_859096",),
          "Insert Plane Orientation (Patient) without Plane Position (Patient).", PS33_PM,
          "Patient plane position and orientation are provided as a pair."),
    _case("REQ-PATH-075", "V7-PM-FLOAT",
          [_op("insert", ["PatientOrientation"], ["R", "A"]),
           _plane([1, 0, 0, 0, 1, 0]),
           _op("insert", [*SHARED, "PlanePositionSequence"], [{
               "ImagePositionPatient": {"vr": "DS", "value": ["0", "0", "0"]},
           }])], PM,
          ("Ps3_C_7_6_1_1_1_ab0c02",),
          "Insert R\\A Patient Orientation with identity patient direction cosines and a matching position.",
          PS33_PM,
          "R and A name directions opposite the positive X and Y direction cosines."),
    _case("REQ-PATH-076", "V7-PM-FLOAT",
          [_op("insert", [*SHARED, "FrameAnatomySequence"], [{
              "AnatomicRegionSequence": [{
                  "CodeValue": "45048000", "CodingSchemeDesignator": "SCT",
                  "CodeMeaning": "Neck",
              }],
              "PrimaryAnatomicStructureSequence": [{
                  "CodeValue": "62413002", "CodingSchemeDesignator": "SCT",
                  "CodeMeaning": "Thyroid lobe",
                  "PrimaryAnatomicStructureModifierSequence": [{
                      "CodeValue": "7771000", "CodingSchemeDesignator": "SCT",
                      "CodeMeaning": "Left",
                  }],
              }],
              "FrameLaterality": "R",
          }])], PM,
          ("Ps3_C_7_6_16_9_FrameLaterality_3ce32c",),
          "Insert Frame Laterality R with a Primary Anatomic Structure Modifier meaning Left.",
          PS33_PM,
          "Frame Laterality agrees with laterality in the Primary Anatomic Structure Modifier."),
    _case("REQ-PATH-085", "V7-PM-ICC",
          [_op("set", ["ColorSpace"], "DISPLAYP3")], PM,
          ("Ps3_C_8_32_2_ColorSpace_0cd0fd",),
          "Name DISPLAYP3 while retaining the sRGB ICC Profile.", PS33_PM,
          "Color Space names the primaries and white point of the ICC Profile."),
    _case("REQ-PATH-090", "V7-PM-FLOAT", [_lut("SS", 4096, 16, 131_072)], PM,
          ("Ps3_C_11_2_1_1_fd1510",),
          "Store 65536 16-bit LUT entries but encode 4096, rather than 0, in LUT Descriptor Value 1.",
          PS33_PM,
          "When the table contains 2^16 entries, LUT Descriptor Value 1 is encoded as 0."),
    _encoding_case("REQ-PATH-092", "V7-PM-FLOAT",
          [{"op": "encapsulate_native_value", "path": ["FloatPixelData"]}],
          ("encoding",), ("Ps5_8_2_0fadc3",),
          "Rewrite native Float Pixel Data as an Undefined Length Value containing a Basic Offset Table and one Fragment.",
          PS35_FLOAT,
          "Float Pixel Data in every Standard Transfer Syntax is native, never encapsulated."),
)


ANNOTATION_CASES = (
    _set_case("REQ-PATH-097", "V7-ANN-CONCAT-SET", [
        {
            "path": "annotations.dcm",
            "retag": True,
            "operations": [_op("set", ["ReferencedImageSequence", 0,
                                        "ReferencedSOPInstanceUID"],
                               CONCATENATION_MEMBER)],
        },
        {"path": "source-image.dcm"},
    ], ANN, ("Ps3_C_37_1_2_1_1_9a4f58",),
        "Reference the WSI Concatenation member present beside the annotations object.",
        PS33_ANN,
        "Bulk Annotations references a Concatenation Source, not an individual member Instance."),
    _case("REQ-PATH-031", "V7-ANN-2D",
          [_op("set", [*ANN1, "AnnotationGroupNumber"], 1)], ANN,
          ("Ps3__C_37_1_2_AnnotationGroupNumber_5fe4bc",),
          "Change Annotation Group 2's number from 2 to 1.", PS33_ANN,
          "Annotation Group Numbers start at 1 and increase by one."),
    _case("REQ-PATH-032", "V7-ANN-2D",
          [_op("set", [*ANN0, "DoublePointCoordinatesData"], _od(1, 2, 3), vr="OD")], ANN,
          ("Ps3__C_37_1_2_DoublePointCoordinatesData_0cb021",),
          "Store three coordinate Values for 2D points.", PS33_ANN,
          "Each 2D point is encoded by an X,Y pair."),
    _case("REQ-PATH-033", "V7-ANN-2D",
          [_op("set", [*ANN0, "NumberOfAnnotations"], 3)], ANN,
          ("Ps3_C_37_1_2_1_1_bde27e", "Ps3_C_37_1_2_1_1_235c62"),
          "Set Number of Annotations to 3 while retaining two POINT tuples.", PS33_ANN,
          "POINT annotations are the concatenated coordinate tuples and their count matches."),
    _case("REQ-PATH-034", "V7-ANN-2D",
          [_op("insert", [*ANN0, "LongPrimitivePointIndexList"], _ol(1), vr="OL")], ANN,
          ("Ps3_C_37_1_2_1_1_5c3618",),
          "Add an index list to a POINT group.", PS33_ANN,
          "POINT indices are computed directly, so no separate index list is present."),
    _case("REQ-PATH-035", "V7-ANN-2D",
          [_op("set", [*ANN1, "LongPrimitivePointIndexList"], _ol(1), vr="OL")], ANN,
          ("Ps3_C_37_1_2_1_1_506ec9",),
          "Shorten the two-POLYGON index list to one Value.", PS33_ANN,
          "The polygon index list contains Number of Annotations Values."),
    _case("REQ-PATH-036", "V7-ANN-2D",
          [_op("set", [*ANN1, "GraphicType"], "POLYLINE"),
           _op("set", [*ANN1, "LongPrimitivePointIndexList"], _ol(1), vr="OL")], ANN,
          ("Ps3_C_37_1_2_1_1_263121",),
          "Treat the two outlines as POLYLINEs but retain only one index.", PS33_ANN,
          "The polyline index list contains Number of Annotations Values."),
    _case("REQ-PATH-037", "V7-ANN-2D",
          [_op("set", [*ANN1, "LongPrimitivePointIndexList"], _ol(3, 9), vr="OL")], ANN,
          ("Ps3_C_37_1_2_1_1_dde335",),
          "Start the polygon index list at coordinate Value 3.", PS33_ANN,
          "The first coordinate tuple begins at Value index 1."),
    _case("REQ-PATH-038", "V7-ANN-2D",
          [_op("set", [*ANN1, "LongPrimitivePointIndexList"], _ol(1, 1), vr="OL")], ANN,
          ("Ps3_C_37_1_2_1_1_810c10",),
          "Make the two polygon indices equal.", PS33_ANN,
          "Polygon coordinate ranges occur in the strictly increasing order of the index list."),
    _case("REQ-PATH-039", "V7-ANN-2D",
          [_op("set", [*ANN1, "DoublePointCoordinatesData"],
               _od(0, 0, 4, 0, 4, 4, 0, 0), vr="OD"),
           _op("set", [*ANN1, "NumberOfAnnotations"], 1),
           _op("set", [*ANN1, "LongPrimitivePointIndexList"], _ol(1), vr="OL")], ANN,
          ("Ps3_C_37_1_2_1_1_e2166b",),
          "Encode one polygon whose last point repeats its first.", PS33_ANN,
          "A polygon is closed implicitly; its first and last points differ."),
    _case("REQ-PATH-040", "V7-ANN-2D",
          [_op("set", [*ANN1, "DoublePointCoordinatesData"],
               _od(0, 0, 4, 4, 4, 0, 0, 4), vr="OD"),
           _op("set", [*ANN1, "NumberOfAnnotations"], 1),
           _op("set", [*ANN1, "LongPrimitivePointIndexList"], _ol(1), vr="OL")], ANN,
          ("Ps3_C_37_1_2_1_1_e4f629",),
          "Encode one self-crossing bow-tie polygon.", PS33_ANN,
          "Polygon line segments do not cross and the polygon has no hole."),
    _case("REQ-PATH-041", "V7-ANN-2D",
          [_op("set", [*ANN1, "DoublePointCoordinatesData"],
               _od(0, 0, 4, 0, 4, 4, 0, 4), vr="OD"),
           _op("set", [*ANN1, "NumberOfAnnotations"], 1),
           _op("set", [*ANN1, "LongPrimitivePointIndexList"], _ol(1), vr="OL")], ANN,
          ("Ps3_C_37_1_2_1_1_aa5274",),
          "Reverse one polygon's vertices to counter-clockwise winding.", PS33_ANN,
          "Vertices wind clockwise when viewed from the slide's top surface."),
    _case("REQ-PATH-042", "V7-ANN-2D",
          [_op("set", [*ANN0, "GraphicType"], "ELLIPSE"),
           _op("set", [*ANN0, "NumberOfAnnotations"], 1)], ANN,
          ("Ps3_C_37_1_2_1_1_430f9f", "Ps3_C_37_1_2_1_1_7d942e"),
          "Treat two point tuples as one ELLIPSE.", PS33_ANN,
          "An ellipse has four axis-endpoint tuples and its count is one quarter of their number."),
    _case("REQ-PATH-043", "V7-ANN-2D",
          [_op("set", [*ANN0, "GraphicType"], "RECTANGLE"),
           _op("set", [*ANN0, "NumberOfAnnotations"], 1)], ANN,
          ("Ps3_C_37_1_2_1_1_7874da", "Ps3_C_37_1_2_1_1_db2f1e"),
          "Treat two point tuples as one RECTANGLE.", PS33_ANN,
          "A rectangle has four corner tuples and its count is one quarter of their number."),
    _case("REQ-PATH-044", "V7-ANN-2D",
          [_op("set", ["PixelOriginInterpretation"], "FRAME")], ANN,
          ("Ps3_C_37_1_2_1_1_bcbcea",),
          "Set Pixel Origin Interpretation to FRAME without identifying a Frame.", PS33_ANN,
          "FRAME coordinates specify one Frame of one image."),
    _case("REQ-PATH-045", "V7-ANN-2D",
          [_op("insert", ["ReferencedImageSequence", 0, "ReferencedFrameNumber"], "1")], ANN,
          ("Ps3_C_37_1_2_1_1_2d725e",),
          "Add a Referenced Frame Number while Pixel Origin Interpretation remains VOLUME.",
          PS33_ANN, "VOLUME coordinates specify one image without a subset of Frames."),
    _case("REQ-PATH-046", "V7-ANN-2D",
          [_op("set", [*ANN0, "MeasurementsSequence", 0, "MeasurementValuesSequence", 0,
                        "FloatingPointValues"], _of(0.5, 0.75, 1.0), vr="OF")], ANN,
          ("Ps3__C_37_1_2_FloatingPointValues_53fe2c",),
          "Store three measurements for two POINT annotations without an Annotation Index List.",
          PS33_ANN, "Without indices, one measurement Value is stored per Annotation."),
    _case("REQ-PATH-047", "V7-ANN-2D",
          [_op("set", [*ANN1, "MeasurementsSequence", 0, "MeasurementValuesSequence", 0,
                        "FloatingPointValues"], _of(1, 2, 3), vr="OF")], ANN,
          ("Ps3__C_37_1_2_FloatingPointValues_76b057",),
          "Store three measurements for the two polygons named by the primitive index list.",
          PS33_ANN, "Without Annotation Index List, measurement count follows the primitive index list."),
    _case("REQ-PATH-048", "V7-ANN-2D",
          [_op("insert", [*ANN1, "MeasurementsSequence", 0, "MeasurementValuesSequence", 0,
                           "AnnotationIndexList"], _ol(1), vr="OL")], ANN,
          ("Ps3__C_37_1_2_FloatingPointValues_8cc06d",),
          "Add one Annotation Index while retaining two measurement Values.", PS33_ANN,
          "With Annotation Index List, the measurement count follows its indices."),
    _case("REQ-PATH-049", "V7-ANN-2D",
          [_op("insert", [*ANN1, "MeasurementsSequence", 0, "MeasurementValuesSequence", 0,
                           "AnnotationIndexList"], _ol(3), vr="OL"),
           _op("set", [*ANN1, "MeasurementsSequence", 0, "MeasurementValuesSequence", 0,
                        "FloatingPointValues"], _of(1), vr="OF")], ANN,
          ("Ps3__C_37_1_2_AnnotationIndexList_67905a",),
          "Reference nonexistent Annotation 3 from a two-annotation group.", PS33_ANN,
          "Annotation Index List Values reference Annotations in the group."),
    _case("REQ-PATH-070", "V7-ANN-2D",
          [_op("set", [*ANN0, "GraphicType"], "ELLIPSE"),
           _op("set", [*ANN0, "DoublePointCoordinatesData"],
               _od(0, 5, 10, 5, 5, 3, 5, 7), vr="OD"),
           _op("set", [*ANN0, "NumberOfAnnotations"], 1),
           _op("insert", [*ANN0, "LongPrimitivePointIndexList"], _ol(1), vr="OL")], ANN,
          ("Ps3_C_37_1_2_1_1_2c0f5d",),
          "Add a primitive index list to an otherwise valid ELLIPSE.", PS33_ANN,
          "The index of each fixed-four-point ellipse is computed, so no index list is present."),
    _case("REQ-PATH-071", "V7-ANN-2D",
          [_op("set", [*ANN1, "GraphicType"], "POLYLINE"),
           _op("set", [*ANN1, "DoublePointCoordinatesData"], _od(0, 0, 1), vr="OD"),
           _op("set", [*ANN1, "NumberOfAnnotations"], 1),
           _op("set", [*ANN1, "LongPrimitivePointIndexList"], _ol(1), vr="OL")], ANN,
          ("Ps3_C_37_1_2_1_1_57f979",),
          "End a POLYLINE's coordinate data halfway through its second point.", PS33_ANN,
          "Every polyline point is encoded as a complete coordinate tuple in the concatenated data."),
    _case("REQ-PATH-072", "V7-ANN-2D",
          [_op("set", [*ANN1, "DoublePointCoordinatesData"], _od(0, 0, 1), vr="OD"),
           _op("set", [*ANN1, "NumberOfAnnotations"], 1),
           _op("set", [*ANN1, "LongPrimitivePointIndexList"], _ol(1), vr="OL")], ANN,
          ("Ps3_C_37_1_2_1_1_dc0ee5",),
          "End a POLYGON's coordinate data halfway through its second point.", PS33_ANN,
          "Every polygon point is encoded as a complete coordinate tuple in the concatenated data."),
    _case("REQ-PATH-084", "V7-ANN-ICC",
          [_op("set", ["ColorSpace"], "DISPLAYP3")], ANN,
          ("Ps3_C_11_15_1_ColorSpace_47a7bc",),
          "Name DISPLAYP3 while retaining the sRGB ICC Profile.", PS33_ANN,
          "Color Space is consistent with the ICC Profile's primaries and white point."),
    _case("REQ-PATH-091", "V7-ANN-2D",
          [_op("set", [*ANN0, "GraphicType"], "TRIANGLE")],
          ("iod-enumerated-values",), ("Ps3__C_37_1_2_GraphicType_707986",),
          "Set Graphic Type to TRIANGLE while retaining the two valid POINT coordinate tuples.",
          PS33_ANN,
          "Table C.37.1-2 enumerates POINT, POLYLINE, POLYGON, ELLIPSE and RECTANGLE only."),
)


DOCUMENT_CASES = (
    _case("REQ-PATH-050", "V7-KOS-ACQ-COMPLETE",
          [_op("delete", ["ContentTemplateSequence"])], KOS,
          ("Ps3_A_35_4_3_1_3_ee396a", "Ps3_C_18_8_1_2_96463f"),
          "Remove the root Content Template Sequence identifying TID 2010.", PS33_SR,
          "A KOS is constructed from TID 2010 and identifies that Template at its root."),
    _case("REQ-PATH-051", "V7-KOS-ACQ-COMPLETE",
          [_op("delete", ["ContentSequence", 1, "ValueType"]),
           _op("delete", ["ContentSequence", 1, "ReferencedSOPSequence"]),
           _op("insert", ["ContentSequence", 1, "ReferencedContentItemIdentifier"], [1, 1])], KOS,
          ("Ps3_A_35_4_3_1_2_fa2e8d",),
          "Convey the second root CONTAINS relationship by-reference to the first Item.", PS33_SR,
          "KOS relationships are conveyed by-value."),
    _case("REQ-PATH-052", "V7-SR-TID1500",
          [_op("set", ["ContentSequence", 3, "TextValue"], "device\tname")], SR,
          ("Ps3_C_17_5_TextValue_cbe4b1",),
          "Put a horizontal tab in a TEXT Content Item's Text Value.", PS33_SR,
          "Text Value permits CR LF lines but no other format control characters."),
    _case("REQ-PATH-053", "V7-SR-TID1500",
          [_op("set", [*MEASURED, "FloatingPointValue"], [1.0, 2.0])], SR,
          ("Ps3_C_18_1_1_FloatingPointValue_929170",),
          "Give Floating Point Value two Values.", PS33_SR,
          "Only one Floating Point Value is present."),
    _case("REQ-PATH-054", "V7-SR-TID1500",
          [_op("set", [*MEASURED, "NumericValue"], ["1", "2"])], SR,
          ("Ps3_C_18_1_1_NumericValue_04da1c",),
          "Give Numeric Value two Values.", PS33_SR,
          "Only one Numeric Value is present."),
    _case("REQ-PATH-055", "V7-SR-TID1500",
          [_op("insert", [*MEASURED, "RationalNumeratorValue"], [1, 2])], SR,
          ("Ps3_C_18_1_1_RationalNumeratorValue_93b0c9",),
          "Insert two Rational Numerator Values.", PS33_SR,
          "Only one Rational Numerator Value is present."),
    _case("REQ-PATH-056", "V7-SR-TID1500",
          [_op("insert", [*MEASURED, "RationalDenominatorValue"], [1, 2])], SR,
          ("Ps3_C_18_1_1_RationalDenominatorValue_7a7dc3",),
          "Insert two Rational Denominator Values.", PS33_SR,
          "Only one Rational Denominator Value is present."),
    _case("REQ-PATH-057", "V7-KOS-ACQ-COMPLETE",
          [_op("insert", ["ContentSequence", 0, "ReferencedSOPSequence", 0,
                           "ReferencedFrameNumber"], "0")], KOS,
          ("Ps3_C_18_4_1_ReferencedFrameNumber_cb2c38",),
          "Add Referenced Frame Number 0 to an IMAGE Content Item.", PS33_SR,
          "Frame numbering begins at 1."),
    _case("REQ-PATH-058", "V7-KOS-ACQ-COMPLETE",
          [_op("insert", ["ContentSequence", 0, "ReferencedSOPSequence", 0, "IconImageSequence"], [{
              "SamplesPerPixel": 1, "PhotometricInterpretation": "MONOCHROME2",
              "Rows": 256, "Columns": 64, "BitsAllocated": 8, "BitsStored": 8,
              "HighBit": 7, "PixelRepresentation": 0,
              "PixelData": {"vr": "OB", "value": "00" * (256 * 64)},
          }])], KOS,
          ("Ps3_C_18_4_1_IconImageSequence_9594fc",),
          "Add a 256 by 64 Icon Image to an IMAGE reference.", PS33_SR,
          "An SR Icon Image is no greater than 128 by 128."),
    _case("REQ-PATH-059", "V7-SR-TID1500",
          [_op("delete", [*SCOORD, "ContentSequence"])], SR,
          ("Ps3_C_18_6_0d9ea4",),
          "Remove the SCOORD's SELECTED FROM IMAGE child.", PS33_SR,
          "An SCOORD is the Source of a SELECTED FROM relationship to an IMAGE."),
    _case("REQ-PATH-060", "V7-SR-TID1500",
          [_op("set", [*SCOORD, "GraphicData"], [-1.0, 0.0])], SR,
          ("Ps3_C_18_6_1_GraphicData_fb751a",),
          "Replace the SCOORD outline with a negative column coordinate.", PS33_SR,
          "SCOORD Graphic Data lies at or above 0\\0 and within the selected image."),
    _case("REQ-PATH-061", "V7-SR-3D",
          [_op("set", [*SCOORD3D, "GraphicData"],
               [0.0001, 0.0002, 0.0, 0.0009, 0.0002, 0.0,
                0.0009, 0.0018, 0.0, 0.0001, 0.0018, 0.0])], SR,
          ("Ps3_C_18_9_1_2_e8d12e",),
          "Remove the closing vertex from the SCOORD3D POLYGON.", PS33_SR,
          "A 3D POLYGON's last vertex equals its first."),
    _case("REQ-PATH-062", "V7-SR-TID1500",
          [_op("set", ["VerificationFlag"], "VERIFIED"),
           _op("set", ["CompletionFlag"], "PARTIAL")], SR,
          ("Ps3_C_17_2_VerificationFlag_4ef4cd",),
          "Set Verification Flag VERIFIED with Completion Flag PARTIAL.", PS33_SR,
          "VERIFIED is used only for a COMPLETE document."),
    _case("REQ-PATH-063", "V7-SR-TID1500",
          [_op("insert", ["CurrentRequestedProcedureEvidenceSequence", 0,
                           "(0040,E012)"], "/relative", vr="UR")], SR,
          ("Ps3_C_17_3_DisplayURI_29ba6d",),
          "Add relative Display URI /relative to current evidence.", PS33_SR,
          "Display URI includes scheme, authority, path and query."),
    _case("REQ-PATH-064", "V7-SR-TID1500",
          [_op("delete", ["CurrentRequestedProcedureEvidenceSequence"])], SR,
          ("Ps3_C_17_2_3_05558b", "Ps3_C_17_2_3_612a8f"),
          "Remove Current Requested Procedure Evidence while retaining the IMAGE reference.",
          PS33_SR, "Current evidence includes every current SOP Instance referenced by the Content Tree."),
    _case("REQ-PATH-065", "V7-KOS-ACQ-COMPLETE",
          [_op("insert", ["IdenticalDocumentsSequence"], [{
              "StudyInstanceUID": "{self.StudyInstanceUID}",
              "ReferencedSeriesSequence": [{
                  "SeriesInstanceUID": "{self.SeriesInstanceUID}",
                  "ReferencedSOPSequence": [{
                      "ReferencedSOPInstanceUID": "{self.SOPInstanceUID}",
                      "ReferencedSOPClassUID": "{self.SOPClassUID}",
                  }],
              }],
          }])], KOS,
          ("Ps3_C_17_2_2_cfad85",),
          "Make Identical Documents Sequence reference the document itself.", PS33_SR,
          "The Sequence references all other duplicates, which have different SOP Instance UIDs."),
    _case("REQ-PATH-066", "V7-SR-TID1500",
          [_op("insert", ["CurrentRequestedProcedureEvidenceSequence", 0,
                           "ReferencedSeriesSequence", 0, "ReferencedSOPSequence", 0,
                           "ReferencedSOPInstanceMACSequence"], [{
              "MACCalculationTransferSyntaxUID": "1.2.840.10008.1.2",
          }])], SR,
          ("Ps3_C_17_3a_MACCalculationTransferSyntaxUID_1ead61",),
          "Insert Referenced SOP Instance MAC data using Implicit VR Little Endian for MAC calculation.",
          PS33_SR,
          "MAC calculation uses an explicit-VR Little Endian Transfer Syntax."),
    _case("REQ-PATH-073", "V7-SR-TID1500",
          [_op("delete", ["ContentSequence", 10, "ContentSequence", 0,
                           "ContentSequence", 2, "ValueType"]),
           _op("delete", ["ContentSequence", 10, "ContentSequence", 0,
                           "ContentSequence", 2, "ConceptCodeSequence"]),
           _op("insert", ["ContentSequence", 10, "ContentSequence", 0,
                           "ContentSequence", 2, "ReferencedContentItemIdentifier"],
               [1, 11, 1])], SR,
          ("Ps3_A_35_3_3_1_2_c338b5", "Ps3_A_35_3_3_1_2_c62eb7"),
          "Convey a nested CONTAINS relationship by-reference to its ancestor Measurement Group.",
          PS33_SR,
          "A CONTAINS relationship is not conveyed by-reference, and no by-reference relationship targets an ancestor."),
    _case("REQ-PATH-074", "V7-SR-3D",
          [_op("delete", ["ContentSequence", 10, "ContentSequence", 0,
                           "ContentSequence", 2, "ValueType"]),
           _op("delete", ["ContentSequence", 10, "ContentSequence", 0,
                           "ContentSequence", 2, "ConceptCodeSequence"]),
           _op("insert", ["ContentSequence", 10, "ContentSequence", 0,
                           "ContentSequence", 2, "ReferencedContentItemIdentifier"],
               [1, 11, 1])], SR,
          ("Ps3_A_35_13_3_1_2_46ad78", "Ps3_A_35_13_3_1_2_67a070"),
          "Convey a nested CONTAINS relationship by-reference to its ancestor Measurement Group.",
          PS33_SR,
          "A CONTAINS relationship is not conveyed by-reference, and no by-reference relationship targets an ancestor."),
    _case("REQ-PATH-077", "V7-SR-TID1500",
          [_op("insert", ["PertinentOtherEvidenceSequence"],
               [_evidence(SOURCE_STUDY, SOURCE_SERIES, SOURCE_IMAGE_1)])], SR,
          ("Ps3_C_17_2_3_9a0301",),
          "List the same source image in Current Requested Procedure Evidence and Pertinent Other Evidence.",
          PS33_SR,
          "One SOP Instance is current evidence or other evidence, not both."),
    _case("REQ-PATH-078", "V7-SR-TID1500",
          [_op("set", ["VerificationFlag"], "VERIFIED"),
           _op("insert", ["VerifyingObserverSequence"], [{
               "VerifyingObserverName": "Pathologist^Test",
               "VerifyingOrganization": "Pathology",
               "VerificationDateTime": "20261024120000",
               "VerifyingObserverIdentificationCodeSequence": [],
           }]),
           _op("insert", ["ParticipantSequence"], [{
               "ParticipationType": "ATTEST", "ObserverType": "PSN",
               "PersonName": "Pathologist^Test", "ParticipationDateTime": "20261024120000",
           }])], SR,
          ("Ps3_C_17_2_5_496e9d",),
          "Identify Pathologist^Test as both Verifying Observer and Attestor.", PS33_SR,
          "An individual is not both the legal authenticator and an Attestor."),
    _case("REQ-PATH-079", "V7-KOS-ACQ-COMPLETE",
          [_op("replace", ["CurrentRequestedProcedureEvidenceSequence"], [
              _evidence(SOURCE_STUDY, SOURCE_SERIES, SOURCE_IMAGE_1, SOURCE_IMAGE_2),
              _evidence(SOURCE_STUDY, OTHER_SERIES,
                        "1.2.826.0.1.3680043.10.999.982"),
          ])], KOS,
          ("Ps3_C_17_6_2_CurrentRequestedProcedureEvidenceSequence_e9fc34",),
          "Add a third Current Requested Procedure Evidence reference that no Content Item references.",
          PS33_SR,
          "A KOS Current Requested Procedure Evidence Sequence includes no other Instances."),
    _case("REQ-PATH-080", "V7-KOS-ACQ-COMPLETE",
          [_op("replace", ["CurrentRequestedProcedureEvidenceSequence"], [
              _evidence(SOURCE_STUDY, SOURCE_SERIES, SOURCE_IMAGE_1),
              _evidence(OTHER_STUDY, SOURCE_SERIES, SOURCE_IMAGE_2),
          ])], KOS,
          ("Ps3_C_17_6_2_1_599086",),
          "Place the second referenced image's evidence in another Study without an Identical Documents reference.",
          PS33_SR,
          "A KOS referencing current evidence in another Study is duplicated there and lists the duplicate."),
    _document_pair("REQ-PATH-081",
          [_op("insert", ["IdenticalDocumentsSequence"], [
              _evidence(OTHER_STUDY, OTHER_SERIES, "{second.SOPInstanceUID}", sop_class=KOS_CLASS),
          ])],
          [_op("set", ["StudyInstanceUID"], OTHER_STUDY),
           _op("set", ["SeriesInstanceUID"], OTHER_SERIES),
           _op("insert", ["IdenticalDocumentsSequence"], [
               _evidence("{first.StudyInstanceUID}", "{first.SeriesInstanceUID}",
                         "{first.SOPInstanceUID}", sop_class=KOS_CLASS),
           ]),
           _op("set", ["ConceptNameCodeSequence", 0, "CodeValue"], "113000")],
          ("Ps3_C_17_2_2_867911",),
          "Create cross-Study duplicates that list each other, then change the second document title code.",
          "Identical copies in multiple Studies preserve the entire document content apart from inclusion identifiers."),
    _case("REQ-PATH-086", "V7-SR-BASIC-TEXT",
          [_op("delete", ["ContentSequence", 0, "ValueType"]),
           _op("delete", ["ContentSequence", 0, "TextValue"]),
           _op("insert", ["ContentSequence", 0, "ReferencedContentItemIdentifier"], [1])], SR,
          ("Ps3_A_35_1_3_1_2_41a954",),
          "Convey the Basic Text SR's CONTAINS relationship by-reference to the root.",
          PS33_SR, "Relationships in Basic Text SR are conveyed by-value."),
    _case("REQ-PATH-087", "V7-SR-ENHANCED",
          [_op("delete", ["ContentSequence", 0, "ValueType"]),
           _op("delete", ["ContentSequence", 0, "ConceptCodeSequence"]),
           _op("insert", ["ContentSequence", 0, "ReferencedContentItemIdentifier"], [1, 2])], SR,
          ("Ps3_A_35_2_3_1_2_c2ed9c",),
          "Convey the Enhanced SR's first HAS CONCEPT MOD relationship by-reference.",
          PS33_SR, "Relationships in Enhanced SR are conveyed by-value."),
    _case("REQ-PATH-088", "V7-SR-TCOORD",
          [_op("delete", ["ContentSequence", 0, "ContentSequence"])], SR,
          ("Ps3_C_18_7_c08e13",),
          "Remove the TCOORD's SELECTED FROM WAVEFORM child.", PS33_SR,
          "A TCOORD is the Source of one or more SELECTED FROM relationships to spatial, image or waveform content."),
    _case("REQ-PATH-089", "V7-SR-TCOORD",
          [_op("set", ["ContentSequence", 0, "ContentSequence", 0,
                        "ReferencedSOPSequence", 0, "ReferencedWaveformChannels"],
               [1, 1, 2, 1])], SR,
          ("Ps3_C_18_7_1_ReferencedSamplePositions_581602",),
          "Reference channels in multiplex groups 1 and 2 while using Referenced Sample Positions.",
          PS33_SR,
          "Referenced Sample Positions is used only when the selected channels are within one multiplex group."),
    _case("REQ-PATH-093", "V7-SR-TID1500",
          [_op("insert", [*MEASURED, "RationalNumeratorValue"], 1),
           _op("insert", [*MEASURED, "RationalDenominatorValue"], 0)], SR,
          ("Ps3_C_18_1_1_MeasuredValueSequence_fcf6c2",),
          "Add a rational representation 1/0 to an otherwise valid measured value.",
          PS33_SR,
          "A zero denominator does not represent an integer or real number."),
    _case("REQ-PATH-094", "V7-SR-TID1500",
          [_op("set", [*SCOORD, "ContentSequence", 0, "ReferencedSOPSequence", 0,
                        "ReferencedSOPClassUID"], COMPREHENSIVE_SR_CLASS),
           _op("set", ["CurrentRequestedProcedureEvidenceSequence", 0,
                        "ReferencedSeriesSequence", 0, "ReferencedSOPSequence", 0,
                        "ReferencedSOPClassUID"], COMPREHENSIVE_SR_CLASS)], SR,
          ("Ps3_C_18_6_c2d2c9",),
          "Change the SCOORD IMAGE Target and its matching evidence entry to reference Comprehensive SR Storage.",
          PS33_SR,
          "An IMAGE Target references an Image Storage SOP Class, not another SR document."),
)


SYNCHRONIZATION_CASES = (
    _case("REQ-PATH-067", "V7-PM-FLOAT",
          [_op("insert", ["NTPSourceAddress"], "192.168.1")], SYNC,
          ("Ps3_C_7_7_NTPSourceAddress_1dc1cf",),
          "Insert malformed IPv4 NTP Source Address 192.168.1.", PS33_SYNC,
          "An IPv4 address is dotted decimal with four octets."),
    _case("REQ-PATH-068", "V7-PM-FLOAT",
          [_op("insert", ["NTPSourceAddress"], "12:34:zz::1")], SYNC,
          ("Ps3_C_7_7_NTPSourceAddress_426275",),
          "Insert malformed IPv6 NTP Source Address 12:34:zz::1.", PS33_SYNC,
          "An IPv6 address uses colon-separated hexadecimal groups."),
    _pair("REQ-PATH-069", "V7-PM-FLOAT",
          [_op("insert", ["SynchronizationFrameOfReferenceUID"],
               "1.2.826.0.1.3680043.10.999.970")],
          [_op("insert", ["SynchronizationFrameOfReferenceUID"],
               "1.2.826.0.1.3680043.10.999.970"),
           _op("set", ["FrameOfReferenceUID"], "1.2.826.0.1.3680043.10.999.971")],
          ("Ps3_C_7_4_2_1_1_110d46",),
          "Give two Parametric Maps of one Series the same Synchronization Frame UID but different Frame of Reference UIDs.",
          "All synchronized SOP Instances in a Series share the same Frame of Reference."),
)


CASES = (
    *SEGMENTATION_CASES,
    *PARAMETRIC_MAP_CASES,
    *ANNOTATION_CASES,
    *DOCUMENT_CASES,
    *SYNCHRONIZATION_CASES,
)

NAMED_BY_EXISTING: dict[str, tuple[str, ...]] = {}

# Filled only with statements deliberately left without an authored case.  The
# builder merges these reasons into the statement ledger.
UNCOVERED: dict[str, str] = {
}

CONTROLS: dict[str, dict] = {}
