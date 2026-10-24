"""Single-component MPEG2 controls, with one-defect cases.

Control authoring requires an existing FFmpeg executable; validation and mutation do
not. The synthetic MPEG2 elementary streams contain four grayscale frames and no
sound. Encapsulation uses one fragment and an empty Basic Offset Table.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pydicom
from pydicom.encaps import encapsulate

from .iod_amendment_cases import _case as _spec, _cite, _edits, _op

CONTROL_PATHS = {
    "V7-MPEG2-MAIN-MONO": "controls-v7/motion/mpeg2-main-mono.dcm",
    "V7-MPEG2-HIGH-MONO": "controls-v7/motion/mpeg2-high-mono.dcm",

}


def write_controls(root: Path, ffmpeg: Path) -> None:
    """Write separate synthetic fixtures; never change either source control."""
    import numpy as np

    source = root / "controls-v7/wsi/W7-TS-JPEG-EXTENDED-MONO8.dcm"
    for index, (control, rows, columns, suffix, level) in enumerate((
        ("V7-MPEG2-MAIN-MONO", 16, 16, "100", "8"),
        ("V7-MPEG2-HIGH-MONO", 720, 1280, "101", "4"),
    ), 1):
        ds = pydicom.dcmread(source)
        frames = np.stack([np.full((rows, columns), 32 + 48 * frame, dtype=np.uint8)
                           for frame in range(4)])
        encoded = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-f", "rawvideo",
             "-pixel_format", "gray", "-video_size", f"{columns}x{rows}", "-framerate", "25",
             "-i", "pipe:0", "-frames:v", "4", "-an", "-c:v", "mpeg2video", "-profile:v", "4",
             "-level:v", level, "-pix_fmt", "yuv420p", "-g", "1", "-bf", "0",
             "-aspect", "16:9" if index == 2 else "1:1", "-f", "mpeg2video", "pipe:1"],
            input=frames.tobytes(), capture_output=True, check=True,
        ).stdout
        # Independent decoder confirms the stream has four full frames of the
        # declared size; lossy grayscale values remain within one level.
        decoded = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-f", "mpegvideo", "-i", "pipe:0",
             "-pix_fmt", "gray", "-f", "rawvideo", "pipe:1"],
            input=encoded, capture_output=True, check=True,
        ).stdout
        reconstructed = np.frombuffer(decoded, dtype=np.uint8).reshape(frames.shape)
        if np.max(np.abs(reconstructed.astype(np.int16) - frames.astype(np.int16))) > 1:
            raise ValueError("MPEG2 fixture does not preserve synthetic gray values within tolerance")
        ds.Rows, ds.Columns = rows, columns
        ds.TotalPixelMatrixRows, ds.TotalPixelMatrixColumns = rows * 2, columns * 2
        spacing = list(map(float, ds.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0].PixelSpacing))
        ds.ImagedVolumeHeight = rows * 2 * spacing[0]
        ds.ImagedVolumeWidth = columns * 2 * spacing[1]
        for frame, item in enumerate(ds.PerFrameFunctionalGroupsSequence):
            position = item.PlanePositionSlideSequence[0]
            r, c = frame // 2, frame % 2
            position.RowPositionInTotalImagePixelMatrix = r * rows + 1
            position.ColumnPositionInTotalImagePixelMatrix = c * columns + 1
            position.XOffsetInSlideCoordinateSystem = str(c * columns * spacing[1])
            position.YOffsetInSlideCoordinateSystem = str(r * rows * spacing[0])
        ds.CineRate = 25
        ds.LossyImageCompression = "01"
        ds.LossyImageCompressionMethod = "ISO_13818_2"
        ds.LossyImageCompressionRatio = str(round(frames.size / len(encoded), 6))
        ds.PixelData = encapsulate([encoded], has_bot=False)
        ds[0x7FE00010].VR = "OB"
        ds[0x7FE00010].is_undefined_length = True
        ds.file_meta.TransferSyntaxUID = "1.2.840.10008.1.2.4." + suffix
        ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID = f"1.2.826.0.1.3680043.10.999.955.{index}"
        output = root / CONTROL_PATHS[control]
        output.parent.mkdir(parents=True, exist_ok=True)
        pydicom.dcmwrite(output, ds, enforce_file_format=True)


def _edit(number, control, attribute, value, requirements, section, rationale):
    return _spec(
        f"REQ-MOTION-{number:03d}", control, "iod_edits",
        _edits(_op("set", [attribute], value)), ["image-metadata"],
        f"Set {attribute} to {value} while preserving the MPEG2 stream.",
        _cite("PS3.5", section, "part05/sect_" + section + ".html"),
        rationale, requirement_ids=list(requirements),
    )


CASES = (
    _edit(1, "V7-MPEG2-MAIN-MONO", "PhotometricInterpretation", "MONOCHROME1",
          ("Ps5_8_2_5_2ae16d",), "8.2.5", "Single-component MPEG2 requires MONOCHROME2."),
    _edit(2, "V7-MPEG2-HIGH-MONO", "PhotometricInterpretation", "MONOCHROME1",
          ("Ps5_8_2_6_601be2",), "8.2.6", "Single-component MPEG2 requires MONOCHROME2."),
    _edit(3, "V7-MPEG2-MAIN-MONO", "HighBit", 6,
          ("Ps5_8_2_5_eab09f",), "8.2.5", "Table 8.2.5-1 fixes High Bit at 7."),
    _edit(4, "V7-MPEG2-HIGH-MONO", "HighBit", 6,
          ("Ps5_8_2_6_303ae3",), "8.2.6", "Table 8.2.5-1 fixes High Bit at 7."),
    _edit(5, "V7-MPEG2-MAIN-MONO", "CineRate", "24",
          ("Ps5_8_2_5_7430f5",), "8.2.5", "Main Level permits 25 or 30 (including 30/1.001) frames per second."),
    _edit(6, "V7-MPEG2-HIGH-MONO", "CineRate", "24",
          ("Ps5_8_2_6_fdcabf",), "8.2.6", "High Level permits 25, 30, 50 or 60 frames per second and the stated NTSC variants."),
    _edit(7, "V7-MPEG2-HIGH-MONO", "Rows", 719,
          ("Ps5_8_2_6_862741",), "8.2.6", "High Level fixes Rows at 720 or 1080; the incorrect Rows value also disrupts tile geometry."),
    _edit(8, "V7-MPEG2-HIGH-MONO", "Columns", 1279,
          ("Ps5_8_2_6_ae499d",), "8.2.6", "At 720 Rows, High Level fixes Columns at 1280; the incorrect Columns value also disrupts tile geometry."),
    *(_spec(
        f"REQ-MOTION-{number:03d}", control, "encoding_rewrite",
        {"operations": [{"op": operation}]}, ["pixel-structure"], changed,
        _cite("PS3.5", section, "part05/sect_" + section + ".html"), rationale,
        requirement_ids=[requirement],
    ) for number, control, operation, section, requirement, changed, rationale in (
        (9, "V7-MPEG2-MAIN-MONO", "split_first_fragment", "8.2.5", "Ps5_8_2_5_8536a7",
         "Split the one MPEG2 stream Fragment into two, preserving every payload byte.",
         "The non-fragmentable Main Level syntax puts the entire stream in one Fragment."),
        (10, "V7-MPEG2-HIGH-MONO", "split_first_fragment", "8.2.6", "Ps5_8_2_6_a4b86d",
         "Split the one MPEG2 stream Fragment into two, preserving every payload byte.",
         "The non-fragmentable High Level syntax puts the entire stream in one Fragment."),
        (11, "V7-MPEG2-MAIN-MONO", "fill_basic_offset_table", "8.2.5", "Ps5_8_2_5_f85091",
         "Give the empty Basic Offset Table one zero offset.",
         "Main Level MPEG2 requires a present but empty Basic Offset Table."),
        (12, "V7-MPEG2-HIGH-MONO", "fill_basic_offset_table", "8.2.6", "Ps5_8_2_6_6b3ca2",
         "Give the empty Basic Offset Table one zero offset.",
         "High Level MPEG2 requires a present but empty Basic Offset Table."),
    )),
)

# Consequences of the one changed Attribute, not independent authored defects.
for case in CASES:
    number = int(case["case_id"].rsplit("-", 1)[1])
    case["expected_cascades"] = (
        ["intrinsic-wsi-dicom-iod-attribute-presence",
         "intrinsic-wsi-dicom-iod-enumerated-values", "intrinsic-wsi-dicom-icc-profile"]
        if number in (1, 2) else
        ["intrinsic-wsi-dicom-tile-geometry", "intrinsic-wsi-dicom-wsi-image"]
        if number in (7, 8) else []
    )
    if number in (1, 2):
        case["rationale"] += " The changed Photometric Interpretation also contradicts the WSI enumeration and the unchanged monochrome-only rescale/LUT and ICC conditions."
