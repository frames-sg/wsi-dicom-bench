"""Residual File Meta Information and multi-object metadata statement witnesses.

The mappings reuse an already-observed defect only where that defect directly violates the
statement.  ``DISPOSITION_CORRECTIONS`` records the UID-definition statement that cannot be
negatively witnessed from a stored file; it is intentionally not credited to a case.
"""

from __future__ import annotations

from .iod_amendment_cases import _case as _spec, _cite, _op


PS310_META = _cite("PS3.10", "7.1", "part10/chapter_7.html#sect_7.1")
PS310_ADDRESS = _cite("PS3.10", "7.1.1.1", "part10/chapter_7.html#sect_7.1.1.1")
PS35_UN = _cite("PS3.5", "6.2.2", "part05/sect_6.2.html#sect_6.2.2")
PS35_JPIP = _cite("PS3.5", "10.8", "part05/sect_10.8.html")
PS33_GROUP = _cite("PS3.3", "C.7.1.4.1.1", "part03/sect_C.7.html#sect_C.7.1.4.1.1")
PS33_CONCAT = _cite("PS3.3", "C.7.6.16.1 and C.7.6.16.2.2.4",
                    "part03/sect_C.7.6.16.html")
PS33_LOSSY = _cite("PS3.3", "C.7.6.1.1.5", "part03/sect_C.7.6.html#sect_C.7.6.1.1.5")
PS33_SEG_LOSSY = _cite("PS3.3", "C.8.20.2.2", "part03/sect_C.8.20.html#sect_C.8.20.2.2")
PS33_PM_LOSSY = _cite("PS3.3", "C.8.32.2.1", "part03/sect_C.8.32.html#sect_C.8.32.2.1")

PM_CLASS = "1.2.840.10008.5.1.4.1.1.30"
OTHER_STUDY = "1.2.826.0.1.3680043.10.999.970"
OTHER_SERIES = "1.2.826.0.1.3680043.10.999.971"
OTHER_CONCAT_SOURCE = "1.2.826.0.1.3680043.10.999.972"


def _case(case_id, control, mutation, parameters, expected, requirements, changed,
          citation, rationale):
    return _spec(
        case_id, control, mutation, parameters, tuple(expected), changed, citation, rationale,
        requirement_ids=list(requirements),
    )


def _rewrite(case_id, operations, requirements, changed, citation, rationale):
    return _case(
        case_id, "CP11-MONO-EVRLE-4F", "encoding_rewrite",
        {"operations": operations}, ("file-meta",), requirements, changed, citation, rationale,
    )


def _pair(case_id, control, first, second, requirements, changed, citation, rationale,
          *, same_sop_instance=False):
    parameters = {
        key: value
        for key, value in (("first", first), ("second", second))
        if value
    }
    if same_sop_instance:
        parameters["same_sop_instance"] = True
    return _case(
        case_id, control, "iod_edit_pair", parameters, ("series-set",), requirements,
        changed, citation, rationale,
    )


def _set(case_id, control, members, requirements, changed, citation, rationale):
    return _case(
        case_id, control, "iod_set_edits", {"members": members}, ("series-set",),
        requirements, changed, citation, rationale,
    )


def _member(path, *operations):
    result = {"path": path}
    if operations:
        result["operations"] = list(operations)
    return result


def _lossy_01():
    return [
        _op("set", ["LossyImageCompression"], "01"),
        _op("insert", ["LossyImageCompressionRatio"], "2.0"),
        _op("insert", ["LossyImageCompressionMethod"], "ISO_15444_1"),
    ]


FILE_META_CASES = (
    _rewrite(
        "REQ-RMD-001", [{"op": "file_meta_implicit", "tag": "(0002,0013)"}],
        ("Ps10_7_1_02d941",),
        "Encode Implementation Version Name with an Implicit VR header inside group 0002.",
        PS310_META,
        "Every File Meta element is encoded Explicit VR Little Endian, independent of the Data Set syntax.",
    ),
    _rewrite(
        "REQ-RMD-002", [{"op": "set_file_prefix", "value": "DICX"}],
        ("Ps10_7_1_607718", "Ps10_7_1_a2a04a"),
        "Replace the four-byte DICOM Prefix DICM with DICX while retaining the preamble, File Meta group and Data Set.",
        PS310_META,
        "A DICOM file has the File Meta header introduced by the literal uppercase DICM prefix.",
    ),
    _rewrite(
        "REQ-RMD-003",
        [{"op": "file_meta_set", "tag": "(0002,0013)", "value_hex": "4f4444"}],
        ("Ps10_7_1_6b69cd",),
        "Write the SH Implementation Version Name as the three unpadded bytes ODD.",
        PS310_META,
        "A File Meta Value is padded to an even encoded Value Length according to its VR.",
    ),
    _rewrite(
        "REQ-RMD-004",
        [{"op": "file_meta_insert", "tag": "(0002,1000)", "vr": "UN",
          "value_hex": "0000"}],
        ("Ps10_7_1_2f09d3", "Ps5_6_2_2_78baa9"),
        "Insert an otherwise ignorable future File Meta element with VR UN.",
        PS35_UN,
        "UN is never used for a File Meta Information Data Element, including an unknown future tag.",
    ),
    _rewrite(
        "REQ-RMD-005",
        [{"op": "file_meta_insert", "tag": "(0002,0102)", "vr": "OB",
          "value_hex": "0000"}],
        ("Ps10_7_1_a0dff3",),
        "Insert Private Information without Private Information Creator UID (0002,0100).",
        PS310_META,
        "The creator of present File Meta Private Information is identified by (0002,0100).",
    ),
    _rewrite(
        "REQ-RMD-006",
        [{"op": "file_meta_insert", "tag": "(0002,0026)", "vr": "UR",
          "text": "http:///dicomweb"}],
        ("Ps10_7_1_1_1_1add3e",),
        "Insert a Web Services Source Presentation Address with no URL authority.",
        PS310_ADDRESS,
        "A Web Services presentation address is an absolute endpoint URL and therefore names its host.",
    ),
    _rewrite(
        "REQ-RMD-007",
        [{"op": "file_meta_insert", "tag": "(0002,0027)", "vr": "UR",
          "text": "https://example.test/dicomweb"}],
        ("Ps10_7_1_1_1_3653a7",),
        "Insert an HTTPS Sending Presentation Address.",
        PS310_ADDRESS,
        "The recorded Web Services presentation-address scheme is http even when secure transport was used.",
    ),
    _rewrite(
        "REQ-RMD-008",
        [{"op": "file_meta_insert", "tag": "(0002,0028)", "vr": "UR",
          "text": "dicom:example.test"}],
        ("Ps10_7_1_1_1_5ec65a",),
        "Insert a DICOM Upper Layer Receiving Presentation Address without a port.",
        PS310_ADDRESS,
        "A DICOM Upper Layer presentation address records dicom:host:port.",
    ),
    _rewrite(
        "REQ-RMD-009",
        [{"op": "file_meta_set", "tag": "(0002,0010)",
          "text": "1.2.840.10008.1.2.4.94"}],
        ("Ps5_10_8_d4693e",),
        "Declare the DICOM JPIP Referenced Transfer Syntax in a PS3.10 file.",
        PS35_JPIP,
        "JPIP Referenced Transfer Syntaxes are negotiated for network transfer and are not used for PS3.10 media storage.",
    ),
)


CONCATENATION_CASES = (
    _set(
        "REQ-RMD-011", "W7-CONCATENATION-2X4F",
        [_member("part-1.dcm"),
         _member("part-2.dcm", _op("set", ["InConcatenationNumber"], 1))],
        ("Ps3_C_7_6_16_1_InConcatenationNumber_f490dd",),
        "Give both members In-concatenation Number 1 while their frame offsets remain 0 and 4.",
        PS33_CONCAT,
        "In-concatenation Numbers start at one and increase by one in frame-offset order.",
    ),
    _set(
        "REQ-RMD-012", "W7-CONCATENATION-2X4F",
        [_member("part-1.dcm", _op("set", ["InConcatenationTotalNumber"], 1)),
         _member("part-2.dcm", _op("set", ["InConcatenationTotalNumber"], 1))],
        ("Ps3_C_7_6_16_1_InConcatenationTotalNumber_4fdb6d",),
        "Set In-concatenation Total Number to 1 in both members.",
        PS33_CONCAT,
        "A present total is greater than one for an IOD that permits concatenations.",
    ),
    _set(
        "REQ-RMD-013", "W7-CONCATENATION-2X4F",
        [_member("part-1.dcm"),
         _member("part-2.dcm", _op("set", ["SOPInstanceUIDOfConcatenationSource"],
                                      OTHER_CONCAT_SOURCE))],
        ("Ps3_C_7_6_16_1_SOPInstanceUIDOfConcatenationSource_487ffc",),
        "Give the second member another SOP Instance UID of Concatenation Source.",
        PS33_CONCAT,
        "All members identify the same unsplit source SOP Instance.",
    ),
    _set(
        "REQ-RMD-014", "W7-CONCATENATION-2X4F",
        [_member("part-1.dcm"),
         _member("part-2.dcm", _op("insert", ["DimensionIndexSequence", 0,
                                                "DimensionDescriptionLabel"], "Alternate row axis"))],
        ("Ps3_C_7_6_16_2_2_4_241add",),
        "Add a Dimension Description Label to only the second member's first Dimension Index Item.",
        PS33_CONCAT,
        "Dimension Index Sequence Attributes and Values are identical across a Concatenation.",
    ),
    _set(
        "REQ-RMD-015", "W7-CONCATENATION-2X4F",
        [_member("part-1.dcm"),
         _member("part-2.dcm", _op("set", ["SharedFunctionalGroupsSequence", 0,
                                             "PixelMeasuresSequence", 0, "SliceThickness"],
                                      "0.002"))],
        ("Ps3_C_7_6_16_2_2_4_3fcf86",),
        "Change the shared Slice Thickness in only the second member.",
        PS33_CONCAT,
        "Shared Functional Groups Items and all their Values are identical across a Concatenation.",
    ),
    _set(
        "REQ-RMD-016", "W7-CONCATENATION-2X4F",
        [_member("part-1.dcm"),
         _member("part-2.dcm", _op("insert", ["PerFrameFunctionalGroupsSequence", 0,
                                                "FrameContentSequence", 0,
                                                "FrameAcquisitionNumber"], 1))],
        ("Ps3_C_7_6_16_2_2_4_b6a910",),
        "Add Frame Acquisition Number to one Per-Frame Functional Groups Item of the second member.",
        PS33_CONCAT,
        "Per-Frame Functional Groups Items have the same Attribute structure across a Concatenation.",
    ),
    _set(
        "REQ-RMD-017", "W7-CONCATENATION-2X4F",
        [_member("part-1.dcm"),
         _member("part-2.dcm", _op("insert", ["ImageComments"], "second member only"))],
        ("Ps3_C_7_6_16_2_2_4_c53142",),
        "Add optional Image Comments to only the second member.",
        PS33_CONCAT,
        "Outside the enumerated per-instance exceptions, Attributes and Values are identical across a Concatenation.",
    ),
)


LOSSY_CASES = (
    _pair(
        "REQ-RMD-018", "CP11-MONO-EVRLE-4F", _lossy_01(), None,
        ("Ps3_C_7_6_1_1_5_491487", "Ps3_C_7_9_LossyImageCompression_e641df",
         "Ps3_C_8_12_4_1_LossyImageCompression_debf6c"),
        "Write two versions of one native WSI SOP Instance with Lossy Image Compression 01 then 00.",
        PS33_LOSSY,
        "Lossy Image Compression is never reset after 01; a lossy version would instead be a new SOP Instance.",
        same_sop_instance=True,
    ),
    _pair(
        "REQ-RMD-019", "V7-SEG-BINARY", _lossy_01(), None,
        ("Ps3_C_8_20_2_LossyImageCompression_9c833d",),
        "Write two versions of one Segmentation SOP Instance with Lossy Image Compression 01 then 00.",
        PS33_LOSSY,
        "The Segmentation Image Module repeats the rule that Lossy Image Compression is not reset.",
        same_sop_instance=True,
    ),
    _pair(
        "REQ-RMD-020", "V7-PM-FLOAT", _lossy_01(), None,
        ("Ps3_C_8_32_2_LossyImageCompression_a5f421",),
        "Write two versions of one Parametric Map SOP Instance with Lossy Image Compression 01 then 00.",
        PS33_LOSSY,
        "The Parametric Map Image Module repeats the rule that Lossy Image Compression is not reset.",
        same_sop_instance=True,
    ),
    _set(
        "REQ-RMD-021", "V7-SEG-FOR-SET",
        [_member("segmentation.dcm"),
         _member("source-image.dcm", *_lossy_01())],
        ("Ps3_C_8_20_2_2_042c5f",),
        "Mark the referenced source WSI as having lossy history while the derived Segmentation remains 00.",
        PS33_SEG_LOSSY,
        "A Segmentation derived from any source with Lossy Image Compression 01 also records 01.",
    ),
    _pair(
        "REQ-RMD-022", "V7-PM-FLOAT",
        [_op("replace", ["SourceImageSequence"], [{
            "ReferencedSOPClassUID": PM_CLASS,
            "ReferencedSOPInstanceUID": "{second.SOPInstanceUID}",
        }])],
        _lossy_01(),
        ("Ps3_C_8_32_2_1_7fa3d3",),
        "Reference the second Parametric Map as the first's source, give the source lossy history 01, and retain 00 on the derived map.",
        PS33_PM_LOSSY,
        "A Parametric Map derived from any source with Lossy Image Compression 01 also records 01.",
    ),
)


GROUP_CASES = (
    _pair(
        "REQ-RMD-010", "CP11-MONO-EVRLE-4F",
        [
            _op("set", ["PatientID"], "GROUP"),
            _op("set", ["PatientSex"], "M"),
            _op("insert", ["GroupOfPatientsIdentificationSequence"], [{
                "PatientID": "MEMBER-1",
                "SubjectRelativePositionInImage": [1, 1, 1],
            }]),
        ],
        [
            _op("set", ["StudyInstanceUID"], OTHER_STUDY),
            _op("set", ["SeriesInstanceUID"], OTHER_SERIES),
            _op("set", ["PatientID"], "MEMBER-1"),
            _op("set", ["PatientSex"], "F"),
        ],
        ("Ps3_C_7_1_4_1_1_64e8d5",),
        "Describe a group as male while the separately imaged member named by its group sequence is female.",
        PS33_GROUP,
        "A Patient Module Attribute present on a non-human group is shared by every group member.",
    ),
)


CASES = (*FILE_META_CASES, *GROUP_CASES, *CONCATENATION_CASES, *LOSSY_CASES)


MAPPINGS = {
    "Ps10_7_1_7cdb3d": {
        "cases": ("IOD-FMI-002",),
        "rationale": "The File Meta SOP Class says VL Microscopic Image while the Data Set remains VL WSI.",
    },
    "Ps3_C_12_1_1_1_ac243d": {
        "cases": ("IOD-FMI-001",),
        "rationale": "The File Meta Media Storage SOP Instance UID differs from the Data Set SOP Instance UID.",
    },
    "Ps10_8_6_6f3918": {
        "cases": ("REQ-FILESET-024",),
        "rationale": "The DICOMDIR lacks its Type 1 File-set UID in File Meta and therefore does not comply with Section 7.",
    },
}
NAMED_BY_EXISTING = MAPPINGS


DISPOSITION_CORRECTIONS = {
    "Ps5_A_7_e5c0fa": {
        "kind": "undecidable",
        "detail": (
            "Defines the UID assigned to JPIP Referenced Deflate; another UID identifies another "
            "syntax, and stored bytes cannot record an intended different UID assignment."
        ),
    },
}


UNCOVERED = {}
