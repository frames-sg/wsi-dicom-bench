"""Authored v5 amendment data: carried-forward adjudications and the IOD structure cohort.

``CARRIED_FORWARD`` records, for each v4 case on which the frozen candidate failed a v5 IOD
rule, whether that failure is an expected failing rule or an adjudicated cascade, with the
observed message, the DICOM 2026c citation, and the rationale. ``STRUCTURE_CASES`` defines
the single-defect cases of the ``iod-structure-evaluation-v1`` cohort.
"""

from __future__ import annotations


BASE = "https://dicom.nema.org/medical/dicom/2026c/output/chtml"
PREFIX = "intrinsic-wsi-dicom-2026c-"
IOD_RULES = tuple(
    PREFIX + name
    for name in (
        "iod-modules",
        "iod-attribute-presence",
        "iod-enumerated-values",
        "iod-vr-vm",
        "iod-value-format",
        "iod-sequence-items",
        "file-meta",
    )
)


def full_rule_id(short: str) -> str:
    return short if short.startswith(("intrinsic-", "pixel-decode-")) else PREFIX + short


def _cite(part: str, section: str, page: str) -> dict:
    return {"edition": "2026c", "part": part, "section": section, "url": f"{BASE}/{page}"}


PS33_A328 = _cite("PS3.3", "A.32.8 Table A.32.8-1", "part03/sect_A.32.8.html")
PS33_FG = _cite("PS3.3", "A.32.8.4 Table A.32.8-2", "part03/sect_A.32.8.4.html")
PS33_MFFG = _cite("PS3.3", "C.7.6.16 Table C.7.6.16-1", "part03/sect_C.7.6.16.html")
PS33_WSI_IMAGE = _cite("PS3.3", "C.8.12.4 Table C.8.12.4-1", "part03/sect_C.8.12.4.html")
PS33_SPECIMEN = _cite("PS3.3", "C.7.6.22 Table C.7.6.22-2", "part03/sect_C.7.6.22.html")
PS33_OPTICAL = _cite("PS3.3", "C.8.12.5 Table C.8.12.5-1", "part03/sect_C.8.12.5.html")
PS33_TILE_ORG = _cite("PS3.3", "C.8.12.14 Table C.8.12.14-1", "part03/sect_C.8.12.14.html")
PS33_EQUIPMENT = _cite("PS3.3", "C.7.5.2 Table C.7-8b", "part03/sect_C.7.5.2.html")
PS33_PATIENT = _cite("PS3.3", "C.7.1.1 Table C.7-1", "part03/sect_C.7.html#sect_C.7.1.1")
PS33_STUDY = _cite("PS3.3", "C.7.2.1 Table C.7-3", "part03/sect_C.7.2.html#sect_C.7.2.1")
PS33_SERIES = _cite("PS3.3", "C.7.3.1 Table C.7-5a", "part03/sect_C.7.3.html#sect_C.7.3.1")
PS33_FOR = _cite("PS3.3", "C.7.4.1 Table C.7-6", "part03/sect_C.7.4.html#sect_C.7.4.1")
PS33_ACQ_CONTEXT = _cite("PS3.3", "C.7.6.14 Table C.7.6.14-1", "part03/sect_C.7.6.14.html")
PS33_GENERAL_IMAGE = _cite("PS3.3", "C.7.6.1 Table C.7-9", "part03/sect_C.7.6.html#sect_C.7.6.1")
PS33_PYRAMID = _cite("PS3.3", "C.7.11.1 Table C.7.11.1-1", "part03/sect_C.7.11.html#sect_C.7.11.1")
PS33_DIMENSION = _cite("PS3.3", "C.7.6.17 Table C.7.6.17-1", "part03/sect_C.7.6.17.html")
PS33_CODE = _cite("PS3.3", "8.8 Table 8.8-1a", "part03/sect_8.8.html")
PS33_PLANE = _cite("PS3.3", "C.8.12.6.1 Table C.8.12.6.1-1", "part03/sect_C.8.12.6.html#sect_C.8.12.6.1")
PS33_PATH_ID = _cite("PS3.3", "C.8.12.6.2 Table C.8.12.6.2-1", "part03/sect_C.8.12.6.2.html")
PS33_FRAME_TYPE = _cite("PS3.3", "C.8.12.9 Table C.8.12.9-1", "part03/sect_C.8.12.9.html")
PS33_PIXEL_MEASURES = _cite("PS3.3", "C.7.6.16.2.1 Table C.7.6.16-2", "part03/sect_C.7.6.16.2.html#sect_C.7.6.16.2.1")
PS33_FRAME_CONTENT = _cite("PS3.3", "C.7.6.16.2.2 Table C.7.6.16-3", "part03/sect_C.7.6.16.2.html#sect_C.7.6.16.2.2")
PS33_HL7 = _cite("PS3.3", "10.14 Table 10-17", "part03/sect_10.14.html")
PS33_SAMPLES = _cite("PS3.3", "C.8.12.4.1.5", "part03/sect_C.8.12.4.html#sect_C.8.12.4.1.5")
PS35_TYPES = _cite("PS3.5", "7.4.2", "part05/sect_7.4.2.html")
PS35_VR = _cite("PS3.5", "6.2 Table 6.2-1", "part05/sect_6.2.html")
PS35_UID = _cite("PS3.5", "9.1", "part05/chapter_9.html#sect_9.1")
PS36_REGISTRY = _cite("PS3.6", "6 Table 6-1", "part06/chapter_6.html")
PS310_META = _cite("PS3.10", "7.1 Table 7.1-1", "part10/chapter_7.html#sect_7.1")


def _expected(rule: str, observed: str, citation: dict, rationale: str) -> dict:
    return {
        "rule_id": full_rule_id(rule),
        "disposition": "expected_failing_rule",
        "observed": observed,
        "citation": citation,
        "rationale": rationale,
    }


def _cascade(rule: str, observed: str, citation: dict, rationale: str) -> dict:
    return {**_expected(rule, observed, citation, rationale), "disposition": "adjudicated_cascade"}


def _missing(rule: str, attribute: str, kind: str, citation: dict) -> dict:
    return _expected(
        rule,
        f"{attribute}: Type {kind} missing",
        citation,
        f"The case removes {attribute.rsplit(' (', 1)[0]}, a Type {kind} Attribute whose "
        "requirement applies to this object, so the rule reports the authored deletion.",
    )


# Adjudicated IOD-rule outcomes of the frozen candidate on carried-forward v4 cases.
# Cases absent from this table produced no IOD-rule failure on the candidate.
CARRIED_FORWARD = {
    "NB-PX-001": [
        _expected(
            "iod-modules",
            "Per-Frame Functional Groups Sequence (5200,9230): 16 Items for Number of Frames 17",
            PS33_MFFG,
            "The case defines the defect as Number of Frames 17 without a matching "
            "functional-group Item; Table C.7.6.16-1 requires one Per-Frame Item per Frame.",
        ),
    ],
    "NB-CO-001": [
        _missing("iod-attribute-presence", "Optical Path Sequence[1] > ICC Profile (0028,2000)", "1C", PS33_OPTICAL),
    ],
    "NB-ID-001": [
        _missing("iod-attribute-presence", "Specimen Description Sequence (0040,0560)", "1", PS33_SPECIMEN),
    ],
    "NB-ID-002": [
        _missing(
            "iod-attribute-presence",
            "Specimen Description Sequence[1] > Specimen Identifier (0040,0551)",
            "1",
            PS33_SPECIMEN,
        ),
    ],
    "NB-ID-004": [
        _expected(
            "file-meta",
            "Media Storage SOP Instance UID (0002,0003) does not match SOP Instance UID (0008,0018)",
            PS310_META,
            "Media Storage SOP Instance UID identifies the SOP Instance of the Data Set that "
            "follows; the patched File Meta UID differs from it.",
        ),
    ],
    "NB-CF-001": [
        _expected(
            "iod-attribute-presence",
            "Lossy Image Compression (0028,2110): Type 1 missing; Lossy Image Compression "
            "Ratio and Method: Type 1C present although its condition is not met",
            PS33_WSI_IMAGE,
            "Lossy Image Compression is Type 1. With it absent, the retained Ratio and "
            "Method no longer meet 'Required if Lossy Image Compression is 01' and PS3.5 "
            "7.4.2 forbids them; those two messages are consequences within the same rule.",
        ),
    ],
    "NB-CF-002": [
        _cascade(
            "iod-attribute-presence",
            "Lossy Image Compression Ratio (0028,2112) and Method (0028,2114): Type 1C "
            "present although its condition is not met",
            PS35_TYPES,
            "The authored defect is lossy Pixel Data declared lossless, localized by "
            "lossy-history. Setting Lossy Image Compression to 00 leaves the unchanged Ratio "
            "and Method present without their condition; PS3.5 7.4.2 forbids that, so the "
            "failure is a correct consequence, not a second mutation.",
        ),
    ],
    "NB-CF-003": [
        _missing("iod-attribute-presence", "Lossy Image Compression Method (0028,2114)", "1C", PS33_WSI_IMAGE),
    ],
    "NB-CF-005": [
        _expected(
            "iod-enumerated-values",
            'Samples per Pixel (0028,0002) "1" is not an Enumerated Value [3]',
            PS33_SAMPLES,
            "C.8.12.4.1.5 gives Samples per Pixel the Enumerated Value 3 when Photometric "
            "Interpretation is not MONOCHROME2; the case sets 1 with RGB retained.",
        ),
        _cascade(
            "iod-attribute-presence",
            "Planar Configuration (0028,0006): Type 1C present although its condition is not met",
            _cite("PS3.3", "C.7.6.3 Table C.7-11c; PS3.5 7.4.2", "part03/sect_C.7.6.3.html"),
            "Planar Configuration is unchanged. It is 'Required if Samples per Pixel has a "
            "Value greater than 1', so PS3.5 7.4.2 forbids it once Samples per Pixel is 1.",
        ),
    ],
    "CP-CF-001": [_missing("iod-attribute-presence", "Acquisition DateTime (0008,002A)", "1", PS33_WSI_IMAGE)],
    "CP-CF-002": [
        _cascade(
            "iod-modules",
            "Multi-Resolution Pyramid Module present although its usage condition is not "
            "met; Slide Label Module required but none of its Attributes is present",
            PS33_A328,
            "Image Type Value 3 LABEL makes the Slide Label Module required and permits the "
            "Multi-Resolution Pyramid Module only for VOLUME or THUMBNAIL (Table A.32.8-1).",
        ),
        _cascade(
            "iod-attribute-presence",
            "Label Text (2200,0002) and Barcode Value (2200,0005): Type 2 missing",
            _cite("PS3.3", "C.8.12.8 Table C.8.12.8-1", "part03/sect_C.8.12.8.html"),
            "Once LABEL makes the Slide Label Module required, its Type 2 Label Text and "
            "Barcode Value are required; the unchanged object lacks them.",
        ),
        _cascade(
            "iod-enumerated-values",
            'Number of Frames (0028,0008) "4" is not an Enumerated Value [1]',
            PS33_WSI_IMAGE,
            "Number of Frames has the Enumerated Value 1 when Image Type Value 3 is "
            "THUMBNAIL, LABEL, or OVERVIEW; the unchanged object has four Frames.",
        ),
    ],
    "CP-CF-003": [_missing("iod-attribute-presence", "Focus Method (0048,0011)", "1", PS33_WSI_IMAGE)],
    "CP-CF-005": [
        _expected(
            "iod-attribute-presence",
            "Rescale Intercept (0028,1052), Rescale Slope (0028,1053), Presentation LUT "
            "Shape (2050,0020): Type 1C missing",
            PS33_WSI_IMAGE,
            "All three are Type 1C 'Required if Photometric Interpretation is MONOCHROME2'; "
            "the case removes them from a MONOCHROME2 object.",
        ),
    ],
    "CP-CF-006": [
        _expected(
            "iod-enumerated-values",
            'Rescale Slope (0028,1053) "2" is not an Enumerated Value [1]',
            PS33_WSI_IMAGE,
            "Rescale Slope has the Enumerated Value 1 in the Whole Slide Microscopy Image Module.",
        ),
    ],
    "CP-CF-007": [
        _expected(
            "iod-modules",
            "Acquisition Context Module (Usage M): none of its Attributes is present",
            PS33_A328,
            "The removed Type 2 Acquisition Context Sequence is the only non-Type-3 "
            "Attribute of the mandatory Acquisition Context Module, which is now absent.",
        ),
        _missing("iod-attribute-presence", "Acquisition Context Sequence (0040,0555)", "2", PS33_ACQ_CONTEXT),
    ],
    "CP-CF-008": [_missing("iod-attribute-presence", "Manufacturer (0008,0070)", "1", PS33_EQUIPMENT)],
    "CP-CF-009": [_missing("iod-attribute-presence", "Device Serial Number (0018,1000)", "1", PS33_EQUIPMENT)],
    "CP-CF-010": [
        _expected(
            "iod-modules",
            "Whole Slide Microscopy Image Frame Type Functional Group (Usage M) absent from "
            "the Shared and every Per-Frame Item",
            PS33_FG,
            "Table A.32.8-2 makes this Functional Group mandatory and Shared; the case removes it.",
        ),
    ],
    "CP-CF-012": [_missing("iod-attribute-presence", "Position Reference Indicator (0020,1040)", "2", PS33_FOR)],
    "CP-CF-013": [
        _expected(
            "iod-enumerated-values",
            'Pixel Representation (0028,0103) "1" is not an Enumerated Value [0]',
            PS33_WSI_IMAGE,
            "Pixel Representation has the Enumerated Value 0 in the Whole Slide Microscopy Image Module.",
        ),
    ],
    "CP-CF-015": [
        _expected(
            "iod-enumerated-values",
            'Planar Configuration (0028,0006) "1" is not an Enumerated Value [0]',
            PS33_WSI_IMAGE,
            "Planar Configuration has the Enumerated Value 0 in the Whole Slide Microscopy Image Module.",
        ),
    ],
    "CP-CF-016": [_missing("iod-attribute-presence", "Content Date (0008,0023)", "1", PS33_MFFG)],
    "CP-CL-002": [_missing("iod-attribute-presence", "Optical Path Sequence (0048,0105)", "1", PS33_OPTICAL)],
    "CP-CL-003": [
        _missing("iod-attribute-presence", "Optical Path Sequence[1] > Optical Path Identifier (0048,0106)", "1", PS33_OPTICAL),
    ],
    "CP-CL-004": [
        _missing(
            "iod-attribute-presence",
            "Optical Path Sequence[1] > Illumination Type Code Sequence (0022,0016)",
            "1",
            PS33_OPTICAL,
        ),
    ],
    "CP-CL-005": [
        _expected(
            "iod-attribute-presence",
            "Illumination Wave Length (0022,0055) and Illumination Color Code Sequence "
            "(0048,0108): Type 1C missing",
            PS33_OPTICAL,
            "Each is required if the other is absent; the case removes both.",
        ),
    ],
    "CP-GE-001": [_missing("iod-attribute-presence", "Total Pixel Matrix Origin Sequence (0048,0008)", "1", PS33_TILE_ORG)],
    "CP-GE-002": [
        _missing(
            "iod-attribute-presence",
            "Total Pixel Matrix Origin Sequence[1] > X Offset in Slide Coordinate System (0040,072A)",
            "1",
            PS33_TILE_ORG,
        ),
    ],
    "CP-GE-003": [_missing("iod-attribute-presence", "Image Orientation (Slide) (0048,0102)", "1C", PS33_TILE_ORG)],
    "CP-ID-005": [_missing("iod-attribute-presence", "Container Identifier (0040,0512)", "1", PS33_SPECIMEN)],
    "CP-ID-006": [
        _missing("iod-attribute-presence", "Issuer of the Container Identifier Sequence (0040,0513)", "2", PS33_SPECIMEN),
    ],
    "CP-ID-007": [
        _missing(
            "iod-attribute-presence",
            "Specimen Description Sequence[1] > Specimen Preparation Sequence (0040,0610)",
            "2",
            PS33_SPECIMEN,
        ),
    ],
    "CP-ID-008": [
        _expected(
            "iod-attribute-presence",
            "Specimen Preparation Sequence[1] > Specimen Preparation Step Content Item "
            "Sequence (0040,0612): Type 1 missing",
            PS33_SPECIMEN,
            "The case adds a preparation Item without its Type 1 content-item Sequence.",
        ),
    ],
    "CP-ID-009": [_missing("iod-attribute-presence", "Patient's Birth Date (0010,0030)", "2", PS33_PATIENT)],
    "CP-ID-010": [_missing("iod-attribute-presence", "Study Date (0008,0020)", "2", PS33_STUDY)],
    "CP-ID-011": [_missing("iod-attribute-presence", "Series Number (0020,0011)", "2", PS33_SERIES)],
}


def _case(
    case_id: str,
    control: str,
    mutation: str,
    parameters: dict,
    expected: tuple[str, ...],
    changed: str,
    citation: dict,
    rationale: str,
    **fields,
) -> dict:
    """One case specification; extra ``fields`` (v6 ``requirement_ids``) follow ``expected``."""
    return {
        "case_id": case_id,
        "control": control,
        "mutation_name": mutation,
        "mutation_parameters": parameters,
        "expected": expected,
        **fields,
        "changed": changed,
        "citation": citation,
        "rationale": rationale,
    }


# Builders of ``iod_edits`` operations, shared with the v6 requirement-statement tables.
def _op(operation: str, path: list, value: object = None, vr: str | None = None) -> dict:
    entry = {"operation": operation, "path": path}
    if operation != "delete":
        entry["value"] = value
    if vr is not None:
        entry["vr"] = vr
    return entry


def _edits(*operations: dict) -> dict:
    return {"operations": list(operations)}


def _code(scheme: str, value: str, meaning: str) -> dict:
    return {"CodeValue": value, "CodingSchemeDesignator": scheme, "CodeMeaning": meaning}


SHARED = ["SharedFunctionalGroupsSequence", 0]
PIXEL_MEASURES = [*SHARED, "PixelMeasuresSequence", 0]
FRAME_TYPE = [*SHARED, "WholeSlideMicroscopyImageFrameTypeSequence", 0]
LEADING_ZERO_UID = "2.25.0123456789"
ONLY = "Only the targeted rule reports this {what} defect; no catalog-v4 rule does."
ALSO = "The {rule} rule independently reports the same defect, so both rules are expected."

STRUCTURE_CASES = (
    # Module and Functional Group usage.
    _case("IOD-MOD-001", "CP06-HTJ2K-LOSSLESS-16F", "iod_insert_attribute",
          {"path": [*SHARED, "PixelValueTransformationSequence"],
           "value": [{"RescaleIntercept": "0", "RescaleSlope": "1", "RescaleType": "US"}]},
          ("iod-modules",),
          "Insert a Pixel Value Transformation Sequence (0028,9145) with one valid Item into the Shared Functional Groups Item.",
          PS33_FG, "Pixel Value Transformation is not a Functional Group Macro of Table A.32.8-2; its Item content is valid. " + ONLY.format(what="Functional Group")),
    _case("IOD-MOD-002", "CP07-HTJ2K-RPCL-4F", "iod_insert_attribute",
          {"path": [*SHARED, "FrameVOILUTSequence"], "value": [{"WindowCenter": "128", "WindowWidth": "256"}]},
          ("iod-modules",),
          "Insert a Frame VOI LUT Sequence (0028,9132) with Window Center 128 and Window Width 256 into the Shared Functional Groups Item.",
          PS33_FG, "Frame VOI LUT is not a Functional Group Macro of Table A.32.8-2. " + ONLY.format(what="Functional Group")),
    _case("IOD-MOD-003", "CP13-IMPLICIT-TILED-FULL", "iod_insert_attribute",
          {"path": [*SHARED, "FrameContentSequence"], "value": [{"FrameAcquisitionNumber": 1}]},
          ("iod-modules",),
          "Insert a Frame Content Sequence (0020,9111) Item with Frame Acquisition Number 1 into the Shared Functional Groups Item of the implicit-position control.",
          PS33_FG, "Table A.32.8-2: Frame Content shall not be used as a Shared Functional Group. " + ONLY.format(what="placement")),
    _case("IOD-MOD-004", "CP03-JPEG-1F", "iod_delete_attribute",
          {"path": [*SHARED, "WholeSlideMicroscopyImageFrameTypeSequence"]},
          ("iod-modules", "core-image-profile"),
          "Remove the mandatory Whole Slide Microscopy Image Frame Type Sequence (0040,0710) from the Shared Functional Groups Item of the single-frame control.",
          PS33_FG, "The mandatory Functional Group Macro is absent for every Frame. " + ALSO.format(rule="core-image-profile")),
    _case("IOD-MOD-005", "CP02-JPEG-16F", "iod_delete_attribute",
          {"path": [*SHARED, "PixelMeasuresSequence"]},
          ("iod-modules", "core-image-profile", "tile-geometry"),
          "Remove the mandatory Pixel Measures Sequence (0028,9110) from the Shared Functional Groups Item.",
          PS33_FG, "The mandatory Pixel Measures Functional Group is absent for every Frame. The core-image-profile and tile-geometry rules also require it, so all three are expected."),
    _case("IOD-MOD-006", "CP04-J2K-LOSSLESS-16F", "iod_remove_sequence_item",
          {"path": ["PerFrameFunctionalGroupsSequence"], "item_index": 15},
          ("iod-modules", "tile-geometry"),
          "Remove Per-Frame Functional Groups Sequence Item 16 of 16, retaining Number of Frames 16 and all Pixel Data.",
          PS33_MFFG, "Table C.7.6.16-1 requires as many Per-Frame Items as Frames. " + ALSO.format(rule="tile-geometry")),
    _case("IOD-MOD-007", "CP05-J2K-LOSSY-4F", "iod_duplicate_sequence_item",
          {"path": ["PerFrameFunctionalGroupsSequence"], "item_index": 3},
          ("iod-modules", "tile-geometry"),
          "Append a copy of Per-Frame Functional Groups Sequence Item 4, giving 5 Items for Number of Frames 4.",
          PS33_MFFG, "Table C.7.6.16-1 requires as many Per-Frame Items as Frames. " + ALSO.format(rule="tile-geometry")),
    _case("IOD-MOD-008", "CP02-JPEG-16F", "iod_insert_attribute",
          {"path": ["PerFrameFunctionalGroupsSequence", 0, "PixelMeasuresSequence"],
           "value": [{"PixelSpacing": ["0.0005", "0.0005"], "SliceThickness": "0.001"}]},
          ("iod-modules", "core-image-profile"),
          "Insert into Per-Frame Item 1 a Pixel Measures Sequence identical to the shared one (Pixel Spacing 0.0005\\0.0005, Slice Thickness 0.001).",
          _cite("PS3.3", "A.32.8.4 Table A.32.8-2; C.7.6.16.1.1", "part03/sect_A.32.8.4.html"),
          "Pixel Measures shall be Shared, and one Functional Group shall not be in both Sequences. " + ALSO.format(rule="core-image-profile")),
    _case("IOD-MOD-009", "CP13-IMPLICIT-TILED-FULL", "iod_delete_attribute",
          {"path": ["AcquisitionContextSequence"]},
          ("iod-modules", "iod-attribute-presence", "core-image-profile"),
          "Remove the empty Type 2 Acquisition Context Sequence (0040,0555), the only non-Type-3 Attribute of the mandatory Acquisition Context Module, from the implicit VR control.",
          PS33_A328, "The mandatory Acquisition Context Module is absent. Attribute presence reports its missing Type 2 Attribute and core-image-profile requires the Sequence, so all three rules report the one deletion."),
    # Attribute presence.
    _case("IOD-PRS-001", "CP04-J2K-LOSSLESS-16F", "iod_delete_attribute", {"path": ["PyramidUID"]},
          ("iod-attribute-presence",), "Remove Pyramid UID (0008,0019); Pyramid Label keeps the Multi-Resolution Pyramid Module present.",
          PS33_PYRAMID, "Pyramid UID is Type 1 in the present Multi-Resolution Pyramid Module. " + ONLY.format(what="Attribute")),
    _case("IOD-PRS-002", "CP03-JPEG-1F", "iod_empty_attribute", {"path": ["PyramidUID"]},
          ("iod-attribute-presence",), "Set Pyramid UID (0008,0019) to zero length.",
          PS33_PYRAMID, "A Type 1 Attribute is present without a Value (PS3.5 7.4.1). " + ONLY.format(what="Attribute")),
    _case("IOD-PRS-003", "CP01-EVRLE-4F-ANISO", "iod_delete_attribute", {"path": ["ReferringPhysicianName"]},
          ("iod-attribute-presence", "clinical-identity-set"), "Remove the Type 2 Referring Physician's Name (0008,0090).",
          PS33_STUDY, "Type 2 Attributes shall be present (PS3.5 7.4.3). " + ALSO.format(rule="clinical-identity-set")),
    _case("IOD-PRS-004", "CP06-HTJ2K-LOSSLESS-16F", "iod_delete_attribute",
          {"path": ["DimensionOrganizationSequence", 0, "DimensionOrganizationUID"]},
          ("iod-attribute-presence",), "Remove Dimension Organization UID (0020,9164) from the Dimension Organization Sequence Item.",
          PS33_DIMENSION, "Dimension Organization UID is Type 1 in the Sequence Item. " + ONLY.format(what="Attribute")),
    _case("IOD-PRS-005", "CP07-HTJ2K-RPCL-4F", "iod_empty_attribute",
          {"path": ["ContainerTypeCodeSequence", 0, "CodeMeaning"]},
          ("iod-attribute-presence",), "Set Code Meaning (0008,0104) of the Container Type Code Sequence Item to zero length.",
          PS33_CODE, "Code Meaning is Type 1 in the Basic Code Sequence Macro. " + ONLY.format(what="Attribute")),
    _case("IOD-PRS-006", "CP03-JPEG-1F", "iod_empty_attribute",
          {"path": ["OpticalPathSequence", 0, "IlluminationTypeCodeSequence", 0, "CodeMeaning"]},
          ("iod-attribute-presence",), "Set Code Meaning (0008,0104) of the Illumination Type Code Sequence Item within the Optical Path Sequence Item to zero length.",
          PS33_CODE, "Code Meaning is Type 1 two Sequence levels down. " + ONLY.format(what="Attribute")),
    _case("IOD-PRS-007", "CP01-EVRLE-4F-ANISO", "iod_delete_attribute",
          {"path": ["PerFrameFunctionalGroupsSequence", 2, "PlanePositionSlideSequence", 0, "ZOffsetInSlideCoordinateSystem"]},
          ("iod-attribute-presence",), "Remove Z Offset in Slide Coordinate System (0040,074A) from the Plane Position (Slide) Item of Per-Frame Item 3.",
          PS33_PLANE, "Z Offset is Type 1 in the Plane Position (Slide) Macro, required even for one focal plane. " + ONLY.format(what="Attribute")),
    _case("IOD-PRS-008", "CP10-EVRLE-16F", "iod_delete_attribute",
          {"path": ["PerFrameFunctionalGroupsSequence", 9, "PlanePositionSlideSequence", 0, "XOffsetInSlideCoordinateSystem"]},
          ("iod-attribute-presence",), "Remove X Offset in Slide Coordinate System (0040,072A) from the Plane Position (Slide) Item of Per-Frame Item 10.",
          PS33_PLANE, "X Offset is Type 1 in the Plane Position (Slide) Macro. " + ONLY.format(what="Attribute")),
    _case("IOD-PRS-009", "CP09-J2K-LOSSLESS-4F", "iod_empty_attribute", {"path": [*FRAME_TYPE, "FrameType"]},
          ("iod-attribute-presence", "core-image-profile"), "Set the shared Frame Type (0008,9007) to zero length.",
          PS33_FRAME_TYPE, "Frame Type is Type 1. " + ALSO.format(rule="core-image-profile")),
    _case("IOD-PRS-010", "CP14-MONO16-EVRLE", "iod_delete_attribute", {"path": [*PIXEL_MEASURES, "SliceThickness"]},
          ("iod-attribute-presence",), "Remove Slice Thickness (0018,0050) from the shared Pixel Measures Item.",
          PS33_PIXEL_MEASURES, "Slice Thickness is Type 1C, required when Volumetric Properties is VOLUME and Image Type Value 3 is not LABEL or OVERVIEW. " + ONLY.format(what="Attribute")),
    _case("IOD-PRS-011", "CP10-EVRLE-16F", "iod_empty_attribute", {"path": [*PIXEL_MEASURES, "SliceThickness"]},
          ("iod-attribute-presence",), "Set Slice Thickness (0018,0050) of the shared Pixel Measures Item to zero length.",
          PS33_PIXEL_MEASURES, "A required Type 1C Attribute is present without a Value. " + ONLY.format(what="Attribute")),
    _case("IOD-PRS-012", "CP10-EVRLE-16F", "iod_delete_attribute",
          {"path": ["DimensionIndexSequence", 1, "FunctionalGroupPointer"]},
          ("iod-attribute-presence",), "Remove Functional Group Pointer (0020,9167) from Dimension Index Sequence Item 2, whose Dimension Index Pointer names an Attribute of the Plane Position (Slide) Functional Group.",
          PS33_DIMENSION, "Functional Group Pointer is Type 1C, required when the Dimension Index Pointer names an Attribute within a Functional Group Sequence. " + ONLY.format(what="Attribute")),
    _case("IOD-PRS-013", "CP04-J2K-LOSSLESS-16F", "iod_delete_attribute", {"path": ["ImagedVolumeDepth"]},
          ("iod-attribute-presence", "core-image-profile"), "Remove Imaged Volume Depth (0048,0003) from a VOLUME image.",
          PS33_WSI_IMAGE, "Imaged Volume Depth is Type 1C, required when Image Type Value 3 is VOLUME. " + ALSO.format(rule="core-image-profile")),
    _case("IOD-PRS-014", "CP07-HTJ2K-RPCL-4F", "iod_insert_attribute", {"path": ["NumberOfFocalPlanes"], "value": 1},
          ("iod-attribute-presence",), "Insert Number of Focal Planes (0048,0013) = 1 while Extended Depth of Field is NO.",
          PS33_WSI_IMAGE, "Number of Focal Planes is Type 1C 'Required if Extended Depth of Field Value is YES' without permission otherwise, so PS3.5 7.4.2 forbids it. " + ONLY.format(what="condition")),
    _case("IOD-PRS-015", "CP11-MONO-EVRLE-4F", "iod_insert_attribute", {"path": ["PlanarConfiguration"], "value": 0},
          ("iod-attribute-presence",), "Insert Planar Configuration (0028,0006) = 0 into the MONOCHROME2 control with Samples per Pixel 1.",
          _cite("PS3.3", "C.7.6.3 Table C.7-11c; PS3.5 7.4.2", "part03/sect_C.7.6.3.html"),
          "Planar Configuration is Type 1C 'Required if Samples per Pixel has a Value greater than 1', so it shall be absent here. " + ONLY.format(what="condition")),
    _case("IOD-PRS-016", "CP02-JPEG-16F", "iod_insert_attribute", {"path": ["PresentationLUTShape"], "value": "IDENTITY"},
          ("iod-attribute-presence",), "Insert Presentation LUT Shape (2050,0020) = IDENTITY into the YBR_FULL_422 control.",
          PS33_WSI_IMAGE, "Presentation LUT Shape is Type 1C 'Required if Photometric Interpretation is MONOCHROME2', so it shall be absent for color. " + ONLY.format(what="condition")),
    _case("IOD-PRS-017", "CP04-J2K-LOSSLESS-16F", "iod_insert_attribute", {"path": ["LossyImageCompressionRatio"], "value": "1"},
          ("iod-attribute-presence",), "Insert Lossy Image Compression Ratio (0028,2112) = 1 into the lossless control whose Lossy Image Compression is 00.",
          PS33_WSI_IMAGE, "The Ratio is Type 1C 'Required if Lossy Image Compression is 01', so it shall be absent for 00. " + ONLY.format(what="condition")),
    # Enumerated Values.
    _case("IOD-ENU-001", "CP04-J2K-LOSSLESS-16F", "iod_set_value", {"path": ["PatientSex"], "value": "X"},
          ("iod-enumerated-values",), "Set the empty Type 2 Patient's Sex (0010,0040) to X.",
          PS33_PATIENT, "Patient's Sex has the Enumerated Values M, F, and O. " + ONLY.format(what="Value")),
    _case("IOD-ENU-002", "CP05-J2K-LOSSY-4F", "iod_insert_attribute", {"path": ["RecognizableVisualFeatures"], "value": "UNKNOWN"},
          ("iod-enumerated-values",), "Insert Recognizable Visual Features (0028,0302) = UNKNOWN.",
          PS33_GENERAL_IMAGE, "Recognizable Visual Features has the Enumerated Values YES and NO. " + ONLY.format(what="Value")),
    _case("IOD-ENU-003", "CP07-HTJ2K-RPCL-4F", "iod_insert_attribute", {"path": ["QualityControlImage"], "value": "MAYBE"},
          ("iod-enumerated-values",), "Insert Quality Control Image (0028,0300) = MAYBE.",
          PS33_GENERAL_IMAGE, "Quality Control Image has the Enumerated Values YES, NO, and BOTH. " + ONLY.format(what="Value")),
    _case("IOD-ENU-004", "CP01-EVRLE-4F-ANISO", "iod_insert_attribute", {"path": ["StereoPairsPresent"], "value": "MAYBE"},
          ("iod-enumerated-values",), "Insert Stereo Pairs Present (0022,0028) = MAYBE.",
          PS33_MFFG, "Stereo Pairs Present has the Enumerated Values YES and NO. " + ONLY.format(what="Value")),
    _case("IOD-ENU-005", "CP02-JPEG-16F", "iod_append_sequence_item",
          {"path": ["IssuerOfTheContainerIdentifierSequence"], "item": {"UniversalEntityID": "2.25.1", "UniversalEntityIDType": "OID"}},
          ("iod-enumerated-values",), "Add one Issuer of the Container Identifier Item with Universal Entity ID 2.25.1 and Universal Entity ID Type OID.",
          PS33_HL7, "Universal Entity ID Type has the Enumerated Values DNS, EUI64, ISO, URI, UUID, X400, and X500; OID is not one. " + ONLY.format(what="Value")),
    _case("IOD-ENU-006", "CP07-HTJ2K-RPCL-4F", "iod_set_value",
          {"path": [*FRAME_TYPE, "FrameType"], "value": ["ORIGINAL", "SECONDARY", "VOLUME", "NONE"]},
          ("iod-enumerated-values", "core-image-profile"), "Set the shared Frame Type (0008,9007) Value 2 from PRIMARY to SECONDARY.",
          PS33_FRAME_TYPE, "Frame Type Values follow Image Type, whose Value 2 shall be PRIMARY (C.8.12.4.1.1). " + ALSO.format(rule="core-image-profile")),
    _case("IOD-ENU-007", "CP11-MONO-EVRLE-4F", "iod_set_value", {"path": ["RescaleIntercept"], "value": "1"},
          ("iod-enumerated-values", "monochrome-presentation"), "Set Rescale Intercept (0028,1052) from 0 to 1 on the MONOCHROME2 control.",
          PS33_WSI_IMAGE, "Rescale Intercept has the Enumerated Value 0. " + ALSO.format(rule="monochrome-presentation")),
    _case("IOD-ENU-008", "CP09-J2K-LOSSLESS-4F", "iod_set_value",
          {"path": ["ImageType"], "value": ["ORIGINAL", "SECONDARY", "VOLUME", "NONE"]},
          ("iod-enumerated-values", "core-image-profile"), "Set Image Type (0008,0008) Value 2 from PRIMARY to SECONDARY.",
          PS33_WSI_IMAGE, "Image Type Value 2 shall be PRIMARY in this IOD (C.8.12.4.1.1). " + ALSO.format(rule="core-image-profile")),
    # VR and VM (explicit VR controls).
    _case("IOD-VRM-001", "CP02-JPEG-16F", "iod_change_vr", {"path": ["Manufacturer"], "vr": "SH"},
          ("iod-vr-vm",), "Re-encode Manufacturer (0008,0070) with explicit VR SH instead of LO, value unchanged.",
          PS36_REGISTRY, "PS3.6 gives Manufacturer the VR LO. " + ONLY.format(what="encoding")),
    _case("IOD-VRM-002", "CP09-J2K-LOSSLESS-4F", "iod_change_vr", {"path": ["StudyDescription"], "vr": "LT"},
          ("iod-vr-vm",), "Re-encode Study Description (0008,1030) with explicit VR LT instead of LO, value unchanged.",
          PS36_REGISTRY, "PS3.6 gives Study Description the VR LO. " + ONLY.format(what="encoding")),
    _case("IOD-VRM-003", "CP03-JPEG-1F", "iod_change_vr",
          {"path": ["SpecimenDescriptionSequence", 0, "SpecimenShortDescription"], "vr": "UC"},
          ("iod-vr-vm",), "Re-encode Specimen Short Description (0040,0600) in the Specimen Description Item with explicit VR UC instead of LO.",
          PS36_REGISTRY, "PS3.6 gives Specimen Short Description the VR LO. " + ONLY.format(what="encoding")),
    _case("IOD-VRM-004", "CP04-J2K-LOSSLESS-16F", "iod_change_vr",
          {"path": ["ContainerTypeCodeSequence", 0, "CodeValue"], "vr": "LO"},
          ("iod-vr-vm",), "Re-encode Code Value (0008,0100) of the Container Type Code Item with explicit VR LO instead of SH.",
          PS36_REGISTRY, "PS3.6 gives Code Value the VR SH. " + ONLY.format(what="encoding")),
    _case("IOD-VRM-005", "CP01-EVRLE-4F-ANISO", "iod_change_vr",
          {"path": ["OpticalPathSequence", 0, "OpticalPathDescription"], "vr": "LT"},
          ("iod-vr-vm",), "Re-encode Optical Path Description (0048,0107) in the Optical Path Item with explicit VR LT instead of ST.",
          PS36_REGISTRY, "PS3.6 gives Optical Path Description the VR ST. " + ONLY.format(what="encoding")),
    _case("IOD-VRM-006", "CP05-J2K-LOSSY-4F", "iod_change_vr", {"path": [*PIXEL_MEASURES, "SliceThickness"], "vr": "LO"},
          ("iod-vr-vm",), "Re-encode the shared Slice Thickness (0018,0050) with explicit VR LO instead of DS, text unchanged.",
          PS36_REGISTRY, "PS3.6 gives Slice Thickness the VR DS. " + ONLY.format(what="encoding")),
    _case("IOD-VRM-007", "CP11-MONO-EVRLE-4F", "iod_change_vr",
          {"path": ["PerFrameFunctionalGroupsSequence", 0, "PlanePositionSlideSequence", 0, "ZOffsetInSlideCoordinateSystem"], "vr": "LO"},
          ("iod-vr-vm",), "Re-encode Z Offset in Slide Coordinate System (0040,074A) of Per-Frame Item 1 with explicit VR LO instead of DS.",
          PS36_REGISTRY, "PS3.6 gives Z Offset in Slide Coordinate System the VR DS. " + ONLY.format(what="encoding")),
    _case("IOD-VRM-008", "CP06-HTJ2K-LOSSLESS-16F", "iod_set_value", {"path": ["Manufacturer"], "value": ["wsi-dicom", "second"]},
          ("iod-vr-vm",), "Give Manufacturer (0008,0070) two Values, wsi-dicom\\second.",
          PS36_REGISTRY, "PS3.6 gives Manufacturer VM 1. " + ONLY.format(what="multiplicity")),
    _case("IOD-VRM-009", "CP07-HTJ2K-RPCL-4F", "iod_set_value",
          {"path": ["SpecimenDescriptionSequence", 0, "SpecimenShortDescription"], "value": ["Research placeholder", "specimen"]},
          ("iod-vr-vm",), "Give Specimen Short Description (0040,0600) two Values in the Specimen Description Item.",
          PS36_REGISTRY, "PS3.6 gives Specimen Short Description VM 1. " + ONLY.format(what="multiplicity")),
    _case("IOD-VRM-010", "CP14-MONO16-EVRLE", "iod_set_value",
          {"path": ["ContainerTypeCodeSequence", 0, "CodeMeaning"], "value": ["Microscope slide", "slide"]},
          ("iod-vr-vm",), "Give Code Meaning (0008,0104) of the Container Type Code Item two Values.",
          PS36_REGISTRY, "PS3.6 gives Code Meaning VM 1. " + ONLY.format(what="multiplicity")),
    _case("IOD-VRM-011", "CP08-HTJ2K-LOSSY-4F", "iod_set_value", {"path": [*PIXEL_MEASURES, "SliceThickness"], "value": ["0.001", "0.001"]},
          ("iod-vr-vm",), "Give the shared Slice Thickness (0018,0050) two Values, 0.001\\0.001.",
          PS36_REGISTRY, "PS3.6 gives Slice Thickness VM 1. " + ONLY.format(what="multiplicity")),
    _case("IOD-VRM-012", "CP10-EVRLE-16F", "iod_set_value",
          {"path": ["PerFrameFunctionalGroupsSequence", 3, "PlanePositionSlideSequence", 0, "ZOffsetInSlideCoordinateSystem"], "value": ["0", "0"]},
          ("iod-vr-vm",), "Give Z Offset in Slide Coordinate System (0040,074A) of Per-Frame Item 4 two Values, 0\\0.",
          PS36_REGISTRY, "PS3.6 gives Z Offset in Slide Coordinate System VM 1. " + ONLY.format(what="multiplicity")),
    # PS3.5 Value formats.
    _case("IOD-FMT-001", "CP03-JPEG-1F", "iod_set_value", {"path": ["PyramidUID"], "value": LEADING_ZERO_UID},
          ("iod-value-format",), f"Set Pyramid UID (0008,0019) to {LEADING_ZERO_UID}, whose third component has a leading zero.",
          PS35_UID, "UID components shall not have leading zeros (PS3.5 9.1). " + ONLY.format(what="Value")),
    _case("IOD-FMT-002", "CP11-MONO-EVRLE-4F", "iod_set_value",
          {"paths": [["DimensionOrganizationSequence", 0, "DimensionOrganizationUID"],
                     ["DimensionIndexSequence", 0, "DimensionOrganizationUID"],
                     ["DimensionIndexSequence", 1, "DimensionOrganizationUID"]],
           "value": LEADING_ZERO_UID},
          ("iod-value-format",), f"Replace the one Dimension Organization UID (0020,9164) with {LEADING_ZERO_UID} at its three references, keeping them consistent.",
          PS35_UID, "UID components shall not have leading zeros; all references still agree, so only the format is wrong. " + ONLY.format(what="Value")),
    _case("IOD-FMT-003", "CP04-J2K-LOSSLESS-16F", "iod_set_value", {"path": ["StudyDate"], "value": "20261301"},
          ("iod-value-format",), "Set Study Date (0008,0020) to 20261301 (month 13).",
          PS35_VR, "DA is YYYYMMDD of the Gregorian calendar. " + ONLY.format(what="Value")),
    _case("IOD-FMT-004", "CP05-J2K-LOSSY-4F", "iod_set_value", {"path": ["ContentDate"], "value": "20260230"},
          ("iod-value-format",), "Set Content Date (0008,0023) to 20260230 (30 February).",
          PS35_VR, "DA is a Gregorian calendar date; 30 February does not exist. " + ONLY.format(what="Value")),
    _case("IOD-FMT-005", "CP06-HTJ2K-LOSSLESS-16F", "iod_set_value", {"path": ["StudyTime"], "value": "250000"},
          ("iod-value-format",), "Set Study Time (0008,0030) to 250000 (hour 25).",
          PS35_VR, "TM hours range from 00 to 23. " + ONLY.format(what="Value")),
    _case("IOD-FMT-006", "CP13-IMPLICIT-TILED-FULL", "iod_set_value", {"path": ["StudyTime"], "value": "12:30:00"},
          ("iod-value-format",), "Set Study Time (0008,0030) to 12:30:00 in the implicit VR control.",
          PS35_VR, "TM is HHMMSS.FFFFFF without separators. " + ONLY.format(what="Value")),
    _case("IOD-FMT-007", "CP07-HTJ2K-RPCL-4F", "iod_set_value", {"path": ["AcquisitionDateTime"], "value": "20261301000000"},
          ("iod-value-format",), "Set Acquisition DateTime (0008,002A) to 20261301000000 (month 13).",
          PS35_VR, "DT months range from 01 to 12. " + ONLY.format(what="Value")),
    _case("IOD-FMT-008", "CP08-HTJ2K-LOSSY-4F", "iod_insert_attribute", {"path": ["BodyPartExamined"], "value": "skin"},
          ("iod-value-format",), "Insert the Type 3 Body Part Examined (0018,0015) = skin (lowercase CS).",
          PS35_VR, "CS permits uppercase letters, digits, space, and underscore. " + ONLY.format(what="Value")),
    _case("IOD-FMT-009", "CP09-J2K-LOSSLESS-4F", "iod_set_value",
          {"path": [*FRAME_TYPE, "FrameType"], "value": ["ORIGINAL", "PRIMARY", "VOLUME", "none"]},
          ("iod-value-format", "core-image-profile"), "Set the shared Frame Type (0008,9007) Value 4 from NONE to lowercase none.",
          PS35_VR, "CS permits uppercase letters only. " + ALSO.format(rule="core-image-profile")),
    _case("IOD-FMT-010", "CP01-EVRLE-4F-ANISO", "iod_set_value", {"path": ["StudyDescription"], "value": "Research placeholder\r\nWSI export"},
          ("iod-value-format",), "Insert CR LF (0DH 0AH) into Study Description (0008,1030).",
          PS35_VR, "LO excludes control characters other than ESC. " + ONLY.format(what="Value")),
    _case("IOD-FMT-011", "CP02-JPEG-16F", "iod_set_value",
          {"path": ["SpecimenDescriptionSequence", 0, "SpecimenShortDescription"], "value": "Research\r\nplaceholder specimen"},
          ("iod-value-format",), "Insert CR LF (0DH 0AH) into Specimen Short Description (0040,0600) of the Specimen Description Item.",
          PS35_VR, "LO excludes control characters other than ESC. " + ONLY.format(what="Value")),
    _case("IOD-FMT-012", "CP03-JPEG-1F", "iod_set_value",
          {"path": ["ContainerTypeCodeSequence", 0, "CodeMeaning"], "value": "Microscope\nslide"},
          ("iod-value-format",), "Insert LF (0AH) into Code Meaning (0008,0104) of the Container Type Code Item.",
          PS35_VR, "LO excludes control characters other than ESC. " + ONLY.format(what="Value")),
    _case("IOD-FMT-013", "CP04-J2K-LOSSLESS-16F", "iod_set_value",
          {"path": ["ImageOrientationSlide"], "value": ["1.00000000000000000", "0", "0", "0", "1", "0"]},
          ("iod-value-format",), "Write Image Orientation (Slide) (0048,0102) Value 1 as the 19-byte DS 1.00000000000000000.",
          PS35_VR, "A DS Value is at most 16 bytes. " + ONLY.format(what="Value text")),
    _case("IOD-FMT-014", "CP05-J2K-LOSSY-4F", "iod_set_value", {"path": [*PIXEL_MEASURES, "SliceThickness"], "value": "0.00100000000000000"},
          ("iod-value-format",), "Write the shared Slice Thickness (0018,0050) as the 19-byte DS 0.00100000000000000.",
          PS35_VR, "A DS Value is at most 16 bytes. " + ONLY.format(what="Value text")),
    _case("IOD-FMT-015", "CP14-MONO16-EVRLE", "iod_set_value",
          {"path": ["PerFrameFunctionalGroupsSequence", 0, "PlanePositionSlideSequence", 0, "XOffsetInSlideCoordinateSystem"], "value": "0.00000000000000000"},
          ("iod-value-format",), "Write X Offset in Slide Coordinate System (0040,072A) of Per-Frame Item 1 as the 19-byte DS 0.00000000000000000.",
          PS35_VR, "A DS Value is at most 16 bytes. " + ONLY.format(what="Value text")),
    _case("IOD-FMT-016", "CP07-HTJ2K-RPCL-4F", "iod_set_value", {"path": ["InstanceNumber"], "value": "0000000000001"},
          ("iod-value-format",), "Write Instance Number (0020,0013) as the 13-byte IS 0000000000001.",
          PS35_VR, "An IS Value is at most 12 bytes. " + ONLY.format(what="Value text")),
    _case("IOD-FMT-017", "CP06-HTJ2K-LOSSLESS-16F", "iod_set_value", {"path": ["ReferringPhysicianName"], "value": "A^B^C^D^E^F"},
          ("iod-value-format",), "Set Referring Physician's Name (0008,0090) to A^B^C^D^E^F, six components.",
          PS35_VR, "A PN component group has at most five components. " + ONLY.format(what="Value")),
    # Sequence Item counts.
    _case("IOD-SEQ-001", "CP04-J2K-LOSSLESS-16F", "iod_duplicate_sequence_item",
          {"path": ["OpticalPathSequence", 0, "IlluminationColorCodeSequence"], "item_index": 0},
          ("iod-sequence-items",), "Append a copy of the Illumination Color Code Sequence Item within the Optical Path Item (2 Items).",
          PS33_OPTICAL, "Only a single Item shall be included in Illumination Color Code Sequence. " + ONLY.format(what="Item count")),
    _case("IOD-SEQ-002", "CP07-HTJ2K-RPCL-4F", "iod_duplicate_sequence_item",
          {"path": ["PerFrameFunctionalGroupsSequence", 1, "PlanePositionSlideSequence"], "item_index": 0},
          ("iod-sequence-items",), "Append a copy of the Plane Position (Slide) Item of Per-Frame Item 2 (2 Items).",
          PS33_PLANE, "Only a single Item shall be included in Plane Position (Slide) Sequence. " + ONLY.format(what="Item count")),
    _case("IOD-SEQ-003", "CP08-HTJ2K-LOSSY-4F", "iod_duplicate_sequence_item",
          {"path": ["PerFrameFunctionalGroupsSequence", 0, "FrameContentSequence"], "item_index": 0},
          ("iod-sequence-items",), "Append a copy of the Frame Content Item of Per-Frame Item 1 (2 Items).",
          PS33_FRAME_CONTENT, "Only a single Item shall be included in Frame Content Sequence. " + ONLY.format(what="Item count")),
    _case("IOD-SEQ-004", "CP05-J2K-LOSSY-4F", "iod_duplicate_sequence_item",
          {"path": [*SHARED, "PixelMeasuresSequence"], "item_index": 0},
          ("iod-sequence-items", "core-image-profile"), "Append a copy of the shared Pixel Measures Item (2 Items).",
          PS33_PIXEL_MEASURES, "Only a single Item shall be included in Pixel Measures Sequence. " + ALSO.format(rule="core-image-profile")),
    _case("IOD-SEQ-005", "CP01-EVRLE-4F-ANISO", "iod_duplicate_sequence_item",
          {"path": [*SHARED, "OpticalPathIdentificationSequence"], "item_index": 0},
          ("iod-sequence-items", "optical-path-structure"), "Append a copy of the shared Optical Path Identification Item (2 Items).",
          PS33_PATH_ID, "Only a single Item shall be included in Optical Path Identification Sequence. " + ALSO.format(rule="optical-path-structure")),
    _case("IOD-SEQ-006", "CP02-JPEG-16F", "iod_duplicate_sequence_item",
          {"path": ["TotalPixelMatrixOriginSequence"], "item_index": 0},
          ("iod-sequence-items", "slide-coordinate-system"), "Append a copy of the Total Pixel Matrix Origin Item (2 Items).",
          PS33_TILE_ORG, "Only a single Item shall be included in Total Pixel Matrix Origin Sequence. " + ALSO.format(rule="slide-coordinate-system")),
    _case("IOD-SEQ-007", "CP03-JPEG-1F", "iod_duplicate_sequence_item",
          {"path": ["ContainerTypeCodeSequence"], "item_index": 0},
          ("iod-sequence-items", "specimen-container"), "Append a copy of the Container Type Code Item (2 Items).",
          PS33_SPECIMEN, "Zero or one Item shall be included in Container Type Code Sequence. " + ALSO.format(rule="specimen-container")),
    _case("IOD-SEQ-008", "CP06-HTJ2K-LOSSLESS-16F", "iod_duplicate_sequence_item",
          {"path": [*SHARED, "WholeSlideMicroscopyImageFrameTypeSequence"], "item_index": 0},
          ("iod-sequence-items", "core-image-profile"), "Append a copy of the shared Whole Slide Microscopy Image Frame Type Item (2 Items).",
          PS33_FRAME_TYPE, "Only a single Item shall be included in this Sequence. " + ALSO.format(rule="core-image-profile")),
    # File Meta Information.
    _case("IOD-FMI-001", "CP11-MONO-EVRLE-4F", "file_meta_dataset_sop_mismatch", {},
          ("file-meta", "identity-set"), "After serialization, patch the File Meta Media Storage SOP Instance UID (0002,0003) bytes to a different same-length valid UID.",
          PS310_META, "Media Storage SOP Instance UID identifies the Data Set's SOP Instance. " + ALSO.format(rule="identity-set")),
    _case("IOD-FMI-002", "CP03-JPEG-1F", "file_meta_replace_value",
          {"tag": "(0002,0002)", "value": "1.2.840.10008.5.1.4.1.1.77.1.2"},
          ("file-meta", "identity-set"), "Replace the File Meta Media Storage SOP Class UID (0002,0002) with VL Microscopic Image Storage 1.2.840.10008.5.1.4.1.1.77.1.2 and rewrite the Group Length.",
          PS310_META, "Media Storage SOP Class UID identifies the SOP Class of the Data Set. " + ALSO.format(rule="identity-set")),
    _case("IOD-FMI-003", "CP05-J2K-LOSSY-4F", "file_meta_replace_value", {"tag": "(0002,0001)", "value_hex": "0002"},
          ("file-meta",), "Replace File Meta Information Version (0002,0001) bytes 00H 01H with 00H 02H.",
          PS310_META, "Version 1 is 00H 01H; with bit 0 of the second byte clear the header does not identify version 1. " + ONLY.format(what="element")),
    _case("IOD-FMI-004", "CP09-J2K-LOSSLESS-4F", "file_meta_remove_element", {"tag": "(0002,0001)"},
          ("file-meta",), "Remove the Type 1 File Meta Information Version (0002,0001) element and rewrite the Group Length.",
          PS310_META, "File Meta Information Version is Type 1. " + ONLY.format(what="element")),
    _case("IOD-FMI-005", "CP08-HTJ2K-LOSSY-4F", "file_meta_remove_element", {"tag": "(0002,0002)"},
          ("file-meta",), "Remove the Type 1 Media Storage SOP Class UID (0002,0002) element and rewrite the Group Length.",
          PS310_META, "Media Storage SOP Class UID is Type 1. " + ONLY.format(what="element")),
    _case("IOD-FMI-006", "CP10-EVRLE-16F", "file_meta_remove_element", {"tag": "(0002,0003)"},
          ("file-meta",), "Remove the Type 1 Media Storage SOP Instance UID (0002,0003) element and rewrite the Group Length.",
          PS310_META, "Media Storage SOP Instance UID is Type 1. " + ONLY.format(what="element")),
    _case("IOD-FMI-007", "CP06-HTJ2K-LOSSLESS-16F", "file_meta_remove_element", {"tag": "(0002,0012)"},
          ("file-meta",), "Remove the Type 1 Implementation Class UID (0002,0012) element and rewrite the Group Length.",
          PS310_META, "Implementation Class UID is Type 1. " + ONLY.format(what="element")),
    _case("IOD-FMI-008", "CP01-EVRLE-4F-ANISO", "file_meta_replace_value", {"tag": "(0002,0012)", "value": LEADING_ZERO_UID},
          ("file-meta",), f"Replace Implementation Class UID (0002,0012) with {LEADING_ZERO_UID} and rewrite the Group Length.",
          _cite("PS3.10", "7.1 Table 7.1-1; PS3.5 9.1", "part10/chapter_7.html#sect_7.1"),
          "UID components shall not have leading zeros; the File Meta check owns group 0002 Values. " + ONLY.format(what="element")),
    _case("IOD-FMI-009", "CP07-HTJ2K-RPCL-4F", "file_meta_replace_value", {"tag": "(0002,0013)", "value": "WSI-DICOM-BENCH-OVERLONG"},
          ("file-meta",), "Replace Implementation Version Name (0002,0013) with the 24-character WSI-DICOM-BENCH-OVERLONG and rewrite the Group Length.",
          PS310_META, "Implementation Version Name has up to 16 characters (SH). " + ONLY.format(what="element")),
)
