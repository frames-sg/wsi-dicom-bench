"""Single-defect codestream cases of the v6 ``requirement-statement-evaluation-v1`` cohort.

Each case changes the codestream of one Frame with the ``codestream`` mutations, on the
last Frame of a multi-frame control (outside the Frames the independent decoder samples),
so only the codestream rule reports it. Expectations are set as for the rest of the cohort:
by running the frozen candidate and adjudicating each result against DICOM 2026c.
"""

from __future__ import annotations

from .iod_amendment_cases import _case as _spec, _cite, _edits, _op


PS35_JPEG = _cite("PS3.5", "8.2.1", "part05/sect_8.2.html#sect_8.2.1")
PS35_JPEG_ENCAPSULATION = _cite("PS3.5", "A.4.1", "part05/sect_A.4.html#sect_A.4.1")
PS35_J2K = _cite("PS3.5", "8.2.4", "part05/sect_8.2.4.html")
PS35_J2K_ENCAPSULATION = _cite("PS3.5", "A.4.4", "part05/sect_A.4.4.html")
PS35_HTJ2K = _cite("PS3.5", "8.2.14", "part05/sect_8.2.14.html")
PS35_HTJ2K_RPCL = _cite("PS3.5", "10.18.1", "part05/sect_10.18.html#sect_10.18.1")
PS33_SAMPLES_PER_PIXEL = _cite("PS3.3", "C.7.6.3.1.1", "part03/sect_C.7.6.3.html#sect_C.7.6.3.1.1")
PS33_IMAGE_PIXEL = _cite("PS3.3", "C.7.6.3 Table C.7-11c", "part03/sect_C.7.6.3.html#table_C.7-11c")

LAST_FRAME = (
    "The edited Frame is the last one, outside the three Frames the independent decoder "
    "samples, and its Fragment and offset table stay consistent, so only the codestream "
    "rule reports the defect."
)
CODED_TRANSFORM = (
    "The value is one the Transfer Syntax table and the IOD admit, so only the codestream "
    "rule, which compares it with the coded transform, reports it."
)


def _patch(marker: str, offset: int, expect: str, value: str) -> dict:
    """Overwrite ``expect`` with ``value`` at ``offset`` in the first ``marker`` segment."""
    return {"operation": "patch", "marker": marker, "occurrence": 0, "offset": offset,
            "expect": expect, "value": value}


def _remove(marker: str, occurrence: int | str = 0) -> dict:
    return {"operation": "remove_segment", "marker": marker, "occurrence": occurrence}


def _insert(marker: str, position: str, value: str) -> dict:
    return {"operation": "insert", "marker": marker, "position": position, "value": value}


def _insert_icc(**fields) -> dict:
    """Two APP2 ICC_PROFILE chunks of the Optical Path ICC Profile, right after SOI."""
    return {"operation": "insert_icc", "marker": "FFD8", "position": "after", "chunks": 2, **fields}


def _case(case_id, control, mutation, parameters, requirements, changed, citation, rationale) -> dict:
    return {**_spec(case_id, control, mutation, parameters, ["codestream"], changed, citation, rationale),
            "requirement_ids": list(requirements)}


def _edit(case_id, control, frame_index, operations, requirements, changed, citation, rationale) -> dict:
    """A ``codestream_edit`` of the zero-based Frame ``frame_index``."""
    return _case(case_id, control, "codestream_edit", {"frame_index": frame_index, "operations": operations},
                 requirements, changed, citation, rationale)


CODESTREAM_CASES = (
    _edit("REQ-CS-001", "CP02-JPEG-16F", 15, [_patch("FFC0", 5, "0001", "0002")],
          ("Ps5_8_2_1_803014", "Ps3_C_7_6_6_1_1_899f77"),
          "Frame 16: set SOF0 number of lines Y from 1 to 2; Rows (0028,0010) stays 1.",
          PS35_JPEG,
          "8.2.1 requires the Pixel Data attributes to agree with the compressed stream, and "
          "C.7.6.6.1.1 defines every Frame by those attributes; the SOF of Frame 16 now codes two "
          "lines. " + LAST_FRAME),
    _edit("REQ-CS-002", "CP02-JPEG-16F", 15, [_patch("FFC0", 7, "0001", "0002")],
          ("Ps5_8_2_1_803014",),
          "Frame 16: set SOF0 samples per line X from 1 to 2; Columns (0028,0011) stays 1.",
          PS35_JPEG,
          "The SOF samples per line disagree with Columns (8.2.1). " + LAST_FRAME),
    _edit("REQ-CS-003", "CP02-JPEG-16F", 15, [_patch("FFC0", 4, "08", "0C")],
          ("Ps5_8_2_1_803014", "Ps5_A_4_1_1e2871"),
          "Frame 16: set SOF0 sample precision P from 8 to 12.",
          PS35_JPEG,
          "A 12-bit precision is outside Process 1 of 1.2.840.10008.1.2.4.50 (Table A.4-3) and "
          "disagrees with Bits Stored 8 (8.2.1); both are messages of the codestream rule. "
          + LAST_FRAME),
    _edit("REQ-CS-004", "CP02-JPEG-16F", 15, [_patch("FFC0", 1, "C0", "C1")],
          ("Ps5_A_4_1_1e2871",),
          "Frame 16: change the SOF0 marker to SOF1 (extended sequential DCT); nothing else.",
          _cite("PS3.5", "A.4.1 Table A.4-3", "part05/sect_A.4.html#table_A.4-3"),
          "PS3.5 A.4.1: JPEG Baseline identifies Process 1 (SOF0); a SOF1 bit stream under "
          "1.2.840.10008.1.2.4.50 is not compliant (A.4.1 Note). " + LAST_FRAME),
    _edit("REQ-CS-005", "CP02-JPEG-16F", 15, [_remove("FFC4", "all")],
          ("Ps5_A_4_1_c5999c",),
          "Frame 16: delete all four DHT marker segments.",
          PS35_JPEG_ENCAPSULATION,
          "Without its Huffman table specifications Frame 16 is an abbreviated-format stream; "
          "A.4.1 requires the interchange format for every Frame. " + LAST_FRAME),
    _edit("REQ-CS-006", "CP02-JPEG-16F", 15, [_remove("FFDB", "all")],
          ("Ps5_A_4_1_c5999c",),
          "Frame 16: delete both DQT marker segments.",
          PS35_JPEG_ENCAPSULATION,
          "The scan's quantization tables are not specified in the Frame (A.4.1 interchange "
          "format). " + LAST_FRAME),
    _edit("REQ-CS-007", "CP02-JPEG-16F", 15, [{"operation": "truncate_end", "expect": "FFD9"}],
          ("Ps5_A_4_1_55978a",),
          "Frame 16: remove the final EOI marker (FFD9H).",
          PS35_JPEG_ENCAPSULATION,
          "Each Frame is encoded separately as one complete interchange-format stream, which ends "
          "with EOI. " + LAST_FRAME),
    _edit("REQ-CS-008", "CP02-JPEG-16F", 15, [_insert("FFD8", "after", "FFD8")],
          ("Ps5_A_4_1_55978a",),
          "Frame 16: insert a second SOI marker right after the first.",
          PS35_JPEG_ENCAPSULATION,
          "A second SOI before the first scan starts another stream inside the Frame. "
          + LAST_FRAME),
    _case("REQ-CS-009", "CP02-JPEG-16F", "codestream_refragment",
          {"frame_index": 15, "parts": [[0, None], [0, None]]},
          ("Ps5_A_4_1_b3fb04", "Ps5_A_4_1_55978a"),
          "Encode Frame 16 as two Fragments that each hold the complete Frame 16 stream; the "
          "Extended Offset Table is replaced by an equivalent Basic Offset Table.",
          PS35_JPEG_ENCAPSULATION,
          "The second Fragment of Frame 16 begins a new stream after the first ended one, so the "
          "Frame's Fragments carry two encoded images. Both offset table forms are valid for "
          "one-Fragment Frames; the Extended Offset Table cannot address a split Frame, so the "
          "case uses the Basic Offset Table, which pixel-structure accepts. " + LAST_FRAME),
    _edit("REQ-CS-010", "CP02-JPEG-16F", 15, [_insert_icc(invert_byte=128)],
          ("Ps5_8_2_1_d49433",),
          "Frame 16: insert two APP2 ICC_PROFILE segments holding the Optical Path ICC Profile "
          "with byte 128 inverted.",
          PS35_JPEG,
          "8.2.1: APP2 ICC_PROFILE chunks, when present, concatenate to exactly the ICC Profile "
          "(0028,2000) Value; one byte differs. Decoders ignore APP2. " + LAST_FRAME),
    _edit("REQ-CS-011", "CP03-JPEG-1F", 0, [_insert_icc(omit_chunk=2)],
          ("Ps5_8_2_1_d49433",),
          "Frame 1: insert APP2 ICC_PROFILE chunk 1 of 2 holding the first half of the Optical "
          "Path ICC Profile, without chunk 2.",
          PS35_JPEG,
          "The embedded chunks concatenate to half the profile, not the ICC Profile Value (8.2.1). "
          "The single Frame is decoded by the independent decoder, which ignores APP2 segments, so "
          "only the codestream rule reports the defect."),
    _case("REQ-CS-012", "CP02-JPEG-16F", "iod_edits",
          _edits(_op("set", ["PhotometricInterpretation"], "RGB")),
          ("Ps3_C_7_6_3_1_1_c17c68",),
          "Set Photometric Interpretation (0028,0004) from YBR_FULL_422 to RGB; the Frames keep "
          "their 2x1 luminance sampling.",
          PS33_SAMPLES_PER_PIXEL,
          "C.7.6.3.1.1: all image planes have the same Rows and Columns, with YBR_FULL_422 the "
          "only exception for downsampled chrominance; the SOF of every Frame subsamples "
          "components 2 and 3. " + CODED_TRANSFORM),
    _case("REQ-CS-013", "CP02-JPEG-16F", "codestream_donor_frame",
          {"frame_index": 15, "donor_control": "CP04-J2K-LOSSLESS-16F", "donor_frame_index": 15},
          ("Ps10_7_2_770df5",),
          "Replace Frame 16 with Frame 16 of the JPEG 2000 lossless control (same 1x1x3 8-bit "
          "pixel shape).",
          _cite("PS3.10", "7.2", "part10/sect_7.2.html"),
          "PS3.10 7.2: the Data Set is encoded in the Transfer Syntax the File Meta Information "
          "identifies; Frame 16 is a JPEG 2000 codestream under JPEG Baseline. " + LAST_FRAME),
    _edit("REQ-CS-014", "CP04-J2K-LOSSLESS-16F", 15, [_patch("FF51", 6, "00000001", "00000002")],
          ("Ps5_8_2_4_47cc48",),
          "Frame 16: set SIZ Xsiz from 1 to 2; Columns (0028,0011) stays 1.",
          PS35_J2K,
          "The SIZ image width disagrees with Columns (8.2.4). " + LAST_FRAME),
    _edit("REQ-CS-015", "CP09-J2K-LOSSLESS-4F", 3,
          [_patch("FF51", 40, "070101070101070101", "0B01010B01010B0101")],
          ("Ps5_8_2_4_47cc48",),
          "Frame 4: set the SIZ precision of all three components from 8 to 12 bits.",
          PS35_J2K,
          "The coded sample precision disagrees with Bits Stored 8 (8.2.4). " + LAST_FRAME),
    _edit("REQ-CS-016", "CP04-J2K-LOSSLESS-16F", 15, [_patch("FF51", 46, "07", "0B")],
          ("Ps3_C_7_11c_BitsStored_d52069",
           "Ps3_C_7_11c_BitsAllocated_69f390",
           "Ps3_C_7_11c_HighBit_a62636"),
          "Frame 16: set the SIZ precision of component 2 alone from 8 to 12 bits.",
          PS33_IMAGE_PIXEL,
          "Table C.7-11c: each sample has the same Bits Allocated, Bits Stored and High Bit; the "
          "components now code 8, 8 and 12 bits. Component 0 still matches Bits Stored. "
          + LAST_FRAME),
    _edit("REQ-CS-017", "CP09-J2K-LOSSLESS-4F", 3, [_patch("FF51", 43, "07", "87")],
          ("Ps3_C_7_11c_PixelRepresentation_178735",),
          "Frame 4: mark SIZ component 1 as signed.",
          PS33_IMAGE_PIXEL,
          "Table C.7-11c: each sample has the same Pixel Representation; component 1 is now signed "
          "while 0 and 2 are not. " + LAST_FRAME),
    _edit("REQ-CS-018", "CP09-J2K-LOSSLESS-4F", 3, [_patch("FF51", 44, "01", "02")],
          ("Ps3_C_7_6_3_1_1_c17c68",),
          "Frame 4: set the SIZ horizontal separation XRsiz of component 1 from 1 to 2.",
          PS33_SAMPLES_PER_PIXEL,
          "C.7.6.3.1.1: all image planes have the same Rows and Columns; component 1 now spans one "
          "column of the two. " + LAST_FRAME),
    _case("REQ-CS-019", "CP04-J2K-LOSSLESS-16F", "iod_edits",
          _edits(_op("set", ["PhotometricInterpretation"], "RGB")),
          ("Ps5_8_2_4_045661", "Ps3_C_8_12_4_1_5_2d19f4"),
          "Set Photometric Interpretation (0028,0004) from YBR_RCT to RGB.",
          PS35_J2K,
          "Every COD applies the Part 1 reversible multiple component transformation, so 8.2.4 "
          "requires YBR_RCT, and C.8.12.4.1.5 does not use RGB for components that are actually "
          "YBR. " + CODED_TRANSFORM),
    _edit("REQ-CS-020", "CP09-J2K-LOSSLESS-4F", 3, [_patch("FF52", 8, "01", "00")],
          ("Ps5_8_2_4_478fac",),
          "Frame 4: set the COD multiple component transformation from 1 to 0.",
          PS35_J2K,
          "With no multiple component transformation the components are those Photometric "
          "Interpretation names, but YBR_RCT names RCT-transformed components (8.2.4). "
          + LAST_FRAME),
    _edit("REQ-CS-021", "CP09-J2K-LOSSLESS-4F", 3, [_patch("FF52", 13, "01", "00")],
          ("Ps5_A_4_4_7d7f64", "Ps5_8_2_4_f23101"),
          "Frame 4: set the COD wavelet transformation from 1 (5-3 reversible) to 0 (9-7 "
          "irreversible).",
          PS35_J2K_ENCAPSULATION,
          "1.2.840.10008.1.2.4.90 identifies the reversible coding process (A.4.4), and with the "
          "9-7 wavelet the multiple component transformation is the ICT, which requires YBR_ICT "
          "(8.2.4); both are messages of the codestream rule. " + LAST_FRAME),
    _edit("REQ-CS-022", "CP04-J2K-LOSSLESS-16F", 15, [_patch("FF5C", 4, "40", "41")],
          ("Ps5_A_4_4_7d7f64",),
          "Frame 16: set the QCD quantization style from 0 (none) to 1 (scalar derived).",
          PS35_J2K_ENCAPSULATION,
          "The lossless JPEG 2000 Transfer Syntax uses no quantization (A.4.4). " + LAST_FRAME),
    _edit("REQ-CS-023", "CP04-J2K-LOSSLESS-16F", 15, [_patch("FF52", 12, "00", "40")],
          ("Ps5_A_4_4_7d7f64",),
          "Frame 16: set the COD code-block style HT bit (40H).",
          PS35_J2K_ENCAPSULATION,
          "HT code-blocks are the ISO/IEC 15444-15 coding process, which JPEG 2000 Lossless Only "
          "does not identify (A.4.4). " + LAST_FRAME),
    _edit("REQ-CS-024", "CP04-J2K-LOSSLESS-16F", 15, [_patch("FF51", 4, "0000", "8000")],
          ("Ps5_A_4_4_5e53e6",),
          "Frame 16: set SIZ Rsiz bit 15 (Part 2 capabilities).",
          PS35_J2K_ENCAPSULATION,
          "Part 1 Transfer Syntaxes admit only Part 1 features; Rsiz declares Part 2 capabilities "
          "that Part 1 decoders cannot decode (A.4.4). " + LAST_FRAME),
    _edit("REQ-CS-025", "CP09-J2K-LOSSLESS-4F", 3, [_insert("FF90", "before", "FF70000300")],
          ("Ps5_A_4_4_5e53e6",),
          "Frame 4: insert a Part 2 DCO marker segment (FF70H) before the first SOT.",
          PS35_J2K_ENCAPSULATION,
          "Variable DC offset is a JPEG 2000 Part 2 extension not admitted in a Part 1 Transfer "
          "Syntax (A.4.4). " + LAST_FRAME),
    _edit("REQ-CS-026", "CP04-J2K-LOSSLESS-16F", 15, [{"operation": "wrap_jp2"}],
          ("Ps5_A_4_4_044fb8",),
          "Frame 16: wrap the codestream in JP2 signature, File Type, JP2 Header and Contiguous "
          "Codestream boxes.",
          PS35_J2K_ENCAPSULATION,
          "A.4.4: the optional JP2 file format header shall not be included. " + LAST_FRAME),
    _edit("REQ-CS-027", "CP04-J2K-LOSSLESS-16F", 15, [{"operation": "append_copy"}],
          ("Ps5_A_4_4_e0caa8", "Ps5_A_4_4_480185"),
          "Frame 16: append a second copy of its codestream after EOC.",
          PS35_J2K_ENCAPSULATION,
          "Frame 16's Fragment now holds two complete codestreams, so the Frame is not encoded "
          "separately and the Fragment holds data of more than one encoded image (A.4.4). "
          + LAST_FRAME),
    _edit("REQ-CS-028", "CP09-J2K-LOSSLESS-4F", 3,
          [{"operation": "truncate_end", "expect": "FFD9"}],
          ("Ps5_A_4_4_e0caa8",),
          "Frame 4: remove the final EOC marker (FFD9H).",
          PS35_J2K_ENCAPSULATION,
          "The Frame no longer holds one complete JPEG 2000 codestream (A.4.4). " + LAST_FRAME),
    _case("REQ-CS-029", "CP04-J2K-LOSSLESS-16F", "codestream_donor_frame",
          {"frame_index": 15, "donor_control": "CP02-JPEG-16F", "donor_frame_index": 15},
          ("Ps5_A_4_4_05e878", "Ps10_7_2_770df5"),
          "Replace Frame 16 with Frame 16 of the JPEG Baseline control (same 1x1x3 8-bit pixel "
          "shape).",
          PS35_J2K_ENCAPSULATION,
          "A.4.4: every Frame uses the JPEG 2000 bit stream; Frame 16 is a JPEG stream under JPEG "
          "2000 Lossless Only (PS3.10 7.2). " + LAST_FRAME),
    _edit("REQ-CS-030", "CP06-HTJ2K-LOSSLESS-16F", 15, [_patch("FF51", 6, "00000001", "00000002")],
          ("Ps5_8_2_14_b9d8c7",),
          "Frame 16: set SIZ Xsiz from 1 to 2; Columns (0028,0011) stays 1.",
          PS35_HTJ2K,
          "The HTJ2K SIZ image width disagrees with Columns (8.2.14). " + LAST_FRAME),
    _case("REQ-CS-031", "CP06-HTJ2K-LOSSLESS-16F", "iod_edits",
          _edits(_op("set", ["PhotometricInterpretation"], "RGB")),
          ("Ps5_8_2_14_8c86ea",),
          "Set Photometric Interpretation (0028,0004) from YBR_RCT to RGB.",
          PS35_HTJ2K,
          "Every COD applies the reversible multiple component transformation, so 8.2.14 requires "
          "YBR_RCT. " + CODED_TRANSFORM),
    _edit("REQ-CS-032", "CP06-HTJ2K-LOSSLESS-16F", 15, [_patch("FF52", 8, "01", "00")],
          ("Ps5_8_2_14_557a1e",),
          "Frame 16: set the COD multiple component transformation from 1 to 0.",
          PS35_HTJ2K,
          "Untransformed components are those Photometric Interpretation names; YBR_RCT names "
          "transformed ones (8.2.14). " + LAST_FRAME),
    _edit("REQ-CS-033", "CP06-HTJ2K-LOSSLESS-16F", 15, [_patch("FF52", 13, "01", "00")],
          ("Ps5_A_4_4_259d88", "Ps5_8_2_14_6f1193"),
          "Frame 16: set the COD wavelet transformation from 5-3 reversible to 9-7 irreversible.",
          PS35_J2K_ENCAPSULATION,
          "HTJ2K Lossless (1.2.840.10008.1.2.4.201) identifies the reversible process (A.4.4), and "
          "the irreversible transformation requires YBR_ICT (8.2.14). " + LAST_FRAME),
    _edit("REQ-CS-034", "CP06-HTJ2K-LOSSLESS-16F", 15, [_patch("FF51", 4, "4000", "0000")],
          ("Ps5_A_4_4_259d88",),
          "Frame 16: clear SIZ Rsiz bit 14 (HTJ2K capabilities).",
          PS35_J2K_ENCAPSULATION,
          "An HTJ2K codestream sets Rsiz bit 14 (ISO/IEC 15444-15); without it the codestream is "
          "not the HTJ2K coding the Transfer Syntax identifies (A.4.4). " + LAST_FRAME),
    _edit("REQ-CS-035", "CP06-HTJ2K-LOSSLESS-16F", 15, [_remove("FF50")],
          ("Ps5_A_4_4_259d88",),
          "Frame 16: delete the CAP marker segment.",
          PS35_J2K_ENCAPSULATION,
          "An HTJ2K codestream carries CAP with Part 15 capabilities (ISO/IEC 15444-15); the Frame "
          "no longer does (A.4.4). " + LAST_FRAME),
    _edit("REQ-CS-036", "CP07-HTJ2K-RPCL-4F", 3, [_patch("FF52", 5, "02", "00")],
          ("Ps5_10_18_1_b86460",),
          "Frame 4: set the COD progression order from RPCL to LRCP.",
          PS35_HTJ2K_RPCL,
          "10.18.1: the HTJ2K Lossless RPCL progression order shall be RPCL. " + LAST_FRAME),
    _edit("REQ-CS-037", "CP07-HTJ2K-RPCL-4F", 3,
          [_insert("FF90", "before", "FF5F000900000001010300")],
          ("Ps5_10_18_1_b86460",),
          "Frame 4: insert a POC marker segment whose one progression change is LRCP.",
          PS35_HTJ2K_RPCL,
          "A progression order change to LRCP breaks the required RPCL progression (10.18.1). "
          + LAST_FRAME),
    _edit("REQ-CS-038", "CP07-HTJ2K-RPCL-4F", 3, [_remove("FF55")],
          ("Ps5_10_18_1_080cc2",),
          "Frame 4: delete the TLM marker segment.",
          PS35_HTJ2K_RPCL,
          "10.18.1: the Tile Length Markers shall be present. " + LAST_FRAME),
)
