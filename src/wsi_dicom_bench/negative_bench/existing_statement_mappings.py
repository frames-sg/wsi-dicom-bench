"""2026d statements broken by an existing v6 case's unchanged authored defect.

Each entry names the case whose mutation directly violates the statement. These are mappings to
existing defects, not inferred coverage from sharing a rule family.
"""

MAPPINGS = {
    "Ps3_C_7_6_22_1_2_464a33": {
        "cases": ("NB-ID-003",),
        "rationale": (
            "The pair assigns one Specimen UID to specimens with different Specimen Identifiers, "
            "so the supposedly global specimen identity is not unique."
        ),
    },
    "Ps3_C_7_6_3_1_3_4a62de": {
        "cases": ("IOD-PRS-015",),
        "rationale": (
            "The case inserts Planar Configuration while Samples per Pixel is one, the condition "
            "under which Planar Configuration is absent."
        ),
    },
    "Ps3_C_11_15_1_1_43d1c6": {
        "cases": ("NB-CO-003",),
        "rationale": "The case changes ICC header bytes 12-15 from the required input-device class scnr.",
    },
    "Ps3_C_11_15_1_1_6cb654": {
        "cases": ("NB-CO-004",),
        "rationale": "The case changes ICC input color-space header bytes 16-19 from RGB to GRAY.",
    },
    "Ps3_C_7_5_1_1_2_6790e6": {
        "cases": ("REQ-PIX-001",),
        "rationale": "The case gives an 8-bit image Pixel Padding Value 256, outside its original stored values.",
    },
    "Ps3_C_7_6_17_1_2ec4fa": {
        "cases": ("NB-GE-002",),
        "rationale": "The case assigns one frame another frame's dimension indices without moving it.",
    },
    "Ps3_C_7_6_1_1_2_a9e514": {
        "cases": ("IOD-ENU-008",),
        "rationale": "The case preserves the multi-valued Image Type shape but breaks its required Value 2.",
    },
    "Ps3_C_8_12_4_1_1_1befe3": {
        "cases": ("IOD-ENU-008",),
        "rationale": "The case sets Image Type Value 2 to SECONDARY instead of PRIMARY.",
    },
    "Ps5_6_1_2_1_91c5aa": {
        "cases": ("REQ-ENC-033",),
        "rationale": "The case encodes byte C9 without Specific Character Set instead of the default ISO-IR 6 repertoire.",
    },
    "Ps5_6_2_176ec1": {
        "cases": ("IOD-FMT-003",),
        "rationale": "The case encodes Study Date 20261301, whose month is not a Gregorian YYYYMMDD date.",
    },
    "Ps5_6_2_5b8243": {
        "cases": ("IOD-FMT-003",),
        "rationale": "The case encodes month 13, which cannot be interpreted in the Gregorian calendar.",
    },
    "Ps5_6_2_80b965": {
        "cases": ("IOD-FMT-017",),
        "rationale": "The case encodes six PN components and therefore five caret delimiters.",
    },
    "Ps5_9_1_e86dd2": {
        "cases": ("IOD-FMT-001",),
        "rationale": "The case gives a multi-digit UID component a leading zero.",
    },
    "Ps5_7_4_1_01939a": {
        "cases": ("IOD-FMT-003",),
        "rationale": "The non-empty Study Date Value is invalid for its DA VR.",
    },
    "Ps5_7_4_3_0c7254": {
        "cases": ("IOD-FMT-003",),
        "rationale": "The known Type 2 Study Date Value is invalid for its DA VR.",
    },
    "Ps5_7_1_1_c8d4ce": {
        "cases": ("IOD-VRM-001",),
        "rationale": "The case writes the standard Manufacturer element with SH instead of dictionary VR LO.",
    },
    "Ps5_7_1_1_ca2b1d": {
        "cases": ("IOD-VRM-001",),
        "rationale": "The case writes a VR different from the PS3.6 Data Dictionary VR.",
    },
    "Ps5_7_4_1_1b4c29": {
        "cases": ("IOD-PRS-002",),
        "rationale": "The case leaves mandatory Type 1 Pyramid UID present with zero Value Length.",
    },
    "Ps5_7_4_1_200da1": {
        "cases": ("IOD-PRS-001",),
        "rationale": "The case removes mandatory Type 1 Pyramid UID.",
    },
    "Ps5_7_4_2_7dcac3": {
        "cases": ("IOD-PRS-014",),
        "rationale": "The case inserts a conditional focal-plane attribute while its condition is false.",
    },
    "Ps5_7_4_2_d74db3": {
        "cases": ("IOD-PRS-007",),
        "rationale": "The case removes a conditional Type 1 slide position attribute while required.",
    },
    "Ps5_7_4_3_828c2e": {
        "cases": ("IOD-PRS-003",),
        "rationale": "The case removes mandatory Type 2 Referring Physician's Name.",
    },
    "Ps5_7_4_3_aa6998": {
        "cases": ("IOD-PRS-003",),
        "rationale": "The case removes a Type 2 Data Element defined by the IOD.",
    },
    "Ps5_7_4_4_31eee8": {
        "cases": ("IOD-PRS-015",),
        "rationale": "The case inserts conditional Planar Configuration while Samples per Pixel is one.",
    },
    "Ps5_7_4_6_048def": {
        "cases": ("IOD-SEQ-001",),
        "rationale": "The case gives a Sequence two Items where its Attribute description permits one.",
    },
    "Ps5_7_8_1_502f66": {
        "cases": ("REQ-ENC-018",),
        "rationale": "The case reserves two blocks in one group with the same ACME Private Creator identifier.",
    },
    "Ps3_C_7_6_3_1_8_a81faf": {
        "cases": ("NB-PX-004",),
        "rationale": "The case moves one Extended Offset Table entry off the Fragment Item Tag boundary.",
    },
    "Ps5_8_2_42fb24": {
        "cases": ("NB-PX-002",),
        "rationale": "The case leaves encapsulated Pixel Data with a Basic Offset Table but no Frame Fragment.",
    },
    "Ps5_A_4_82c271": {
        "cases": ("NB-PX-003",),
        "rationale": "The case changes the first Basic Offset Table Value from zero to 8, so it no longer points to the first Fragment Item Tag.",
    },
    "Ps5_A_4_890675": {
        "cases": ("NB-PX-007",),
        "rationale": "The case keeps a Native Transfer Syntax but writes Pixel Data as an undefined-length encapsulated Item stream instead of Native Format with Explicit Value Length.",
    },
    "Ps5_8_1_8ae787": {
        "cases": ("NB-CF-005",),
        "rationale": (
            "The case declares one sample per pixel while retaining interleaved RGB Pixel Data, "
            "so its Attributes no longer describe how the Pixel Data is encoded."
        ),
    },
    "Ps5_7_3_3c0c4e": {
        "cases": ("REQ-ENC-064",),
        "rationale": (
            "The Implicit VR case writes the multi-byte Palette LUT Descriptor Values in Big "
            "Endian order instead of least-significant-byte first."
        ),
    },
    "Ps5_A_1_777bab": {
        "cases": ("REQ-ENC-064",),
        "rationale": (
            "The Implicit VR Little Endian case writes multi-byte Values in Big Endian order, "
            "directly violating the syntax's overall Little Endian requirement."
        ),
    },
    "Ps5_A_2_2fd46a": {
        "cases": ("REQ-ENC-067",),
        "rationale": (
            "The Explicit VR Little Endian case writes a private Item Value in Big Endian order, "
            "directly violating the syntax's overall Little Endian requirement."
        ),
    },
    "Ps5_A_4_238b32": {
        "cases": ("REQ-ENC-070",),
        "rationale": (
            "The encapsulated-transfer-syntax case writes a private Item Value in Big Endian "
            "order, directly violating the Data Set's overall Little Endian requirement."
        ),
    },
    "Ps3_C_7_6_16_1_1_e8853c": {
        "cases": ("IOD-MOD-008",),
        "rationale": (
            "The case copies Pixel Measures from the Shared Functional Groups Item into a "
            "Per-Frame Functional Groups Item, so one Standard Functional Group is present in "
            "both locations."
        ),
    },
    "Ps3_C_1_2_3_a1fe07": {
        "cases": ("CP-CF-007",),
        "rationale": (
            "Acquisition Context Sequence is Type 2 through the Acquisition Context Module even "
            "where another module would make it optional; removing it demonstrates that the "
            "lowest applicable Type designation governs."
        ),
    },
}
