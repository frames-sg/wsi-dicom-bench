"""Residual codec/header obligations, using independently encoded positive controls."""
from __future__ import annotations

from pathlib import Path

import pydicom

from . import controls_v7_wsi as author
from .iod_amendment_cases import _case as _spec, _cite, _edits, _op
from .mutations.codec_statement import with_identity_stage
from .mutations.codestream import _rewrap
from .mutations.dicom import frames

CONTROL_PATHS = {
    "V7-RLE-PACKETS": "controls-v7/codecs/rle-packets.dcm",
    "V7-J2K-TWO-STAGE": "controls-v7/codecs/j2k-two-stage.dcm",
}


def write_controls(root: Path):
    raster = [[[11 + 10 * (row // 2) + column] if row % 2 == 0 else [42 + row // 2]
               for column in range(8)] for row in range(4)]
    spec = author.Spec("V7-RLE-PACKETS", rows=2, columns=4, total_rows=4, total_columns=8,
                       samples=1, photometric="MONOCHROME2", raster=raster)
    built = author._dcmtk_control("V7-RLE-PACKETS", spec, author.RLE, "dcmcrle", (), "dcmdrle")
    path = root / CONTROL_PATHS["V7-RLE-PACKETS"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(built["V7-RLE-PACKETS.dcm"])
    ds = pydicom.dcmread(root / "controls-v7/wsi/W7-TS-J2K-PART2-ICT.dcm")
    ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID = "1.2.826.0.1.3680043.10.999.956.1"
    _rewrap(ds, [with_identity_stage(frame) for frame in frames(ds)])
    pydicom.dcmwrite(root / CONTROL_PATHS["V7-J2K-TWO-STAGE"], ds, enforce_file_format=True)
    write_waveform8(root)


def _case(number, control, mutation, parameters, requirements, section, changed, rationale,
          expected=("codestream",)):
    return _spec(f"REQ-CODEC-{number:03d}", control, mutation, parameters, list(expected), changed,
                 _cite("PS3.5", section, "part05/sect_" + section + ".html"), rationale,
                 requirement_ids=list(requirements))


def _patch(number, control, operation, requirements, section, changed, rationale):
    return _case(number, control, "codestream_edit", {"frame_index": 0, "operations": [operation]},
                 requirements, section, changed, rationale)


CASES = (
    _patch(1, "W7-TS-HTJ2K-RPCL-128",
           {"operation": "patch", "marker": "FF52", "offset": 9, "expect": "05", "value": "00"},
           ("Ps5_10_18_1_a950cd",), "10.18.1",
           "Set the 128x128 Frame's COD decomposition count from 5 to 0.",
           "With no decomposition its base resolution is 128x128, exceeding 64 in both dimensions."),
    _case(2, "W7-TS-RLE-RGB", "iod_edits", _edits(
        _op("set", ["BitsAllocated"], 16), _op("set", ["BitsStored"], 16), _op("set", ["HighBit"], 15)),
        ("Ps5_8_2_2_c961f8",), "8.2.2", "Declare 16-bit RGB samples while preserving the three byte-segment RLE Frames.",
        "The declared format is internally consistent but needs six RLE segments, not the encoded three."),
    _patch(3, "W7-TS-JPEG-LS-LOSSLESS-RGB",
           {"operation": "patch", "marker": "FFF7", "offset": 7, "expect": "0008", "value": "0009"},
           ("Ps5_8_2_3_c509e8",), "8.2.3", "Change the JPEG-LS SOF55 width from 8 to 9.",
           "The compressed header width disagrees with the unchanged Columns Attribute."),
    _case(4, "W7-TS-JPEG-LS-NEAR-RGB", "encoding_rewrite",
          {"operations": [{"op": "file_meta_set", "tag": "(0002,0010)", "text": "1.2.840.10008.1.2.4.80"}]},
          ("Ps5_A_4_3_e86721",), "A.4.3", "Declare JPEG-LS Lossless for the unchanged NEAR=2 Frames.",
          "A nonzero near-lossless error bound is incompatible with the Lossless Transfer Syntax."),
    _patch(5, "W7-TS-JPEG-LS-LOSSLESS-RGB",
           {"operation": "remove_segment", "marker": "FFF7"},
           ("Ps5_A_4_3_79e44a",), "A.4.3", "Remove the JPEG-LS SOF55 frame header while retaining the scan.",
           "Interchange format includes the parameters needed to interpret each Frame."),
    _case(6, "W7-TS-JXL-LOSSY-MONO8", "encoding_rewrite",
          {"preserve_source_encoding": True, "operations": [{"op": "file_meta_set", "tag": "(0002,0010)", "text": "1.2.840.10008.1.2.4.110"}]},
          ("Ps5_A_4_12_814b6e",), "A.4.12", "Declare JPEG XL Lossless for the unchanged VarDCT lossy Frames.",
          "The encoded coding process is not the lossless process named by the Transfer Syntax."),
    _case(7, "W7-TS-JXL-LOSSLESS-RGB", "encoding_rewrite",
          {"preserve_source_encoding": True, "operations": [{"op": "patch_value", "path": ["Rows"], "offset": 0, "hex": "0700"}]},
          ("Ps5_8_2_15_091321",), "8.2.15", "Set Rows to 7 while the JPEG XL headers still encode 8 rows.",
          "The one wrong Rows Value conflicts with both the stream dimensions and WSI tile geometry."),
    _patch(8, "W7-TS-J2K-PART2-ICT",
           {"operation": "insert", "marker": "FF90", "position": "before", "value": "FF79000300"},
           ("Ps5_A_4_4_ab7220",), "A.4.4", "Add an ATK marker identifying a Part 2 extension outside Annex J.",
           "The DICOM Part 2 syntaxes admit the Annex J multiple component extensions only."),
    _case(9, "V7-J2K-TWO-STAGE", "codec_statement_defect", {"operation": "two-component-collections"},
          ("Ps5_A_4_4_6e9c4b",), "A.4.4", "Partition the active identity stage into two collections within the one Fragment.",
          "Both null transforms preserve the same components and samples; the single Fragment now carries two collections."),
    *(_case(number, "V7-RLE-PACKETS", "codec_statement_defect", {"operation": operation},
            (requirement,), section, changed, rationale)
      for number, operation, requirement, section, changed, rationale in (
        (10, "rle-padding", "Ps5_G_3_3774f3", "G.3", "Change the RLE segment's required NULL pad to 01H.",
         "The seven encoded run bytes need a trailing zero to make the segment even."),
        (11, "rle-forbidden-run", "Ps5_G_3_1_48c218", "G.3.1", "Insert two -128 no-op run headers before the RLE packets.",
         "The pixel values and even segment length remain unchanged, but the reserved run header is forbidden."),
        (12, "rle-literal-repeat", "Ps5_G_3_1_961ac0", "G.3.1", "Make the first three literal sample values equal without changing their packet.",
         "Three equal consecutive samples must be encoded as a Replicate Run."),
        (13, "rle-row-crossing", "Ps5_G_3_1_5f6b0b", "G.3.1", "Repacketize the unchanged samples so one literal run crosses the row boundary.",
         "The decoded values and dimensions are unchanged; each row nevertheless must be encoded separately."),
        (14, "rle-unused-offset", "Ps5_G_5_92c185", "G.5", "Set the first unused RLE Segment Offset to 64 instead of zero.",
         "Only the one declared segment is used, and all unused segment offsets must be zero."),
    )),
    _case(15, "W7-TS-DEFLATED-IMAGE-FRAME", "encoding_rewrite",
          {"preserve_source_encoding": True, "operations": [{"op": "patch_value", "path": ["PixelData"], "offset": 229, "hex": "01"}]},
          ("Ps5_A_4_13_a456ca",), "A.4.13", "Change the first Frame's NULL after its odd-length Deflate stream to 01H.",
          "The Deflate stream and decoded samples are unchanged; its single trailing pad must be NULL."),
    _case(16, "W7-TS-ENCAPSULATED-UNCOMPRESSED", "encoding_rewrite",
          {"operations": [{"op": "set_vr", "path": ["PixelData"], "vr": "OW"}]},
          ("Ps5_A_4_11_bd0aed",), "A.4.11", "Encode encapsulated uncompressed Pixel Data with OW rather than OB.",
          "All encapsulated transfer syntaxes use OB for Pixel Data.", expected=("encoding",)),
    _case(17, "CP10-EVRLE-16F", "encoding_rewrite",
          {"operations": [{"op": "set_element_length", "path": ["PixelData"], "length": 50}]},
          ("Ps5_7_1_2_85dc52",), "7.1.2", "Increase the final Pixel Data Value Length by two without adding bytes.",
          "The length extends past the available Value; parsing and encoded-length inspection report this same defect.",
          expected=("encoding",)),
    _case(18, "V7-WAVEFORM", "encoding_rewrite",
          {"operations": [{"op": "set_vr", "path": ["WaveformSequence", 0, "WaveformData"], "vr": "OB"}]},
          ("Ps5_8_3_8dc825",), "8.3", "Change 16-bit Waveform Data VR from OW to OB.",
          "Waveform Bits Allocated 16 requires OW.", expected=("encoding",)),
)

# The last Value overruns the file, so the parser reports the same length defect too.
CASES[16]["expected_cascades"] = ["intrinsic-pixel-structure"]

CONTROL_PATHS["V7-WAVEFORM-8"] = "controls-v7/codecs/waveform-8.dcm"


def write_waveform8(root: Path):
    """A.34.5 permits signed-byte samples in Ambulatory ECG Waveforms."""
    import struct
    from pydicom.uid import AmbulatoryECGWaveformStorage
    ds = pydicom.dcmread(root / "controls-v7/iods/waveform.dcm")
    ds.SOPClassUID = ds.file_meta.MediaStorageSOPClassUID = AmbulatoryECGWaveformStorage
    ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID = "1.2.826.0.1.3680043.10.999.956.2"
    group = ds.WaveformSequence[0]
    samples = struct.unpack("<4h", group.WaveformData)
    group.WaveformBitsAllocated = 8
    group.WaveformSampleInterpretation = "SB"
    group.ChannelDefinitionSequence[0].WaveformBitsStored = 8
    group.WaveformData = struct.pack("4b", *samples)
    group[0x54001010].VR = "OB"
    pydicom.dcmwrite(root / CONTROL_PATHS["V7-WAVEFORM-8"], ds, enforce_file_format=True)


CASES += (
    _case(19, "V7-WAVEFORM-8", "encoding_rewrite",
          {"operations": [{"op": "set_vr", "path": ["WaveformSequence", 0, "WaveformData"], "vr": "OW"}]},
          ("Ps5_8_3_7a124d",), "8.3", "Change Explicit VR 8-bit Waveform Data from OB to OW.",
          "An Explicit VR syntax uses OB for 8-bit Waveform Data.", expected=("encoding",)),
    _case(20, "V7-WAVEFORM", "encoding_rewrite",
          {"edits": [_op("insert", ["WaveformSequence", 0, "ChannelDefinitionSequence", 0, "ChannelMinimumValue"], "ffff", vr="OW")],
           "operations": [{"op": "set_vr", "path": ["WaveformSequence", 0, "ChannelDefinitionSequence", 0, "ChannelMinimumValue"], "vr": "OB"}]},
          ("Ps5_8_3_7c241f",), "8.3", "Encode the channel's minimum sample -1 with OB while Waveform Data retains OW.",
          "The related channel value uses the same VR as Waveform Data.", expected=("encoding",)),
)
CASES[6]["expected_cascades"] = ["intrinsic-wsi-dicom-tile-geometry", "intrinsic-wsi-dicom-wsi-image"]

# A named failure must diagnose this clause, rather than merely another
# property handled by the same broad codec/encoding rule.
for case, fragment in zip(CASES, (
    "128x128 base resolution", "makes 6 Byte Segments", "SOF55 samples per line is 9",
    "SOS NEAR 2 selects near-lossless coding", "has no SOF55 frame header",
    "first frame uses VarDCT encoding", "JPEG XL image height is 8",
    "Part 2 Annex other than the Annex J", "MCC stage 4 defines 2 component collections",
    "padded with a nonzero byte", "run header of -128", "contains a three-byte repeat",
    "crosses the row boundary", "all unused segment offsets are zero",
    "odd-length stream is followed by a single trailing NULL byte",
    "encapsulated Pixel Data with VR OW", "needs 50 bytes but the Data Set ends after 48",
    "VR OB with Waveform Bits Allocated (5400,1004) 16",
    "VR OW with Waveform Bits Allocated (5400,1004) 8",
    "ChannelMinimumValue (5400,0110): VR OB where Waveform Data (5400,1010) is OW",
), strict=True):
    case["message_fragment"] = fragment

CONTROL_TOOL_LIMITS = {
    "V7-J2K-TWO-STAGE": "OpenJPEG opj_decompress rejects SGcod MCT=2 in both the original independently encoded Part2 ICT control and this control with an identity stage; this decoder limitation does not adjudicate Annex J conformance."
}
