"""Single-defect Data Set encoding cases of the v6 ``requirement-statement-evaluation-v1`` cohort.

Defects that pydicom would normalize away on writing (element order, VR and reserved bytes,
delimiter lengths, Group Lengths, text bytes) are written into the encoded Data Set with
``encoding_rewrite``; the rest use ``iod_edits``. Expectations are set as for the rest of
the cohort: by running the frozen candidate and adjudicating each result against DICOM 2026c.
"""

from __future__ import annotations

from .iod_amendment_cases import _case as _spec, _cite, _code, _edits, _op


PS35_REPERTOIRE = _cite("PS3.5", "6.1.1", "part05/chapter_6.html#sect_6.1.1")
PS35_EXTENDED_REPERTOIRE = _cite("PS3.5", "6.1.2.2", "part05/chapter_6.html#sect_6.1.2.2")
PS35_CODE_ELEMENTS = _cite("PS3.5", "6.1.2.5.1", "part05/chapter_6.html#sect_6.1.2.5.1")
PS35_LINE_RESET = _cite("PS3.5", "6.1.2.5.3", "part05/chapter_6.html#sect_6.1.2.5.3")
PS35_VALUE_REPRESENTATIONS = _cite("PS3.5", "6.2", "part05/sect_6.2.html#sect_6.2")
PS35_PN_GROUPS = _cite("PS3.5", "6.2.1.2", "part05/sect_6.2.html#sect_6.2.1.2")
PS35_ITEMS = _cite("PS3.5", "7.5.1", "part05/chapter_7.html#sect_7.5.1")
PS35_PRIVATE_TAGS = _cite("PS3.5", "7.8.1", "part05/chapter_7.html#sect_7.8.1")
PS35_IMPLICIT_LITTLE = _cite("PS3.5", "A.1", "part05/chapter_A.html#sect_A.1")
PS35_EXPLICIT_LITTLE = _cite("PS3.5", "A.2", "part05/chapter_A.html#sect_A.2")
PS35_ENCAPSULATED_SYNTAXES = _cite("PS3.5", "A.4", "part05/chapter_A.html#sect_A.4")
PS310_DATA_SET = _cite("PS3.10", "7.2", "part10/chapter_7.html#sect_7.2")
PS33_SOP_COMMON = _cite("PS3.3", "C.12.1", "part03/sect_C.12.html#sect_C.12.1")
PS33_CHARACTER_SET = _cite("PS3.3", "C.12.1.1.2", "part03/sect_C.12.html#sect_C.12.1.1.2")
PS33_SIGNATURES = _cite("PS3.3", "C.12.1.1.3 Table C.12-6", "part03/sect_C.12.html#sect_C.12.1.1.3")
PS33_PRIVATE_DEFINITIONS = _cite("PS3.3", "C.12.1.1.7.1", "part03/sect_C.12.html#sect_C.12.1.1.7.1")
PS33_TIMEZONE = _cite("PS3.3", "C.12.1.1.8", "part03/sect_C.12.html#sect_C.12.1.1.8")

ENCODED_ONLY = "Only the encoding rule reads this from the encoded bytes; the parser normalizes it away."
IMPLICIT_LITTLE_ENDIAN = "1.2.840.10008.1.2"
# A private Sequence Item holding US or OW Values written Big Endian, under each Little
# Endian encoding: Implicit VR (an undefined-length Sequence), Explicit VR, and encapsulated.
BIG_ENDIAN_VALUES = (
    ("(0028,1101)", "US", "010000000010", "Red Palette Color Lookup Table Descriptor (0028,1101) 256\\0\\16"),
    ("(0028,1222)", "OW", "00000002000a00140001000400ff",
     "Segmented Green Palette Color Lookup Table Data (0028,1222) with a discrete and a linear segment"),
    ("(0028,3002)", "US", "010000000008", "LUT Descriptor (0028,3002) 256\\0\\8"),
)


def _case(case_id, control, mutation, parameters, requirements, changed, citation, rationale,
          expected) -> dict:
    return {**_spec(case_id, control, mutation, parameters, list(expected), changed, citation, rationale),
            "requirement_ids": list(requirements)}


def _rewrite(case_id, control, operations, requirements, changed, citation, rationale,
             expected=("encoding",), **before) -> dict:
    """An ``encoding_rewrite`` case; ``edits``, ``lengths`` or ``transfer_syntax`` apply before
    the encoded-byte ``operations``."""
    return _case(case_id, control, "encoding_rewrite", {**before, "operations": operations},
                 requirements, changed, citation, rationale, expected)


def _edit(case_id, control, operations, requirements, changed, citation, rationale,
          expected=("encoding",)) -> dict:
    """An ``iod_edits`` case."""
    return _case(case_id, control, "iod_edits", _edits(*operations), requirements, changed,
                 citation, rationale, expected)


def _element(tag: str, vr: str, **value) -> dict:
    """One element as written: ``text`` (with its ``encoding``), ``value_hex`` or ``items``."""
    return {"tag": tag, "vr": vr, **value}


def _creator(text: str = "ACME", **fields) -> dict:
    """The Private Creator (0029,0010) of the private block the cases use."""
    return _element("(0029,0010)", "LO", text=text, **fields)


def _private_sequence(*item: dict, **fields) -> dict:
    """Private Sequence (0029,1001) with one Item holding ``item``."""
    return {"tag": "(0029,1001)", "vr": "SQ", **fields, "items": [list(item)]}


def _insert(into: list, *elements: dict) -> dict:
    """Insert encoded ``elements`` into the Data Set at ``into``, at their sorted position."""
    return {"op": "insert", "into": into, "elements": list(elements)}


def _set_value(path: list, value_hex: str) -> dict:
    return {"op": "set_value", "path": path, "value_hex": value_hex}


def _describe(value_hex: str) -> dict:
    """Replace the encoded Optical Path Description (0048,0107) of the Optical Path Item."""
    return _set_value(["OpticalPathSequence", 0, "OpticalPathDescription"], value_hex)


def _character_set(value: str | list[str]) -> list[dict]:
    return [_op("insert", ["SpecificCharacterSet"], value)]


def _signed(transfer_syntax: str, signed_at: str) -> list[dict]:
    """A MAC Parameters Item signing Patient ID and the Digital Signatures Item that uses it."""
    return [
        _op("insert", ["MACParametersSequence"], [{
            "MACIDNumber": 1, "MACAlgorithm": "SHA256", "DataElementsSigned": [0x0010_0020],
            "MACCalculationTransferSyntaxUID": transfer_syntax,
        }]),
        _op("insert", ["DigitalSignaturesSequence"], [{
            "MACIDNumber": 1, "DigitalSignatureUID": "2.25.1000000000000000000000000000000001",
            "CertificateType": "X509_1993_SIG", "CertificateOfSigner": "0000", "Signature": "0000",
            "DigitalSignatureDateTime": signed_at,
        }]),
    ]


def _characteristics(status: str, **fields) -> list[dict]:
    """A Private Data Element Characteristics Item for the ACME block of group 0029."""
    return [_op("insert", ["PrivateDataElementCharacteristicsSequence"], [{
        "PrivateGroupReference": 0x0029, "PrivateCreatorReference": "ACME",
        "BlockIdentifyingInformationStatus": status, **fields,
    }])]


def _defined(multiplicity: int | list[int], vr: str, **fields) -> list[dict]:
    """A SAFE block whose one definition, of element 01 (AcmeValue), has ``multiplicity``."""
    return _characteristics("SAFE", PrivateDataElementDefinitionSequence=[{
        "PrivateDataElement": 1, "PrivateDataElementValueMultiplicity": multiplicity,
        "PrivateDataElementValueRepresentation": vr, "PrivateDataElementKeyword": "AcmeValue",
        "PrivateDataElementName": "Acme Value", **fields,
    }])


def _mixed(nonidentifying: list[int], identifying: list[int]) -> list[dict]:
    """A MIXED block listing its nonidentifying and identifying element numbers as given."""
    return _characteristics("MIXED", NonidentifyingPrivateElements=nonidentifying,
                            DeidentificationActionSequence=[
                                {"IdentifyingPrivateElements": identifying, "DeidentificationAction": "D"}])


ENCODING_CASES = (
    _rewrite("REQ-ENC-001", "CP10-EVRLE-16F",
        [{"op": "swap", "path": ["StudyDate"], "with": "AcquisitionDate"}],
        ("Ps5_7_1_c4fdc1",),
        "Swap the encoded Study Date (0008,0020) and Acquisition Date (0008,0022) elements of the "
        "top-level Data Set.",
        _cite("PS3.5", "7.1", "part05/chapter_7.html#sect_7.1"),
        "Data Elements shall be in increasing tag order. " + ENCODED_ONLY),
    _rewrite("REQ-ENC-002", "CP01-EVRLE-4F-ANISO",
        [{"op": "duplicate", "path": ["OpticalPathSequence", 0, "OpticalPathIdentifier"]}],
        ("Ps5_7_5_1_a89833",),
        "Encode Optical Path Identifier (0048,0106) twice in the Optical Path Sequence Item.",
        PS35_ITEMS,
        "Within an Item each Data Element appears only once; the parser keeps one. " + ENCODED_ONLY),
    _rewrite("REQ-ENC-003", "CP10-EVRLE-16F",
        [_insert([], _creator(), _element("(0029,1002)", "LO", text="B"),
                 _element("(0029,1001)", "LO", text="A"))],
        ("Ps5_7_8_127399",),
        "Insert a private block whose (0029,1002) is encoded before (0029,1001).",
        _cite("PS3.5", "7.8", "part05/chapter_7.html#sect_7.8"),
        "Private Data Elements shall be in increasing tag order. " + ENCODED_ONLY),
    _rewrite("REQ-ENC-004", "CP10-EVRLE-16F",
        [{"op": "set_vr", "path": ["OpticalPathSequence", 0, "ICCProfile"], "vr": "ob"}],
        ("Ps5_7_1_1_6bb31f",),
        "Encode the VR of ICC Profile (0028,2000) as lower-case \"ob\", with the Optical Path "
        "Sequence in Explicit Length.",
        _cite("PS3.5", "7.1.1", "part05/chapter_7.html#sect_7.1.1"),
        "The VR shall be upper-case letters. The parser reads unknown VR bytes as UN, which the VR "
        "check reports as UN where PS3.6 specifies OB, so both rules are expected.",
        expected=("encoding", "iod-vr-vm"),
        lengths=[{"path": ["OpticalPathSequence"], "sequence": "defined", "items": "defined"}]),
    _rewrite("REQ-ENC-005", "CP10-EVRLE-16F",
        [_insert([], _creator(),
                 _private_sequence(_creator(), _element("(0029,1001)", "XX", value_hex="0000")))],
        ("Ps5_7_8_ec77b4", "Ps5_7_8_2_2daf2a", "Ps5_A_2_465474"),
        "Insert a private Sequence (0029,1001) of Explicit Length whose Item holds a private "
        "element with VR bytes \"XX\" and a 32-bit Value Length.",
        PS35_EXPLICIT_LITTLE,
        "Private Data Elements shall use a VR of PS3.5 6.2 and Explicit VR Transfer Syntaxes "
        "encode one; the parser reads unknown VR bytes as UN. " + ENCODED_ONLY),
    _rewrite("REQ-ENC-006", "CP03-JPEG-1F",
        [_insert([], _creator(),
                 _private_sequence(_creator(), _element("(0029,1001)", "XX", value_hex="0000")))],
        ("Ps5_A_4_878ca2",),
        "As REQ-ENC-005 in the JPEG Baseline control.",
        PS35_ENCAPSULATED_SYNTAXES,
        "Encapsulated Transfer Syntaxes encode an Explicit VR of PS3.5 6.2. " + ENCODED_ONLY),
    _rewrite("REQ-ENC-007", "CP10-EVRLE-16F",
        [{"op": "set_reserved", "path": ["OpticalPathSequence", 0, "ICCProfile"], "hex": "0100"}],
        ("Ps5_7_1_2_6cc044",),
        "Set the two reserved bytes after the OB VR of ICC Profile (0028,2000) to 0100H.",
        _cite("PS3.5", "7.1.2", "part05/chapter_7.html#sect_7.1.2"),
        "Reserved bytes shall be 0000H; the parser does not decode them. " + ENCODED_ONLY),
    _rewrite("REQ-ENC-008", "CP10-EVRLE-16F",
        [_insert([], _element("(0008,0000)", "UL", value_hex="00000000"))],
        ("Ps5_7_2_e5da2e",),
        "Insert Group Length (0008,0000) = 0 before the group 0008 elements.",
        _cite("PS3.5", "7.2", "part05/chapter_7.html#sect_7.2"),
        "A Group Length, if present, shall be consistent with the encoding; the parser reads it "
        "as a retired element. " + ENCODED_ONLY),
    _rewrite("REQ-ENC-009", "CP10-EVRLE-16F",
        [{"op": "set_delimiter_length", "path": ["OpticalPathSequence"], "item": 0, "length": 4}],
        ("Ps5_7_5_1_aaae21",),
        "Set the Value Length of the Item Delimitation Item ending Optical Path Sequence Item 1 "
        "to 4.",
        PS35_ITEMS,
        "The Item Delimitation Item has Value Length 00000000H; the parser ignores its length. "
        + ENCODED_ONLY),
    _rewrite("REQ-ENC-010", "CP10-EVRLE-16F",
        [{"op": "set_delimiter_length", "path": ["OpticalPathSequence"], "item": None, "length": 2}],
        ("Ps5_7_5_2_29cc8f", "Ps5_7_5_2_94b19c"),
        "Set the Value Length of the Sequence Delimitation Item ending the Optical Path Sequence "
        "to 2.",
        _cite("PS3.5", "7.5.2", "part05/chapter_7.html#sect_7.5.2"),
        "The Sequence Delimitation Item has Value Length 00000000H and no Value; the parser "
        "ignores its length. " + ENCODED_ONLY),
    _rewrite("REQ-ENC-011", "CP10-EVRLE-16F", [_insert([], _element("(FFFF,0010)", "LO", text="X"))],
        ("Ps5_7_5_1_0563be",),
        "Insert (FFFF,0010) LO \"X\" after Pixel Data.",
        PS35_ITEMS,
        "Data Element Tags (FFFF,eeee) are reserved and shall not be used; the parser treats the "
        "odd group as private. " + ENCODED_ONLY),
    _rewrite("REQ-ENC-012", "CP10-EVRLE-16F", [_insert([], _element("(0003,0010)", "LO", text="X"))],
        ("Ps5_7_8_1_83055e",),
        "Insert (0003,0010) LO \"X\".",
        PS35_PRIVATE_TAGS,
        "Elements of groups 0001, 0003, 0005, 0007 and FFFF shall not be used. " + ENCODED_ONLY),
    _rewrite("REQ-ENC-013", "CP01-EVRLE-4F-ANISO",
        [_insert(["OpticalPathSequence", 0], _element("(0002,0010)", "UI", text="1.2.840.10008.1.2.1"))],
        ("Ps5_7_5_1_3363bd", "Ps10_7_1_3a8346"),
        "Insert Transfer Syntax UID (0002,0010) into the Optical Path Sequence Item.",
        PS35_ITEMS,
        "Groups 0000, 0002 and 0006 shall not be present within Sequence Items, and group 0002 "
        "belongs to the File Meta Information alone (PS3.10 7.1); the File Meta check reads the "
        "top level only. " + ENCODED_ONLY),
    _rewrite("REQ-ENC-014", "CP10-EVRLE-16F", [_insert([], _element("(5000,0005)", "US", value_hex="0100"))],
        ("Ps5_7_6_dea12f",),
        "Insert the retired Curve Dimensions (5000,0005) US 1.",
        _cite("PS3.5", "7.6", "part05/chapter_7.html#sect_7.6"),
        "Repeating Groups are allowed only in the even groups 6000-601E; the dictionary still "
        "registers 50xx. " + ENCODED_ONLY),
    _rewrite("REQ-ENC-015", "CP10-EVRLE-16F", [_insert([], _element("(0029,1001)", "LO", text="V"))],
        ("Ps5_7_8_1_645952",),
        "Insert private element (0029,1001) LO \"V\" without a Private Creator (0029,0010).",
        PS35_PRIVATE_TAGS,
        "Private Creator (gggg,0010) reserves the block (gggg,10xx). " + ENCODED_ONLY),
    _rewrite("REQ-ENC-016", "CP10-EVRLE-16F", [_insert([], _element("(0029,0001)", "LO", text="V"))],
        ("Ps5_7_8_1_8e6821",),
        "Insert private element (0029,0001) LO \"V\".",
        PS35_PRIVATE_TAGS,
        "The rules do not allow (gggg,0001-000F) or (gggg,0100-0FFF) in an odd group. " + ENCODED_ONLY),
    _rewrite("REQ-ENC-017", "CP10-EVRLE-16F", [_insert([], _creator("  "))],
        ("Ps5_7_8_1_783078",),
        "Insert Private Creator (0029,0010) holding only spaces.",
        PS35_PRIVATE_TAGS,
        "The implementer inserts an identification code to reserve a block. " + ENCODED_ONLY),
    _rewrite("REQ-ENC-018", "CP10-EVRLE-16F",
        [_insert([], _creator(), _element("(0029,0011)", "LO", text="ACME"))],
        ("Ps5_7_8_1_783078",),
        "Insert Private Creators (0029,0010) and (0029,0011) with the same identification code ACME.",
        PS35_PRIVATE_TAGS,
        "A Private Creator identifier may be used only once within a Group. " + ENCODED_ONLY),
    _rewrite("REQ-ENC-019", "CP10-EVRLE-16F", [_insert([], _creator("ACMÉ", encoding="latin-1"))],
        ("Ps5_7_8_1_9dc403",),
        "Declare Specific Character Set ISO_IR 100 and insert Private Creator (0029,0010) \"ACM\" "
        "followed by byte C9H.",
        PS35_PRIVATE_TAGS,
        "Private Creators use the Default Character Repertoire whatever Specific Character Set; the "
        "value-format check admits ISO_IR 100 text. " + ENCODED_ONLY,
        edits=_character_set("ISO_IR 100")),
    _rewrite("REQ-ENC-020", "CP10-EVRLE-16F", [_insert([], _creator("AC\\M"))],
        ("Ps5_7_8_1_8472d4",),
        "Re-encode the control in Implicit VR Little Endian and insert Private Creator (0029,0010) "
        "\"AC\\M\".",
        PS35_PRIVATE_TAGS,
        "A Private Creator has VM 1. The parser's dictionary gives Private Creators LO in Implicit "
        "VR, so the VR/VM check also counts two Values; both rules are expected.",
        expected=("encoding", "iod-vr-vm"),
        transfer_syntax=IMPLICIT_LITTLE_ENDIAN),
    _rewrite("REQ-ENC-021", "CP10-EVRLE-16F",
        [_insert([], _creator(), _private_sequence(_element("(6000,3000)", "OW", value_hex="0000")))],
        ("Ps5_7_8_2_f3885e",),
        "Insert a private Sequence (0029,1001) whose Item holds Overlay Data (6000,3000).",
        _cite("PS3.5", "7.8.2", "part05/chapter_7.html#sect_7.8.2"),
        "Overlay Data shall not be included within a Private Sequence Item. " + ENCODED_ONLY),
    _rewrite("REQ-ENC-022", "CP01-EVRLE-4F-ANISO",
        [_insert([], _creator()),
         _insert(["OpticalPathSequence", 0], _element("(0029,1001)", "LO", text="V"))],
        ("Ps5_7_8_1_195bb9",),
        "Insert Private Creator (0029,0010) at the top level and private element (0029,1001) into "
        "the Optical Path Sequence Item, which reserves no block.",
        PS35_PRIVATE_TAGS,
        "Items do not inherit the reservations of the Data Set that contains them. " + ENCODED_ONLY),
    _rewrite("REQ-ENC-023", "CP10-EVRLE-16F",
        [_insert(["OriginalAttributesSequence", 0, "ModifiedAttributesSequence", 0],
                 _element("(0029,1001)", "LO", text="V"))],
        ("Ps3_C_12_1_1_9_1_8190ee",),
        "Insert an Original Attributes Sequence Item whose Modified Attributes Sequence Item holds "
        "private element (0029,1001) without its Private Creator.",
        _cite("PS3.3", "C.12.1.1.9.1", "part03/sect_C.12.html#sect_C.12.1.1.9.1"),
        "Private Data Elements in the Modified Attributes Item shall be accompanied by their "
        "Private Creator. " + ENCODED_ONLY,
        edits=[_op("insert", ["OriginalAttributesSequence"], [{
            "AttributeModificationDateTime": "20240101000000+0000", "ModifyingSystem": "SYS",
            "ReasonForTheAttributeModification": "CORRECT", "SourceOfPreviousValues": "",
            "ModifiedAttributesSequence": [{"PatientID": "OLD"}],
        }])]),
    _rewrite("REQ-ENC-024", "CP10-EVRLE-16F",
        [{"op": "set_vr", "path": ["OpticalPathSequence", 0, "IlluminationTypeCodeSequence"], "vr": "UN"}],
        ("Ps5_6_2_2_894175",),
        "Encode the Undefined Length Illumination Type Code Sequence (0022,0016) with VR UN, its "
        "Items left in Explicit VR, inside an Explicit Length Optical Path Sequence.",
        _cite("PS3.5", "6.2.2", "part05/sect_6.2.html#sect_6.2.2"),
        "In Undefined Length Sequences a UN Value remains in Implicit VR form; the parser reads "
        "the Items as Explicit VR SQ. " + ENCODED_ONLY,
        lengths=[{"path": ["OpticalPathSequence"], "sequence": "defined", "items": "defined"}]),
    _rewrite("REQ-ENC-025", "CP14-MONO16-EVRLE", [{"op": "set_vr", "path": ["PixelData"], "vr": "OB"}],
        ("Ps5_A_2_abe7d8",),
        "Encode the 16-bit native Pixel Data (7FE0,0010) with VR OB.",
        PS35_EXPLICIT_LITTLE,
        "Native Pixel Data with Bits Allocated above 8 shall be OW. The Pixel Data structure check "
        "reports the top-level case too, so both rules are expected.",
        expected=("encoding", "pixel-structure")),
    _edit("REQ-ENC-026", "CP03-JPEG-1F", [_op("insert", ["IconImageSequence"], [{
            "SamplesPerPixel": 1, "PhotometricInterpretation": "MONOCHROME2", "Rows": 2, "Columns": 2,
            "BitsAllocated": 16, "BitsStored": 8, "HighBit": 7, "PixelRepresentation": 0,
            "PixelData": {"vr": "OB", "value": "00" * 8},
        }])],
        ("Ps5_A_4_7baed6",),
        "Insert an Icon Image Sequence Item with native 2x2 Pixel Data (7FE0,0010) of VR OB and "
        "Bits Allocated 16.",
        PS35_ENCAPSULATED_SYNTAXES,
        "Nested native Pixel Data with Bits Allocated above 8 shall be OW. An Icon Image is the "
        "only nested image, and its samples have 1 or 8 bits (PS3.3 C.7.6.1.1.6), so the pixel "
        "attribute check is expected as well.",
        expected=("encoding", "pixel-attributes")),
    _rewrite("REQ-ENC-027", "CP10-EVRLE-16F",
        [{"op": "patch_value", "path": ["OpticalPathSequence", 0, "ICCProfile"], "offset": 0,
          "hex": "00000263"}],
        ("Ps5_6_2_93b003",),
        "Set the ICC profile header size of ICC Profile (0028,2000) to 611, so the even 612-byte "
        "Value ends in pad byte 6EH.",
        PS35_VALUE_REPRESENTATIONS,
        "OB Values are padded with a single trailing NULL. The ICC Profile check also rejects bytes "
        "after the declared size that are not NULL padding, so both rules are expected.",
        expected=("encoding", "icc-profile")),
    _edit("REQ-ENC-030", "CP10-EVRLE-16F", _character_set(["ISO_IR 100", "ISO 2022 IR 100"]),
        ("Ps3_C_12_1_1_2_fd6abd",),
        "Insert Specific Character Set ISO_IR 100\\ISO 2022 IR 100.",
        PS33_CHARACTER_SET,
        "The same character set shall not be used more than once."),
    _edit("REQ-ENC-031", "CP10-EVRLE-16F", _character_set(["ISO 2022 IR 6", "ISO_IR 192"]),
        ("Ps3_C_12_1_1_2_fd82cf",),
        "Insert Specific Character Set ISO 2022 IR 6\\ISO_IR 192.",
        PS33_CHARACTER_SET,
        "ISO_IR 192, GB18030 and GBK may only be the single Value 1."),
    _rewrite("REQ-ENC-032", "CP10-EVRLE-16F", [_describe("44656661756c74206f70746963616c2070617468c0af")],
        ("Ps3_C_12_1_1_2_a2828b",),
        "Declare ISO_IR 192 and end Optical Path Description (0048,0107) in the overlong UTF-8 "
        "sequence C0H AFH.",
        PS33_CHARACTER_SET,
        "The minimal length UTF-8 encoding shall be used. The parser decodes the bytes to an ST "
        "escape that the value-format check admits. " + ENCODED_ONLY,
        edits=_character_set("ISO_IR 192")),
    _rewrite("REQ-ENC-033", "CP10-EVRLE-16F", [_describe("44656661756c74206f70746963616c2070617468c958")],
        ("Ps5_6_1_2_2_aaf21c",),
        "Put byte C9H in Optical Path Description (0048,0107) of the control without Specific "
        "Character Set.",
        PS35_EXTENDED_REPERTOIRE,
        "Extending the Default Character Repertoire needs Specific Character Set. The value-format "
        "check also rejects the decoded character and the presence check requires Specific "
        "Character Set, so all three rules are expected.",
        expected=("encoding", "iod-value-format", "iod-attribute-presence")),
    _rewrite("REQ-ENC-034", "CP10-EVRLE-16F", [_describe("44656661756c74206f70746963616c20706174688558")],
        ("Ps5_6_1_1_676368",),
        "Declare ISO_IR 100 and put the C1 byte 85H in Optical Path Description (0048,0107).",
        PS35_REPERTOIRE,
        "Characters from the C1 set shall not be used. The value-format check also rejects the "
        "decoded control character, so both rules are expected.",
        expected=("encoding", "iod-value-format"),
        edits=_character_set("ISO_IR 100")),
    _rewrite("REQ-ENC-035", "CP10-EVRLE-16F", [_describe("44656661756c74206f70746963616c20706174681b45")],
        ("Ps5_6_1_2_5_1_54e495", "Ps5_6_1_2_5_d4ec20"),
        "Declare ISO 2022 IR 100\\ISO 2022 IR 87 and end Optical Path Description (0048,0107) in "
        "ESC 04/05.",
        PS35_CODE_ELEMENTS,
        "ESC 04/05 is a C1 control function; the C1 code element shall not be used. " + ENCODED_ONLY,
        edits=_character_set(["ISO 2022 IR 100", "ISO 2022 IR 87"])),
    _rewrite("REQ-ENC-036", "CP10-EVRLE-16F", [_describe("44656661756c74206f70746963616c20706174681b6e")],
        ("Ps5_6_1_1_c5c47d", "Ps5_6_1_2_5_d4ec20"),
        "As REQ-ENC-035 with the locking shift ESC 06/14.",
        PS35_REPERTOIRE,
        "G0 and G1 are invoked in GL and GR; locking shifts shall not be used (6.1.2.5.2). "
        + ENCODED_ONLY,
        edits=_character_set(["ISO 2022 IR 100", "ISO 2022 IR 87"])),
    _rewrite("REQ-ENC-037", "CP10-EVRLE-16F", [_describe("44656661756c74201b242943b0a1")],
        ("Ps5_6_1_2_3_93d068", "Ps5_6_1_2_4_213779"),
        "Declare \\ISO 2022 IR 87 and designate ISO-IR 149 with ESC 02/04 02/09 04/03 in Optical "
        "Path Description (0048,0107).",
        _cite("PS3.5", "6.1.2.3", "part05/chapter_6.html#sect_6.1.2.3"),
        "Additional Coded Character Sets shall be named by Values of Specific Character Set "
        "(6.1.2.4). " + ENCODED_ONLY,
        edits=_character_set(["", "ISO 2022 IR 87"])),
    _rewrite("REQ-ENC-038", "CP10-EVRLE-16F", [_describe("44656661756c74201b244230211b2842")],
        ("Ps5_6_1_2_5_4_3ea86a", "Ps5_6_1_2_4_213779"),
        "Declare the single Value ISO_IR 100 and put ESC 02/04 04/02, a two-byte character and ESC "
        "02/08 04/02 in Optical Path Description (0048,0107).",
        _cite("PS3.5", "6.1.2.5.4", "part05/chapter_6.html#sect_6.1.2.5.4"),
        "With a single-valued Specific Character Set Code Extension shall not be used. " + ENCODED_ONLY,
        edits=_character_set("ISO_IR 100")),
    _rewrite("REQ-ENC-039", "CP10-EVRLE-16F", [_describe("44656661756c74201b244230211b2842")],
        ("Ps5_6_1_2_2_aaf21c", "Ps5_6_1_2_5_4_3ea86a", "Ps5_6_1_3_c65780"),
        "Put ESC 02/04 04/02, a two-byte character and ESC 02/08 04/02 in Optical Path Description "
        "(0048,0107) of the control without Specific Character Set.",
        PS35_EXTENDED_REPERTOIRE,
        "Code Extension needs Specific Character Set, and without it Code Extension shall not be "
        "used (6.1.2.5.4); ESC is ASCII, so no other check sees it. " + ENCODED_ONLY),
    _rewrite("REQ-ENC-040", "CP10-EVRLE-16F", [_describe("44656661756c74201b214058")],
        ("Ps5_6_1_2_5_1_1c6da1",),
        "Declare ISO 2022 IR 100\\ISO 2022 IR 87 and put the C0 designation ESC 02/01 04/00 in "
        "Optical Path Description (0048,0107).",
        PS35_CODE_ELEMENTS,
        "The primary control set is always the C0 code element; no escape sequence designates "
        "control sets. " + ENCODED_ONLY,
        edits=_character_set(["ISO 2022 IR 100", "ISO 2022 IR 87"])),
    _rewrite("REQ-ENC-041", "CP10-EVRLE-16F", [_describe("44656661756c74201b285a58")],
        ("Ps5_6_1_2_5_2_396321", "Ps5_6_1_3_c65780"),
        "As REQ-ENC-040 with ESC 02/08 05/10, which no PS3.3 table defines.",
        _cite("PS3.5", "6.1.2.5.2", "part05/chapter_6.html#sect_6.1.2.5.2"),
        "Only the escape sequences of PS3.3 Tables C.12-3 and C.12-4 shall be used, and ESC only "
        "for them (6.1.3). " + ENCODED_ONLY,
        edits=_character_set(["ISO 2022 IR 100", "ISO 2022 IR 87"])),
    _rewrite("REQ-ENC-042", "CP10-EVRLE-16F", [_describe("1b244230210d0a1b284244656661756c")],
        ("Ps5_6_1_2_5_3_68512a",),
        "Declare \\ISO 2022 IR 87 and leave ISO-IR 87 designated to G0 over the CR LF of Optical "
        "Path Description (0048,0107).",
        PS35_LINE_RESET,
        "The Value 1 character set shall be active before the end of a line. " + ENCODED_ONLY,
        edits=_character_set(["", "ISO 2022 IR 87"])),
    _rewrite("REQ-ENC-043", "CP10-EVRLE-16F", [_describe("1b242943b0a10d0ab0a1")],
        ("Ps5_6_1_2_5_3_4b3ce3", "Ps5_6_1_2_5_3_1fdc6c", "Ps5_6_1_2_3_2a236f"),
        "Declare \\ISO 2022 IR 149 and use ISO-IR 149 characters on the second line of Optical Path "
        "Description (0048,0107) without designating it again.",
        PS35_LINE_RESET,
        "Value 1 (empty) designates no G1 set at the start of a line, so the escape sequence shall "
        "precede the first use in each line (6.1.2.3). " + ENCODED_ONLY,
        edits=_character_set(["", "ISO 2022 IR 149"])),
    _rewrite("REQ-ENC-044", "CP10-EVRLE-16F", [_describe("44656661756c74206f70746963616c0a70617468")],
        ("Ps5_6_1_3_b90cab",),
        "Separate the lines of Optical Path Description (0048,0107) with a bare LF.",
        _cite("PS3.5", "6.1.3", "part05/chapter_6.html#sect_6.1.3"),
        "In ST, LT and UT a new line is CR LF. " + ENCODED_ONLY),
    _rewrite("REQ-ENC-045", "CP10-EVRLE-16F", [_set_value(["StudyDescription"], "1b2442305c1b2842")],
        ("Ps5_6_2_8c8195",),
        "Declare \\ISO 2022 IR 87 and make byte 5CH the second byte of a two-byte character of "
        "Study Description (0008,1030).",
        PS35_VALUE_REPRESENTATIONS,
        "5CH shall not be present in LO. The parser splits the Value there, so the VR/VM check also "
        "counts two Values; both rules are expected.",
        expected=("encoding", "iod-vr-vm"),
        edits=_character_set(["", "ISO 2022 IR 87"])),
    _rewrite("REQ-ENC-046", "CP10-EVRLE-16F",
        [_set_value(["AccessionNumber"], "1b2442" + "3021" * 17 + "1b2842")],
        ("Ps5_6_2_76a6fd",),
        "Declare \\ISO 2022 IR 87 and encode Accession Number (0008,0050) as 17 two-byte characters "
        "between escape sequences.",
        PS35_VALUE_REPRESENTATIONS,
        "SH holds 16 characters, escape sequences not counted; the value-format check leaves Code "
        "Extension Values to the encoded bytes. " + ENCODED_ONLY,
        edits=_character_set(["", "ISO 2022 IR 87"])),
    _rewrite("REQ-ENC-047", "CP10-EVRLE-16F", [_set_value(["ReferringPhysicianName"], "1b24423b331b2842")],
        ("Ps5_6_2_1_2_c9f7ed", "Ps5_6_2_1_2_951141"),
        "Declare \\ISO 2022 IR 87 and encode Referring Physician's Name (0008,0090) as two-byte "
        "characters in the alphabetic component group.",
        PS35_PN_GROUPS,
        "The alphabetic group uses the Value 1 set, without ISO 2022 escapes. " + ENCODED_ONLY,
        edits=_character_set(["", "ISO 2022 IR 87"])),
    _rewrite("REQ-ENC-048", "CP10-EVRLE-16F", [_set_value(["ReferringPhysicianName"], "e4b8ad5e4120")],
        ("Ps5_6_2_1_2_ca8329",),
        "Declare ISO_IR 192 and put U+4E2D in the alphabetic component group of Referring "
        "Physician's Name (0008,0090).",
        PS35_PN_GROUPS,
        "Under a multi-byte set without Code Extension the alphabetic group is drawn from "
        "U+0020-U+1FFF and the listed Japanese code points. " + ENCODED_ONLY,
        edits=_character_set("ISO_IR 192")),
    _rewrite("REQ-ENC-049", "CP10-EVRLE-16F", [_set_value(["ReferringPhysicianName"], "413d1b242943b0a15e42")],
        ("Ps5_6_2_1_2_46301a", "Ps5_6_2_1_2_8d573f"),
        "Declare ISO 2022 IR 100\\ISO 2022 IR 149 and keep ISO-IR 149 in G1 at the \"^\" of the "
        "ideographic group of Referring Physician's Name (0008,0090).",
        PS35_PN_GROUPS,
        "Before \"^\" and \"=\" the character set switches back to that of Value 1, which has a G1 "
        "set. " + ENCODED_ONLY,
        edits=_character_set(["ISO 2022 IR 100", "ISO 2022 IR 149"])),
    _rewrite("REQ-ENC-050", "CP10-EVRLE-16F", [_set_value(["ReferringPhysicianName"], "3d1b24423b33")],
        ("Ps5_6_2_1_2_ed7e68",),
        "Declare \\ISO 2022 IR 87 and end Referring Physician's Name (0008,0090) with ISO-IR 87 "
        "still designated to G0.",
        PS35_PN_GROUPS,
        "Without Value 1 the Default Character Repertoire shall be switched to at the end of the "
        "Value. " + ENCODED_ONLY,
        edits=_character_set(["", "ISO 2022 IR 87"])),
    _rewrite("REQ-ENC-051", "CP10-EVRLE-16F",
        [_set_value(["ReferringPhysicianName"], "59616d6164615e5461726f753d3d1b242943b0a1")],
        ("Ps5_6_2_1_2_12c186",),
        "Declare \\ISO 2022 IR 87 and designate ISO-IR 149 in the phonetic component group of "
        "Referring Physician's Name (0008,0090).",
        PS35_PN_GROUPS,
        "The phonetic group uses the sets of Specific Character Set Values 1 through n. " + ENCODED_ONLY,
        edits=_character_set(["", "ISO 2022 IR 87"])),
    _edit("REQ-ENC-052", "CP10-EVRLE-16F", [
        _op("insert", ["PatientSpeciesCodeSequence"], [_code("SCT", "448771007", "Canis lupus familiaris")]),
        _op("insert", ["AnatomicalOrientationType"], "QUADRUPED"),
        _op("insert", ["PatientBreedDescription"], ""),
        _op("insert", ["PatientBreedCodeSequence"], []),
        _op("insert", ["BreedRegistrationSequence"], []),
        _op("insert", ["ResponsiblePerson"], ""),
        _op("insert", ["ResponsibleOrganization"], ""),
        _op("set", ["PatientName"], "RESEARCH^PLACEHOLDER^ANON"),
    ],
        ("Ps5_6_2_ff8eab",),
        "Code the patient as Canis lupus familiaris, with the empty Type 2C veterinary Attributes "
        "and Anatomical Orientation Type QUADRUPED, and give Patient's Name (0010,0010) a third "
        "component.",
        PS35_VALUE_REPRESENTATIONS,
        "For veterinary use only the first two components are used and the rest shall not be "
        "present."),
    _edit("REQ-ENC-053", "CP10-EVRLE-16F", [_op("insert", ["TimezoneOffsetFromUTC"], "-0000")],
        ("Ps3_C_12_1_1_8_589a40",),
        "Insert Timezone Offset From UTC (0008,0201) = -0000.",
        PS33_TIMEZONE,
        "The offset for UTC shall be +0000."),
    _edit("REQ-ENC-054", "CP10-EVRLE-16F", [_op("insert", ["TimezoneOffsetFromUTC"], " +0100")],
        ("Ps3_C_12_1_1_8_5d989e",),
        "Insert Timezone Offset From UTC (0008,0201) = \" +0100\".",
        PS33_TIMEZONE,
        "Leading space characters shall not be present; SH admits them."),
    _edit("REQ-ENC-055", "CP10-EVRLE-16F", _signed("1.2.840.10008.1.2.1", "20240101120000"),
        ("Ps3_C_12_6_DigitalSignatureDateTime_c19323",),
        "Insert a MAC Parameters Sequence Item and a Digital Signatures Sequence Item whose Digital "
        "Signature DateTime (0400,0105) has no UTC offset.",
        PS33_SIGNATURES,
        "The Digital Signature DateTime shall include an offset from UTC."),
    _edit("REQ-ENC-056", "CP10-EVRLE-16F", _signed(IMPLICIT_LITTLE_ENDIAN, "20240101120000+0000"),
        ("Ps3_C_12_6_MACCalculationTransferSyntaxUID_c73a1b",),
        "As REQ-ENC-055 with a UTC offset and MAC Calculation Transfer Syntax UID (0400,0010) = "
        "Implicit VR Little Endian.",
        PS33_SIGNATURES,
        "Only Explicit VR Little Endian Transfer Syntaxes shall be used for the MAC calculation."),
    _edit("REQ-ENC-057", "CP10-EVRLE-16F", [_op("insert", ["EncryptedAttributesSequence"], [
            {"EncryptedContentTransferSyntaxUID": "1.2.840.10008.1.2.2", "EncryptedContent": "0000"}])],
        ("Ps3_C_12_1_EncryptedContentTransferSyntaxUID_6d1938",),
        "Insert an Encrypted Attributes Sequence Item whose Encrypted Content Transfer Syntax UID "
        "(0400,0510) is Explicit VR Big Endian.",
        PS33_SOP_COMMON,
        "Only Explicit VR Little Endian Transfer Syntaxes shall be used for the encrypted Data Set."),
    _edit("REQ-ENC-058", "CP10-EVRLE-16F", _defined([2, 2], "LO"),
        ("Ps3_C_12_1_1_7_1_45ff05",),
        "Insert a Private Data Element Characteristics Sequence Item whose definition gives the "
        "fixed multiplicity 2 as the range 2,2.",
        PS33_PRIVATE_DEFINITIONS,
        "A fixed multiplicity is a single integer Value."),
    _edit("REQ-ENC-059", "CP10-EVRLE-16F", _defined([1, 0], "SQ", PrivateDataElementNumberOfItems=[1, 0]),
        ("Ps3_C_12_1_1_7_1_30c8d1",),
        "As REQ-ENC-058 with Value Representation SQ and multiplicity 1,0.",
        PS33_PRIVATE_DEFINITIONS,
        "For SQ the multiplicity shall be 1."),
    _edit("REQ-ENC-060", "CP10-EVRLE-16F", _defined(1, "SQ", PrivateDataElementNumberOfItems=[3, 3]),
        ("Ps3_C_12_1_1_7_2_98e21e",),
        "As REQ-ENC-058 with Value Representation SQ, multiplicity 1 and Number of Items 3,3.",
        _cite("PS3.3", "C.12.1.1.7.2", "part03/sect_C.12.html#sect_C.12.1.1.7.2"),
        "A fixed number of Items is a single integer Value."),
    _edit("REQ-ENC-061", "CP10-EVRLE-16F", _mixed([3, 3], [1]),
        ("Ps3_C_12_1_NonidentifyingPrivateElements_1b7b56",),
        "Insert a MIXED Private Data Element Characteristics Item whose Nonidentifying Private "
        "Elements (0008,0304) lists 0003H twice.",
        PS33_SOP_COMMON,
        "Multiple Values shall be in increasing order and each listed at most once."),
    _edit("REQ-ENC-062", "CP10-EVRLE-16F", _mixed([3], [2, 1]),
        ("Ps3_C_12_1_IdentifyingPrivateElements_53d273",),
        "As REQ-ENC-061 with Identifying Private Elements (0008,0306) 0002H\\0001H in the "
        "Deidentification Action Item.",
        PS33_SOP_COMMON,
        "Multiple Values shall be in increasing order."),
    _edit("REQ-ENC-063", "CP10-EVRLE-16F",
        [_op("set", ["SpecimenDescriptionSequence", 0, "SpecimenUID"], "1.2.840.10008.99.1")],
        ("Ps5_9_b45977", "Ps5_9_2_b903b5"),
        "Set Specimen UID (0040,0554) to 1.2.840.10008.99.1.",
        _cite("PS3.5", "9", "part05/chapter_9.html"),
        "The root 1.2.840.10008 is reserved for DICOM defined items and shall not identify a "
        "specimen (PS3.5 9), which the encoding rule reports; a UID under the root is also "
        "registered in PS3.6 Annex A, which this one is not, and iod-value-format reports that "
        "(PS3.5 9.2).",
        expected=("encoding", "iod-value-format")),
    *(
        _rewrite(case_id, control,
            [_insert([], _creator(), _private_sequence(_element(tag, vr, value_hex=value), **sequence))],
            (requirement,),
            f"{reencoded}Insert a private Sequence (0029,1001) whose Item holds {described} encoded "
            "Big Endian.",
            citation,
            f"{described} shall be encoded in Little Endian. " + ENCODED_ONLY,
            **before)
        for control, citation, reencoded, before, sequence, cases in (
            ("CP10-EVRLE-16F", PS35_IMPLICIT_LITTLE, "Re-encode the control in Implicit VR Little Endian. ",
             {"transfer_syntax": IMPLICIT_LITTLE_ENDIAN}, {"length": "undefined"},
             (("REQ-ENC-064", "Ps5_A_1_debced"), ("REQ-ENC-065", "Ps5_A_1_75aab3"),
              ("REQ-ENC-066", "Ps5_A_1_461476"))),
            ("CP10-EVRLE-16F", PS35_EXPLICIT_LITTLE, "", {}, {},
             (("REQ-ENC-067", "Ps5_A_2_2c73c1"), ("REQ-ENC-068", "Ps5_A_2_5dcbfa"),
              ("REQ-ENC-069", "Ps5_A_2_497172"))),
            ("CP03-JPEG-1F", PS35_ENCAPSULATED_SYNTAXES, "", {}, {},
             (("REQ-ENC-070", "Ps5_A_4_bda4a7"), ("REQ-ENC-071", "Ps5_A_4_19a420"),
              ("REQ-ENC-072", "Ps5_A_4_c9f614"))),
        )
        for (case_id, requirement), (tag, vr, value, described) in zip(cases, BIG_ENDIAN_VALUES)
    ),
    _edit("REQ-ENC-076", "CP10-EVRLE-16F",
        [_op("insert", ["OpticalPathSequence", 0, "SpecificCharacterSet"], "ISO_IR 100")],
        ("Ps5_7_5_3_397ec3",),
        "Insert Specific Character Set (0008,0005) ISO_IR 100 into the Optical Path Sequence Item.",
        _cite("PS3.5", "7.5.3", "part05/chapter_7.html#sect_7.5.3"),
        "An encapsulated Data Set includes Specific Character Set only if the IOD defines it for "
        "that Sequence, and Table C.8.12.5-1 does not."),
    _rewrite("REQ-ENC-073", "CP10-EVRLE-16F", [{"op": "break_deflate_padding"}],
        ("Ps5_A_5_04de07",),
        "Re-encode the control in Deflated Explicit VR Little Endian and give the deflated bit "
        "stream the wrong trailing pad for its length.",
        _cite("PS3.5", "A.5", "part05/chapter_A.html#sect_A.5"),
        "An odd-length deflated bit stream is followed by a single NULL byte and an even-length one "
        "by none. " + ENCODED_ONLY,
        transfer_syntax="1.2.840.10008.1.2.1.99"),
    _rewrite("REQ-ENC-074", "CP10-EVRLE-16F", [{"op": "append", "hex": "000000"}],
        ("Ps10_7_2_f911da",),
        "Append three NULL bytes after the last Data Element.",
        PS310_DATA_SET,
        "A File contains a single Data Set; the bytes after it are no Data Element."),
    _rewrite("REQ-ENC-075", "CP10-EVRLE-16F", [{"op": "append", "hex": "feffdde000000000"}],
        ("Ps10_7_2_f911da",),
        "Append a Sequence Delimitation Item (FFFE,E0DD) after the last Data Element.",
        PS310_DATA_SET,
        "A File contains a single Data Set; a delimiter outside any Sequence belongs to none. The "
        "parser skips it; only the encoded bytes show it."),
    _rewrite("REQ-ENC-077", "CP02-JPEG-16F",
        [{"op": "set_delimiter_length", "path": ["PixelData"], "item": None, "length": 4}],
        ("Ps5_A_4_f5f245",),
        "Set the Value Length of the Sequence Delimitation Item ending the encapsulated Pixel Data "
        "(7FE0,0010) to 4.",
        PS35_ENCAPSULATED_SYNTAXES,
        "The Sequence of Items ends with a Sequence Delimitation Item of Value Length 00000000H. "
        + ENCODED_ONLY),
    _rewrite("REQ-ENC-078", "CP02-JPEG-16F", [{"op": "drop_pixel_delimiter"}],
        ("Ps5_7_1_2_d38d67", "Ps5_7_5_2_e7bdad"),
        "End the file after the last Fragment of the encapsulated Pixel Data (7FE0,0010), without "
        "its Sequence Delimitation Item.",
        PS35_ENCAPSULATED_SYNTAXES,
        "A Value of Undefined Length ends with a Sequence Delimitation Item. The candidate's parser "
        "accepts the end of the file in its place, so of its rules only the encoding rule reports "
        "the omission; the bench's decoder stage cannot read the Data Set and fails "
        "frame-geometry, an independent report of the same defect.",
        expected=("encoding", "pixel-decode-wsi-dicom-2026c-frame-geometry")),
    _rewrite("REQ-ENC-079", "CP02-JPEG-16F", [{"op": "insert_fragment", "hex": ""}],
        ("Ps5_A_4_fd123f",),
        "Insert a zero-length Fragment Item after the last Fragment of the encapsulated Pixel Data "
        "(7FE0,0010).",
        PS35_ENCAPSULATED_SYNTAXES,
        "Each Item holding a Fragment has an even length of at least two bytes. After the last "
        "Fragment it moves no offset the Extended Offset Table records, and the parser drops empty "
        "Items, so only the encoded bytes show it."),
)
