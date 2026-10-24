"""Residual generic IOD and recommendation statement cases."""

from __future__ import annotations

import struct

from .iod_amendment_cases import SHARED, _case as _spec, _cite, _edits, _op
from .requirement_cases import INPUT_PROFILE


def _lut8_profile() -> bytes:
    """Return the control profile with a valid A2B0 lut8Type tag appended."""
    profile = bytearray.fromhex(INPUT_PROFILE)
    lut = bytearray(b"mft1" + b"\0" * 4 + bytes([3, 3, 2, 0]))
    for value in (1, 0, 0, 0, 1, 0, 0, 0, 1):
        lut += struct.pack(">i", value << 16)
    identity = bytes(range(256))
    lut += identity * 3
    lut += bytes(2**3 * 3)
    lut += identity * 3
    offset = (len(profile) + 3) // 4 * 4
    profile += b"\0" * (offset - len(profile)) + lut
    profile[0:4] = len(profile).to_bytes(4, "big")
    profile[132:136] = b"A2B0"
    profile[136:140] = offset.to_bytes(4, "big")
    profile[140:144] = len(lut).to_bytes(4, "big")
    return bytes(profile)


def _case(case_id, control, mutation, parameters, expected, requirements, changed, citation,
          rationale, **fields):
    return _spec(
        case_id, control, mutation, parameters, expected, changed, citation, rationale,
        requirement_ids=list(requirements), **fields,
    )


CASES = (
    _case(
        "REQ-GENERIC-001", "CP10-EVRLE-16F", "iod_edits",
        _edits(
            _op("insert", [*SHARED, "(0029,0010)"], "ACME FG", vr="LO"),
            _op("insert", [*SHARED, "(0029,1001)"],
                [{"PixelSpacing": ["0.0005", "0.0005"]}], vr="SQ"),
        ),
        ("iod-modules",), ("Ps3_C_7_6_16_1_1_b640e8",),
        "Insert a private Functional Group whose Item repeats Pixel Spacing from the Standard "
        "Pixel Measures Functional Group.",
        _cite("PS3.3", "C.7.6.16.1.1", "part03/sect_C.7.6.16.html#sect_C.7.6.16.1.1"),
        "A Private Functional Group does not replicate an Attribute of a Standard Functional "
        "Group; the private block is otherwise properly reserved in the Shared Item.",
    ),
    _case(
        "REQ-GENERIC-002", "V7-MPEG2-HIGH-MONO", "iod_edits",
        _edits(_op("insert", ["PixelAspectRatio"], ["1", "1"])),
        ("iod-attribute-presence", "image-metadata"), ("Ps5_8_2_6_d4f25d",),
        "Insert Pixel Aspect Ratio 1\\1 into the MPEG2 Main Profile / High Level image.",
        _cite("PS3.5", "8.2.6", "part05/sect_8.2.6.html"),
        "MPEG2 Main Profile / High Level metadata omits Pixel Aspect Ratio because aspect ratio "
        "is carried by the stream; both the specialized metadata rule and the IOD condition "
        "reject the otherwise valid two-integer Value.",
    ),
    _case(
        "REQ-GENERIC-003", "CP02-JPEG-16F", "encoding_rewrite",
        {"operations": [{
            "op": "patch_value", "path": ["OpticalPathSequence", 0, "ICCProfile"],
            "offset": 64, "hex": "00000001",
        }]},
        ("iod-value-format",), ("Ps3_C_11_15_1_1_108351",),
        "Change the ICC Profile Rendering Intent from Perceptual (0) to Media-Relative "
        "Colorimetric (1).",
        _cite("PS3.3", "C.11.15.1.1", "part03/sect_C.11.15.html#sect_C.11.15.1.1"),
        "The profile remains structurally valid, but departs from the recommendation to use "
        "Perceptual Rendering Intent.",
        expected_evidence="advisory",
        expected_advisory_contains="recommends Perceptual (0)",
    ),
    _case(
        "REQ-GENERIC-004", "CP02-JPEG-16F", "encoding_rewrite",
        {"operations": [{
            "op": "set_value", "path": ["OpticalPathSequence", 0, "ICCProfile"],
            "value_hex": _lut8_profile().hex(),
        }]},
        ("iod-value-format",), ("Ps3_C_11_15_1_1_ee816f",),
        "Relabel the first ICC tag as A2B0 and its data type as eight-bit LUT type mft1.",
        _cite("PS3.3", "C.11.15.1.1", "part03/sect_C.11.15.html#sect_C.11.15.1.1"),
        "The profile remains structurally valid, but a LUT tag uses lut8Type instead of the "
        "recommended 16-bit lut16Type.",
        expected_evidence="advisory",
        expected_advisory_contains='A2B0 tag is of type "mft1"',
    ),
    _case(
        "REQ-GENERIC-005", "V7-SEG-FRACTIONAL-MPEG2", "iod_edits",
        _edits(_op("set", ["LossyImageCompression"], "00")),
        ("lossy-history",), ("Ps3_C_8_20_2_2_1e508c",),
        "Set Lossy Image Compression to 00 while retaining the lossy MPEG2 Segmentation frames.",
        _cite("PS3.3", "C.8.20.2.2", "part03/sect_C.8.20.html#sect_C.8.20.2.2"),
        "A Segmentation encoded with a lossy Transfer Syntax records Lossy Image Compression 01.",
    ),
    _case(
        "REQ-GENERIC-006", "V7-PM-JPEGLS-NEAR", "iod_edits",
        _edits(_op("set", ["LossyImageCompression"], "00")),
        ("lossy-history",), ("Ps3_C_8_32_2_1_d04416",),
        "Set Lossy Image Compression to 00 while retaining the near-lossless JPEG-LS "
        "Parametric Map frames.",
        _cite("PS3.3", "C.8.32.2.1", "part03/sect_C.8.32.html#sect_C.8.32.2.1"),
        "A Parametric Map encoded with a lossy Transfer Syntax records Lossy Image Compression 01.",
    ),
)


UNCOVERED = {}
