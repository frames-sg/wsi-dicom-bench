"""Single-defect IOD-rule cases for the v7 ``requirement-statement-evaluation-v2`` cohort.

Each case breaks a normative statement that one of the generated-table rules
(``iod-value-format``, ``iod-vr-vm``, ``iod-attribute-presence``, ``iod-enumerated-values``,
``iod-modules`` and ``iod-sequence-items``) enforces, and names it in ``requirement_ids``.
Values a DICOM writer would normalize away (padding, odd Value Lengths, malformed numeric
text) are written into the encoded bytes with ``encoding_rewrite``; the rest use
``iod_edits``. Every Attribute a case adds around its defect is otherwise conformant.

``NAMED_BY_EXISTING`` names the statements that carried-forward and requirement-statement
cases already break, and ``UNCOVERED`` the statements no single-defect case can hold, with
the reason. Expectations are set as for the rest of the cohort: by running the frozen
candidate and adjudicating each result against DICOM 2026d.
"""

from __future__ import annotations

from functools import partial

from .encoding_cases import _creator, _defined, _element, _insert, _set_value
from .iod_amendment_cases import SHARED, _case as _spec, _cite, _code, _edits, _op


PS33_CODE = _cite("PS3.3", "8.1", "part03/sect_8.html#sect_8.1")
PS33_MAPPING_RESOURCE = _cite("PS3.3", "8.4", "part03/sect_8.4.html")
PS33_EXTENSION = _cite("PS3.3", "8.7", "part03/sect_8.7.html")
PS33_PHOTOMETRIC = _cite("PS3.3", "C.7.6.3.1.2", "part03/sect_C.7.6.3.html#sect_C.7.6.3.1.2")
PS33_PLANAR = _cite("PS3.3", "C.7.6.3.1.3", "part03/sect_C.7.6.3.html#sect_C.7.6.3.1.3")
PS33_IMAGE_TYPE = _cite("PS3.3", "C.7.6.1.1.2 and C.8.12.4.1.1", "part03/sect_C.7.6.html#sect_C.7.6.1.1.2")
PS33_PRESENTATION_LUT = _cite("PS3.3", "C.7.6.1 Table C.7-9 and C.8.12.4 Table C.8.12.4-1",
                              "part03/sect_C.8.12.4.html")
PS33_ORIENTATION = _cite("PS3.3", "C.7.6.1.1.1", "part03/sect_C.7.6.html#sect_C.7.6.1.1.1")
PS33_HL7_DOCUMENT = _cite("PS3.3", "C.12.1.1.6", "part03/sect_C.12.html#sect_C.12.1.1.6")
PS35_REPERTOIRE = _cite("PS3.5", "6.1.2.1 and 6.1.2.3", "part05/chapter_6.html#sect_6.1.2.3")
PS35_SHIFTS = _cite("PS3.5", "6.1.2.5.2", "part05/chapter_6.html#sect_6.1.2.5.2")
PS35_CONTROLS = _cite("PS3.5", "6.1.3", "part05/chapter_6.html#sect_6.1.3")
PS35_VR = _cite("PS3.5", "6.2 Table 6.2-1", "part05/sect_6.2.html")
PS35_PN = _cite("PS3.5", "6.2.1.2", "part05/sect_6.2.html#sect_6.2.1.2")
PS35_UNKNOWN = _cite("PS3.5", "6.2.2", "part05/sect_6.2.2.html")
PS35_URI = _cite("PS3.5", "6.2.3", "part05/sect_6.2.3.html")
PS35_MULTIPLE = _cite("PS3.5", "6.4", "part05/sect_6.4.html")
PS35_ENUMERATED = _cite("PS3.5", "6.3", "part05/sect_6.3.html")
PS35_SEQUENCE = _cite("PS3.5", "7.5", "part05/chapter_7.html#sect_7.5")
PS35_TYPE_3 = _cite("PS3.5", "7.4.5", "part05/sect_7.4.5.html")
PS35_RETIRED = _cite("PS3.5", "7.7", "part05/chapter_7.html#sect_7.7")
PS35_PRIVATE = _cite("PS3.5", "7.8", "part05/chapter_7.html#sect_7.8")
PS35_PRIVATE_ENCODING = _cite("PS3.5", "7.8.2", "part05/chapter_7.html#sect_7.8.2")
PS35_PIXEL = _cite("PS3.5", "8.1 and 8.1.1", "part05/chapter_8.html#sect_8.1.1")
PS35_UID = _cite("PS3.5", "9.1", "part05/chapter_9.html#sect_9.1")
PS35_IMPLICIT_LITTLE = _cite("PS3.5", "A.1", "part05/chapter_A.html#sect_A.1")
PS35_EXPLICIT_LITTLE = _cite("PS3.5", "A.2", "part05/chapter_A.html#sect_A.2")
PS35_ENCAPSULATED = _cite("PS3.5", "A.4", "part05/chapter_A.html#sect_A.4")

IMPLICIT_LITTLE_ENDIAN = "1.2.840.10008.1.2"
VL_PHOTOGRAPHIC_CLASS = "1.2.840.10008.5.1.4.1.1.77.1.4"
CDA_RELEASE_2 = "2.16.840.1.113883.1.7.2"
REFERENCED = "1.2.826.0.1.3680043.10.999.950"
OTHER_STUDY = "1.2.826.0.1.3680043.10.999.951"
OTHER_SERIES = "1.2.826.0.1.3680043.10.999.952"
MONO = "CP11-MONO-EVRLE-4F"
SPECIMEN = ["SpecimenDescriptionSequence", 0]
ICON_PIXEL_DATA = ["IconImageSequence", 0, "PixelData"]
# Data Element Tags written into the encoded bytes.
PATIENT_SIZE = "(0010,1020)"
PATIENT_WEIGHT = "(0010,1030)"
DATE_OF_LAST_CALIBRATION = "(0018,1200)"
ACQUISITION_UID = "(0008,0017)"
MANUFACTURER_DEVICE_CLASS_UID = "(0018,100B)"
# The Overlay Plane Module of group 6000 (PS3.3 C.9.2), whose keywords name repeating tags.
OVERLAY_ROWS = "(6000,0010)"
OVERLAY_COLUMNS = "(6000,0011)"
OVERLAY_TYPE = "(6000,0040)"
OVERLAY_ORIGIN = "(6000,0050)"
OVERLAY_BITS_ALLOCATED = "(6000,0100)"
OVERLAY_BIT_POSITION = "(6000,0102)"
OVERLAY_DATA = "(6000,3000)"

ENCODED = "Values a writer would normalize are written into the encoded bytes."


def _case(case_id, control, mutation, parameters, expected, requirements, changed, citation,
          rationale) -> dict:
    return _spec(case_id, control, mutation, parameters, expected, changed, citation, rationale,
                 requirement_ids=list(requirements))


def _edit(case_id, control, operations, requirements, changed, citation, rationale, expected):
    """An ``iod_edits`` case; the family partials below default ``expected``."""
    return _case(case_id, control, "iod_edits", _edits(*operations), expected, requirements,
                 changed, citation, rationale)


def _rewrite(case_id, control, operations, requirements, changed, citation, rationale, expected,
             **before):
    """An ``encoding_rewrite`` case; ``edits`` or ``transfer_syntax`` apply before the
    encoded-byte ``operations``."""
    return _case(case_id, control, "encoding_rewrite", {**before, "operations": operations},
                 expected, requirements, changed, citation, rationale)


FORMAT = ("iod-value-format",)
_format = partial(_edit, expected=FORMAT)
_format_bytes = partial(_rewrite, expected=FORMAT)
_vr_vm = partial(_edit, expected=("iod-vr-vm",))
_vr_vm_bytes = partial(_rewrite, expected=("iod-vr-vm",))
_presence = partial(_edit, expected=("iod-attribute-presence",))
_enumerated = partial(_edit, expected=("iod-enumerated-values",))


def _hex(text: str) -> str:
    return text.encode("utf-8").hex()


def _icon(**changes) -> dict:
    """An 8-bit MONOCHROME2 Icon Image Item (PS3.3 C.7.6.1.1.6) of ``Rows`` x ``Columns``."""
    icon = {
        "SamplesPerPixel": 1, "PhotometricInterpretation": "MONOCHROME2",
        "Rows": 2, "Columns": 3, "BitsAllocated": 8, "BitsStored": 8, "HighBit": 7,
        "PixelRepresentation": 0, "PixelData": {"vr": "OB", "value": "00" * 6},
    }
    icon.update(changes)
    return _op("insert", ["IconImageSequence"], [{key: value for key, value in icon.items() if value is not None}])


def _palette_icon(entries: int, data_vr: str = "OW", **changes) -> dict:
    """A PALETTE COLOR Icon Image whose 8-bit tables hold ``entries`` one-byte entries."""
    tables = {}
    for color in ("Red", "Green", "Blue"):
        tables[f"{color}PaletteColorLookupTableDescriptor"] = {"vr": "US", "value": [entries, 0, 8]}
        tables[f"{color}PaletteColorLookupTableData"] = {"vr": "OW", "value": "00" * entries}
    tables["RedPaletteColorLookupTableData"] = {"vr": data_vr, "value": "00" * entries}
    return _icon(PhotometricInterpretation="PALETTE COLOR", **{**tables, **changes})


def _overlay(columns: int, data_vr: str = "OW") -> list[dict]:
    """A one-row Overlay Plane (PS3.3 C.9.2) of ``columns`` bits in group 6000."""
    data = "00" * ((columns + 15) // 16 * 2)
    return [
        _op("insert", [OVERLAY_ROWS], 1, vr="US"),
        _op("insert", [OVERLAY_COLUMNS], columns, vr="US"),
        _op("insert", [OVERLAY_TYPE], "G", vr="CS"),
        _op("insert", [OVERLAY_ORIGIN], [1, 1], vr="SS"),
        _op("insert", [OVERLAY_BITS_ALLOCATED], 1, vr="US"),
        _op("insert", [OVERLAY_BIT_POSITION], 0, vr="US"),
        _op("insert", [OVERLAY_DATA], data, vr=data_vr),
    ]


def _voi_lut(entries: int, data_vr: str = "OW") -> dict:
    """A VOI LUT Sequence Item (PS3.3 C.11.2) of ``entries`` 8-bit entries, one byte each."""
    return _op("insert", ["VOILUTSequence"], [{
        "LUTDescriptor": {"vr": "US", "value": [entries, 0, 8]},
        "LUTExplanation": "Identity",
        "LUTData": {"vr": data_vr, "value": "00" * entries},
    }])


def _photo(retrieval: dict) -> list[dict]:
    """Reference a VL Photographic Image of another Study as the patient photo (PS3.3
    Table 10-3b), listed in the Studies Containing Other Referenced Instances Sequence."""
    instance = {"ReferencedSOPClassUID": VL_PHOTOGRAPHIC_CLASS, "ReferencedSOPInstanceUID": REFERENCED}
    return [
        _op("insert", ["ReferencedPatientPhotoSequence"], [{
            "TypeOfInstances": "DICOM", "StudyInstanceUID": OTHER_STUDY,
            "SeriesInstanceUID": OTHER_SERIES, "ReferencedSOPSequence": [instance], **retrieval,
        }]),
        _op("insert", ["StudiesContainingOtherReferencedInstancesSequence"], [{
            "StudyInstanceUID": OTHER_STUDY,
            "ReferencedSeriesSequence": [{"SeriesInstanceUID": OTHER_SERIES,
                                          "ReferencedInstanceSequence": [instance]}],
        }]),
    ]


def _institution(**code) -> dict:
    """Insert an Institution Code Sequence Item (PS3.3 Table C.7-8) coded as ``code``."""
    return _op("insert", ["InstitutionCodeSequence"], [{
        "CodingSchemeDesignator": "99LOCAL", "CodeMeaning": "Example Hospital", **code,
    }])


def _anatomy(**fields) -> dict:
    """Insert an Anatomic Region Sequence Item of DCMR CID 4 in Enhanced Encoding Mode."""
    return _op("insert", ["AnatomicRegionSequence"], [{
        **_code("SCT", "818981001", "Abdomen"),
        "ContextIdentifier": "4", "MappingResource": "DCMR",
        "ContextGroupVersion": "20260101000000", **fields,
    }])


def _image_type(*values: str) -> dict:
    return _op("set", ["ImageType"], list(values))


def _retrieve_uri(value_hex: str) -> dict:
    """Encode ``value_hex`` as the Retrieve URI of the Private Data Element Definition."""
    return _set_value(["PrivateDataElementCharacteristicsSequence", 0,
                       "PrivateDataElementDefinitionSequence", 0, "RetrieveURI"], value_hex)


def _private_sequence(*elements: tuple[str, str, object]) -> list[dict]:
    """Insert an ACME private Sequence whose one Item holds the given (tag, VR, Value) triples."""
    item = {tag: {"vr": vr, "value": value} for tag, vr, value in elements}
    return [
        _op("insert", ["(0029,0010)"], "ACME", vr="LO"),
        _op("insert", ["(0029,1001)"], [item], vr="SQ"),
    ]


URI_DEFINITION = _defined(1, "LO", RetrieveURI="https://example.com/acme/value")


VALUE_FORMAT_CASES = (
    _format("REQ-IOD-001", "CP02-JPEG-16F", [_anatomy(MappingResource="dcmr")],
        ("Ps3_8_4_79bf54",),
        "Insert an Anatomic Region Sequence Item of CID 4 whose Mapping Resource (0008,0105) is "
        "lower-case dcmr.",
        PS33_MAPPING_RESOURCE,
        "Mapping Resource is CS, whose Defined Terms are upper-case; lower-case letters are "
        "outside the CS repertoire."),
    _format_bytes("REQ-IOD-002", "CP10-EVRLE-16F",
        [_set_value(["StudyDescription"], _hex("Research placeholder WSI export\0"))],
        ("Ps5_6_1_2_3_51ae57", "Ps5_6_2_f340d0"),
        "Pad the 31-character Study Description (0008,1030) to even length with NULL (00H) "
        "instead of SPACE.",
        _cite("PS3.5", "6.1.2.3 and 6.2", "part05/sect_6.2.html"),
        "Character strings are padded with SPACE. The encoding rule reads the pad byte from the "
        "encoded bytes and reports it too, so both rules are expected. " + ENCODED,
        expected=(*FORMAT, "encoding")),
    _format("REQ-IOD-003", "CP01-EVRLE-4F-ANISO",
        [_op("set", ["OpticalPathSequence", 0, "OpticalPathDescription"], "Default optical\x7fpath")],
        ("Ps5_6_1_2_3_a287c9",),
        "Put DELETE (7FH) in Optical Path Description (0048,0107).",
        PS35_REPERTOIRE, "The character DELETE shall not be used in DICOM character strings."),
    _format("REQ-IOD-004", "CP10-EVRLE-16F",
        [_op("set", ["OpticalPathSequence", 0, "OpticalPathDescription"], "Default optical\x0epath")],
        ("Ps5_6_1_2_5_2_0f91c6", "Ps5_6_1_3_62ad2e"),
        "Put the locking shift SO (0EH) in Optical Path Description (0048,0107).",
        PS35_SHIFTS,
        "Locking shifts shall not be used, and SO is not one of the five C0 control characters "
        "text may use (6.1.3). The encoding rule reads the shift from the encoded bytes and "
        "reports it too, so both rules are expected.",
        expected=(*FORMAT, "encoding")),
    _format("REQ-IOD-005", "CP04-J2K-LOSSLESS-16F", [_op("set", ["AccessionNumber"], "RESE\tARCH")],
        ("Ps5_6_2_f0355c",),
        "Put TAB (09H) in Accession Number (0008,0050).",
        PS35_VR, "SH shall not have control characters other than ESC."),
    _format_bytes("REQ-IOD-006", "CP10-EVRLE-16F",
        [_insert([], _element(ACQUISITION_UID, "UI", text="2.25.1234567890 "))],
        ("Ps5_6_2_82cca4", "Ps5_6_2_5e4dd5", "Ps5_9_1_9be579"),
        "Insert Acquisition UID (0008,0017) 2.25.1234567890, 15 characters, padded with SPACE "
        "(20H).",
        PS35_UID,
        "An odd-length UID is padded with a single trailing NULL. The encoding rule reads the pad "
        "byte from the encoded bytes and reports it too, so both rules are expected. " + ENCODED,
        expected=(*FORMAT, "encoding")),
    _format("REQ-IOD-007", "CP06-HTJ2K-LOSSLESS-16F", [_op("insert", ["PatientAge"], "045X")],
        ("Ps5_6_2_7e81a8",),
        "Insert Patient's Age (0010,1010) 045X.",
        PS35_VR, "AS is three digits followed by D, W, M or Y."),
    _format_bytes("REQ-IOD-008", "CP10-EVRLE-16F",
        [_insert([], _element(PATIENT_WEIGHT, "DS", text="70,5"))],
        ("Ps5_6_2_f892eb",),
        "Insert Patient's Weight (0010,1030) 70,5 with a decimal comma.",
        PS35_VR, "A fixed point DS holds only digits, a leading sign and a period. " + ENCODED),
    _format_bytes("REQ-IOD-009", "CP01-EVRLE-4F-ANISO",
        [_insert([], _element(PATIENT_SIZE, "DS", text="1.75D+00"))],
        ("Ps5_6_2_0c85c6",),
        "Insert Patient's Size (0010,1020) 1.75D+00 with a Fortran D exponent.",
        PS35_VR, "A floating point DS marks its exponent with E or e. " + ENCODED),
    _format("REQ-IOD-010", "CP07-HTJ2K-RPCL-4F", [_op("set", ["ContentTime"], "240000")],
        ("Ps5_6_2_e33c94",),
        "Set Content Time (0008,0033) to 240000.",
        PS35_VR, "Midnight is 0000; 24 is outside the hour range."),
    _format("REQ-IOD-011", "CP09-J2K-LOSSLESS-4F",
        [_op("set", ["AcquisitionDateTime"], "19700101000000.1234567")],
        ("Ps5_6_2_3ed511",),
        "Set Acquisition DateTime (0008,002A) to 19700101000000.1234567, seven fractional digits.",
        PS35_VR, "The DT Fractional Second holds 1 to 6 digits."),
    _format("REQ-IOD-012", "CP04-J2K-LOSSLESS-16F",
        [_op("set", ["AcquisitionDateTime"], "19700101000000.")],
        ("Ps5_6_2_14f3d9",),
        "Set Acquisition DateTime (0008,002A) to 19700101000000. with no fractional digits.",
        PS35_VR, "Without a Fractional Second the preceding period is not included."),
    _format("REQ-IOD-013", "CP06-HTJ2K-LOSSLESS-16F",
        [_op("set", ["AcquisitionDateTime"], "19700101000000+01")],
        ("Ps5_6_2_f7c84a",),
        "Set Acquisition DateTime (0008,002A) to 19700101000000+01, a two-digit offset.",
        PS35_VR, "The DT offset suffix holds four digits."),
    _format("REQ-IOD-014", "CP13-IMPLICIT-TILED-FULL",
        [_op("set", ["AcquisitionDateTime"], "19700101000000-0000")],
        ("Ps5_6_2_768fdd",),
        "Set Acquisition DateTime (0008,002A) to 19700101000000-0000.",
        PS35_VR, "The offset of a DT Value in UTC is +0000."),
    _format("REQ-IOD-015", "CP14-MONO16-EVRLE", [_op("set", ["AcquisitionDateTime"], "+0000")],
        ("Ps5_6_2_75c3d6",),
        "Set Acquisition DateTime (0008,002A) to +0000, an offset without a year.",
        PS35_VR, "The DT YYYY component shall not be null."),
    _format("REQ-IOD-016", "CP03-JPEG-1F", [_op("set", ["StudyTime"], "000000.1234567")],
        ("Ps5_6_2_2720d0",),
        "Set Study Time (0008,0030) to 000000.1234567, seven fractional digits.",
        PS35_VR, "The TM FFFFFF component holds 1 to 6 digits."),
    _format("REQ-IOD-017", "CP02-JPEG-16F", [_op("set", ["AcquisitionTime"], "000000.")],
        ("Ps5_6_2_c534bd",),
        "Set Acquisition Time (0008,0032) to 000000. with no fractional digits.",
        PS35_VR, "Without FFFFFF the preceding period is not included."),
    _format_bytes("REQ-IOD-018", "CP11-MONO-EVRLE-4F",
        [_set_value(["InstanceNumber"], _hex("1.0 "))],
        ("Ps5_6_2_4f76de",),
        "Encode Instance Number (0020,0013) as 1.0.",
        PS35_VR, "IS holds only digits and a leading sign. " + ENCODED),
    _format("REQ-IOD-019", "CP09-J2K-LOSSLESS-4F", [_op("insert", ["AcquisitionNumber"], "2147483648")],
        ("Ps5_6_2_b9e2da",),
        "Insert Acquisition Number (0020,0012) 2147483648.",
        PS35_VR, "IS is within -2^31 to 2^31-1."),
    _format("REQ-IOD-020", "CP01-EVRLE-4F-ANISO", [_op("set", ["ReferringPhysicianName"], "A=B=C=D")],
        ("Ps5_6_2_57497d",),
        "Set Referring Physician's Name (0008,0090) to A=B=C=D, four component groups.",
        PS35_VR, "PN has at most two component group delimiters."),
    _format("REQ-IOD-021", "CP10-EVRLE-16F", [
        _op("insert", ["SpecificCharacterSet"], "ISO_IR 192"),
        _op("set", ["ReferringPhysicianName"], "Jose\u0301" * 13),
    ],
        ("Ps5_6_2_1_2_e3d9df",),
        "Declare ISO_IR 192 and set Referring Physician's Name (0008,0090) to 13 times José "
        "written with COMBINING ACUTE ACCENT, 52 base characters and 13 combining marks.",
        PS35_PN,
        "Each combining character counts toward the 64-character component group maximum, which "
        "the value-format rule reports.",
        expected=FORMAT),
    _format_bytes("REQ-IOD-022", "CP10-EVRLE-16F",
        [_retrieve_uri(_hex("https://example.com/acme/caf\u00e9"))],
        ("Ps5_6_2_2653e9", "Ps5_6_2_3_f3fccc", "Ps5_6_2_3_019dcb"),
        "Insert a Private Data Element Definition whose Retrieve URI (0040,E010) path ends in é as "
        "the UTF-8 bytes C3H A9H.",
        PS35_URI,
        "UR uses the RFC 3986 subset of the Default Character Repertoire; other characters are "
        "percent-encoded UTF-8. " + ENCODED,
        edits=URI_DEFINITION),
    _format_bytes("REQ-IOD-023", "CP11-MONO-EVRLE-4F",
        [_retrieve_uri(_hex("https://ex\u00e4mple.com/acme/id"))],
        ("Ps5_6_2_3_fb1c60",),
        "Insert a Private Data Element Definition whose Retrieve URI (0040,E010) host is "
        "exämple.com in raw UTF-8.",
        PS35_URI, "A domain name outside the permitted characters uses the IDNA encoding. " + ENCODED,
        edits=URI_DEFINITION),
    _format("REQ-IOD-024", "CP13-IMPLICIT-TILED-FULL",
        _photo({"DICOMRetrievalSequence": [{"RetrieveAETitle": "    "}]}),
        ("Ps5_6_2_10b562",),
        "Reference a patient photo whose DICOM Retrieval Sequence Retrieve AE Title (0008,0054) "
        "is four spaces.",
        PS35_VR, "An AE Value consisting solely of spaces shall not be used."),
    _format_bytes("REQ-IOD-025", "CP10-EVRLE-16F",
        [_insert([], _element(DATE_OF_LAST_CALIBRATION, "DA", text="20240101\\20250101")),
         {"op": "drop_padding", "path": ["DateOfLastCalibration"]}],
        ("Ps5_6_4_3472c2",),
        "Insert Date of Last Calibration (0018,1200) 20240101\\20250101 with its odd 17-byte "
        "Value Field unpadded.",
        PS35_MULTIPLE, "The whole Value Field of a multi-valued string, delimiters included, has "
        "even length. " + ENCODED),
    _format_bytes("REQ-IOD-026", "CP01-EVRLE-4F-ANISO",
        [_insert([], _element(DATE_OF_LAST_CALIBRATION, "DA", text="20240101 \\20250101"))],
        ("Ps5_6_4_f2e91a", "Ps5_6_2_3981c3"),
        "Insert Date of Last Calibration (0018,1200) with its pad SPACE after Value 1: "
        "\"20240101 \\20250101\".",
        PS35_MULTIPLE, "The single padding character goes at the end of the Value Field, after the "
        "last Value. " + ENCODED),
    _format_bytes("REQ-IOD-027", "CP14-MONO16-EVRLE",
        [_insert([], _element(MANUFACTURER_DEVICE_CLASS_UID, "UI", value_hex=_hex("2.25.1001\0\\2.25.1002")))],
        ("Ps5_6_4_fde9f8",),
        "Insert Manufacturer's Device Class UID (0018,100B) 2.25.1001\\2.25.1002 with a NULL after "
        "Value 1.",
        PS35_MULTIPLE, "Only the last UID Value is padded with NULL. " + ENCODED),
    _format("REQ-IOD-028", "CP07-HTJ2K-RPCL-4F",
        [_op("insert", ["DateOfLastCalibration"], "20240101/20250101")],
        ("Ps5_6_4_8bab9c", "Ps5_6_4_0a3e14", "Ps5_7_1_1_88ebbc"),
        "Insert Date of Last Calibration (0018,1200) 20240101/20250101, two dates delimited by "
        "a solidus.",
        PS35_MULTIPLE, "Multiple string Values are delimited by 5CH."),
    _format("REQ-IOD-029", "CP10-EVRLE-16F", [
        _op("insert", ["(0029,0010)"], "ACME", vr="LO"),
        _op("insert", ["(0029,1001)"], "20261301", vr="DA"),
    ],
        ("Ps5_7_8_2_c93d2d",),
        "Insert private element (0029,1001) DA 20261301 in the ACME block.",
        PS35_PRIVATE_ENCODING, "Private Data Elements use the VRs of PS3.5 6.2 and conform to "
        "their encoding; month 13 is no DA."),
    _format_bytes("REQ-IOD-030", "CP01-EVRLE-4F-ANISO",
        [{"op": "drop_padding", "path": ICON_PIXEL_DATA}],
        ("Ps5_8_1_1_649518", "Ps5_6_2_e0c655"),
        "Insert a 3x1 Icon Image and drop the NULL that pads its 3-byte OB Pixel Data "
        "(7FE0,0010) to even length.",
        PS35_PIXEL, "Pixel Data, like all Value Fields, has even length, and OB pads with a "
        "single NULL. " + ENCODED,
        edits=[_icon(Rows=1, Columns=3, PixelData={"vr": "OB", "value": "000000"})]),
    _format("REQ-IOD-031", "CP03-JPEG-1F", [_op("set", ["PyramidUID"], "2.25.12A45")],
        ("Ps5_9_1_5dab00", "Ps5_9_1_e2c578"),
        "Set Pyramid UID (0008,0019) to 2.25.12A45.",
        PS35_UID, "UID components are numbers of the digits 0-9."),
    _format("REQ-IOD-032", "CP06-HTJ2K-LOSSLESS-16F", [_op("set", ["PyramidUID"], "2,25,12345")],
        ("Ps5_9_1_98ae51",),
        "Set Pyramid UID (0008,0019) to 2,25,12345.",
        PS35_UID, "UID components are separated by periods."),
    _format("REQ-IOD-033", "CP09-J2K-LOSSLESS-4F",
        [_op("set", ["PyramidUID"], "2.25." + "1" * 60)],
        ("Ps5_9_1_fcd445",),
        "Set Pyramid UID (0008,0019) to 2.25 followed by a 60-digit component, 65 characters.",
        PS35_UID, "A UID has at most 64 characters."),
    # PS3.5 A.1: OB, OL, OV and OW Values in Implicit VR Little Endian.
    _format_bytes("REQ-IOD-034", "CP10-EVRLE-16F",
        [{"op": "drop_padding", "path": ICON_PIXEL_DATA}],
        ("Ps5_A_1_0482a6", "Ps5_A_1_8481bf", "Ps5_A_1_0a4a49"),
        "Re-encode the control in Implicit VR Little Endian, insert a 3x1 Icon Image, and drop "
        "the pad of its 3-byte Pixel Data (7FE0,0010), which is OW in Implicit VR.",
        PS35_IMPLICIT_LITTLE, "Pixel Data is OW in Implicit VR, so its Value Length is even. " + ENCODED,
        edits=[_icon(Rows=1, Columns=3, PixelData={"vr": "OB", "value": "000000"})],
        transfer_syntax=IMPLICIT_LITTLE_ENDIAN),
    _format_bytes("REQ-IOD-035", "CP10-EVRLE-16F",
        [{"op": "drop_padding", "path": [OVERLAY_DATA]}],
        ("Ps5_A_1_ea8197",),
        "Re-encode the control in Implicit VR Little Endian, insert a 1x8 Overlay Plane in group "
        "6000, and drop the pad of its 1-byte Overlay Data (6000,3000).",
        PS35_IMPLICIT_LITTLE, "Overlay Data is OW in Implicit VR, so its Value Length is even. " + ENCODED,
        edits=_overlay(8), transfer_syntax=IMPLICIT_LITTLE_ENDIAN),
    _format_bytes("REQ-IOD-036", "CP11-MONO-EVRLE-4F",
        [{"op": "drop_padding", "path": ["IconImageSequence", 0, "RedPaletteColorLookupTableData"]}],
        ("Ps5_A_1_04740e",),
        "Re-encode the control in Implicit VR Little Endian, insert a PALETTE COLOR Icon Image of "
        "3 one-byte entries per table, and drop the pad of Red Palette Color Lookup Table Data "
        "(0028,1201).",
        PS35_IMPLICIT_LITTLE, "Palette Color Lookup Table Data is OW, so its Value Length is even. " + ENCODED,
        edits=[_palette_icon(3)], transfer_syntax=IMPLICIT_LITTLE_ENDIAN),
    _format_bytes("REQ-IOD-037", "CP11-MONO-EVRLE-4F",
        [{"op": "drop_padding", "path": ["VOILUTSequence", 0, "LUTData"]}],
        ("Ps5_A_1_86c594",),
        "Re-encode the control in Implicit VR Little Endian, insert a VOI LUT Sequence Item of 3 "
        "one-byte entries, and drop the pad of its LUT Data (0028,3006).",
        PS35_IMPLICIT_LITTLE, "LUT Data is US or OW, so its Value Length is even. " + ENCODED,
        edits=[_voi_lut(3)], transfer_syntax=IMPLICIT_LITTLE_ENDIAN),
    _format_bytes("REQ-IOD-038", "CP10-EVRLE-16F",
        [_insert([], _element(PATIENT_SIZE, "DS", text="1 .2"))],
        ("Ps5_6_2_ce2868",),
        "Insert Patient's Size (0010,1020) as DS 1 .2 with an embedded SPACE.",
        PS35_VR, "DS does not allow embedded spaces. " + ENCODED),
    _format_bytes("REQ-IOD-039", "CP10-EVRLE-16F",
        [_insert([], _element(ACQUISITION_UID, "UI", value_hex="20" + _hex("2.25.1") + "00"))],
        ("Ps5_6_2_4f6b04",),
        "Insert Acquisition UID (0008,0017) with a leading SPACE before 2.25.1 and a trailing NULL pad.",
        PS35_UID, "UI does not allow a leading SPACE. " + ENCODED),
    _format_bytes("REQ-IOD-074", "CP10-EVRLE-16F",
        [{"op": "set_value", "path": ["AcquisitionDateTime"], "text": " 19700101000000 "}],
        ("Ps5_6_2_e1decf",),
        "Set Acquisition DateTime (0008,002A) to a leading SPACE, 19700101000000, and a trailing pad.",
        PS35_VR, "DT does not allow leading or embedded spaces. " + ENCODED),
    _format_bytes("REQ-IOD-075", "CP10-EVRLE-16F",
        [{"op": "set_value", "path": ["AcquisitionDateTime"], "text": "1970    01010000"}],
        ("Ps5_6_2_b82926",),
        "Set Acquisition DateTime (0008,002A) to 1970 followed by four SPACE bytes and 01010000.",
        PS35_VR, "DT prohibits null components before later components. " + ENCODED),
    _format_bytes("REQ-IOD-076", "CP10-EVRLE-16F",
        [{"op": "set_value", "path": ["InstanceNumber"], "value_hex": "3109"}],
        ("Ps5_6_2_daeeb8",),
        "Set Instance Number (0020,0013) to byte 31H followed by TAB (09H).",
        PS35_VR, "IS does not allow TAB or another Control Character. " + ENCODED),
    _format("REQ-IOD-079", "CP10-EVRLE-16F", _defined([1, 3, 0], "LO"),
        ("Ps3_C_12_1_1_7_1_03edd3",),
        "Insert a Private Data Element definition whose Value Multiplicity is the range 1-3 with stride 0.",
        _cite("PS3.3", "C.12.1.1.7.1", "part03/sect_C.12.html#sect_C.12.1.1.7.1"),
        "The third Value of a ranged Private Data Element Value Multiplicity is a nonzero stride."),
    _format_bytes("REQ-IOD-080", "CP10-EVRLE-16F",
        [_insert([], _element("(0028,0009)", "AT", value_hex="0000"))],
        ("Ps5_6_4_7a0ae1",),
        "Insert Frame Increment Pointer (0028,0009) with a two-byte partial AT Value.",
        PS35_MULTIPLE, "Fixed-length binary Values are concatenated whole, without a delimiter. " + ENCODED),
)


VR_VM_CASES = (
    _vr_vm("REQ-IOD-040", "CP02-JPEG-16F", [_op("insert", ["PatientOrientation"], ["A", "F", "L"])],
        ("Ps3_C_7_6_1_1_1_b53257",),
        "Insert Patient Orientation (0020,0020) A\\F\\L, three Values.",
        PS33_ORIENTATION, "Patient Orientation is specified by two Values, row then column."),
    _vr_vm("REQ-IOD-041", "CP04-J2K-LOSSLESS-16F", [_op("insert", ["StationName"], "SLIDE\\SCANNER")],
        ("Ps5_6_2_7c3538", "Ps5_6_1_2_3_5f1078"),
        "Insert Station Name (0008,1010) SLIDE\\SCANNER, a name holding BACKSLASH (5CH).",
        PS35_VR, "5CH is not present in SH, where it delimits Values, so the VM 1 Attribute reads "
        "as two Values."),
    _vr_vm_bytes("REQ-IOD-042", "CP10-EVRLE-16F",
        [{"op": "set_vr", "path": ["StudyDescription"], "vr": "UN"}],
        ("Ps5_6_2_2_b96c3e",),
        "Encode Study Description (0008,1030) with VR UN in the Explicit VR control.",
        PS35_UNKNOWN, "UN is for Private Data Elements and Values of unknown VR; Study Description "
        "is LO and its 32-byte Value fits a 16-bit Value Length."),
    _vr_vm("REQ-IOD-043", "CP01-EVRLE-4F-ANISO", [
        _op("insert", ["(0029,0010)"], _hex("ACME"), vr="UN"),
        _op("insert", ["(0029,1001)"], "V", vr="LO"),
    ],
        ("Ps5_6_2_2_b4d2eb",),
        "Insert the ACME private block with its Private Creator (0029,0010) encoded with VR UN.",
        PS35_UNKNOWN, "A Private Creator is LO; UN shall not be used for it."),
    _vr_vm_bytes("REQ-IOD-044", "CP10-EVRLE-16F",
        [{"op": "set_vr", "path": ["AcquisitionContextSequence"], "vr": "OB"}],
        ("Ps5_7_5_251684",),
        "Encode the empty Explicit Length Acquisition Context Sequence (0040,0555) with VR OB.",
        PS35_SEQUENCE, "A Sequence of zero or more Items has VR SQ. " + ENCODED,
        lengths=[{"path": ["AcquisitionContextSequence"], "sequence": "defined"}]),
    _vr_vm("REQ-IOD-045", "CP06-HTJ2K-LOSSLESS-16F",
        [_op("insert", ["RecognitionCode"], ["ACR-NEMA 2.0", "EXTRA"])],
        ("Ps5_7_7_b39a73",),
        "Insert the retired Recognition Code (0008,0010) with two Values.",
        PS35_RETIRED, "A retired Data Element holds valid data of its older definition, which "
        "gives it VM 1."),
    _vr_vm("REQ-IOD-046", "CP11-MONO-EVRLE-4F", [
        _op("insert", ["(0030,0010)"], "ACME", vr="LO"),
        _op("insert", ["(0030,1001)"], "V", vr="LO"),
    ],
        ("Ps5_7_8_992cc6",),
        "Insert a private block, Private Creator (0030,0010) ACME and (0030,1001) LO V, in the even "
        "group 0030.",
        PS35_PRIVATE, "Private Data Elements have an odd Group Number; PS3.6 defines no "
        "element of group 0030."),
    _vr_vm("REQ-IOD-047", "CP09-J2K-LOSSLESS-4F", [
        _op("insert", ["(0029,0010)"], "ACME", vr="LO"),
        _op("insert", ["(0029,1001)"], [{"Manufacturer": {"vr": "SH", "value": "ACME"}}], vr="SQ"),
    ],
        ("Ps5_7_8_2_fc38c1",),
        "Insert a private Sequence (0029,1001) whose Item holds Manufacturer (0008,0070) with "
        "VR SH.",
        PS35_PRIVATE_ENCODING, "Standard Data Elements in a Private Data Sequence use their PS3.6 "
        "VR, LO for Manufacturer."),
    # PS3.5 A.2 and A.4: the VRs of Pixel, Overlay, palette and LUT Data.
    *(
        _vr_vm(case_id, control, operations, requirements, f"{prefix}{changed}", citation, rationale)
        for control, prefix, citation, cases in (
            ("CP10-EVRLE-16F", "", PS35_EXPLICIT_LITTLE, (
                ("REQ-IOD-048", "pixel", ("Ps5_A_2_7e2850", "Ps5_A_2_45d343", "Ps5_A_2_4fe8ab")),
                ("REQ-IOD-049", "overlay", ("Ps5_A_2_7687c9",)),
                ("REQ-IOD-050", "palette", ("Ps5_A_2_972477",)),
            )),
            ("CP03-JPEG-1F", "In the JPEG Baseline control, ", PS35_ENCAPSULATED, (
                ("REQ-IOD-052", "pixel", ("Ps5_A_4_5af91b", "Ps5_A_4_45b4b3", "Ps5_A_4_42ecb9")),
                ("REQ-IOD-053", "overlay", ("Ps5_A_4_5cc995",)),
                ("REQ-IOD-054", "palette", ("Ps5_A_4_3b7a41",)),
            )),
        )
        for case_id, kind, requirements in cases
        for operations, changed, rationale in ({
            "pixel": ([_icon(Rows=2, Columns=2, PixelData={"vr": "OL", "value": "00" * 4})],
                      "insert an 8-bit 2x2 Icon Image whose Pixel Data (7FE0,0010) has VR OL.",
                      "Pixel Data with Bits Allocated of 8 or less is OB or OW."),
            "overlay": (_overlay(32, "OL"),
                        "insert a 1x32 Overlay Plane whose Overlay Data (6000,3000) has VR OL.",
                        "Overlay Data is OB or OW."),
            "palette": ([_palette_icon(256, "OB")],
                        "insert a PALETTE COLOR Icon Image whose Red Palette Color Lookup Table "
                        "Data (0028,1201) has VR OB.",
                        "Palette Color Lookup Table Data is OW."),
        }[kind],)
    ),
    _vr_vm("REQ-IOD-051", MONO, [_voi_lut(256, "OB")],
        ("Ps5_A_2_54edc7",),
        "Insert a VOI LUT Sequence Item whose LUT Data (0028,3006) has VR OB.",
        PS35_EXPLICIT_LITTLE, "LUT Data is US or OW."),
    _vr_vm("REQ-IOD-081", "CP10-EVRLE-16F",
        _private_sequence(("(0066,0129)", "OW", "00000000")),
        ("Ps5_A_2_5cbc84",),
        "Insert a private Sequence Item whose Track Point Index List is OW instead of OL.",
        PS35_EXPLICIT_LITTLE, "Explicit VR Little Endian assigns Track Point Index List VR OL."),
    _vr_vm("REQ-IOD-082", "CP10-EVRLE-16F",
        _private_sequence(("(0028,1408)", "OB", "0000")),
        ("Ps5_A_2_e15d71",),
        "Insert a private Sequence Item whose Blending LUT Data is OB instead of OW.",
        PS35_EXPLICIT_LITTLE, "Explicit VR Little Endian assigns Blending LUT Data VR OW."),
    _vr_vm("REQ-IOD-083", "CP03-JPEG-1F",
        _private_sequence(("(0066,0129)", "OW", "00000000")),
        ("Ps5_A_4_cd73d1",),
        "In an encapsulated control, insert a private Sequence Item whose Track Point Index List "
        "is OW instead of OL.",
        PS35_ENCAPSULATED, "Encapsulated Transfer Syntaxes keep Track Point Index List VR OL."),
    _vr_vm("REQ-IOD-084", "CP03-JPEG-1F",
        _private_sequence(("(0028,1408)", "OB", "0000")),
        ("Ps5_A_4_3dedae",),
        "In an encapsulated control, insert a private Sequence Item whose Blending LUT Data is OB instead of OW.",
        PS35_ENCAPSULATED, "Encapsulated Transfer Syntaxes keep Blending LUT Data VR OW."),
)


PRESENCE_CASES = (
    _presence("REQ-IOD-060", "CP10-EVRLE-16F", [_institution(CodeValue="EXAMPLE-HOSPITAL-1")],
        ("Ps3_8_1_5e1957",),
        "Insert an Institution Code Sequence Item whose 18-character code is in Code Value "
        "(0008,0100).",
        PS33_CODE, "A code longer than 16 characters is not in Code Value. Code Value is SH, so "
        "the value-format rule reports the same 18 characters.",
        expected=("iod-attribute-presence", *FORMAT)),
    _presence("REQ-IOD-061", "CP02-JPEG-16F", [_institution(LongCodeValue="EX-HOSP-1")],
        ("Ps3_8_1_1c95ed",),
        "Insert an Institution Code Sequence Item whose 9-character code is in Long Code Value "
        "(0008,0119), without Code Value.",
        PS33_CODE, "A code of 16 characters or less is in Code Value, and Long Code Value is "
        "absent."),
    _presence("REQ-IOD-062", "CP04-J2K-LOSSLESS-16F",
        [_institution(LongCodeValue="urn:oid:1.2.826.0.1.3680043.10.999.953")],
        ("Ps3_8_1_aeece1",),
        "Insert an Institution Code Sequence Item whose URN code is in Long Code Value (0008,0119).",
        PS33_CODE, "A code in URN notation is in URN Code Value."),
    _presence("REQ-IOD-063", "CP06-HTJ2K-LOSSLESS-16F",
        [_institution(URNCodeValue="EXAMPLEHOSPITAL01")],
        ("Ps3_8_1_597bf2",),
        "Insert an Institution Code Sequence Item whose 17-character code, not a URN or URL, is in "
        "URN Code Value (0008,0120).",
        PS33_CODE, "A code longer than 16 characters in another notation is in Long Code Value."),
    _presence("REQ-IOD-064", "CP07-HTJ2K-RPCL-4F",
        [_anatomy(ContextGroupExtensionFlag="Y", ContextGroupLocalVersion="20260102000000")],
        ("Ps3_8_7_2d698d",),
        "Insert an Anatomic Region Sequence Item of CID 4 with Context Group Extension Flag "
        "(0008,010B) Y and no Context Group Extension Creator UID (0008,010D).",
        PS33_EXTENSION, "An extended Context Group names the creator of its extension."),
    _presence("REQ-IOD-065", "CP09-J2K-LOSSLESS-4F",
        [_op("insert", ["HL7StructuredDocumentReferenceSequence"], [{
            "ReferencedSOPClassUID": CDA_RELEASE_2,
            "HL7InstanceIdentifier": "1.2.826.0.1.3680043.10.999.954^1",
        }])],
        ("Ps3_C_12_1_1_6_0f08ec",),
        "Insert an HL7 Structured Document Reference Item for a CDA Release 2 document without "
        "Referenced SOP Instance UID (0008,1155).",
        PS33_HL7_DOCUMENT, "An HL7 Structured Document reference is a SOP Class UID and SOP "
        "Instance UID pair."),
    _presence("REQ-IOD-066", MONO,
        [_palette_icon(256, GreenPaletteColorLookupTableData=None)],
        ("Ps3_C_7_6_3_1_2_00abdd",),
        "Insert a PALETTE COLOR Icon Image without Green Palette Color Lookup Table Data "
        "(0028,1202).",
        PS33_PHOTOMETRIC, "With PALETTE COLOR the Red, Green and Blue tables are present."),
    _presence("REQ-IOD-067", "CP10-EVRLE-16F", [_op("delete", ["PlanarConfiguration"])],
        ("Ps3_C_7_6_3_1_3_5d2797",),
        "Remove Planar Configuration (0028,0006) from the RGB control.",
        PS33_PLANAR, "Planar Configuration is present when Samples per Pixel is greater than 1."),
    _rewrite("REQ-IOD-068", "CP13-IMPLICIT-TILED-FULL",
        [_insert(["IconImageSequence", 0], _creator(), _element("(0029,1001)", "OB", value_hex="00" * 6))],
        ("Ps5_8_1_80d60f", "Ps5_7_8_f1a77f"),
        "Insert a 2x3 Icon Image whose six pixels are in private element (0029,1001) OB of its "
        "Item, with Private Creator (0029,0010) ACME, instead of Pixel Data (7FE0,0010).",
        PS35_PIXEL, "Image data is exchanged in Pixel Data, and a private element does not take "
        "the place of a required standard one.",
        expected=("iod-attribute-presence",), edits=[_icon(PixelData=None)]),
    _presence("REQ-IOD-069", "CP14-MONO16-EVRLE", [_icon(HighBit=None)],
        ("Ps5_8_1_1_3229af",),
        "Insert an Icon Image without High Bit (0028,0102).",
        PS35_PIXEL, "Bits Allocated, Bits Stored and High Bit define the pixel structure."),
)


ENUMERATED_CASES = (
    _enumerated("REQ-IOD-070", "CP01-EVRLE-4F-ANISO", [_image_type("", "PRIMARY", "VOLUME", "NONE")],
        ("Ps3_C_7_6_1_1_2_e953ef", "Ps3_C_8_12_4_1_1_296245", "Ps5_6_3_ed2fcf"),
        "Set Image Type (0008,0008) Value 1 empty.",
        PS33_IMAGE_TYPE, "Value 1 identifies the Pixel Data Characteristics, ORIGINAL or DERIVED; "
        "an empty Value is no Enumerated Value."),
    _enumerated("REQ-IOD-071", "CP04-J2K-LOSSLESS-16F", [_image_type("ORIGINAL", "", "VOLUME", "NONE")],
        ("Ps3_C_7_6_1_1_2_d4e4dd",),
        "Set Image Type (0008,0008) Value 2 empty.",
        PS33_IMAGE_TYPE, "Value 2 identifies the Patient Examination Characteristics, PRIMARY in "
        "VL WSI."),
    _enumerated("REQ-IOD-072", MONO, [_op("set", ["PresentationLUTShape"], "INVERSE")],
        ("Ps3_C_7_9_PresentationLUTShape_92f0e9",),
        "Set Presentation LUT Shape (2050,0020) to INVERSE in the MONOCHROME2 control.",
        PS33_PRESENTATION_LUT, "Presentation LUT Shape is IDENTITY for MONOCHROME2 and color."),
)


SEQUENCE_ITEM_CASES = (
    _edit("REQ-IOD-073", "CP03-JPEG-1F", [_op("insert", ["ContributingEquipmentSequence"], [])],
        ("Ps5_7_4_5_4ef00e",),
        "Insert the Type 3 Contributing Equipment Sequence (0018,A001) with zero Items.",
        PS35_TYPE_3, "A Type 3 Sequence is not present with zero Items.",
        expected=("iod-sequence-items",)),
)


PIXEL_STRUCTURE_CASES = (
    _edit("REQ-IOD-077", "CP10-EVRLE-16F",
        [_op("set", ["NumberOfFrames"], "0")],
        ("Ps3_C_7_6_6_1_1_8d631a", "Ps5_8_1_1_5123f3"),
        "Set Number of Frames (0028,0008) to 0 while retaining the native Pixel Data.",
        PS35_PIXEL, "A multi-frame image has at least one Frame, so Number of Frames is greater than zero; "
        "the unchanged Per-Frame Functional Groups Item count also disagrees with the new value.",
        expected=("pixel-structure", "iod-sequence-items")),
)


WSI_IMAGE_CASES = (
    _edit("REQ-IOD-086", "W7-ZSTACK-3P-TILED-FULL",
        [_op("set", ["SpecimenLabelInImage"], "YES")],
        ("Ps3_C_8_12_4_1_SpecimenLabelInImage_0b6709",),
        "Set Specimen Label in Image (0048,0010) to YES on a VOLUME image.",
        _cite("PS3.3", "C.8.12.4.1 and Table C.8.12.4-1",
              "part03/sect_C.8.12.4.html#sect_C.8.12.4.1"),
        "Specimen Label in Image is NO for VOLUME and THUMBNAIL images.",
        expected=("wsi-image",)),
    _edit("REQ-IOD-078", "CP10-EVRLE-16F",
        [_op("insert", [*SHARED, "SpecimenReferenceSequence"], [
            {"SpecimenUID": "1.2.826.0.1.3680043.10.999.7.78.99"}
        ])],
        ("Ps3_C_7_6_22_2_SpecimenDescriptionSequence_184620",),
        "Insert a shared Specimen Reference Item whose Specimen UID names no Specimen Description Item.",
        _cite("PS3.3", "C.7.6.22.2 and Table C.7.6.22-2",
              "part03/sect_C.7.6.22.html#sect_C.7.6.22.2"),
        "Each specimen referenced as imaged in Pixel Data is identified by a declared Specimen Description Item.",
        expected=("wsi-image",)),
    _edit("REQ-IOD-085", "W7-OPTICAL-PATHS-2-MONO", [
        _op("set", ["OpticalPathSequence", 1, "OpticalPathIdentifier"], "1"),
        *(_op("set", ["PerFrameFunctionalGroupsSequence", frame,
                       "OpticalPathIdentificationSequence", 0, "OpticalPathIdentifier"], "1")
          for frame in range(4, 8)),
    ],
        ("Ps3_C_8_12_5_1_OpticalPathIdentifier_d84211",),
        "Give Optical Path Sequence Item 2 and Frames 5-8 the identifier 1 already used by Item 1 "
        "and Frames 1-4.",
        _cite("PS3.3", "C.8.12.5.1 and Table C.8.12.5-1",
              "part03/sect_C.8.12.5.html#sect_C.8.12.5.1"),
        "Each Optical Path Sequence Item has a unique Optical Path Identifier.",
        expected=("wsi-image",)),
)


CASES = (
    *VALUE_FORMAT_CASES,
    *VR_VM_CASES,
    *PRESENCE_CASES,
    *ENUMERATED_CASES,
    *SEQUENCE_ITEM_CASES,
    *PIXEL_STRUCTURE_CASES,
    *WSI_IMAGE_CASES,
)

# These byte-level defects prevent Data Set framing, so the candidate reports them through the
# catalogued parser-failure path of intrinsic-pixel-structure before value-format dispatch.
for case in CASES:
    if case["case_id"] in {
        "REQ-IOD-034", "REQ-IOD-035", "REQ-IOD-036", "REQ-IOD-037", "REQ-IOD-080",
    }:
        case["expected"] = ("pixel-structure",)

# Statements that cases already in manifest-v6 break, by case.
NAMED_BY_EXISTING: dict[str, tuple[str, ...]] = {}

# Statements no single-defect case can hold, and why.
UNCOVERED: dict[str, str] = {}

BLOCKED_CASES = {}
