"""PS3.5 framing statements enforced when the candidate parses a DICOM Data Set.

Each mutation keeps the Part 10 envelope and source control intact but makes one field or
delimiter layout unreadable.  The candidate reports these pre-dispatch rejections through
``intrinsic-pixel-structure``; ``intrinsic-wsi-dicom-encoding`` may independently report the
same malformed byte stream and is adjudicated from the observed result by the v7 builder.
"""

from __future__ import annotations

from .iod_amendment_cases import _case as _spec, _cite


CONTROL = "CP10-EVRLE-16F"
DIMENSION_ORGANIZATION = "DimensionOrganizationSequence"
PIXEL_STRUCTURE = ("pixel-structure",)


def _case(case_id, parameters, requirements, changed, section, rationale):
    return _spec(
        case_id,
        CONTROL,
        "encoding_rewrite",
        parameters,
        PIXEL_STRUCTURE,
        changed,
        _cite("PS3.5", section,
              f"part05/sect_{'.'.join(section.split('.')[:2])}.html"),
        rationale,
        requirement_ids=list(requirements),
    )


CASES = (
    _case(
        "REQ-PARSE-001",
        {"operations": [{
            "op": "edit_element_header", "path": ["StudyDate"],
            "offset": 4, "remove": 2, "hex": "",
        }]},
        ("Ps5_7_1_f793ac", "Ps5_7_1_2_489caa", "Ps5_A_2_cd3108"),
        "Remove the two-byte VR field from the Explicit VR Study Date element.",
        "7.1.2",
        "The element no longer has any standard Data Element structure or the four fields of "
        "an Explicit VR element, so parsing rejects it before IOD checks run.",
    ),
    _case(
        "REQ-PARSE-002",
        {"operations": [
            {"op": "insert", "elements": [
                {"tag": "(7777,0010)", "vr": "UT", "text": "x"},
            ]},
            {"op": "set_element_length", "path": ["(7777,0010)"], "length": 100000},
        ]},
        ("Ps5_7_1_2_d61905",),
        "Insert a two-byte UT Value, then encode its 32-bit Value Length as 100000.",
        "7.1.2",
        "The long-form primitive element claims bytes beyond the Data Set, so the parser "
        "rejects the unequal Value Length and Value.",
    ),
    _case(
        "REQ-PARSE-003",
        {
            "transfer_syntax": "1.2.840.10008.1.2",
            "operations": [{
                "op": "edit_element_header", "path": ["StudyDate"],
                "offset": 4, "hex": "4441",
            }],
        },
        ("Ps5_7_1_77af7f", "Ps5_7_1_3_527d85", "Ps5_A_1_3fcdef",
         "Ps5_A_1_9969cd"),
        "Insert Explicit VR bytes 'DA' between the Study Date Tag and its Implicit VR length.",
        "7.1.3",
        "The declared Implicit VR Data Set now contains an Explicit VR-style header and no "
        "longer has the required three consecutive fields.",
    ),
    _case(
        "REQ-PARSE-004",
        {
            "transfer_syntax": "1.2.840.10008.1.2",
            "operations": [{
                "op": "set_element_length", "path": ["StudyDate"], "length": 100000,
            }],
        },
        ("Ps5_7_1_3_db44fd",),
        "Encode the Implicit VR Study Date Value Length as 100000 without changing its Value.",
        "7.1.3",
        "The primitive Value is shorter than its encoded explicit length, so parsing ends "
        "prematurely.",
    ),
    _case(
        "REQ-PARSE-005",
        {
            "lengths": [{
                "path": [DIMENSION_ORGANIZATION],
                "sequence": "defined", "items": "defined",
            }],
            "operations": [{
                "op": "edit_item_header", "path": [DIMENSION_ORGANIZATION],
                "item": 0, "offset": 4, "hex": "53510000",
            }],
        },
        ("Ps5_7_5_1593f5",),
        "Insert an Explicit VR SQ field and reserved bytes into an Item header.",
        "7.5",
        "Item and delimiter elements always use their Implicit VR eight-byte structure; the "
        "extra Explicit VR field misframes the Item.",
    ),
    _case(
        "REQ-PARSE-006",
        {"operations": [{
            "op": "edit_item_header", "path": [DIMENSION_ORGANIZATION],
            "item": 0, "offset": 0, "remove": 4, "hex": "08001000",
        }]},
        ("Ps5_7_5_1_16ec1d",),
        "Replace the first Item Tag (FFFE,E000) with (0008,0010).",
        "7.5.1",
        "A Sequence Value begins with a non-Item Tag, so the Sequence parser rejects it.",
    ),
    _case(
        "REQ-PARSE-007",
        {"operations": [{
            "op": "edit_element_header",
            "path": [DIMENSION_ORGANIZATION, 0, "DimensionOrganizationUID"],
            "offset": 4, "remove": 2, "hex": "",
        }]},
        ("Ps5_7_5_e1942b", "Ps5_7_5_1_83352b"),
        "Remove the Explicit VR field from the first Data Element inside a Sequence Item.",
        "7.5.1",
        "The Item Value is no longer a Data Set of elements encoded according to the declared "
        "Explicit VR Transfer Syntax.",
    ),
    _case(
        "REQ-PARSE-008",
        {"operations": [{
            "op": "drop_delimiter", "path": [DIMENSION_ORGANIZATION], "item": 0,
        }]},
        ("Ps5_7_5_1_4c33bb", "Ps5_7_5_1_95977a"),
        "Remove the Item Delimitation Item from the undefined-length Sequence Item.",
        "7.5.1",
        "The undefined-length Item has no encoded boundary after its Data Elements.",
    ),
    _case(
        "REQ-PARSE-009",
        {"operations": [
            {"op": "insert", "elements": [{
                "tag": "ReferencedImageSequence", "vr": "SQ", "items": [[]],
            }]},
            {"op": "set_item_length", "path": ["ReferencedImageSequence"],
             "item": 0, "length": 8},
        ]},
        ("Ps5_7_5_1_9986b0", "Ps5_7_5_1_f0461e"),
        "Give an empty defined-length Item a nonzero Value Length of eight bytes.",
        "7.5.1",
        "The empty Item claims bytes from the following element, so its length is neither zero "
        "nor the total length of its empty Data Set.",
    ),
    _case(
        "REQ-PARSE-010",
        {"operations": [
            {"op": "insert", "elements": [{
                "tag": "ReferencedImageSequence", "vr": "SQ", "items": [],
            }]},
            {"op": "set_element_length", "path": ["ReferencedImageSequence"], "length": 8},
        ]},
        ("Ps5_7_5_2_83af70", "Ps5_7_5_2_5a0961"),
        "Give a defined-length Sequence with zero Items a nonzero Value Length of eight bytes.",
        "7.5.2",
        "The empty Sequence claims the following element as an Item, so its encoded length is "
        "neither zero nor the total length of its zero Items.",
    ),
    _case(
        "REQ-PARSE-011",
        {"operations": [{
            "op": "drop_delimiter", "path": [DIMENSION_ORGANIZATION],
        }]},
        ("Ps5_7_5_2_957daa", "Ps5_7_5_2_b8c23d"),
        "Remove the Sequence Delimitation Item from the undefined-length Sequence.",
        "7.5.2",
        "The Sequence ends by neither an explicit length nor its required delimiter.",
    ),
)


UNCOVERED = {}
