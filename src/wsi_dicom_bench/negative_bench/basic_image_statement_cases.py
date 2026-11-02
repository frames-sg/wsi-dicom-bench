"""Non-motion pixel metadata and still-image transfer-syntax statement cases."""

from __future__ import annotations

from .iod_amendment_cases import _case as _spec, _cite, _edits, _op


def _case(case_id, control, mutation, parameters, requirements, changed, part, section,
          page, rationale):
    return _spec(
        case_id, control, mutation, parameters, ("image-metadata",), changed,
        _cite(part, section, page), rationale, requirement_ids=list(requirements),
    )


def _edit(case_id, control, operations, requirements, changed, part, section, page, rationale):
    return _case(case_id, control, "iod_edits", _edits(*operations), requirements, changed,
                 part, section, page, rationale)


def _encoded(case_id, control, operation, requirements, changed, section, rationale):
    return _case(
        case_id, control, "encoding_rewrite",
        {"preserve_source_encoding": True, "operations": [operation]},
        requirements, changed, "PS3.5", section, f"part05/sect_{section}.html", rationale,
    )


CASES = (
    _encoded(
        "REQ-IMG-001", "W7-TS-JPEG-LS-LOSSLESS-RGB",
        {"op": "set_value", "path": ["PlanarConfiguration"], "value_hex": "0100"},
        ("Ps3_C_7_6_3_1_2_93fa52", "Ps5_8_2_3_4e64b0"),
        "Set Planar Configuration to 1 in the JPEG-LS RGB image.", "8.2.3",
        "The DICOM header must declare component-interleaved layout (0) because JPEG-LS "
        "records the actual interleave in its codestream.",
    ),
    _encoded(
        "REQ-IMG-002", "W7-TS-J2K-PART1-ICT",
        {"op": "set_value", "path": ["PlanarConfiguration"], "value_hex": "0100"},
        ("Ps5_8_2_4_d71faf",),
        "Set Planar Configuration to 1 in the JPEG 2000 image.", "8.2.4",
        "JPEG 2000 records component organization in the codestream, so the DICOM Attribute "
        "is fixed at 0.",
    ),
    _encoded(
        "REQ-IMG-003", "W7-TS-HTJ2K-RPCL-128",
        {"op": "set_value", "path": ["PlanarConfiguration"], "value_hex": "0100"},
        ("Ps5_8_2_14_b2f50a",),
        "Set Planar Configuration to 1 in the HTJ2K image.", "8.2.14",
        "HTJ2K records component organization in the codestream, so the DICOM Attribute is "
        "fixed at 0.",
    ),
    _encoded(
        "REQ-IMG-004", "W7-TS-JXL-LOSSLESS-RGB",
        {"op": "set_value", "path": ["PlanarConfiguration"], "value_hex": "0100"},
        ("Ps5_8_2_15_167cfb",),
        "Set Planar Configuration to 1 in the JPEG XL image.", "8.2.15",
        "JPEG XL records component organization in the codestream, so the DICOM Attribute is "
        "fixed at 0.",
    ),
    _edit(
        "REQ-IMG-005", "CP10-EVRLE-16F",
        [_op("set", ["PhotometricInterpretation"], "YBR_FULL_422")],
        ("Ps3_C_7_6_3_1_2_dbe575", "Ps5_8_2_8a024f"),
        "Set native Pixel Data Photometric Interpretation to YBR_FULL_422.",
        "PS3.5", "8.2", "part05/sect_8.2.html",
        "Subsampled YBR_FULL_422 is permitted only in an encapsulated compressed format, not "
        "the native Explicit VR Little Endian control.",
    ),
    _edit(
        "REQ-IMG-006", "CP14-MONO16-EVRLE",
        [_op("set", ["BitsStored"], 12), _op("set", ["HighBit"], 11)],
        ("Ps3_C_8_12_4_1_BitsStored_ed2b6b",),
        "Set Bits Stored to 12 and High Bit to 11 while Bits Allocated remains 16.",
        "PS3.3", "C.8.12.4-1", "part03/sect_C.8.12.4.html",
        "The VL Whole Slide Microscopy Image Module requires Bits Stored to equal Bits "
        "Allocated even though the generic native-pixel relationship remains internally valid.",
    ),
    _edit(
        "REQ-IMG-007", "CP14-MONO16-EVRLE", [_op("set", ["HighBit"], 14)],
        ("Ps3_C_8_12_4_1_HighBit_e8f419", "Ps5_8_1_1_b0091d"),
        "Set High Bit to 14 while Bits Stored remains 16.",
        "PS3.5", "8.1.1", "part05/sect_8.1.html",
        "High Bit must be one less than Bits Stored both generically and for VL Whole Slide "
        "Microscopy.",
    ),
    _edit(
        "REQ-IMG-008", "CP10-EVRLE-16F",
        [_op("set", ["BitsStored"], 9), _op("set", ["HighBit"], 8)],
        ("Ps5_8_1_1_14376b",),
        "Set Bits Stored to 9 and High Bit to 8 while Bits Allocated remains 8.",
        "PS3.5", "8.1.1", "part05/sect_8.1.html",
        "Bits Stored exceeds the eight allocated bits while High Bit remains consistent with "
        "the changed Bits Stored value.",
    ),
    _edit(
        "REQ-IMG-009", "CP10-EVRLE-16F",
        [_op("set", ["BitsAllocated"], 12), _op("set", ["BitsStored"], 12),
         _op("set", ["HighBit"], 11)],
        ("Ps5_8_1_1_65182e", "Ps5_8_1_1_2b593e"),
        "Set Bits Allocated and Bits Stored to 12 and High Bit to 11.",
        "PS3.5", "8.1.1", "part05/sect_8.1.html",
        "Twelve allocated bits is neither one nor a multiple of eight; the other pixel bit-field "
        "relationships remain mutually consistent.",
    ),
    _encoded(
        "REQ-IMG-010", "W7-TS-JPEG-BASELINE-YBR422",
        {"op": "set_value", "path": ["PhotometricInterpretation"], "text": "YBR_RCT "},
        ("Ps5_8_2_1_fe09df",),
        "Set JPEG Baseline Photometric Interpretation to padded YBR_RCT.", "8.2.1",
        "YBR_RCT is a Standard Value but is not admitted for JPEG Baseline Pixel Data.",
    ),
    _encoded(
        "REQ-IMG-011", "W7-TS-RLE-RGB",
        {"op": "set_value", "path": ["PhotometricInterpretation"], "text": "YBR_RCT "},
        ("Ps5_8_2_2_8b7a45",),
        "Set RLE Photometric Interpretation to padded YBR_RCT.", "8.2.2",
        "YBR_RCT is a Standard Value but is not admitted for RLE Pixel Data.",
    ),
    _encoded(
        "REQ-IMG-012", "W7-TS-JPEG-LS-LOSSLESS-RGB",
        {"op": "set_value", "path": ["PhotometricInterpretation"], "text": "YBR_RCT "},
        ("Ps5_8_2_3_a4a3ff",),
        "Set JPEG-LS Photometric Interpretation to padded YBR_RCT.", "8.2.3",
        "YBR_RCT is a Standard Value but is not admitted for JPEG-LS Pixel Data.",
    ),
    _encoded(
        "REQ-IMG-013", "W7-TS-J2K-PART1-ICT",
        {"op": "set_value", "path": ["PhotometricInterpretation"], "text": "YBR_FULL_422"},
        ("Ps5_8_2_4_fad88b",),
        "Set JPEG 2000 Photometric Interpretation to YBR_FULL_422.", "8.2.4",
        "YBR_FULL_422 is a Standard Value but is not admitted for JPEG 2000 Pixel Data.",
    ),
    _encoded(
        "REQ-IMG-014", "W7-TS-HTJ2K-RPCL-128",
        {"op": "set_value", "path": ["PhotometricInterpretation"], "text": "YBR_FULL_422"},
        ("Ps5_8_2_14_f3a8d2",),
        "Set HTJ2K Photometric Interpretation to YBR_FULL_422.", "8.2.14",
        "YBR_FULL_422 is a Standard Value but is not admitted for HTJ2K Pixel Data.",
    ),
    _encoded(
        "REQ-IMG-015", "W7-TS-JXL-LOSSLESS-RGB",
        {"op": "set_value", "path": ["PhotometricInterpretation"], "text": "YBR_FULL_422"},
        ("Ps5_8_2_15_c4fa2a",),
        "Set JPEG XL Photometric Interpretation to YBR_FULL_422.", "8.2.15",
        "YBR_FULL_422 is a Standard Value but is not admitted for JPEG XL Pixel Data.",
    ),
)

# The twelve-bit cell mutation is also rejected by the byte-count/framing check: the retained
# eight-bit Pixel Data does not hold cells of the declared Bits Allocated size.
next(case for case in CASES if case["case_id"] == "REQ-IMG-009")["expected"] = (
    "image-metadata", "pixel-structure",
)


UNCOVERED = {}
