"""Residual encapsulated Pixel Data framing statement cases."""

from __future__ import annotations

from .iod_amendment_cases import _case as _spec, _cite


J2K = "W7-TS-J2K-PART1-ICT"
ENCAPSULATED_UNCOMPRESSED = "W7-TS-ENCAPSULATED-UNCOMPRESSED"
PS35_A4 = _cite("PS3.5", "A.4", "part05/sect_A.4.html")


def _case(number, control, operation, requirements, changed, rationale):
    return _spec(
        f"REQ-PXS-{number:03d}", control, "encoding_rewrite",
        {"preserve_source_encoding": True, "operations": [operation]},
        ("pixel-structure",), changed, PS35_A4, rationale,
        requirement_ids=list(requirements),
    )


CASES = (
    _case(
        1, J2K, {"op": "pixel_data_defined_length"},
        ("Ps5_A_4_33a347", "Ps5_A_4_d4b47e", "Ps5_A_4_e82862"),
        "Encode the unchanged Basic Offset Table and JPEG 2000 Fragments as one defined-length "
        "Pixel Data Value and remove the Sequence Delimitation Item.",
        "An encapsulated Transfer Syntax represents top-level Pixel Data as an undefined-length "
        "Item stream, not a defined-length primitive Value.",
    ),
    _case(
        2, J2K, {"op": "drop_basic_offset_table"},
        ("Ps5_A_4_9063da",),
        "Remove the Basic Offset Table Item so the first JPEG 2000 Frame Fragment becomes the "
        "first Item in Pixel Data.",
        "The first Item has the Basic Offset Table role even when its Value is empty.",
    ),
    _case(
        3, J2K, {"op": "corrupt_first_fragment_tag"},
        ("Ps5_A_4_b9093d",),
        "Change the first Frame Fragment Tag from (FFFE,E000) to reserved (FFFE,E001), leaving "
        "its Item Length and codestream bytes unchanged.",
        "Each encoded stream Fragment is encapsulated in an Item tagged (FFFE,E000).",
    ),
    _case(
        4, ENCAPSULATED_UNCOMPRESSED, {"op": "extend_first_fragment"},
        ("Ps5_A_4_11_acf161",),
        "Append two zero bytes inside the first Encapsulated Uncompressed Frame Fragment and "
        "increase only that Item Length.",
        "An Encapsulated Uncompressed Fragment contains the same exact native Frame bytes and "
        "only the padding required for an even Item Length.",
    ),
    _case(
        5, J2K,
        {"op": "edit_element_header", "path": ["PixelData"], "offset": 0, "remove": 6,
         "hex": "e07f08004f46"},
        ("Ps5_A_4_61f90c",),
        "Change Pixel Data (7FE0,0010) VR OB to Float Pixel Data (7FE0,0008) VR OF while "
        "retaining the encapsulated Item stream and JPEG 2000 Transfer Syntax.",
        "Encapsulated image Transfer Syntaxes apply to top-level Pixel Data, not Float or Double "
        "Float Pixel Data.",
    ),
)


UNCOVERED = {}
