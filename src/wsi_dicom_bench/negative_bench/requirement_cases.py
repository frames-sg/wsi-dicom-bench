"""Single-defect cases of the v6 ``requirement-statement-evaluation-v1`` cohort.

Each case breaks one normative statement that a catalog-v6 rule enforces and names, in
``requirement_ids``, the statements of the evaluated engine's requirement catalog
(``wsi-dicom requirements --json``) that it exercises. Defects are built with the
``iod_edits`` and ``iod_edit_pair`` mutations; every Attribute a case adds around its
defect (a Sequence's Type 1 members, the Common Instance Reference listing of a
reference) is otherwise conformant, so the case has one defect.

The expected rules are authored from the rule definitions. Like the IOD structure
cohort, they are set by running the frozen candidate and adjudicating each result
against DICOM 2026c before the manifest is locked; they are not blinded.
"""

from __future__ import annotations

from functools import partial

from .codestream_cases import CODESTREAM_CASES
from .encoding_cases import ENCODING_CASES
from .iod_amendment_cases import SHARED, _case as _spec, _cite, _code, _edits, _op


PS33_SELECTOR = _cite("PS3.3", "10.17 Table 10-20", "part03/sect_10.17.html")
PS33_DCMR = _cite("PS3.3", "8.6", "part03/sect_8.6.html")
PS33_ORIGINAL = _cite("PS3.3", "C.12.1.1.9", "part03/sect_C.12.html#sect_C.12.1.1.9")
PS33_SIGNED = _cite("PS3.3", "C.12.1.1.3.1.1", "part03/sect_C.12.html#sect_C.12.1.1.3.1.1")
PS33_HL7_DOCUMENT = _cite("PS3.3", "C.12.1.1.6", "part03/sect_C.12.html#sect_C.12.1.1.6")
PS33_SOURCE_INSTANCE = _cite("PS3.3", "C.12.4.1.2", "part03/sect_C.12.4.html")
PS33_PATIENT_PHOTO = _cite("PS3.3", "C.2.2.1.1", "part03/sect_C.2.2.html")
PS33_GROUP = _cite("PS3.3", "C.7.1.4.1.1.1", "part03/sect_C.7.html#sect_C.7.1.4")
PS33_CALIBRATION = _cite("PS3.3", "C.7.5.1.1.1", "part03/sect_C.7.5.html#sect_C.7.5.1.1.1")
PS33_ORIENTATION = _cite("PS3.3", "C.7.6.1.1.1", "part03/sect_C.7.6.html#sect_C.7.6.1.1.1")
PS33_LATERALITY = _cite("PS3.3", "C.7.6.1 Table C.7-9", "part03/sect_C.7.6.html#sect_C.7.6.1")
PS33_PREPARATION = _cite("PS3.3", "C.7.6.22.1.3", "part03/sect_C.7.6.22.html")
PS33_FRAME_REFERENCE = _cite("PS3.3", "10.2, 10.3 and 10.3b", "part03/sect_10.3.html")
PS33_IDENTIFICATION = _cite("PS3.3", "C.7.2.1, C.7.3.1 and C.12.1", "part03/sect_C.7.3.html#sect_C.7.3.1")
PS33_MEASURED_VALUE = _cite("PS3.3", "10.2 Table 10-2", "part03/sect_10.2.html")
PS33_PERSON = _cite("PS3.3", "10.1 Table 10-1", "part03/sect_10.html#sect_10.1")
PS33_WSI_ATTRIBUTES = _cite("PS3.3", "C.8.12.4.1", "part03/sect_C.8.12.4.html")
PS33_IMAGE_TYPE = _cite("PS3.3", "C.7.6.1.1.2", "part03/sect_C.7.6.html#sect_C.7.6.1.1.2")
PS33_TILES = _cite("PS3.3", "C.8.12.14.1", "part03/sect_C.8.12.14.html")
PS33_OPTICAL_PATHS = _cite("PS3.3", "C.8.12.5.1", "part03/sect_C.8.12.5.html")
PS33_REFERENCE_INDICATOR = _cite("PS3.3", "C.7.4.1.1.2", "part03/sect_C.7.4.html#sect_C.7.4.1.1.2")
PS33_DERIVATION = _cite("PS3.3", "C.7.6.1.1.2 and C.7.6.1.1.5", "part03/sect_C.7.6.html#sect_C.7.6.1.1.2")
PS33_SPACING = _cite("PS3.3", "10.7.1.3", "part03/sect_10.7.html#sect_10.7.1.3")
PS33_TILING = _cite("PS3.3", "A.32.8.4.1.2", "part03/sect_A.32.8.4.html")
PS33_FRAME_OF_REFERENCE = _cite("PS3.3", "C.7.4.1.1.1", "part03/sect_C.7.4.html#sect_C.7.4.1.1.1")
PS35_UID_ROLES = _cite("PS3.5", "9", "part05/chapter_9.html")
PS33_INSTANCE_NUMBER = _cite("PS3.3", "C.7.6.16.1", "part03/sect_C.7.6.16.html")
PS33_DIMENSION_ORGANIZATION = _cite("PS3.3", "C.7.6.17.2", "part03/sect_C.7.6.17.2.html")
PS33_SPECIMEN_IDENTIFIER = _cite("PS3.3", "C.7.6.22.1.2", "part03/sect_C.7.6.22.html")
PS33_FRAME_EXTRACTION = _cite("PS3.3", "C.12.9 Table C.12-9", "part03/sect_C.12.9.html")
PS316_UNITS = _cite("PS3.16", "CID 82", "part16/sect_CID_82.html")
PS316_LOCALIZATION = _cite("PS3.16", "TID 8004", "part16/sect_TID_8004.html")
PS33_PADDING = _cite("PS3.3", "C.7.5.1.1.2", "part03/sect_C.7.5.html#sect_C.7.5.1.1.2")
PS33_ASPECT = _cite("PS3.3", "C.7.6.3.1.7", "part03/sect_C.7.6.3.html#sect_C.7.6.3.1.7")
PS33_ICON = _cite("PS3.3", "C.7.6.1.1.6", "part03/sect_C.7.6.html#sect_C.7.6.1.1.6")
PS33_PALETTE = _cite("PS3.3", "C.7.6.3.1.5 and C.7.6.3.1.6", "part03/sect_C.7.6.3.html#sect_C.7.6.3.1.5")
PS33_SEGMENTED = _cite("PS3.3", "C.7.9.2", "part03/sect_C.7.9.2.html")

WSI_CLASS = "1.2.840.10008.5.1.4.1.1.77.1.6"
VL_PHOTOGRAPHIC_CLASS = "1.2.840.10008.5.1.4.1.1.77.1.4"
HL7_CDA_SR_CLASS = "1.2.840.10008.5.1.4.1.1.88.11"
REFERENCED = "1.2.826.0.1.3680043.10.999.940"
OTHER_STUDY = "1.2.826.0.1.3680043.10.999.941"
OTHER_SERIES = "1.2.826.0.1.3680043.10.999.942"
NOW = "20260101120000"

# Data Element Tags that Attribute Tag Values name.
BODY_PART_EXAMINED = 0x0018_0015
PATIENT_ID = 0x0010_0020
SPECIMEN_UID = 0x0040_0554
SPECIMEN_DESCRIPTION_SEQUENCE = 0x0040_0560
SOP_CLASS_UID = 0x0008_0016
SOP_INSTANCE_UID = 0x0008_0018
TRANSFER_SYNTAX_UID = 0x0002_0010
DATE_OF_LAST_CALIBRATION = 0x0018_1200
PRIVATE_ELEMENT = 0x0019_1010
PRIVATE_ELEMENT_NUMBER = 0x0019_0010

WSI_AND_PROFILE = ("wsi-image", "core-image-profile")
# The 612-byte RGB Input Device ICC Profile of the color controls' Optical Path.
INPUT_PROFILE = (
    "00000264000000000430000073636e725247422058595a2007e8000100010000000000006163737000000000"
    "0000000000000000000000000000000000000000000000000000f6c3000100000000d3230000000000000000"
    "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000b"
    "7258595a00000108000000146758595a0000011c000000146258595a00000130000000146368616400000144"
    "0000002c72545243000001700000002067545243000001900000002062545243000001b00000002077747074"
    "000001d00000001463696370000001e40000000c64657363000001f00000003e637072740000022e00000036"
    "58595a200000000000006f93000038ed0000039158595a2000000000000062a40000b78f000018df58595a20"
    "00000000000024a000000f830000b6cf73663332000000000000e52500004433ffffd6aeffff3ff30001b6a8"
    "00000965000009f5ffffee7700010794706172610000000000030000000266660000f2a700000d59000013d0"
    "00000a5b706172610000000000030000000266660000f2a700000d59000013d000000a5b7061726100000000"
    "00030000000266660000f2a700000d59000013d000000a5b58595a20000000000000f33d0001000000011698"
    "6369637000000000010d01006d6c756300000000000000010000000c656e5553000000220000001c00730052"
    "00470042002000490045004300360031003900360036002d0032002e00316d6c756300000000000000010000"
    "000c656e55530000001a0000001c005000750062006c0069006300200044006f006d00610069006e"
)
SPECIMEN = ["SpecimenDescriptionSequence", 0]


def _case(
    case_id: str,
    control: str,
    mutation: str,
    parameters: dict,
    expected: tuple[str, ...],
    requirements: tuple[str, ...],
    changed: str,
    citation: dict,
    rationale: str,
) -> dict:
    return _spec(case_id, control, mutation, parameters, expected, changed, citation, rationale,
                 requirement_ids=list(requirements))


def _iod_edits(case_id, control, operations, requirements, changed, citation, rationale, expected):
    """An ``iod_edits`` case; ``_relation``, ``_wsi_image`` and ``_pixel`` default ``expected``."""
    return _case(case_id, control, "iod_edits", _edits(*operations), expected, requirements,
                 changed, citation, rationale)


_relation = partial(_iod_edits, expected=("attribute-relations",))


def _original(modified: dict, nonconforming: dict | None = None) -> dict:
    """Insert an Original Attributes Sequence Item recording ``modified`` as the prior
    Values and, when given, one Nonconforming Modified Attributes Item."""
    item = {
        "SourceOfPreviousValues": "",
        "AttributeModificationDateTime": NOW,
        "ModifyingSystem": "wsi-dicom-bench",
        "ReasonForTheAttributeModification": "CORRECT",
        "ModifiedAttributesSequence": [modified],
    }
    if nonconforming is not None:
        item["NonconformingModifiedAttributesSequence"] = [
            {**nonconforming, "NonconformingDataElementValue": "4142"}
        ]
    return _op("insert", ["OriginalAttributesSequence"], [item])


def _listed(study: str | None = None, sop_class: str = WSI_CLASS) -> dict:
    """List the referenced Instance in the Common Instance Reference Module."""
    instance = {"ReferencedSOPClassUID": sop_class, "ReferencedSOPInstanceUID": REFERENCED}
    series = [{"SeriesInstanceUID": OTHER_SERIES, "ReferencedInstanceSequence": [instance]}]
    if study is None:
        return _op("insert", ["ReferencedSeriesSequence"], series)
    return _op("insert", ["StudiesContainingOtherReferencedInstancesSequence"], [{
        "StudyInstanceUID": study,
        "ReferencedSeriesSequence": series,
    }])


def _photo(sop_class: str, **reference) -> dict:
    """Insert a Referenced Patient Photo Item (PS3.3 Table 10-3b) in another Study."""
    return _op("insert", ["ReferencedPatientPhotoSequence"], [{
        "TypeOfInstances": "DICOM",
        "StudyInstanceUID": OTHER_STUDY,
        "SeriesInstanceUID": OTHER_SERIES,
        "ReferencedSOPSequence": [
            {"ReferencedSOPClassUID": sop_class, "ReferencedSOPInstanceUID": REFERENCED, **reference}
        ],
        "DICOMRetrievalSequence": [{"RetrieveAETitle": "ARCHIVE"}],
    }])


def _person(meaning: str = "Person 1") -> dict:
    return {
        "PersonIdentificationCodeSequence": [_code("99LOCAL", "P1", meaning)],
        "InstitutionName": "Example Hospital",
    }


def _measured(**values) -> dict:
    """Replace the Acquisition Context with one NUMERIC Content Item (PS3.3 Table 10-2)."""
    return _op("replace", ["AcquisitionContextSequence"], [{
        "ValueType": "NUMERIC",
        "ConceptNameCodeSequence": [_code("SCT", "246205007", "Quantity")],
        "NumericValue": "1", **values,
        "MeasurementUnitsCodeSequence": [_code("UCUM", "mm", "millimeter")],
    }])


def _preparation_step(datetime: str) -> dict:
    return {"SpecimenPreparationStepContentItemSequence": [
        {"ValueType": "TEXT",
         "ConceptNameCodeSequence": [_code("DCM", "121041", "Specimen Identifier")],
         "TextValue": "{self.ContainerIdentifier}"},
        {"ValueType": "CODE",
         "ConceptNameCodeSequence": [_code("DCM", "111701", "Processing type")],
         "ConceptCodeSequence": [_code("SCT", "9265001", "Specimen processing")]},
        {"ValueType": "DATETIME",
         "ConceptNameCodeSequence": [_code("DCM", "111702", "DateTime of processing")],
         "DateTime": datetime},
    ]}


def _mac(signed: list[int]) -> dict:
    return _op("insert", ["MACParametersSequence"], [{
        "MACIDNumber": 1,
        "MACCalculationTransferSyntaxUID": "1.2.840.10008.1.2.1",
        "MACAlgorithm": "SHA256",
        "DataElementsSigned": signed,
    }])


RELATION_CASES = (
    _relation("REQ-REL-001", "CP02-JPEG-16F", [
        _original({"BodyPartExamined": ""}, {
            "SelectorAttribute": PRIVATE_ELEMENT,
            "SelectorAttributePrivateCreator": "ACME",
            "SelectorValueNumber": 1,
        })],
        ("Ps3_10_17_1_2_e5ece3",),
        "Record a nonconforming private Attribute whose Selector Attribute (0072,0026) is (0019,1010) instead of the (0019,0010) form.",
        PS33_SELECTOR, "PS3.3 10.17.1.2 encodes a private Selector Attribute with its element's block byte zeroed and names the block by the Private Creator."),
    _relation("REQ-REL-002", "CP02-JPEG-16F", [
        _original({"BodyPartExamined": ""}, {
            "SelectorAttribute": BODY_PART_EXAMINED, "SelectorValueNumber": 2,
        })],
        ("Ps3_10_20_SelectorValueNumber_350d86",),
        "Record nonconforming Body Part Examined (VM 1) with Selector Value Number (0072,0028) 2.",
        PS33_SELECTOR, "The selected Attribute has VM 1 in PS3.6, so Selector Value Number shall be 1."),
    _relation("REQ-REL-003", "CP02-JPEG-16F", [
        _original({"BodyPartExamined": ""}, {
            "SelectorAttribute": BODY_PART_EXAMINED, "SelectorValueNumber": 1,
            "SelectorSequencePointer": PATIENT_ID, "SelectorSequencePointerItems": "1",
        })],
        ("Ps3_10_20_SelectorSequencePointer_baa08d",),
        "Record a nonconforming Attribute whose Selector Sequence Pointer (0072,0052) names Patient ID (0010,0020), which is not a Sequence.",
        PS33_SELECTOR, "Each Selector Sequence Pointer Value names the Sequence at one nesting level."),
    _relation("REQ-REL-004", "CP02-JPEG-16F", [
        _original({"BodyPartExamined": ""}, {
            "SelectorAttribute": SPECIMEN_UID, "SelectorValueNumber": 1,
            "SelectorSequencePointer": SPECIMEN_DESCRIPTION_SEQUENCE,
            "SelectorSequencePointerItems": ["1", "1"],
        })],
        ("Ps3_10_20_SelectorSequencePointerItems_fcd3e1",),
        "Record a nested nonconforming Specimen UID with one Selector Sequence Pointer Value and two Selector Sequence Pointer Items (0074,1057) Values.",
        PS33_SELECTOR, "Selector Sequence Pointer Items has one Value per Selector Sequence Pointer Value."),
    _relation("REQ-REL-005", "CP02-JPEG-16F", [
        _original({"BodyPartExamined": ""}, {
            "SelectorAttribute": SPECIMEN_UID, "SelectorValueNumber": 1,
            "SelectorSequencePointer": SPECIMEN_DESCRIPTION_SEQUENCE,
            "SelectorSequencePointerItems": "1",
            "SelectorSequencePointerPrivateCreator": "ACME",
        })],
        ("Ps3_10_20_SelectorSequencePointerPrivateCreator_46d4e2",),
        "Give a public Selector Sequence Pointer Value the Private Creator ACME in Selector Sequence Pointer Private Creator (0072,0054).",
        PS33_SELECTOR, "The Private Creator Value of a public Sequence Pointer shall be empty. "
        "Its Type 1C condition is a private Selector Sequence Pointer, so iod-attribute-presence reports the same Attribute.",
        expected=("attribute-relations", "iod-attribute-presence")),
    _relation("REQ-REL-006", "CP02-JPEG-16F", [
        _original({"BodyPartExamined": ""}, {
            "SelectorAttribute": BODY_PART_EXAMINED, "SelectorValueNumber": 1,
            "SelectorSequencePointer": PRIVATE_ELEMENT_NUMBER,
            "SelectorSequencePointerItems": "1",
            "SelectorSequencePointerPrivateCreator": ["ACME", "ACME"],
        })],
        ("Ps3_10_20_SelectorSequencePointerPrivateCreator_379163",),
        "Give a one-Value private Selector Sequence Pointer two Selector Sequence Pointer Private Creator Values.",
        PS33_SELECTOR, "Selector Sequence Pointer Private Creator has one Value per Selector Sequence Pointer Value."),
    _relation("REQ-REL-007", "CP02-JPEG-16F", [
        _original({"BodyPartExamined": ""}, {"SelectorValueNumber": 1})],
        ("Ps3_C_12_1_1_9_2_52e512",),
        "Record a Nonconforming Modified Attributes Item without a Selector Attribute (0072,0026).",
        PS33_ORIGINAL, "The Item identifies no Attribute. Without a Selector Attribute the Selector Sequence Pointer is required, so iod-attribute-presence also reports it.",
        expected=("attribute-relations", "iod-attribute-presence")),
    _relation("REQ-REL-008", "CP02-JPEG-16F", [
        _original({"BodyPartExamined": "CHEST"}, {
            "SelectorAttribute": BODY_PART_EXAMINED, "SelectorValueNumber": 1,
        })],
        ("Ps3_C_12_1_1_9_1_09372b",),
        "Record nonconforming top-level Body Part Examined while the Modified Attributes Item holds it with the Value CHEST.",
        PS33_ORIGINAL, "A nonconforming top-level Attribute is held in the Modified Attributes Sequence with a zero length Value."),
    _relation("REQ-REL-009", "CP02-JPEG-16F", [
        _op("insert", ["AnatomicRegionSequence"], [{
            **_code("SCT", "818981001", "Abdomen"),
            "ContextIdentifier": "0004", "MappingResource": "DCMR",
            "ContextGroupVersion": "20260101000000",
        }])],
        ("Ps3_8_6_2191da",),
        "Insert an Anatomic Region Sequence Item with Context Identifier (0008,010F) 0004 for a DCMR Context Group.",
        PS33_DCMR, "A DCMR Context Identifier is the CID number in digits without leading zeros."),
    _relation("REQ-REL-010", "CP02-JPEG-16F", [
        _op("insert", ["SourceImageSequence"], [{
            "ReferencedSOPClassUID": WSI_CLASS, "ReferencedSOPInstanceUID": REFERENCED,
            "ReferencedFrameNumber": "0",
        }]),
        _listed()],
        ("Ps3_10_3_ReferencedFrameNumber_174e7c",),
        "Insert a Source Image Sequence Item with Referenced Frame Number (0008,1160) 0, listed in the Referenced Series Sequence.",
        PS33_FRAME_REFERENCE, "The first Frame is Frame number 1."),
    _relation("REQ-REL-011", "CP02-JPEG-16F", [
        _op("replace", ["AcquisitionContextSequence"], [{
            "ValueType": "IMAGE",
            "ConceptNameCodeSequence": [_code("DCM", "121112", "Source of Measurement")],
            "ReferencedSOPSequence": [{
                "ReferencedSOPClassUID": WSI_CLASS, "ReferencedSOPInstanceUID": REFERENCED,
                "ReferencedFrameNumber": "0",
            }],
        }]),
        _listed()],
        ("Ps3_10_2_ReferencedFrameNumber_587608",),
        "Replace the Acquisition Context Sequence with an IMAGE Content Item referencing Frame number 0, listed in the Referenced Series Sequence.",
        PS33_FRAME_REFERENCE, "The first Frame is Frame number 1."),
    _relation("REQ-REL-012", "CP02-JPEG-16F", [
        _photo(VL_PHOTOGRAPHIC_CLASS, ReferencedFrameNumber="0"),
        _listed(OTHER_STUDY, VL_PHOTOGRAPHIC_CLASS)],
        ("Ps3_10_3b_ReferencedFrameNumber_f9c771",),
        "Reference Frame number 0 of a VL Photographic Image in the Referenced Patient Photo Sequence, listed in the Studies Containing Other Referenced Instances Sequence.",
        PS33_FRAME_REFERENCE, "The first Frame is Frame number 1."),
    *(
        _relation(case_id, "CP02-JPEG-16F", [
            _op("insert", [names], ["A^B", "C^D", "E^F"]),
            _op("insert", [sequence], [_person(), _person()]),
        ],
            (requirement,),
            f"Insert three {names} Values and two {sequence} Items.",
            PS33_IDENTIFICATION, f"With more than one Item, {table} requires one Item per name Value, in the same order.")
        for case_id, names, sequence, requirement, table in (
            ("REQ-REL-013", "PerformingPhysicianName", "PerformingPhysicianIdentificationSequence",
             "Ps3_C_7_5a_PerformingPhysicianIdentificationSequence_0e6615", "Table C.7-5a"),
            ("REQ-REL-014", "OperatorsName", "OperatorIdentificationSequence",
             "Ps3_C_7_5a_OperatorIdentificationSequence_830798", "Table C.7-5a"),
            ("REQ-REL-015", "PhysiciansOfRecord", "PhysiciansOfRecordIdentificationSequence",
             "Ps3_C_7_3_PhysiciansOfRecordIdentificationSequence_19326f", "Table C.7-3"),
            ("REQ-REL-016", "NameOfPhysiciansReadingStudy", "PhysiciansReadingStudyIdentificationSequence",
             "Ps3_C_7_3_PhysiciansReadingStudyIdentificationSequence_d559d9", "Table C.7-3"),
            ("REQ-REL-017", "ConsultingPhysicianName", "ConsultingPhysicianIdentificationSequence",
             "Ps3_C_7_3_ConsultingPhysicianIdentificationSequence_5a5065", "Table C.7-3"),
        )
    ),
    _relation("REQ-REL-018", "CP02-JPEG-16F", [
        _op("insert", ["ContributingEquipmentSequence"], [{
            "PurposeOfReferenceCodeSequence": [_code("DCM", "109103", "Modifying Equipment")],
            "Manufacturer": "wsi-dicom-bench",
            "OperatorsName": ["A^B", "C^D"],
            "OperatorIdentificationSequence": [_person()],
        }])],
        ("Ps3_C_12_1_OperatorIdentificationSequence_a0dcbe",),
        "Insert a Contributing Equipment Item with two Operators' Name Values and one Operator Identification Sequence Item.",
        PS33_IDENTIFICATION, "Table C.12-1 requires one Operator Identification Item per Operators' Name Value, a single Item included."),
    _relation("REQ-REL-019", "CP02-JPEG-16F", [
        _op("insert", ["DateOfLastCalibration"], ["20240101", "20250101"]),
        _op("insert", ["TimeOfLastCalibration"], ["120000"]),
    ],
        ("Ps3_C_7_5_1_1_1_6f6b31",),
        "Insert two Date of Last Calibration Values and one Time of Last Calibration Value.",
        PS33_CALIBRATION, "When both are present they are paired Value by Value."),
    _relation("REQ-REL-020", "CP02-JPEG-16F", [
        _op("insert", ["DateOfLastCalibration"], ["20250101", "20240101"]),
    ],
        ("Ps3_C_7_5_1_1_1_697183",),
        "Insert Date of Last Calibration Values 20250101 then 20240101.",
        PS33_CALIBRATION, "Calibration dates are ordered from the oldest to the most recent."),
    _relation("REQ-REL-021", "CP02-JPEG-16F", [
        _op("insert", ["GroupOfPatientsIdentificationSequence"], [
            {"PatientID": "M1", "SubjectRelativePositionInImage": [0, 1, 1]}
        ])],
        ("Ps3_C_7_1_4_1_1_1_a03c8a",),
        "Insert a Group of Patients Item whose Subject Relative Position in Image (0010,0028) has the Value 0.",
        PS33_GROUP, "Subject positions are ordinals from 1."),
    _relation("REQ-REL-022", "CP02-JPEG-16F", [
        _op("insert", ["OpticalPathSequence", 0, "ColorSpace"], "ADOBERGB"),
    ],
        ("Ps3_C_8_12_5_1_ColorSpace_36ee23",),
        "Insert Color Space (0028,2002) ADOBERGB into the Optical Path Item, whose ICC Profile has sRGB primaries.",
        PS33_OPTICAL_PATHS, "Color Space names the color space the ICC Profile defines."),
    _relation("REQ-REL-023", "CP02-JPEG-16F", [
        _op("replace", [*SPECIMEN, "SpecimenPreparationSequence"],
            [_preparation_step("20250102"), _preparation_step("20250101")]),
    ],
        ("Ps3_C_7_6_22_1_3_372144",),
        "Replace the Specimen Preparation Sequence with two dated steps, 20250102 before 20250101.",
        PS33_PREPARATION, "Specimen Preparation Sequence Items are in ascending chronological order."),
    _relation("REQ-REL-024", "CP02-JPEG-16F", [_mac([SOP_INSTANCE_UID, SOP_CLASS_UID])],
        ("Ps3_C_12_1_1_3_1_1_13525c",),
        "Insert a MAC Parameters Item whose Data Elements Signed lists SOP Instance UID before SOP Class UID.",
        PS33_SIGNED, "Data Elements Signed lists Tags in the order they appear in the Data Set."),
    _relation("REQ-REL-025", "CP02-JPEG-16F", [_mac([TRANSFER_SYNTAX_UID])],
        ("Ps3_C_12_1_1_3_1_1_eb25f8",),
        "Insert a MAC Parameters Item whose Data Elements Signed lists Transfer Syntax UID (0002,0010).",
        PS33_SIGNED, "Tags with a group below 0008 are not signed; the Tag is also not at the Item's level, which the same rule reports."),
    _relation("REQ-REL-026", "CP02-JPEG-16F", [_mac([DATE_OF_LAST_CALIBRATION])],
        ("Ps3_C_12_1_1_3_1_1_5b9eec",),
        "Insert a MAC Parameters Item whose Data Elements Signed lists Date of Last Calibration, which the Data Set does not hold.",
        PS33_SIGNED, "Each signed Tag is that of a Data Element at the level of the MAC Parameters Sequence."),
    _relation("REQ-REL-027", "CP02-JPEG-16F", [_measured(NumericValue=["1", "2"])],
        ("Ps3_10_2_NumericValue_728e74",),
        "Replace the Acquisition Context Sequence with a NUMERIC Content Item whose Numeric Value has two Values.",
        PS33_MEASURED_VALUE, "A Measured Value Item holds a single Value."),
    _relation("REQ-REL-028", "CP02-JPEG-16F", [_measured(FloatingPointValue=[1.0, 2.0])],
        ("Ps3_10_2_FloatingPointValue_796684",),
        "Give the NUMERIC Content Item one Numeric Value and two Floating Point Values.",
        PS33_MEASURED_VALUE, "Floating Point Value has the same number of Values as Numeric Value."),
    _relation("REQ-REL-029", "CP02-JPEG-16F",
        [_measured(RationalNumeratorValue=[1, 2], RationalDenominatorValue=[1])],
        ("Ps3_10_2_RationalNumeratorValue_f9fd94",),
        "Give the NUMERIC Content Item one Numeric Value and two Rational Numerator Values.",
        PS33_MEASURED_VALUE, "Rational Numerator Value has the same number of Values as Numeric Value."),
    _relation("REQ-REL-030", "CP02-JPEG-16F",
        [_measured(RationalNumeratorValue=[1], RationalDenominatorValue=[1, 2])],
        ("Ps3_10_2_RationalDenominatorValue_cc4bf1",),
        "Give the NUMERIC Content Item one Numeric Value and two Rational Denominator Values.",
        PS33_MEASURED_VALUE, "Rational Denominator Value has the same number of Values as Numeric Value."),
    _relation("REQ-REL-031", "CP02-JPEG-16F", [
        _op("insert", ["PerformingPhysicianIdentificationSequence"], [_person("A^B^C^D^E^F")]),
    ],
        ("Ps3_10_1_PersonIdentificationCodeSequence_7d0584",),
        "Insert a Person Identification Code whose Code Meaning A^B^C^D^E^F has six components.",
        PS33_PERSON, "A caret-delimited Code Meaning is a person name in PN form, which has at most five components."),
    _relation("REQ-REL-032", "CP02-JPEG-16F", [_op("insert", ["PatientOrientation"], ["A", "FX"])],
        ("Ps3_C_7_6_1_1_1_b78dcd",),
        "Insert Patient Orientation A\\FX.",
        PS33_ORIENTATION, "Biped orientation Values are built from A, P, R, L, H and F."),
    _relation("REQ-REL-033", "CP02-JPEG-16F", [_op("insert", ["PatientOrientation"], ["A", "X"])],
        ("Ps3_C_7_6_1_1_1_1e27ca",),
        "Insert Patient Orientation A\\X.",
        PS33_ORIENTATION, "Each non-empty Value holds at least one orientation abbreviation."),
    _relation("REQ-REL-034", "CP02-JPEG-16F", [
        _op("insert", ["AnatomicalOrientationType"], "QUADRUPED"),
        _op("insert", ["PatientOrientation"], ["LE", "LEX"]),
    ],
        ("Ps3_C_7_6_1_1_1_d49ff3",),
        "Insert Anatomical Orientation Type QUADRUPED and Patient Orientation LE\\LEX.",
        PS33_ORIENTATION, "Quadruped orientation Values are built from the C.7.6.1.1.1 quadruped abbreviations."),
    _relation("REQ-REL-035", "CP02-JPEG-16F", [
        _op("insert", ["AnatomicalOrientationType"], "QUADRUPED"),
        _op("insert", ["PatientOrientation"], ["LE", "CRDIPAL"]),
    ],
        ("Ps3_C_7_6_1_1_1_2a7108",),
        "Insert Anatomical Orientation Type QUADRUPED and Patient Orientation LE\\CRDIPAL (four abbreviations).",
        PS33_ORIENTATION, "A Value holds at most three abbreviations."),
    _relation("REQ-REL-036", "CP02-JPEG-16F", [
        _op("insert", ["ImageLaterality"], "R"),
        _op("insert", ["Laterality"], "L"),
    ],
        ("Ps3_C_7_9_ImageLaterality_0d7859",),
        "Insert Image Laterality R and Laterality L.",
        PS33_LATERALITY, "Image Laterality is consistent with Laterality. Laterality is Type 2C, "
        "required only without Image Laterality, so iod-attribute-presence reports the same pair.",
        expected=("attribute-relations", "iod-attribute-presence")),
    _relation("REQ-REL-037", "CP02-JPEG-16F", [
        _op("insert", ["ImageLaterality"], "L"),
        _op("insert", ["PrimaryAnatomicStructureSequence"], [{
            **_code("SCT", "76752008", "Breast"),
            "PrimaryAnatomicStructureModifierSequence": [_code("SCT", "24028007", "Right")],
        }]),
    ],
        ("Ps3_C_7_9_ImageLaterality_0d7859",),
        "Insert Image Laterality L and a Primary Anatomic Structure with the laterality modifier Right.",
        PS33_LATERALITY, "Image Laterality is consistent with the laterality modifiers of the anatomy."),
    _relation("REQ-REL-038", "CP02-JPEG-16F", [
        _photo(WSI_CLASS),
        _listed(OTHER_STUDY)],
        ("Ps3_C_2_2_1_1_70c5e1",),
        "Reference a VL Whole Slide Microscopy Image as the patient photo, listed in the Studies Containing Other Referenced Instances Sequence.",
        PS33_PATIENT_PHOTO, "A patient photo reference names a VL Photographic or Secondary Capture Image."),
    _relation("REQ-REL-039", "CP02-JPEG-16F", [
        _op("insert", ["HL7StructuredDocumentReferenceSequence"], [{
            "ReferencedSOPClassUID": HL7_CDA_SR_CLASS, "ReferencedSOPInstanceUID": REFERENCED,
            "HL7InstanceIdentifier": "1.2.826.0.1.3680043.10.999.943^1",
        }]),
        _listed(OTHER_STUDY, HL7_CDA_SR_CLASS)],
        ("Ps3_C_12_1_1_6_b6eb69",),
        "Insert an HL7 Structured Document reference whose Referenced SOP Class UID is a DICOM Storage SOP Class.",
        PS33_HL7_DOCUMENT, "The Referenced SOP Class UID of an HL7 Structured Document is the HL7 Object Identifier of its Hierarchical Message Description."),
    _relation("REQ-REL-040", "CP02-JPEG-16F", [
        _op("insert", ["SourceInstanceSequence"], [
            {"ReferencedSOPClassUID": WSI_CLASS, "ReferencedSOPInstanceUID": REFERENCED}
        ]),
        _listed()],
        ("Ps3_C_12_4_1_2_a52a75",),
        "Insert a Source Instance Sequence Item naming a VL Whole Slide Microscopy Image, listed in the Referenced Series Sequence.",
        PS33_SOURCE_INSTANCE, "Images are referenced by Source Image Sequence, not Source Instance Sequence."),
)


_wsi_image = partial(_iod_edits, expected=("wsi-image",))


WSI_IMAGE_CASES = (
    _wsi_image("REQ-WSI-001", "CP02-JPEG-16F",
        [_op("set", ["ImageType"], ["ORIGINAL", "PRIMARY", "VOLUME"])],
        ("Ps3_C_8_12_4_1_1_75b5c5",),
        "Set Image Type to ORIGINAL\\PRIMARY\\VOLUME.",
        PS33_WSI_ATTRIBUTES, "Image Type has exactly four Values in VL WSI.", expected=WSI_AND_PROFILE),
    _wsi_image("REQ-WSI-002", "CP02-JPEG-16F",
        [_op("set", ["ImageType"], ["ORIGINAL", "PRIMARY", "VOLUME", ""])],
        ("Ps3_C_8_12_4_1_1_b18b99",),
        "Set Image Type Value 4 (Derived Pixel) empty.",
        PS33_WSI_ATTRIBUTES, "Derived Pixel is a non-empty Value; its Defined Terms are extensible.",
        expected=WSI_AND_PROFILE),
    _wsi_image("REQ-WSI-003", "CP02-JPEG-16F",
        [_op("set", ["ImageType"], ["ORIGINAL", "PRIMARY", "", "NONE"])],
        ("Ps3_C_8_12_4_1_1_f4d4e2", "Ps3_C_7_6_1_1_2_ef6680"),
        "Set Image Type Value 3 (Image Flavor) empty.",
        PS33_IMAGE_TYPE, "Value 3 is present and non-empty. The Multi-Resolution Pyramid Module "
        "is present only for VOLUME or THUMBNAIL, so iod-modules reports it.",
        expected=(*WSI_AND_PROFILE, "iod-modules")),
    _wsi_image("REQ-WSI-004", "CP02-JPEG-16F",
        [_op("set", [*SHARED, "WholeSlideMicroscopyImageFrameTypeSequence", 0, "FrameType"],
             ["ORIGINAL", "PRIMARY", "VOLUME", "NONE", "EXTRA"])],
        ("Ps3_C_8_12_4_1_1_75b5c5",),
        "Give the shared Frame Type (0008,9007) a fifth Value.",
        PS33_WSI_ATTRIBUTES, "Frame Type has exactly four Values in VL WSI.", expected=WSI_AND_PROFILE),
    _wsi_image("REQ-WSI-005", "CP02-JPEG-16F", [_op("insert", ["(0048,0304)"], "SOME", vr="CS")],
        ("Ps3_C_8_12_14_1_TilesOverlap_0699b8",),
        "Insert Tiles Overlap (0048,0304) SOME in the TILED_FULL control.",
        PS33_TILES, "With Dimension Organization Type TILED_FULL, Tiles Overlap is NONE when present."),
    _wsi_image("REQ-WSI-006", "CP02-JPEG-16F", [_op("set", ["ImagedVolumeDepth"], 0.0)],
        ("Ps3_C_8_12_4_1_2_3e7c7c",),
        "Set Imaged Volume Depth (0048,0003) to 0.",
        PS33_WSI_ATTRIBUTES, "Imaged Volume Depth is the nominal thickness of the imaged volume and is not zero.",
        expected=WSI_AND_PROFILE),
    _wsi_image("REQ-WSI-007", "CP02-JPEG-16F", [_op("set", ["PositionReferenceIndicator"], "STAGE")],
        ("Ps3_C_7_4_1_1_2_71f60f",),
        "Set Position Reference Indicator (0020,1040) to STAGE.",
        PS33_REFERENCE_INDICATOR, "A slide-related Frame of Reference has Position Reference Indicator SLIDE_CORNER."),
    _wsi_image("REQ-WSI-008", "CP02-JPEG-16F",
        [_op("set", [*SHARED, "OpticalPathIdentificationSequence", 0, "OpticalPathIdentifier"], "9")],
        ("Ps3_C_8_12_5_1_1_d6f6c9",),
        "Set the shared Optical Path Identifier to 9, which no Optical Path Sequence Item has.",
        PS33_OPTICAL_PATHS, "Each Frame's Optical Path Identification resolves to an Optical Path Sequence Item.",
        expected=("wsi-image", "optical-path-structure")),
    _wsi_image("REQ-WSI-009", "CP02-JPEG-16F", [
        _op("insert", [*SHARED, "DerivationImageSequence"], [{
            "DerivationCodeSequence": [_code("DCM", "113040", "Lossy Compression")],
            "SourceImageSequence": [{
                "ReferencedSOPClassUID": WSI_CLASS, "ReferencedSOPInstanceUID": REFERENCED,
                "PurposeOfReferenceCodeSequence": [_code("DCM", "121320", "Uncompressed predecessor")],
            }],
        }]),
        _listed()],
        ("Ps3_C_7_6_1_1_5_808c0a",),
        "Insert a shared Derivation Image Item with Derivation Code Lossy Compression while Image Type Value 1 stays ORIGINAL.",
        PS33_DERIVATION, "A compressed version of another image is DERIVED."),
    _wsi_image("REQ-WSI-010", "CP02-JPEG-16F", [
        _op("insert", [*SHARED, "DerivationImageSequence"], [{
            "DerivationCodeSequence": [_code("DCM", "113090", "Image stitching")],
            "SourceImageSequence": [{
                "ReferencedSOPClassUID": WSI_CLASS,
                "ReferencedSOPInstanceUID": "{self.SOPInstanceUID}",
                "PurposeOfReferenceCodeSequence": [
                    _code("DCM", "121322", "Source image for image processing operation")],
            }],
        }]),
        _op("set", ["ImageType"], ["DERIVED", "PRIMARY", "VOLUME", "NONE"]),
        _op("set", [*SHARED, "WholeSlideMicroscopyImageFrameTypeSequence", 0, "FrameType"],
            ["DERIVED", "PRIMARY", "VOLUME", "NONE"]),
        _op("insert", ["ReferencedSeriesSequence"], [{
            "SeriesInstanceUID": "{self.SeriesInstanceUID}",
            "ReferencedInstanceSequence": [{
                "ReferencedSOPClassUID": WSI_CLASS,
                "ReferencedSOPInstanceUID": "{self.SOPInstanceUID}",
            }],
        }]),
    ],
        ("Ps3_C_7_6_1_1_2_c26085",),
        "Make the image and its Frames DERIVED with a Derivation Image Item whose source is its own SOP Instance UID, listed in the Referenced Series Sequence.",
        PS33_DERIVATION, "A derived image's sources are other SOP Instances."),
    _wsi_image("REQ-WSI-011", "CP02-JPEG-16F",
        [_op("set", [*SHARED, "PixelMeasuresSequence", 0, "PixelSpacing"], ["0", "0.0005"])],
        ("Ps3_10_7_1_3_758737",),
        "Set the shared Pixel Spacing Value 1 to 0.",
        PS33_SPACING, "Pixel spacing is positive and non-zero when the Total Pixel Matrix has more "
        "than one row and column, whatever the Frame size; tile-geometry also requires it.",
        expected=("wsi-image", "tile-geometry")),
    _wsi_image("REQ-WSI-012", "CP02-JPEG-16F",
        [_op("insert", [*SHARED, "PixelMeasuresSequence", 0, "SpacingBetweenSlices"], "-1")],
        ("Ps3_C_7_6_16_2_SpacingBetweenSlices_7cbf0e",),
        "Insert Spacing Between Slices (0018,0088) -1 into the shared Pixel Measures Item.",
        PS33_SPACING, "Spacing Between Slices is not negative."),
    _wsi_image("REQ-WSI-013", "CP11-MONO-EVRLE-4F",
        [_op("set", ["PerFrameFunctionalGroupsSequence", 1, "PlanePositionSlideSequence", 0,
                     "ColumnPositionInTotalImagePixelMatrix"], 4)],
        ("Ps3_A_32_8_4_1_2_2c5e3d", "Ps3_A_32_8_4_1_2_922f97"),
        "Move Frame 2's Column Position in Total Image Pixel Matrix from 3 to 4, off the 2-column tiling.",
        PS33_TILING, "Frames occupy a regular tiling: column positions are a multiple of Columns plus a constant. The Dimension Index Values then disagree with the positions, which dimension-order reports, and a TILED_FULL Frame leaves its implicit position, which tile-geometry reports.",
        expected=("wsi-image", "dimension-order", "tile-geometry")),
)


def _pair(case_id, control, first, second, expected, requirements, changed, citation, rationale):
    parameters = {key: value for key, value in (("first", first), ("second", second)) if value}
    return _case(case_id, control, "iod_edit_pair", parameters, expected, requirements,
                 changed, citation, rationale)


def _group(positions: list[int]) -> dict:
    return _op("insert", ["GroupOfPatientsIdentificationSequence"],
               [{"PatientID": "M1", "SubjectRelativePositionInImage": positions}])


def _extraction(source: str) -> dict:
    return _op("insert", ["FrameExtractionSequence"],
               [{"MultiFrameSourceSOPInstanceUID": source, "SimpleFrameList": [1]}])


SERIES_SET_CASES = (
    _pair("REQ-SET-001", "CP02-JPEG-16F", None,
          [_op("set", ["FrameOfReferenceUID"], "1.2.826.0.1.3680043.10.999.944")],
          ("series-set", "clinical-identity-set"), ("Ps3_C_7_4_1_1_1_ea9bd3", "Ps3_C_7_4_1_1_1_ca125c"),
          "Give the second Instance of the Series another Frame of Reference UID.",
          PS33_FRAME_OF_REFERENCE, "A Series has a single Frame of Reference UID."),
    _pair("REQ-SET-002", "CP02-JPEG-16F", None,
          [_op("set", ["ContainerIdentifier"], "OTHER-SLIDE")],
          ("series-set", "clinical-identity-set"), ("Ps3_C_7_4_1_c35eb2", "Ps3_C_7_4_1_1_1_eaeaff"),
          "Give the second Instance, sharing the Frame of Reference UID, another Container Identifier.",
          PS33_FRAME_OF_REFERENCE, "Images sharing a slide-related Frame of Reference are of one slide."),
    _pair("REQ-SET-003", "CP02-JPEG-16F", None,
          [_op("set", ["InstanceNumber"], "{first.InstanceNumber}")],
          ("series-set",), ("Ps3_C_7_6_16_1_InstanceNumber_9d6547",),
          "Give the second Instance the first Instance's Instance Number.",
          PS33_INSTANCE_NUMBER, "Instance Numbers are shared only by the members of one Concatenation."),
    _case("REQ-SET-004", "CP02-JPEG-16F", "iod_edits", _edits(
              _op("set", ["PyramidUID"], "{self.FrameOfReferenceUID}")),
          ("series-set",), ("Ps5_9_ad5517", "Ps5_9_5a69d2"),
          "Set Pyramid UID to the Frame of Reference UID.",
          PS35_UID_ROLES, "A UID identifies one entity; the same UID in two identifying roles fails within the set."),
    _pair("REQ-SET-005", "CP02-JPEG-16F", None,
          [_op("set", [*SPECIMEN, "SpecimenUID"], "1.2.826.0.1.3680043.10.999.945")],
          ("series-set",), ("Ps3_C_7_6_22_1_2_19f6e2",),
          "Give the second Instance's specimen, with the same Specimen Identifier and issuer, another Specimen UID.",
          PS33_SPECIMEN_IDENTIFIER, "One Specimen Identifier and issuer name one specimen within a Study."),
    _pair("REQ-SET-006", "CP02-JPEG-16F", [_group([1, 1, 1])], [_group([2, 1, 1])],
          ("series-set",), ("Ps3_C_7_1_4_1_1_1_093320",),
          "Record group member M1 at position 1 in the first Instance and position 2 in the second.",
          PS33_GROUP, "One group, with the same members, has one arrangement in the image."),
    _pair("REQ-SET-007", "CP02-JPEG-16F",
          [_extraction("1.2.826.0.1.3680043.10.999.946")],
          [_extraction("{first.SOPInstanceUID}")],
          ("series-set",), ("Ps3_C_12_9_FrameExtractionSequence_74490f",),
          "Extract the second Instance from the first, which was itself extracted, without carrying the first's Frame Extraction Item.",
          PS33_FRAME_EXTRACTION, "An extraction from an extracted Instance holds all of the parent's Items and one new Item."),
)


VALUE_SET_CASES = (
    _case("REQ-VS-001", "CP11-MONO-EVRLE-4F", "iod_edits", _edits(
              _op("insert", [*SHARED, "RealWorldValueMappingSequence"], [{
                  "LUTExplanation": "Optical density", "LUTLabel": "OD",
                  "RealWorldValueFirstValueMapped": {"vr": "US", "value": 0},
                  "RealWorldValueLastValueMapped": {"vr": "US", "value": 255},
                  "RealWorldValueIntercept": 0.0, "RealWorldValueSlope": 0.01,
                  "MeasurementUnitsCodeSequence": [_code("99LOCAL", "mm", "millimeter")],
              }])),
          ("iod-value-sets",), (),
          "Insert a shared Real World Value Mapping Item whose Measurement Units Code is (mm, 99LOCAL) in the MONOCHROME2 control.",
          PS316_UNITS, "The Real World Value Mapping Functional Group binds Measurement Units to CID 82, a Defined, non-extensible group comprising UCUM."),
    _case("REQ-VS-002", "CP02-JPEG-16F", "iod_edits", _edits(
              _op("insert", [*SPECIMEN, "SpecimenLocalizationContentItemSequence"], [
                  {"ValueType": "TEXT",
                   "ConceptNameCodeSequence": [_code("DCM", "111718", "Location of Specimen")],
                   "TextValue": "upper left"},
              ] * 2)),
          ("iod-value-sets",), (),
          "Insert a Specimen Localization Content Item Sequence with two TEXT Location of Specimen Items.",
          PS316_LOCALIZATION, "DTID 8004 Row 2 occurs at most once."),
    _case("REQ-VS-003", "CP02-JPEG-16F", "iod_edits", _edits(
              _op("insert", [*SPECIMEN, "SpecimenLocalizationContentItemSequence"], [
                  {"ValueType": "NUMERIC",
                   "ConceptNameCodeSequence": [_code("DCM", "111719", "Location of Specimen X offset")],
                   "NumericValue": "1.5",
                   "MeasurementUnitsCodeSequence": [_code("UCUM", "mm", "millimeter")]},
                  {"ValueType": "TEXT",
                   "ConceptNameCodeSequence": [_code("DCM", "111718", "Location of Specimen")],
                   "TextValue": "upper left"},
              ])),
          ("iod-value-sets",), (),
          "Insert a Specimen Localization Content Item Sequence with the X offset Item before the Location of Specimen Item.",
          PS316_LOCALIZATION, "DTID 8004 is ordered; its Items follow the Template row order."),
)


def _icon(**changes) -> dict:
    icon = {
        "SamplesPerPixel": 1, "PhotometricInterpretation": "MONOCHROME2",
        "Rows": 2, "Columns": 3, "BitsAllocated": 8, "BitsStored": 8, "HighBit": 7,
        "PixelRepresentation": 0, "PixelData": {"vr": "OB", "value": "00" * 6},
    }
    icon.update(changes)
    return _op("insert", ["IconImageSequence"], [icon])


def _descriptors(first: int, bits: int) -> dict:
    return {
        f"{color}PaletteColorLookupTableDescriptor": {"vr": "US", "value": [first, 0, bits]}
        for color in ("Red", "Green", "Blue")
    }


def _palette_data(hex_entries: str, segmented: bool = False) -> dict:
    prefix = "Segmented" if segmented else ""
    return {
        f"{prefix}{color}PaletteColorLookupTableData": {"vr": "OW", "value": hex_entries}
        for color in ("Red", "Green", "Blue")
    }


def _words(values: list[int]) -> str:
    return "".join(value.to_bytes(2, "little").hex() for value in values)


def _optical_palette(table: dict, with_profile: bool = True) -> list[dict]:
    """Insert an Optical Path palette and, unless the control has one, the ICC Profile that
    a palette requires (PS3.3 Table C.8.12.5-1)."""
    palette = _op("insert", ["OpticalPathSequence", 0, "PaletteColorLookupTableSequence"], [table])
    if not with_profile:
        return [palette]
    return [palette, _op("insert", ["OpticalPathSequence", 0, "ICCProfile"], INPUT_PROFILE, vr="OB")]


_pixel = partial(_iod_edits, expected=("pixel-attributes",))


MONO = "CP11-MONO-EVRLE-4F"
PIXEL_ATTRIBUTE_CASES = (
    _pixel("REQ-PIX-001", MONO, [_op("insert", ["PixelPaddingValue"], 256, vr="US")],
        ("Ps3_C_7_5_1_1_2_8d8819",),
        "Insert Pixel Padding Value (0028,0120) 256 into the 8-bit MONOCHROME2 control.",
        PS33_PADDING, "Pixel Padding Value lies within the stored sample range 0 to 255."),
    _pixel("REQ-PIX-002", MONO, [
        _op("insert", ["PixelPaddingValue"], 10, vr="US"),
        _op("insert", ["PixelPaddingRangeLimit"], 0, vr="US"),
    ],
        ("Ps3_C_7_5_1_1_2_62cd75",),
        "Insert Pixel Padding Value 10 and Pixel Padding Range Limit 0 in the MONOCHROME2 control.",
        PS33_PADDING, "For MONOCHROME2, Pixel Padding Value is less than or equal to Pixel Padding Range Limit."),
    _pixel("REQ-PIX-003", MONO, [_op("insert", ["PixelAspectRatio"], ["0", "1"])],
        ("Ps3_C_7_6_3_1_7_fbe0d7",),
        "Insert Pixel Aspect Ratio (0028,0034) 0\\1.",
        PS33_ASPECT, "Both integer Values are greater than 0. With Pixel Spacing present Pixel Aspect "
        "Ratio is not required, so iod-attribute-presence reports the same Attribute.",
        expected=("pixel-attributes", "iod-attribute-presence")),
    *(
        _pixel(case_id, MONO, [_icon(**change)], requirements, changed, PS33_ICON, rationale)
        for case_id, change, requirements, changed, rationale in (
            ("REQ-PIX-004", {"PhotometricInterpretation": "RGB", "SamplesPerPixel": 3,
                             "PlanarConfiguration": 0,
                             "PixelData": {"vr": "OB", "value": "00" * 18}},
             ("Ps3_C_7_6_1_1_6_8478b8", "Ps3_C_7_6_1_1_6_b7c7c0", "Ps3_C_7_6_1_1_6_c2da50"),
             "Insert an RGB Icon Image with three samples per pixel.",
             "Icon Images are monochrome or palette color with a single sample per pixel."),
            ("REQ-PIX-006", {"BitsAllocated": 16, "BitsStored": 16, "HighBit": 15,
                             "PixelData": {"vr": "OW", "value": "00" * 12}},
             ("Ps3_C_7_6_1_1_6_c5156c",),
             "Insert a 16-bit Icon Image.",
             "Icon Image samples have 1 or 8 bits."),
            ("REQ-PIX-007", {"HighBit": 6},
             ("Ps3_C_7_6_1_1_6_cc071c", "Ps3_C_7_11c_HighBit_41bada"),
             "Insert an 8-bit Icon Image with High Bit 6.",
             "High Bit is one less than Bits Stored."),
            ("REQ-PIX-008", {"PixelRepresentation": 1},
             ("Ps3_C_7_6_1_1_6_6776f0",),
             "Insert a signed Icon Image.",
             "Icon Images are unsigned."),
            ("REQ-PIX-009", {"PixelAspectRatio": ["1", "1"]},
             ("Ps3_C_7_6_1_1_6_aeb525",),
             "Insert an Icon Image with Pixel Aspect Ratio 1\\1.",
             "Icon pixels are square, so Pixel Aspect Ratio is not present."),
            ("REQ-PIX-010", {"BitsAllocated": 12, "BitsStored": 8,
                             "PixelData": {"vr": "OW", "value": "00" * 12}},
             ("Ps3_C_7_11c_BitsAllocated_f6fab6", "Ps3_C_7_6_1_1_6_c5156c"),
             "Insert an Icon Image with Bits Allocated 12.",
             "Bits Allocated is 1 or a multiple of 8, and 1 or 8 in an Icon Image."),
        )
    ),
    _pixel("REQ-PIX-005", MONO, [_icon(PlanarConfiguration=0)],
        ("Ps3_C_7_6_1_1_6_c2da50",),
        "Insert a MONOCHROME2 Icon Image with Planar Configuration (0028,0006).",
        PS33_ICON, "Planar Configuration is not present in an Icon Image. It is Type 1C, required only "
        "with more than one sample, so iod-attribute-presence reports the same Attribute.",
        expected=("pixel-attributes", "iod-attribute-presence")),
    _pixel("REQ-PIX-011", MONO, [_icon(PhotometricInterpretation="PALETTE COLOR",
                                      **_descriptors(256, 8), **_palette_data("00" * 512))],
        ("Ps3_C_7_6_3_1_5_ad0ea4",),
        "Insert a PALETTE COLOR Icon Image whose 8-bit Palette Color Lookup Table Data holds 512 bytes for 256 entries.",
        PS33_PALETTE, "8-bit entries are stored as 8 bits allocated, one byte each."),
    _pixel("REQ-PIX-012", MONO, [_icon(PhotometricInterpretation="PALETTE COLOR",
                                      **_descriptors(65535, 8), **_palette_data("00" * 65536))],
        ("Ps3_C_7_6_3_1_5_a1e82c",),
        "Insert a PALETTE COLOR Icon Image with 65536 8-bit entries and a descriptor first Value of 65535.",
        PS33_PALETTE, "2^16 table entries are encoded as a first descriptor Value of 0."),
    _pixel("REQ-PIX-013", MONO, [_icon(**{
        **_descriptors(256, 8), **_palette_data("00" * 256),
        "PhotometricInterpretation": "PALETTE COLOR",
        "RedPaletteColorLookupTableDescriptor": {"vr": "US", "value": [256, 1, 8]}})],
        ("Ps3_C_7_6_3_1_5_1747e4",),
        "Insert a PALETTE COLOR Icon Image whose Red descriptor second Value is 1 and Green and Blue are 0.",
        PS33_PALETTE, "The second descriptor Value is identical for each color."),
    _pixel("REQ-PIX-014", MONO, [_icon(**{
        **_descriptors(256, 8), **_palette_data("00" * 256),
        "PhotometricInterpretation": "PALETTE COLOR",
        "RedPaletteColorLookupTableDescriptor": {"vr": "US", "value": [128, 0, 8]}})],
        ("Ps3_C_7_6_3_1_5_c598ef",),
        "Insert a PALETTE COLOR Icon Image whose Red descriptor declares 128 entries and Green and Blue 256.",
        PS33_PALETTE, "The first descriptor Value is identical for each color."),
    _pixel("REQ-PIX-015", MONO, [_icon(PhotometricInterpretation="PALETTE COLOR",
                                      **_descriptors(256, 12), **_palette_data("00" * 512))],
        ("Ps3_C_7_6_3_1_5_98671f",),
        "Insert a PALETTE COLOR Icon Image whose descriptors' third Value is 12.",
        PS33_PALETTE, "The third descriptor Value is 8 or 16."),
    _pixel("REQ-PIX-016", MONO, [_icon(**{
        **_descriptors(256, 8), **_palette_data("00" * 256),
        "PhotometricInterpretation": "PALETTE COLOR",
        "RedPaletteColorLookupTableDescriptor": {"vr": "US", "value": [256, 0, 16]},
        "RedPaletteColorLookupTableData": {"vr": "OW", "value": "00" * 512}})],
        ("Ps3_C_7_6_3_1_5_ed0814",),
        "Insert a PALETTE COLOR Icon Image with a 16-bit Red table and 8-bit Green and Blue tables.",
        PS33_PALETTE, "The third descriptor Value is identical for each color."),
    _pixel("REQ-PIX-017", MONO, [_icon(
        PhotometricInterpretation="PALETTE COLOR", BitsAllocated=1, BitsStored=1, HighBit=0,
        PixelData={"vr": "OB", "value": "0000"}, **_descriptors(2, 8), **_palette_data("0000"))],
        ("Ps3_C_7_6_1_1_6_502a69",),
        "Insert a 1-bit PALETTE COLOR Icon Image.",
        PS33_ICON, "A palette color Icon Image has 8 bits allocated."),
    _pixel("REQ-PIX-018", MONO, _optical_palette({**_descriptors(256, 8), **_palette_data("00" * 256)}),
        ("Ps3_C_7_6_3_1_5_6b3ce7",),
        "Insert an Optical Path palette with 8-bit entries.",
        PS33_PALETTE, "A Palette Color Lookup Table in an Image IOD has 16-bit entries."),
    _pixel("REQ-PIX-019", "CP02-JPEG-16F",
        _optical_palette({**_descriptors(256, 16), **_palette_data("00" * 512)}, with_profile=False),
        ("Ps3_C_7_6_3_1_6_e94d80",),
        "Insert a 16-bit Optical Path palette into the three-sample control.",
        PS33_PALETTE, "Palette Color Lookup Tables are used only with a single sample per pixel."),
    _pixel("REQ-PIX-020", "CP02-JPEG-16F",
        _optical_palette({**_descriptors(3, 16),
                           **_palette_data(_words([0, 3, 1, 2, 3]), segmented=True)}, with_profile=False),
        ("Ps3_C_7_9_2_a92a46",),
        "Insert a segmented Optical Path palette into the three-sample control.",
        PS33_SEGMENTED, "Segmented lookup tables are used only with a single sample per pixel."),
    _pixel("REQ-PIX-021", MONO, _optical_palette({
        **_descriptors(9, 16),
        **_palette_data(_words([0, 2, 0, 100, 1, 3, 400, 2, 2, 0, 0]), segmented=True)}),
        ("Ps3_C_7_9_2_84cfee",),
        "Insert a segmented Optical Path palette expanding to 10 entries with descriptors declaring 9.",
        PS33_SEGMENTED, "Expanded segments have the number of entries the descriptors declare."),
    _pixel("REQ-PIX-022", MONO, _optical_palette({
        **_descriptors(4, 16),
        **_palette_data(_words([0, 2, 0, 1, 2, 2, 0, 0, 2, 1, 8, 0]), segmented=True)}),
        ("Ps3_C_7_9_2_3_a8252a",),
        "Insert a segmented Optical Path palette whose second indirect segment copies the first.",
        PS33_SEGMENTED, "An indirect segment does not copy another indirect segment."),
    _pixel("REQ-PIX-023", MONO, _optical_palette({
        **_descriptors(4, 16), **_palette_data(_words([0, 2, 0, 1, 2, 1, 2, 0]), segmented=True)}),
        ("Ps3_C_7_9_2_3_01ce43",),
        "Insert a segmented Optical Path palette with an indirect segment pointing to byte offset 2, inside a segment.",
        PS33_SEGMENTED, "An indirect segment's offset is the byte offset of a segment."),
    _pixel("REQ-PIX-024", MONO, _optical_palette({
        **_descriptors(4, 16), **_palette_data(_words([1, 4, 9]), segmented=True)}),
        ("Ps3_C_7_9_2_2_c7a7b2",),
        "Insert a segmented Optical Path palette that begins with a linear segment.",
        PS33_SEGMENTED, "A linear segment continues from the previous segment's last entry, so it cannot come first."),
    _pixel("REQ-PIX-025", MONO, _optical_palette({
        **_descriptors(4, 16), **_palette_data(_words([0, 5, 1, 2]), segmented=True)}),
        ("Ps3_C_7_9_2_1_dfe589",),
        "Insert a segmented Optical Path palette whose discrete Segment Length exceeds the remaining data.",
        PS33_SEGMENTED, "A discrete segment holds its Segment Length entries."),
)


REQUIREMENT_CASES = (
    *RELATION_CASES,
    *WSI_IMAGE_CASES,
    *SERIES_SET_CASES,
    *VALUE_SET_CASES,
    *PIXEL_ATTRIBUTE_CASES,
    *CODESTREAM_CASES,
    *ENCODING_CASES,
)

# Statements no case of this cohort exercises yet, and why.
UNCOVERED = {
    "Ps3_C_8_12_4_1_SpecimenLabelInImage_fd0f41": "needs an OVERVIEW or LABEL control",
    "Ps3_C_8_12_4_1_SpecimenLabelInImage_0b6709": "exercised by carried-forward case CP-CF-004 (mutation volume_specimen_label_yes)",
    "Ps3_C_8_12_5_1_OpticalPathIdentifier_d84211": "needs a two-optical-path control",
    "Ps3_C_7_6_16_2_2_4_241add": "needs a Concatenation control pair",
    "Ps3_C_7_6_16_2_2_4_3fcf86": "needs a Concatenation control pair",
    "Ps3_C_7_6_16_2_2_4_b6a910": "needs a Concatenation control pair",
    "Ps3_C_7_6_16_2_2_4_c53142": "needs a Concatenation control pair",
    "Ps3_C_7_6_16_1_SOPInstanceUIDOfConcatenationSource_487ffc": "needs a Concatenation control pair",
    "Ps3_C_7_6_16_1_InConcatenationNumber_f490dd": "needs a Concatenation control pair",
    "Ps3_C_7_6_16_1_InConcatenationTotalNumber_4fdb6d": "needs a Concatenation control pair",
    "Ps3_C_7_6_17_2_4ebae3": "needs a second Instance with its own Dimension Index structure",
    "Ps3_C_7_6_16_2_5_1_17ac5a": "needs a LOCALIZER control",
    "Ps5_8_2_3_c509e8": "needs a control: JPEG-LS Lossless (1.2.840.10008.1.2.4.80) VL WSI, RGB, several Frames",
    "Ps5_A_4_3_e86721": "needs a control: JPEG-LS Lossless (1.2.840.10008.1.2.4.80) VL WSI, RGB, several Frames",
    "Ps5_A_4_3_79e44a": "needs a control: JPEG-LS Lossless (1.2.840.10008.1.2.4.80) VL WSI, RGB, several Frames",
    "Ps5_A_4_3_af4cd4": "needs a control: JPEG-LS Lossless (1.2.840.10008.1.2.4.80) VL WSI, RGB, several Frames",
    "Ps5_A_4_3_116d52": "needs a control: JPEG-LS Lossless (1.2.840.10008.1.2.4.80) VL WSI, RGB, several Frames",
    "Ps5_8_2_2_c961f8": "needs a control: RLE Lossless (1.2.840.10008.1.2.5) VL WSI, RGB 8-bit, several Frames",
    "Ps5_G_3_3774f3": "needs a control: RLE Lossless (1.2.840.10008.1.2.5) VL WSI, RGB 8-bit, several Frames",
    "Ps5_G_3_1_961ac0": "needs a control: RLE Lossless (1.2.840.10008.1.2.5) VL WSI, RGB 8-bit, several Frames",
    "Ps5_G_3_1_5f6b0b": "needs a control: RLE Lossless (1.2.840.10008.1.2.5) VL WSI, RGB 8-bit, several Frames",
    "Ps5_G_5_92c185": "needs a control: RLE Lossless (1.2.840.10008.1.2.5) VL WSI, RGB 8-bit, several Frames",
    "Ps5_8_2_15_091321": "needs a control: JPEG XL Lossless (1.2.840.10008.1.2.4.110) and JPEG XL JPEG Recompression (1.2.840.10008.1.2.4.111) VL WSI controls",
    "Ps5_A_4_12_814b6e": "needs a control: JPEG XL Lossless (1.2.840.10008.1.2.4.110) and JPEG XL JPEG Recompression (1.2.840.10008.1.2.4.111) VL WSI controls",
    "Ps5_10_18_1_a950cd": "needs a control: HTJ2K Lossless RPCL (1.2.840.10008.1.2.4.202) VL WSI with Frames larger than 64 x 64 pixels",
    "Ps5_A_4_4_ab7220": "needs a control: JPEG 2000 Part 2 Multi-component (1.2.840.10008.1.2.4.92 or .93) VL WSI",
    "Ps5_A_4_4_6e9c4b": "needs a control: JPEG 2000 Part 2 Multi-component (1.2.840.10008.1.2.4.92 or .93) VL WSI",
    "Ps5_A_6_34f1d3": "needs a JPIP Referenced control: Pixel Data Provider URL in place of Pixel Data is more than one defect on a pixel control",
    "Ps5_A_11_836dbf": "needs a JPIP Referenced control: Pixel Data Provider URL in place of Pixel Data is more than one defect on a pixel control",
    "Ps5_A_4_11_bd0aed": "needs a control: Encapsulated Uncompressed Explicit VR Little Endian (1.2.840.10008.1.2.1.98) VL WSI",
    "Ps5_7_1_2_85dc52": "a Value Length that overstates its Value leaves the parser unable to read the file, so the other rules give no verdict and the case cannot be single-defect",
}

# Core profile v4 rows: one per catalog-v6 rule, mapped to this cohort's cases.
PROFILE_ROWS = (
    ("CP-V6-VS-001", "PS3.16", "Annex B and Annex A", "value_set",
     "Coded entries use the Defined, non-extensible Context Groups, and Content Item trees follow the Defined Templates, that the IOD tables bind.",
     "iod-value-sets"),
    ("CP-V6-WSI-001", "PS3.3", "C.8.12.4.1, C.8.12.14.1 and A.32.8.4.1.2", "wsi_image_constraint",
     "VL WSI Image and Frame Type have four Values, Specimen Label in Image follows the flavor, Tiles Overlap, Imaged Volume Depth, Position Reference Indicator, optical paths, derivation, pixel spacing and the regular tiling hold.",
     "wsi-image"),
    ("CP-V6-REL-001", "PS3.3", "8.6, 10.17, C.7, C.8.12.5 and C.12", "attribute_relation",
     "Constraints between Attributes hold in the Data Set and every Item.",
     "attribute-relations"),
    ("CP-V6-SET-001", "PS3.3", "C.7.4.1.1.1, C.7.6.16, C.7.6.17, C.7.6.22 and C.12.9", "set_relation",
     "Instances of the evaluated set agree on Frames of Reference, UID roles, Instance Numbers, Specimen Identifiers, Frame Extraction history and patient group arrangements.",
     "series-set"),
    ("CP-V6-PIX-001", "PS3.3", "C.7.5.1.1.2, C.7.6.1.1.6, C.7.6.3.1 and C.7.9", "pixel_description",
     "Pixel Padding, Pixel Aspect Ratio, Icon Images and palette tables follow their constraints.",
     "pixel-attributes"),
    ("CP-V6-CS-001", "PS3.5", "8.2 and A.4", "codestream",
     "Each encapsulated Frame holds one complete codestream of the coding process its Transfer Syntax identifies, agreeing with the Image Pixel Attributes.",
     "codestream"),
    ("CP-V6-ENC-001", "PS3.5", "6.1, 6.2, 7 and Annex A", "data_set_encoding",
     "The Data Set as encoded in the file's bytes follows PS3.5 element order, VR, length, private block and character set encoding.",
     "encoding"),
)
# Controls that pass every rule of the rows above and cover native, JPEG, JPEG 2000 and
# HTJ2K encodings in color and MONOCHROME2.
PROFILE_POSITIVE_CONTROLS = (
    "CP01-EVRLE-4F-ANISO", "CP02-JPEG-16F", "CP04-J2K-LOSSLESS-16F",
    "CP06-HTJ2K-LOSSLESS-16F", "CP07-HTJ2K-RPCL-4F", "CP11-MONO-EVRLE-4F",
)
