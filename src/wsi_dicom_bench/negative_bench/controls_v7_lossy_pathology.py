"""Deterministic lossy Segmentation and Parametric Map positive controls."""

from __future__ import annotations

from pathlib import Path

import pydicom
from pydicom.encaps import encapsulate, generate_frames
from pydicom.tag import Tag


PACKAGE = Path(__file__).resolve().parent
CONTROL_PATHS = {
    "V7-SEG-FRACTIONAL-MPEG2": "controls-v7/iods/seg-fractional-mpeg2.dcm",
    "V7-PM-JPEGLS-NEAR": "controls-v7/iods/pm-jpegls-near.dcm",
}


def _geometry(dataset, rows: int, columns: int) -> None:
    dataset.Rows = rows
    dataset.Columns = columns
    dataset.TotalPixelMatrixRows = rows * 2
    dataset.TotalPixelMatrixColumns = columns * 2
    spacing = list(map(float, dataset.SharedFunctionalGroupsSequence[0]
                       .PixelMeasuresSequence[0].PixelSpacing))
    for frame, item in enumerate(dataset.PerFrameFunctionalGroupsSequence):
        row, column = divmod(frame, 2)
        position = item.PlanePositionSlideSequence[0]
        position.RowPositionInTotalImagePixelMatrix = row * rows + 1
        position.ColumnPositionInTotalImagePixelMatrix = column * columns + 1
        position.XOffsetInSlideCoordinateSystem = str(column * columns * spacing[1])
        position.YOffsetInSlideCoordinateSystem = str(row * rows * spacing[0])


def write_controls() -> None:
    """Derive the controls from existing positive objects without changing the sources."""
    motion = pydicom.dcmread(PACKAGE / "controls-v7/motion/mpeg2-main-mono.dcm")
    segmentation = pydicom.dcmread(PACKAGE / "controls-v7/iods/seg-fractional.dcm")
    segmentation.PixelData = motion.PixelData
    segmentation["PixelData"].VR = "OB"
    segmentation["PixelData"].is_undefined_length = True
    segmentation.file_meta.TransferSyntaxUID = motion.file_meta.TransferSyntaxUID
    segmentation.CineRate = 25
    segmentation.LossyImageCompression = "01"
    segmentation.LossyImageCompressionMethod = "ISO_13818_2"
    segmentation.LossyImageCompressionRatio = "2.0"
    _geometry(segmentation, 16, 16)
    segmentation.SOPInstanceUID = segmentation.file_meta.MediaStorageSOPInstanceUID = (
        "1.2.826.0.1.3680043.10.999.957.1"
    )

    jpeg_ls_path = (
        Path(pydicom.__file__).resolve().parent
        / "data/test_files/JPEGLSNearLossless_16.dcm"
    )
    jpeg_ls = pydicom.dcmread(jpeg_ls_path)
    frame = next(generate_frames(jpeg_ls.PixelData, number_of_frames=1))
    parametric_map = pydicom.dcmread(PACKAGE / "controls-v7/iods/pm-float.dcm")
    del parametric_map.FloatPixelData
    parametric_map.PixelData = encapsulate([frame] * 4, has_bot=False)
    parametric_map["PixelData"].VR = "OB"
    parametric_map["PixelData"].is_undefined_length = True
    parametric_map.file_meta.TransferSyntaxUID = jpeg_ls.file_meta.TransferSyntaxUID
    parametric_map.BitsAllocated = 16
    parametric_map.BitsStored = 16
    parametric_map.HighBit = 15
    parametric_map.PixelRepresentation = 0
    parametric_map.LossyImageCompression = "01"
    parametric_map.LossyImageCompressionMethod = "ISO_14495_1"
    parametric_map.LossyImageCompressionRatio = str(round(50 * 10 * 2 / len(frame), 6))
    mapping = parametric_map.SharedFunctionalGroupsSequence[0].RealWorldValueMappingSequence[0]
    del mapping.DoubleFloatRealWorldValueFirstValueMapped
    del mapping.DoubleFloatRealWorldValueLastValueMapped
    mapping.add_new(Tag(0x00409216), "US", 0)
    mapping.add_new(Tag(0x00409211), "US", 65535)
    _geometry(parametric_map, 50, 10)
    parametric_map.SOPInstanceUID = parametric_map.file_meta.MediaStorageSOPInstanceUID = (
        "1.2.826.0.1.3680043.10.999.957.2"
    )

    for control_id, dataset in (
        ("V7-SEG-FRACTIONAL-MPEG2", segmentation),
        ("V7-PM-JPEGLS-NEAR", parametric_map),
    ):
        output = PACKAGE / CONTROL_PATHS[control_id]
        output.parent.mkdir(parents=True, exist_ok=True)
        pydicom.dcmwrite(output, dataset, enforce_file_format=True)


if __name__ == "__main__":
    write_controls()
