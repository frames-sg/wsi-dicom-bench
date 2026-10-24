"""JPIP referenced-image obligations exercised through JSON, not Part 10 storage.

PS3.5 10.8 forbids the JPIP Referenced syntaxes for media storage. The JSON
metadata keeps a known Transfer Syntax hint and a Pixel Data Provider URL,
which allows reference and image-attribute checks without retrieving pixels.
"""
from __future__ import annotations

import json
from pathlib import Path

import pydicom

from .json_statement_cases import _normalize_empty_values

CONTROL_ID = "W7-TS-J2K-PART1-ICT"
CONTROL_PATH = "controls-v7/wsi/W7-TS-J2K-PART1-ICT.dcm"
SYNTAXES = {"jpip": "1.2.840.10008.1.2.4.94", "htj2k": "1.2.840.10008.1.2.4.204"}


def _case(number, kind, operation, requirements, expected, changed, rationale):
    section = "A.6" if kind == "jpip" else "A.11"
    return {
        "case_id": f"REQ-JPIP-{number:03d}",
        "source_control_id": CONTROL_ID,
        "transfer_syntax": SYNTAXES[kind],
        "document_builder": "jpip_statement_cases.build_document",
        "operation": operation,
        "requirement_ids": list(requirements),
        "expected": [expected], "expected_cascades": [],
        "changed": changed, "rationale": rationale,
        "citation": {"part": "PS3.5", "edition": "2026d", "section": section,
                     "url": f"https://dicom.nema.org/medical/dicom/current/output/chtml/part05/sect_{section}.html"},
    }


CASES = (
    _case(1, "jpip", "photometric", ("Ps5_A_6_71e374",), "image-metadata",
          "Change the three-component JPIP Photometric Interpretation from YBR_ICT to RGB.",
          "JPIP Referenced allows MONOCHROME1, MONOCHROME2, YBR_ICT or YBR_RCT, not RGB."),
    _case(2, "htj2k", "photometric", ("Ps5_A_11_5f6235",), "image-metadata",
          "Change the three-component HTJ2K JPIP Photometric Interpretation from YBR_ICT to RGB.",
          "JPIP HTJ2K Referenced allows MONOCHROME1, MONOCHROME2, YBR_ICT or YBR_RCT, not RGB."),
    _case(3, "jpip", "missing-url", ("Ps5_A_6_be37ad", "Ps5_A_6_581e00"), "intrinsic-pixel-structure",
          "Remove Pixel Data Provider URL from the referenced image metadata.",
          "Referenced Pixel Data is supplied through the required Provider URL; no inline Pixel Data is substituted."),
    _case(4, "htj2k", "missing-url", ("Ps5_A_11_3b11ba", "Ps5_A_11_6a17ab"), "intrinsic-pixel-structure",
          "Remove Pixel Data Provider URL from the referenced image metadata.",
          "Referenced Pixel Data is supplied through the required Provider URL; no inline Pixel Data is substituted."),
    _case(5, "jpip", "transport", ("Ps5_8_4_1_dc90bc",), "intrinsic-pixel-structure",
          "Change the Pixel Data Provider URL scheme from HTTPS to FTP.",
          "The JPIP transport uses HTTP or HTTPS; a syntactically valid FTP URI still violates this requirement."),
    _case(6, "jpip", "floating", ("Ps5_A_6_dcb6d6",), "intrinsic-pixel-structure",
          "Add a Float Pixel Data Value to the JPIP referenced metadata.",
          "JPIP references integer Pixel Data and forbids Float Pixel Data; the added representation also triggers the IOD's exclusion."),
    _case(7, "htj2k", "floating", ("Ps5_A_11_3cba9b",), "intrinsic-pixel-structure",
          "Add a Float Pixel Data Value to the JPIP referenced metadata.",
          "JPIP references integer Pixel Data and forbids Float Pixel Data; the added representation also triggers the IOD's exclusion."),
)


def build_document(case_id: str | None, source: Path) -> bytes:
    """Build one valid JPIP metadata control (None) or its named defect."""
    document = pydicom.dcmread(source).to_json_dict()
    _normalize_empty_values(document)
    document.pop("7FE00010")
    document["00287FE0"] = {"vr": "UR", "Value": ["https://example.invalid/jpip/color.jp2"]}
    if case_id is not None:
        case = next((case for case in CASES if case["case_id"] == case_id), None)
        if case is None:
            raise ValueError(f"unknown JPIP case {case_id}")
        operation = case["operation"]
        if operation == "photometric":
            document["00280004"]["Value"] = ["RGB"]
        elif operation == "missing-url":
            del document["00287FE0"]
        elif operation == "transport":
            document["00287FE0"]["Value"] = ["ftp://example.invalid/jpip/color.jp2"]
        elif operation == "floating":
            document["7FE00008"] = {"vr": "OF", "InlineBinary": "AAAAAA=="}
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")

for case in CASES:
    if case["operation"] in ("missing-url", "floating"):
        case["expected_cascades"] = ["intrinsic-wsi-dicom-iod-attribute-presence"]
