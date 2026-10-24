"""DICOM JSON syntax and Attribute defects, distinct from encoded-file mutations.

Each document derives from the same conformant WSI control. Empty DICOM Values
are represented as absent Value members, as Annex F.2.5 requires. No source
file is changed. A case changes one encoding property and names the normative
statement(s) that the JSON-model or IOD check must detect.
"""

from __future__ import annotations

import json
from pathlib import Path

import pydicom

CONTROL_ID = "CP10-EVRLE-16F"
TRANSFER_SYNTAX = "1.2.840.10008.1.2.1"
RULE = "intrinsic-wsi-dicom-json-model"


def _case(number, requirements, section, changed, rationale):
    return {
        "case_id": f"REQ-JSON-{number:03d}",
        "source_control_id": CONTROL_ID,
        "requirement_ids": list(requirements),
        "expected": ["json-model"],
        "changed": changed,
        "citation": {
            "part": "PS3.18", "edition": "2026d", "section": section,
            "url": "https://dicom.nema.org/medical/dicom/2026d/output/chtml/part18/chapter_F.html",
        },
        "rationale": rationale,
    }


CASES = [
    _case(1, ("Ps18_F_1_f1d5d4", "Ps18_F_2_3_ac289e"), "F.1 and F.2.3",
          "Study Date DA Value is 2026-01-01 instead of YYYYMMDD.",
          "A JSON string must still obey its DICOM VR definition; ISO calendar syntax is not DA."),
    _case(2, ("Ps18_F_2_dc9ab9",), "F.2",
          "The document contains one invalid UTF-8 byte in Study Description.",
          "The JSON model uses UTF-8; a raw FF byte is not a UTF-8 code unit."),
    _case(3, ("Ps18_F_2_2_467f17",), "F.2.2",
          "The first two root Attribute properties exchange positions.",
          "Every Attribute and Value remains unchanged, but tag order is no longer ascending."),
    _case(4, ("Ps18_F_2_2_f11873",), "F.2.2",
          "Group Length (0008,0000) is added with VR UL and Value 0.",
          "Group Length Attributes are forbidden in the JSON model regardless of their Value."),
    _case(5, ("Ps18_F_2_3_523a5a",), "F.2.3 Table F.2.3-1",
          "Rows US Value is a JSON String containing the same decimal digits as the control.",
          "US requires a JSON Number, even when a String could be parsed as that integer."),
    _case(6, ("Ps18_F_2_3_219bd2",), "F.2.3",
          "The first Dimension Index Pointer AT Value changes 0048021F to 0048021f.",
          "The tag value is numerically unchanged; AT requires uppercase hexadecimal representation."),
    _case(7, ("Ps18_F_2_5_9122d6",), "F.2.5",
          "Patient ID is empty but retains a Value member containing an empty String.",
          "A zero-length Attribute must omit Value, BulkDataURI and InlineBinary."),
]

# Reading a malformed JSON Value can also leave the derived Data Set without
# that Attribute. These are consequences of the one JSON defect, not extra
# independently authored defects.
for case in CASES:
    case["expected_cascades"] = {
        "REQ-JSON-001": ["intrinsic-wsi-dicom-iod-value-format"],
        "REQ-JSON-005": ["intrinsic-wsi-dicom-iod-attribute-presence"],
        "REQ-JSON-006": ["intrinsic-wsi-dicom-dimension-order", "intrinsic-wsi-dicom-iod-attribute-presence"],
    }.get(case["case_id"], [])

# A serialized LT or UR is one string by construction. JSON preserves the
# invalid multiplicity explicitly, so it can exercise the IOD VM check.
CASES.extend([
    {**_case(8, ("Ps5_6_2_89a67a", "Ps5_6_4_29bb04"), "6.2 and 6.4",
             "Retrieve URI has two individually valid URI Strings in its Value array.",
             "UR has VM 1; using JSON retains two Values instead of joining them into one malformed URI."),
     "expected": ["iod-vr-vm"], "expected_cascades": [],
     "citation": {"part": "PS3.5", "edition": "2026d", "section": "6.2 and 6.4",
                  "url": "https://dicom.nema.org/medical/dicom/2026d/output/chtml/part05/sect_6.4.html"}},
    {**_case(9, ("Ps5_6_2_5e8cdb",), "6.2",
             "Image Comments LT has two Strings in its Value array.",
             "LT has VM 1; its backslash is ordinary text in a file, while JSON exposes the invalid multiplicity."),
     "expected": ["iod-vr-vm"], "expected_cascades": [],
     "citation": {"part": "PS3.5", "edition": "2026d", "section": "6.2",
                  "url": "https://dicom.nema.org/medical/dicom/2026d/output/chtml/part05/sect_6.2.html"}},
])


def _normalize_empty_values(document):
    for attribute in document.values():
        values = attribute.get("Value")
        if values in ([], [""], [{}]):
            attribute.pop("Value")
        elif attribute.get("vr") == "SQ":
            for item in values or []:
                _normalize_empty_values(item)


def build_document(case_id: str | None, source: Path) -> bytes:
    """Encode the valid control (None) or one named, single-defect document."""
    document = pydicom.dcmread(source).to_json_dict()
    _normalize_empty_values(document)
    # A known ASCII marker makes the invalid UTF-8 mutation exact and local.
    document["00081030"] = {"vr": "LO", "Value": ["JSON_ENCODING_CONTROL"]}
    document = json.loads(json.dumps(document, sort_keys=True))
    if case_id == "REQ-JSON-001":
        document["00080020"]["Value"] = ["2026-01-01"]
    elif case_id == "REQ-JSON-003":
        keys = list(document)
        keys[0], keys[1] = keys[1], keys[0]
        document = {key: document[key] for key in keys}
    elif case_id == "REQ-JSON-004":
        document["00080000"] = {"vr": "UL", "Value": [0]}
        document = dict(sorted(document.items()))
    elif case_id == "REQ-JSON-005":
        document["00280010"]["Value"] = [str(document["00280010"]["Value"][0])]
    elif case_id == "REQ-JSON-006":
        pointer = document["00209222"]["Value"][0]["00209165"]
        if pointer["Value"] != ["0048021F"]:
            raise ValueError("JSON control must index Row Position in Total Image Pixel Matrix")
        pointer["Value"] = ["0048021f"]
    elif case_id == "REQ-JSON-007":
        document["00100020"] = {"vr": "LO", "Value": [""]}
    elif case_id == "REQ-JSON-008":
        document["0040E010"] = {"vr": "UR", "Value": ["https://example.com/a", "https://example.com/b"]}
        document = dict(sorted(document.items()))
    elif case_id == "REQ-JSON-009":
        document["00204000"] = {"vr": "LT", "Value": ["first", "second"]}
        document = dict(sorted(document.items()))
    elif case_id not in (None, "REQ-JSON-002"):
        raise ValueError(f"unknown DICOM JSON case {case_id}")
    encoded = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if case_id == "REQ-JSON-002":
        encoded = encoded.replace(b"JSON_ENCODING_CONTROL", b"JSON_ENCODING_\xff", 1)
    return encoded
