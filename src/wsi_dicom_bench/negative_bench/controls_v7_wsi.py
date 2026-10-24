"""Build the controls-v7 VL WSI controls: every configuration DICOM 2026d allows.

Derivation. Every control starts from the controls-v4 file ``CP01-EVRLE-4F-ANISO.dcm`` (itself
a fresh deterministic derivative of the sealed PHI-free controls-v2 fixture VC01, built by
``build_core_profile_controls.py``). Its Patient, Study, Equipment, Acquisition, Specimen and
Optical Path content (including its ICC Profile) is kept; geometry, Image Type, tiling, optical
paths, focal planes, Pixel Data and the Transfer Syntax are rewritten by the builders below.

Correction of the source geometry. CP01 (and CP11, CP12 level-0 and CP14, built the same way)
has Image Orientation (Slide) 1\\0\\0\\0\\1\\0 and Pixel Spacing 0.0005\\0.00025 (row, column), but
records X Offset in Slide Coordinate System 0.001 mm for its Frames at Column Position 3: the
row spacing was applied along X (correct: 2 x 0.00025 = 0.0005 mm). No per-frame offset is
copied from the source. ``slide_offset`` recomputes every X/Y Offset as the Total Pixel Matrix
origin + (column - 1) x column spacing x the row direction cosines + (row - 1) x row spacing x
the column direction cosines, and ``verify`` checks every committed Frame against it
(``frame_offset_problems``). controls-v4 itself is unchanged.

The pixel content is a seeded synthetic raster (``_raster``): a smooth gradient plus noise drawn from
SHA-256 in counter mode, so it is byte-identical across platforms and numpy versions. Every new
UID is ``2.25.`` + the first 128 bits of SHA-256 over ``wsi-dicom-bench-controls-v7-wsi``, the
control id and a role. Compressed Frames are made by the external encoders named in each
builder (dcmtk with CharLS, libopenjp2 through a small C program compiled with clang, OpenJPH,
libjxl) and checked by round-trip decoding where the process is lossless. Signed controls are signed with an ephemeral
RSA key that exists only in a temporary directory; only the signed object, whose certificate is
embedded in its Digital Signatures Sequence, is written.

Run ``python -m wsi_dicom_bench.negative_bench.controls_v7_wsi build <output>`` to write the
controls into a new directory, and ``verify`` to rebuild them and compare every file with the
committed bytes and the SHA-256 in ``CONTROLS``, and to check every Frame's slide offsets.
Signed controls are not byte-reproducible (the key is ephemeral and the timestamp is real), so
``verify`` checks their recorded SHA-256 and verifies their signatures with dcmsign instead of
rebuilding them.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import shutil
import subprocess
import tempfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.encaps import encapsulate
from pydicom.sequence import Sequence
from pydicom.uid import UID

HERE = Path(__file__).resolve().parent
SOURCE_CONTROL = HERE / "controls-v4" / "CP01-EVRLE-4F-ANISO.dcm"
OUTPUT = HERE / "controls-v7" / "wsi"
NAMESPACE = "wsi-dicom-bench-controls-v7-wsi"

EVRLE = "1.2.840.10008.1.2.1"
ENCAPSULATED_UNCOMPRESSED = "1.2.840.10008.1.2.1.98"
DEFLATED_EVRLE = "1.2.840.10008.1.2.1.99"
RLE = "1.2.840.10008.1.2.5"
JPEG_BASELINE = "1.2.840.10008.1.2.4.50"
JPEG_EXTENDED = "1.2.840.10008.1.2.4.51"
JPEG_LOSSLESS = "1.2.840.10008.1.2.4.57"
JPEG_LOSSLESS_SV1 = "1.2.840.10008.1.2.4.70"
JPEG_LS_LOSSLESS = "1.2.840.10008.1.2.4.80"
JPEG_LS_NEAR_LOSSLESS = "1.2.840.10008.1.2.4.81"
J2K_LOSSLESS = "1.2.840.10008.1.2.4.90"
J2K = "1.2.840.10008.1.2.4.91"
J2K_PART2_LOSSLESS = "1.2.840.10008.1.2.4.92"
J2K_PART2 = "1.2.840.10008.1.2.4.93"
JPEG_XL_LOSSLESS = "1.2.840.10008.1.2.4.110"
JPEG_XL_JPEG_RECOMPRESSION = "1.2.840.10008.1.2.4.111"
JPEG_XL = "1.2.840.10008.1.2.4.112"
HTJ2K_LOSSLESS_RPCL = "1.2.840.10008.1.2.4.202"
DEFLATED_IMAGE_FRAME = "1.2.840.10008.1.2.8.1"

WSI_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.77.1.6"
ORIENTATION = (1, 0, 0, 0, 1, 0)  # Image Orientation (Slide): rows along +X, columns along +Y
IMPLEMENTATION_CLASS_UID = "2.25.269557681719719925684832053554655571250"
MAX_CONTROL_BYTES = 512 * 1024
TILES_OVERLAP = 0x00480304  # not in the pydicom 3.0.2 dictionary


# --- identities and content -------------------------------------------------------------------


def _uid(control_id: str, role: str) -> str:
    digest = hashlib.sha256(f"{NAMESPACE}:{control_id}:{role}".encode()).digest()[:16]
    return f"2.25.{int.from_bytes(digest, 'big')}"


def _stream(seed: str, length: int) -> bytes:
    """``length`` deterministic bytes: SHA-256 of ``seed`` and a counter."""
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(hashlib.sha256(f"{seed}:{counter}".encode()).digest())
        counter += 1
    return bytes(out[:length])


def _raster(seed: str, rows: int, columns: int, samples: int, bits: int = 8) -> list[list[list[int]]]:
    """A seeded raster ``[row][column][sample]``: a gradient plus 5 bits of noise."""
    noise = _stream(seed, rows * columns * samples)
    top = (1 << bits) - 1
    scale = top / 255
    raster = []
    for y in range(rows):
        line = []
        for x in range(columns):
            pixel = []
            for s in range(samples):
                base = (x * 160 // max(columns, 1) + y * 64 // max(rows, 1) + s * 40) % 224
                value = base + (noise[(y * columns + x) * samples + s] & 0x1F)
                pixel.append(min(top, int(value * scale) + (value & 0xFF if bits > 8 else 0)))
            line.append(pixel)
        raster.append(line)
    return raster


def _reduce(raster: list[list[list[int]]]) -> list[list[list[int]]]:
    """Halve a raster by the rounded mean of each 2x2 block (pyramid resampling)."""
    rows, columns = len(raster) // 2, len(raster[0]) // 2
    return [
        [
            [
                (
                    raster[2 * y][2 * x][s]
                    + raster[2 * y][2 * x + 1][s]
                    + raster[2 * y + 1][2 * x][s]
                    + raster[2 * y + 1][2 * x + 1][s]
                    + 2
                )
                // 4
                for s in range(len(raster[0][0]))
            ]
            for x in range(columns)
        ]
        for y in range(rows)
    ]


def _tile(raster, top: int, left: int, rows: int, columns: int, bits: int) -> bytes:
    """One native Frame (color-by-pixel) cut from ``raster``; outside pixels are 0."""
    out = bytearray()
    width = bits // 8
    for y in range(top, top + rows):
        for x in range(left, left + columns):
            inside = y < len(raster) and x < len(raster[0])
            for value in raster[y][x] if inside else [0] * len(raster[0][0]):
                out.extend(int(value).to_bytes(width, "little"))
    return bytes(out)


def _code(value: str, scheme: str, meaning: str) -> Dataset:
    item = Dataset()
    item.CodeValue = value
    item.CodingSchemeDesignator = scheme
    item.CodeMeaning = meaning
    return item


def _ds(value: float) -> str:
    """A DS string of at most 16 bytes without float noise."""
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


# --- the image specification --------------------------------------------------------------------


@dataclass(frozen=True)
class OpticalPath:
    identifier: str
    description: str
    illumination: tuple[str, str, str] = ("111744", "DCM", "Brightfield illumination")
    wavelength: float | None = 550.0
    color: tuple[str, str, str] | None = ("371251000", "SCT", "White")
    palette: tuple[int, int, int] | None = None  # the emission color the ramp ends at
    channel: tuple[str, str, str] | None = None  # CID 8122, when not the natural interpretation


BRIGHTFIELD = (OpticalPath("0", "Default optical path"),)


@dataclass(frozen=True)
class Frame:
    """One encoded Frame: its 1-based Total Pixel Matrix position, focal plane and path."""

    row: int
    column: int
    plane: int = 0
    path: int = 0


@dataclass
class Spec:
    control_id: str
    role: str = "instance"
    group: str | None = None  # the control whose Study/Series/Frame of Reference is shared
    image_type: tuple[str, str, str, str] = ("ORIGINAL", "PRIMARY", "VOLUME", "NONE")
    rows: int = 8
    columns: int = 8
    total_rows: int = 16
    total_columns: int = 16
    spacing: float = 0.00025  # mm: the row spacing, and the column spacing unless given
    column_spacing: float | None = None  # mm, for anisotropic pixels
    planes: int = 1
    plane_spacing_um: float = 1.0
    paths: tuple[OpticalPath, ...] = BRIGHTFIELD
    samples: int = 3
    photometric: str = "RGB"
    bits: int = 8
    organization: str | None = "TILED_FULL"
    per_frame: bool = True
    frames: tuple[Frame, ...] | None = None  # None: the TILED_FULL order
    origin: tuple[float, float] = (0.0, 0.0)
    frame_of_reference: bool = True
    pyramid: bool = True
    instance_number: int = 1
    seed: str = ""
    raster: list | None = None
    edf: tuple[int, float] | None = None
    extra: dict = field(default_factory=dict)  # {tag: (VR, value)} added verbatim

    @property
    def pixel_spacing(self) -> tuple[float, float]:
        """(row spacing, column spacing) in mm, as Pixel Spacing (0028,0030) orders them."""
        return self.spacing, self.column_spacing or self.spacing

    def frame_order(self) -> tuple[Frame, ...]:
        if self.frames is not None:
            return self.frames
        order = []
        for path in range(len(self.paths)):
            for plane in range(self.planes):
                for top in range(0, self.total_rows, self.rows):
                    for left in range(0, self.total_columns, self.columns):
                        order.append(Frame(top + 1, left + 1, plane, path))
        return tuple(order)


def _template() -> Dataset:
    if not SOURCE_CONTROL.is_file():
        raise RuntimeError(f"source control is missing: {SOURCE_CONTROL}")
    return pydicom.dcmread(SOURCE_CONTROL)


def _optical_path_item(template_item: Dataset, path: OpticalPath, monochrome: bool) -> Dataset:
    item = Dataset()
    item.IlluminationTypeCodeSequence = Sequence([_code(*path.illumination)])
    if path.wavelength is not None:
        item.IlluminationWaveLength = path.wavelength
    if path.palette is not None or not monochrome:
        item.ICCProfile = template_item.ICCProfile
    item.OpticalPathIdentifier = path.identifier
    item.OpticalPathDescription = path.description
    if path.color is not None:
        item.IlluminationColorCodeSequence = Sequence([_code(*path.color)])
    if path.channel is not None:
        item.ChannelDescriptionCodeSequence = Sequence([_code(*path.channel)])
    if path.palette is not None:
        item.PaletteColorLookupTableSequence = Sequence([_palette(path)])
    return item


def _palette(path: OpticalPath) -> Dataset:
    """A 256-entry, 16-bit-entry ramp from black to the path's emission color, for 8-bit
    stored values starting at 0 (PS3.3 C.7.6.3.1.5 and C.7.9)."""
    item = Dataset()
    for name, channel in zip(("Red", "Green", "Blue"), path.palette):
        item.add_new(_PALETTE_DESCRIPTOR[name], "US", [256, 0, 16])
        table = b"".join(((value * channel // 255) * 257).to_bytes(2, "little") for value in range(256))
        setattr(item, f"{name}PaletteColorLookupTableData", table)
    item.PaletteColorLookupTableUID = _uid("palette", path.description)
    return item


_PALETTE_DESCRIPTOR = {"Red": 0x00281101, "Green": 0x00281102, "Blue": 0x00281103}


def build_dataset(spec: Spec) -> tuple[Dataset, list[bytes]]:
    """The VL WSI Data Set of ``spec`` and its native Frames (color-by-pixel)."""
    ds = _template()
    template_path = ds.OpticalPathSequence[0]
    group = spec.group or spec.control_id
    monochrome = spec.photometric == "MONOCHROME2"

    ds.PatientName = "RESEARCH^PLACEHOLDER"
    ds.PatientID = "RESEARCH"
    ds.StudyInstanceUID = _uid(group, "study")
    ds.SeriesInstanceUID = _uid(group, "series")
    ds.SOPInstanceUID = _uid(spec.control_id, spec.role)
    ds.InstanceNumber = str(spec.instance_number)
    ds.ContainerIdentifier = f"SYNTH-{group}"
    specimen = ds.SpecimenDescriptionSequence[0]
    specimen.SpecimenIdentifier = f"SYNTH-{group}"
    specimen.SpecimenUID = _uid(group, "specimen")
    ds.ImageType = list(spec.image_type)
    flavor = spec.image_type[2]

    if spec.frame_of_reference:
        ds.FrameOfReferenceUID = _uid(group, "frame-of-reference")
        ds.PositionReferenceIndicator = "SLIDE_CORNER"
    else:
        del ds.FrameOfReferenceUID
        del ds.PositionReferenceIndicator
    for keyword in ("PyramidUID", "PyramidLabel"):
        if keyword in ds:
            del ds[keyword]
    if spec.pyramid:
        ds.PyramidUID = _uid(group, "pyramid")
        ds.PyramidLabel = "Synthetic pyramid"

    ds.SpecimenLabelInImage = "YES" if flavor in ("LABEL", "OVERVIEW") else "NO"
    ds.BurnedInAnnotation = "NO"
    if flavor == "LABEL":
        ds.BarcodeValue = f"SYNTH-{group}"
        ds.LabelText = "SYNTHETIC RESEARCH LABEL"

    # Image Pixel
    ds.Rows, ds.Columns = spec.rows, spec.columns
    ds.SamplesPerPixel = spec.samples
    ds.PhotometricInterpretation = spec.photometric
    if spec.samples > 1:
        ds.PlanarConfiguration = 0
    elif "PlanarConfiguration" in ds:
        del ds.PlanarConfiguration
    ds.BitsAllocated = ds.BitsStored = spec.bits
    ds.HighBit = spec.bits - 1
    ds.PixelRepresentation = 0
    ds.LossyImageCompression = "00"
    if monochrome:
        ds.PresentationLUTShape = "IDENTITY"
        ds.RescaleIntercept = "0"
        ds.RescaleSlope = "1"

    # Tile organization and the imaged volume
    ds.TotalPixelMatrixRows = spec.total_rows
    ds.TotalPixelMatrixColumns = spec.total_columns
    ds.TotalPixelMatrixFocalPlanes = spec.planes
    origin = ds.TotalPixelMatrixOriginSequence[0]
    origin.XOffsetInSlideCoordinateSystem = _ds(spec.origin[0])
    origin.YOffsetInSlideCoordinateSystem = _ds(spec.origin[1])
    origin.ZOffsetInSlideCoordinateSystem = "0"
    ds.ImageOrientationSlide = list(ORIENTATION)
    for keyword in ("ImagedVolumeWidth", "ImagedVolumeHeight", "ImagedVolumeDepth"):
        if keyword in ds:
            del ds[keyword]
    depth_um = spec.plane_spacing_um * spec.planes if spec.planes > 1 else 1.0
    if flavor in ("VOLUME", "THUMBNAIL"):
        ds.ImagedVolumeWidth = spec.total_columns * spec.pixel_spacing[1]
        ds.ImagedVolumeHeight = spec.total_rows * spec.pixel_spacing[0]
        ds.ImagedVolumeDepth = depth_um
    if spec.edf is None:
        ds.ExtendedDepthOfField = "NO"
    else:
        ds.ExtendedDepthOfField = "YES"
        ds.NumberOfFocalPlanes = spec.edf[0]
        ds.DistanceBetweenFocalPlanes = spec.edf[1]

    # Optical paths
    ds.OpticalPathSequence = Sequence(
        [_optical_path_item(template_path, path, monochrome) for path in spec.paths]
    )
    ds.NumberOfOpticalPaths = len(spec.paths)

    # Functional groups
    shared = ds.SharedFunctionalGroupsSequence[0]
    measures = shared.PixelMeasuresSequence[0]
    measures.PixelSpacing = [_ds(value) for value in spec.pixel_spacing]
    measures.SliceThickness = _ds(depth_um / 1000 if spec.planes == 1 else spec.plane_spacing_um / 1000)
    if spec.planes > 1:
        measures.SpacingBetweenSlices = _ds(spec.plane_spacing_um / 1000)
    shared.WholeSlideMicroscopyImageFrameTypeSequence[0].FrameType = list(spec.image_type)
    if "OpticalPathIdentificationSequence" in shared:
        del shared.OpticalPathIdentificationSequence
    if len(spec.paths) == 1:
        identification = Dataset()
        identification.OpticalPathIdentifier = spec.paths[0].identifier
        shared.OpticalPathIdentificationSequence = Sequence([identification])

    order = spec.frame_order()
    ds.NumberOfFrames = str(len(order))
    dimension_uid = _uid(spec.control_id, f"{spec.role}-dimension")
    ds.DimensionOrganizationSequence[0].DimensionOrganizationUID = dimension_uid
    if spec.organization is None:
        if "DimensionOrganizationType" in ds:
            del ds.DimensionOrganizationType
    else:
        ds.DimensionOrganizationType = spec.organization
    indices = _dimension_indices(spec, order, dimension_uid)
    if indices is None:
        for keyword in ("DimensionIndexSequence", "PerFrameFunctionalGroupsSequence"):
            if keyword in ds:
                del ds[keyword]
    else:
        ds.DimensionIndexSequence, values = indices
        ds.PerFrameFunctionalGroupsSequence = Sequence(
            [_per_frame(spec, frame, value) for frame, value in zip(order, values)]
        )

    # Frames
    raster = spec.raster
    if raster is None:
        raster = _raster(spec.seed or spec.control_id, spec.total_rows, spec.total_columns,
                         spec.samples, spec.bits)
    frames = []
    for frame in order:
        tile = _tile(raster, frame.row - 1, frame.column - 1, spec.rows, spec.columns, spec.bits)
        if frame.plane or frame.path:
            # Other focal planes and optical paths carry their own seeded content.
            other = _raster(f"{spec.seed or spec.control_id}:{frame.plane}:{frame.path}",
                            spec.rows, spec.columns, spec.samples, spec.bits)
            tile = _tile(other, 0, 0, spec.rows, spec.columns, spec.bits)
        frames.append(tile)
    ds.PixelData = b"".join(frames)
    ds["PixelData"].VR = "OW" if spec.bits == 16 else "OB"
    for tag, (vr, value) in spec.extra.items():
        ds.add_new(tag, vr, value)
    _file_meta(ds, EVRLE)
    return ds, frames


def _dimension_indices(spec: Spec, order, dimension_uid):
    """The Dimension Index Sequence and per-Frame index values, or None for no per-frame groups."""
    if not spec.per_frame:
        return None
    pointers = [((0x0048, 0x021F), "rows"), ((0x0048, 0x021E), "columns")]
    if spec.planes > 1:
        pointers.append(((0x0040, 0x074A), "planes"))
    if len(spec.paths) > 1:
        pointers.append(((0x0048, 0x0106), "paths"))
    items = []
    for pointer, _ in pointers:
        item = Dataset()
        item.DimensionOrganizationUID = dimension_uid
        item.DimensionIndexPointer = pointer
        item.FunctionalGroupPointer = (
            (0x0048, 0x0207) if pointer == (0x0048, 0x0106) else (0x0048, 0x021A)
        )
        items.append(item)
    keys = {
        "rows": sorted({f.row for f in order}),
        "columns": sorted({f.column for f in order}),
        "planes": sorted({f.plane for f in order}),
        "paths": sorted({f.path for f in order}),
    }
    values = []
    for frame in order:
        lookup = {"rows": frame.row, "columns": frame.column, "planes": frame.plane, "paths": frame.path}
        values.append([keys[name].index(lookup[name]) + 1 for _, name in pointers])
    return Sequence(items), values


def _per_frame(spec: Spec, frame: Frame, index_values) -> Dataset:
    item = Dataset()
    content = Dataset()
    content.DimensionIndexValues = index_values
    item.FrameContentSequence = Sequence([content])
    position = Dataset()
    x, y = slide_offset((spec.origin[0], spec.origin[1]), ORIENTATION, spec.pixel_spacing,
                        frame.row, frame.column)
    position.XOffsetInSlideCoordinateSystem = _ds(x)
    position.YOffsetInSlideCoordinateSystem = _ds(y)
    position.ZOffsetInSlideCoordinateSystem = _ds(frame.plane * spec.plane_spacing_um)
    position.ColumnPositionInTotalImagePixelMatrix = frame.column
    position.RowPositionInTotalImagePixelMatrix = frame.row
    item.PlanePositionSlideSequence = Sequence([position])
    if len(spec.paths) > 1:
        identification = Dataset()
        identification.OpticalPathIdentifier = spec.paths[frame.path].identifier
        item.OpticalPathIdentificationSequence = Sequence([identification])
    return item


def slide_offset(origin, orientation, pixel_spacing, row: int, column: int) -> tuple[float, float]:
    """X and Y Offset in Slide Coordinate System (mm) of the pixel at 1-based (row, column):
    origin + (column - 1) x column spacing x row direction + (row - 1) x row spacing x column
    direction (PS3.3 C.8.12.2.1, C.8.12.14.1). The controls-v4 sources apply the row spacing
    along X; every controls-v7 offset is recomputed here instead of copied."""
    row_spacing, column_spacing = pixel_spacing
    return tuple(
        origin[axis]
        + (column - 1) * column_spacing * orientation[axis]
        + (row - 1) * row_spacing * orientation[3 + axis]
        for axis in (0, 1)
    )


def frame_offset_problems(ds: Dataset) -> list[str]:
    """Every Plane Position (Slide) whose X/Y Offset disagrees with its matrix position."""
    if "PerFrameFunctionalGroupsSequence" not in ds:
        return []
    origin = ds.TotalPixelMatrixOriginSequence[0]
    origin_xy = (float(origin.XOffsetInSlideCoordinateSystem), float(origin.YOffsetInSlideCoordinateSystem))
    orientation = [float(v) for v in ds.ImageOrientationSlide]
    spacing = [float(v) for v in ds.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0].PixelSpacing]
    problems = []
    for number, item in enumerate(ds.PerFrameFunctionalGroupsSequence, start=1):
        if "PlanePositionSlideSequence" not in item:
            continue
        position = item.PlanePositionSlideSequence[0]
        expected = slide_offset(origin_xy, orientation, spacing,
                                int(position.RowPositionInTotalImagePixelMatrix),
                                int(position.ColumnPositionInTotalImagePixelMatrix))
        actual = (float(position.XOffsetInSlideCoordinateSystem), float(position.YOffsetInSlideCoordinateSystem))
        if any(abs(a - e) > 1e-9 for a, e in zip(actual, expected)):
            problems.append(f"Frame {number}: X/Y Offset {actual}, expected {expected}")
    return problems


def _file_meta(ds: Dataset, transfer_syntax: str) -> None:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = WSI_SOP_CLASS
    meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    meta.TransferSyntaxUID = UID(transfer_syntax)
    meta.ImplementationClassUID = IMPLEMENTATION_CLASS_UID
    meta.ImplementationVersionName = "WSIBENCH-V7"
    ds.file_meta = meta


def _derive(ds: Dataset, source: Dataset) -> None:
    """Record that ``ds`` was resampled from ``source`` (PS3.3 C.7.6.16.2.6, C.12.2)."""
    reference = Dataset()
    reference.ReferencedSOPClassUID = source.SOPClassUID
    reference.ReferencedSOPInstanceUID = source.SOPInstanceUID
    ds.SourceImageSequence = Sequence([copy.deepcopy(reference)])
    derivation = Dataset()
    derivation.DerivationCodeSequence = Sequence([_code("113085", "DCM", "Spatial resampling")])
    derived_source = copy.deepcopy(reference)
    derived_source.PurposeOfReferenceCodeSequence = Sequence(
        [_code("121322", "DCM", "Source image for image processing operation")]
    )
    derived_source.SpatialLocationsPreserved = "YES"
    derivation.SourceImageSequence = Sequence([derived_source])
    ds.SharedFunctionalGroupsSequence[0].DerivationImageSequence = Sequence([derivation])
    series = Dataset()
    series.SeriesInstanceUID = source.SeriesInstanceUID
    series.ReferencedInstanceSequence = Sequence([copy.deepcopy(reference)])
    ds.ReferencedSeriesSequence = Sequence([series])


# Encapsulated Explicit VR LE syntaxes pydicom knows, by the padded length of their UID.
_STAND_INS = {22: "1.2.840.10008.1.2.4.50", 24: "1.2.840.10008.1.2.4.201"}


def _bytes(ds: Dataset) -> bytes:
    """The file bytes of ``ds``.

    pydicom 3.0.2 cannot write a Transfer Syntax it does not know (JPEG XL, Deflated Image
    Frame Compression). Such a Data Set is written under a known encapsulated Explicit VR Little
    Endian syntax whose UID has the same padded length, and only the Transfer Syntax UID Value
    in the File Meta Information is then replaced, so no length or offset changes.
    """
    transfer_syntax = str(ds.file_meta.TransferSyntaxUID)
    replace = not UID(transfer_syntax).is_transfer_syntax
    if replace:
        value = transfer_syntax.encode() + b"\0" * (len(transfer_syntax) % 2)
        stand_in = _STAND_INS[len(value)].encode()
        stand_in += b"\0" * (len(stand_in) % 2)
        ds.file_meta.TransferSyntaxUID = UID(_STAND_INS[len(value)])
    buffer = io.BytesIO()
    try:
        ds.save_as(buffer, enforce_file_format=True)
    finally:
        ds.file_meta.TransferSyntaxUID = UID(transfer_syntax)
    data = buffer.getvalue()
    if replace:
        meta_end = 144 + int.from_bytes(data[140:144], "little")  # preamble, DICM, group length
        if data[:meta_end].count(stand_in) != 1:
            raise RuntimeError("stand-in Transfer Syntax UID is not unique in the File Meta")
        data = data[:meta_end].replace(stand_in, value) + data[meta_end:]
        written = pydicom.dcmread(io.BytesIO(data), stop_before_pixels=True).file_meta
        if str(written.TransferSyntaxUID) != transfer_syntax:
            raise RuntimeError("Transfer Syntax UID replacement failed")
    if len(data) > MAX_CONTROL_BYTES:
        raise RuntimeError(f"{ds.SOPInstanceUID}: control is {len(data)} bytes")
    return data


# --- 1. Image Types: a full study set -----------------------------------------------------------

SET_ID = "W7-SET-PYRAMID-3L-LOT"


def build_image_type_set() -> dict[str, bytes]:
    """A three-level pyramid, its THUMBNAIL apex, a LABEL and an OVERVIEW in one Series.

    The VOLUME levels and the THUMBNAIL share the Frame of Reference and the Pyramid UID
    (PS3.3 A.32.8-1: Frame of Reference required, Multi-Resolution Pyramid permitted, only for
    VOLUME and THUMBNAIL). The OVERVIEW keeps the Series' Frame of Reference and has no Pyramid
    UID; the LABEL has neither (both "may be present otherwise" / "shall be present only if").
    Each derived level is the 2x2 rounded mean of the level above, with Derivation Image and
    Common Instance Reference content.
    """
    level_raster = _raster(SET_ID, 32, 32, 3)
    specs = [
        Spec(SET_ID, role="level-0", rows=16, columns=16, total_rows=32, total_columns=32,
             spacing=0.00025, raster=level_raster, instance_number=1),
    ]
    raster = level_raster
    for level, (tile, size) in enumerate(((8, 16), (8, 8)), start=1):
        raster = _reduce(raster)
        specs.append(Spec(SET_ID, role=f"level-{level}", rows=tile, columns=tile, total_rows=size,
                          total_columns=size, spacing=0.00025 * 2**level, raster=raster,
                          image_type=("DERIVED", "PRIMARY", "VOLUME", "RESAMPLED"),
                          instance_number=level + 1))
    raster = _reduce(raster)
    specs.append(Spec(SET_ID, role="thumbnail", rows=4, columns=4, total_rows=4, total_columns=4,
                      spacing=0.002, raster=raster, per_frame=False, instance_number=4,
                      image_type=("DERIVED", "PRIMARY", "THUMBNAIL", "RESAMPLED")))
    specs.append(Spec(SET_ID, role="overview", rows=12, columns=24, total_rows=12,
                      total_columns=24, spacing=0.0025, origin=(-0.03, -0.0075), pyramid=False,
                      per_frame=False, seed=f"{SET_ID}:overview", instance_number=5,
                      image_type=("ORIGINAL", "PRIMARY", "OVERVIEW", "NONE")))
    specs.append(Spec(SET_ID, role="label", rows=8, columns=8, total_rows=8, total_columns=8,
                      spacing=0.0025, pyramid=False, frame_of_reference=False, per_frame=False,
                      seed=f"{SET_ID}:label", instance_number=6,
                      image_type=("ORIGINAL", "PRIMARY", "LABEL", "NONE")))
    names = ["level-0", "level-1", "level-2", "thumbnail", "overview", "label"]
    built = {}
    previous = None
    for name, spec in zip(names, specs):
        ds, _ = build_dataset(spec)
        if spec.image_type[0] == "DERIVED":
            _derive(ds, previous)
        if spec.image_type[2] in ("VOLUME", "THUMBNAIL"):
            previous = ds
        built[f"{SET_ID}/{name}.dcm"] = _bytes(ds)
    return built


# --- 2. Tiling ---------------------------------------------------------------------------------

EPIFLUORESCENCE = ("111743", "DCM", "Epifluorescence illumination")
FLUORESCENCE_PATHS = (
    OpticalPath("1", "Green emission (FITC)", EPIFLUORESCENCE, 488.0, None,
                channel=("371246006", "SCT", "Green")),
    OpticalPath("2", "Red emission (TRITC)", EPIFLUORESCENCE, 561.0, None,
                channel=("371240000", "SCT", "Red")),
)


def _single(control_id: str, spec: Spec) -> dict[str, bytes]:
    ds, _ = build_dataset(spec)
    return {f"{control_id}.dcm": _bytes(ds)}


def build_tiled_sparse() -> dict[str, bytes]:
    """TILED_SPARSE: 5 of the 9 tiles of a 3x3 grid, out of raster order, each placed by its
    Plane Position (Slide) (PS3.3 C.7.6.17.3, A.32.8.3.1.2: sparse encoding is permitted)."""
    control_id = "W7-TILED-SPARSE-5OF9"
    frames = tuple(Frame(r, c) for r, c in ((9, 9), (1, 1), (1, 17), (17, 1), (17, 17)))
    return _single(control_id, Spec(control_id, total_rows=24, total_columns=24, frames=frames,
                                    organization="TILED_SPARSE", spacing=0.0005,
                                    column_spacing=0.00025,
                                    extra={TILES_OVERLAP: ("CS", "NONE")}))


def build_absent_organization() -> dict[str, bytes]:
    """Dimension Organization Type absent: every Frame placed explicitly (PS3.3 C.7.6.17.3)."""
    control_id = "W7-TILED-NOTYPE-4F"
    frames = tuple(Frame(r, c) for r, c in ((9, 9), (9, 1), (1, 9), (1, 1)))
    return _single(control_id, Spec(control_id, frames=frames, organization=None))


def build_z_stack() -> dict[str, bytes]:
    """TILED_FULL with three focal planes 1 um apart (Total Pixel Matrix Focal Planes 3)."""
    control_id = "W7-ZSTACK-3P-TILED-FULL"
    return _single(control_id, Spec(control_id, planes=3, plane_spacing_um=1.0))


def build_optical_paths() -> dict[str, bytes]:
    """TILED_FULL with two epifluorescence optical paths, MONOCHROME2, frames ordered by path."""
    control_id = "W7-OPTICAL-PATHS-2-MONO"
    return _single(control_id, Spec(control_id, paths=FLUORESCENCE_PATHS, samples=1,
                                    photometric="MONOCHROME2"))


def build_extended_depth_of_field() -> dict[str, bytes]:
    """Extended Depth of Field YES: five acquisition planes 0.5 um apart in one encoded plane."""
    control_id = "W7-EDF-5P"
    return _single(control_id, Spec(control_id, edf=(5, 0.5)))


def build_3d_organization() -> dict[str, bytes]:
    """Dimension Organization Type 3D: three whole-matrix Frames at equally spaced focal planes."""
    control_id = "W7-3D-ORGANIZATION-3P"
    frames = tuple(Frame(1, 1, plane) for plane in range(3))
    return _single(control_id, Spec(control_id, rows=16, columns=16, planes=3,
                                    plane_spacing_um=1.5, frames=frames, organization="3D"))


# --- 3. Concatenation --------------------------------------------------------------------------

CONCATENATION_ID = "W7-CONCATENATION-2X4F"


def build_concatenation() -> dict[str, bytes]:
    """One TILED_FULL level of 8 Frames split into two Instances of one Concatenation.

    PS3.3 C.7.6.16.1: the Instances share Concatenation UID, SOP Instance UID of Concatenation
    Source (the UID the unsplit Instance had), Instance Number, the Shared Functional Groups and
    the Dimension Index Sequence; only Number of Frames, Concatenation Frame Offset Number,
    In-concatenation Number, SOP Instance UID and the Per-Frame Items of their own Frames differ.
    TILED_FULL then spans the Frames of both Instances in order (C.7.6.17.3).
    """
    spec = Spec(CONCATENATION_ID, role="source", total_rows=16, total_columns=32)
    source, frames = build_dataset(spec)
    if "RepresentativeFrameNumber" in source:
        del source.RepresentativeFrameNumber
    source_uid = source.SOPInstanceUID
    built = {}
    for number, start in ((1, 0), (2, 4)):
        part = copy.deepcopy(source)
        part.SOPInstanceUID = _uid(CONCATENATION_ID, f"part-{number}")
        part.file_meta.MediaStorageSOPInstanceUID = part.SOPInstanceUID
        part.ConcatenationUID = _uid(CONCATENATION_ID, "concatenation")
        part.SOPInstanceUIDOfConcatenationSource = source_uid
        part.InConcatenationNumber = number
        part.InConcatenationTotalNumber = 2
        part.ConcatenationFrameOffsetNumber = start
        part.NumberOfFrames = "4"
        part.PerFrameFunctionalGroupsSequence = Sequence(
            list(source.PerFrameFunctionalGroupsSequence)[start : start + 4]
        )
        part.PixelData = b"".join(frames[start : start + 4])
        built[f"{CONCATENATION_ID}/part-{number}.dcm"] = _bytes(part)
    return built


# --- 5. Photometric Interpretation and bit depth -------------------------------------------------

FITC = OpticalPath("FITC", "Green emission (FITC)", EPIFLUORESCENCE, 488.0, None,
                   channel=("371246006", "SCT", "Green"))


def build_mono8_palette() -> dict[str, bytes]:
    """MONOCHROME2 8-bit fluorescence with a Palette Color Lookup Table Sequence in its Optical
    Path, and the ICC Profile that the palette makes required (PS3.3 C.8.12.5)."""
    cid = "W7-MONO8-FLUO-PALETTE"
    path = OpticalPath("FITC", "Green emission (FITC)", EPIFLUORESCENCE, 488.0, None,
                       palette=(0, 255, 64), channel=("371246006", "SCT", "Green"))
    return _single(cid, Spec(cid, paths=(path,), samples=1, photometric="MONOCHROME2"))


def build_mono16() -> dict[str, bytes]:
    """MONOCHROME2 16-bit fluorescence (Bits Stored 16), no palette, Explicit VR LE (OW)."""
    cid = "W7-MONO16-FLUO"
    return _single(cid, Spec(cid, paths=(FITC,), samples=1, photometric="MONOCHROME2", bits=16))


def build_rgb16() -> dict[str, bytes]:
    """RGB 16-bit (Bits Allocated 16 is an Enumerated Value of the WSI Image Module for every
    Photometric Interpretation), Explicit VR LE (OW)."""
    cid = "W7-RGB16-EVRLE"
    return _single(cid, Spec(cid, bits=16))


# --- encoders ----------------------------------------------------------------------------------


def _run(command: list[str], cwd: Path | None = None) -> str:
    """Run an encoder; a non-zero exit or a missing tool is an error, never ignored."""
    if shutil.which(command[0]) is None:
        raise RuntimeError(f"required tool is not on PATH: {command[0]}")
    result = subprocess.run(command, capture_output=True, text=True, timeout=300, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(command)} failed ({result.returncode}): {result.stderr[-2000:]}")
    return result.stdout + result.stderr


def _dcmtk_frames(ds: Dataset, tool: str, *options: str) -> tuple[str, list[bytes]]:
    """Encode the native ``ds`` with a dcmtk tool and return its Transfer Syntax and Frames.

    Only the Frames are kept: every Attribute the tool would change (UIDs, Image Type,
    lossy history, implementation identity) is written by the builder instead.
    """
    from pydicom.encaps import generate_frames

    with tempfile.TemporaryDirectory() as temporary:
        source, target = Path(temporary) / "in.dcm", Path(temporary) / "out.dcm"
        ds.save_as(source, enforce_file_format=True)
        _run([tool, *options, str(source), str(target)])
        encoded = pydicom.dcmread(target)
        frames = list(generate_frames(encoded.PixelData, number_of_frames=int(encoded.NumberOfFrames)))
        return str(encoded.file_meta.TransferSyntaxUID), frames


def _encapsulate(ds: Dataset, frames: list[bytes], transfer_syntax: str) -> None:
    """Replace Pixel Data by one Fragment per Frame, with a Basic Offset Table (PS3.5 A.4)."""
    ds.PixelData = encapsulate([f + b"\0" * (len(f) % 2) for f in frames], has_bot=True)
    ds["PixelData"].VR = "OB"
    ds["PixelData"].is_undefined_length = True
    ds.file_meta.TransferSyntaxUID = UID(transfer_syntax)


def _lossy(ds: Dataset, native_bytes: int, frames: list[bytes], method: str) -> None:
    """Record lossy compression (PS3.3 C.7.6.1.1.5) with the measured ratio."""
    ds.LossyImageCompression = "01"
    ratio = native_bytes / sum(len(f) for f in frames)
    ds.LossyImageCompressionRatio = [f"{ratio:.4g}"]
    ds.LossyImageCompressionMethod = [method]


def _native_size(ds: Dataset) -> int:
    return int(ds.Rows) * int(ds.Columns) * int(ds.SamplesPerPixel) * int(ds.BitsAllocated) // 8 * int(
        ds.NumberOfFrames
    )


def _decoded_by(data: bytes, tool: str, *options: str) -> bytes:
    """The native Pixel Data an independent decoder recovers from the control ``data``."""
    with tempfile.TemporaryDirectory() as temporary:
        source, target = Path(temporary) / "in.dcm", Path(temporary) / "out.dcm"
        source.write_bytes(data)
        _run([tool, *options, str(source), str(target)])
        return bytes(pydicom.dcmread(target).PixelData)


def _require_lossless(control_id: str, data: bytes, native: list[bytes], tool: str, *options: str) -> None:
    decoded = _decoded_by(data, tool, *options)
    expected = b"".join(native)
    if decoded[: len(expected)] != expected or len(decoded) - len(expected) > 1:
        raise RuntimeError(f"{control_id}: {tool} does not recover the native Frames bit-exactly")


# --- 4. Transfer Syntaxes ------------------------------------------------------------------------


def _dcmtk_control(control_id: str, spec: Spec, expected_ts: str, tool: str, options: tuple[str, ...],
                   decoder: str | None, lossy_method: str | None = None) -> dict[str, bytes]:
    ds, native = build_dataset(spec)
    transfer_syntax, frames = _dcmtk_frames(ds, tool, *options)
    if transfer_syntax != expected_ts:
        raise RuntimeError(f"{control_id}: {tool} wrote {transfer_syntax}, not {expected_ts}")
    native_bytes = _native_size(ds)
    _encapsulate(ds, frames, transfer_syntax)
    if lossy_method:
        _lossy(ds, native_bytes, frames, lossy_method)
    data = _bytes(ds)
    if decoder:
        _require_lossless(control_id, data, native, decoder)
    return {f"{control_id}.dcm": data}


def build_rle() -> dict[str, bytes]:
    """RLE Lossless (PS3.5 A.4.2) with dcmcrle; RGB, decoded bit-exactly by dcmdrle."""
    return _dcmtk_control("W7-TS-RLE-RGB", Spec("W7-TS-RLE-RGB"), RLE, "dcmcrle", (), "dcmdrle")


def build_jpeg_lossless() -> dict[str, bytes]:
    """JPEG Lossless Process 14, Selection Value 6 (dcmcjpeg +el +sv 6); RGB."""
    cid = "W7-TS-JPEG-LOSSLESS-P14-SV6"
    return _dcmtk_control(cid, Spec(cid), JPEG_LOSSLESS, "dcmcjpeg", ("+el", "+sv", "6"), "dcmdjpeg")


def build_jpeg_lossless_sv1() -> dict[str, bytes]:
    """JPEG Lossless Process 14, Selection Value 1 (dcmcjpeg +e1); RGB."""
    cid = "W7-TS-JPEG-LOSSLESS-SV1"
    return _dcmtk_control(cid, Spec(cid), JPEG_LOSSLESS_SV1, "dcmcjpeg", ("+e1",), "dcmdjpeg")


def build_jpeg_extended() -> dict[str, bytes]:
    """JPEG Extended (Process 2 and 4) 8-bit MONOCHROME2 (dcmcjpeg +ee), the only 8-bit form
    PS3.5 Table 8.2.1-1 lists for 1.2.840.10008.1.2.4.51; Bits Stored 12 is excluded by the
    WSI Image Module (Bits Stored equals Bits Allocated)."""
    cid = "W7-TS-JPEG-EXTENDED-MONO8"
    spec = Spec(cid, samples=1, photometric="MONOCHROME2", rows=16, columns=16, total_rows=32,
                total_columns=32)
    return _dcmtk_control(cid, spec, JPEG_EXTENDED, "dcmcjpeg", ("+ee", "+q", "85"), None,
                          "ISO_10918_1")


def build_jpeg_baseline_422() -> dict[str, bytes]:
    """JPEG Baseline YBR_FULL_422 with 4:2:2 subsampling (dcmcjpeg +eb +cy +s2), 16x16 tiles."""
    cid = "W7-TS-JPEG-BASELINE-YBR422"
    spec = Spec(cid, rows=16, columns=16, total_rows=32, total_columns=32)
    built = _dcmtk_control(cid, spec, JPEG_BASELINE, "dcmcjpeg", ("+eb", "+cy", "+s2", "+q", "85"),
                           None, "ISO_10918_1")
    ds = pydicom.dcmread(io.BytesIO(built[f"{cid}.dcm"]))
    ds.PhotometricInterpretation = "YBR_FULL_422"
    return {f"{cid}.dcm": _bytes(ds)}


def build_jpeg_ls_lossless() -> dict[str, bytes]:
    """JPEG-LS Lossless (dcmcjpls +el, CharLS); RGB, line interleaved."""
    cid = "W7-TS-JPEG-LS-LOSSLESS-RGB"
    return _dcmtk_control(cid, Spec(cid), JPEG_LS_LOSSLESS, "dcmcjpls", ("+el",), "dcmdjpls")


def build_jpeg_ls_near_lossless() -> dict[str, bytes]:
    """JPEG-LS Near-Lossless NEAR=2 (dcmcjpls +en +md 2); RGB (PS3.5 Table 8.2.3-1)."""
    cid = "W7-TS-JPEG-LS-NEAR-RGB"
    return _dcmtk_control(cid, Spec(cid), JPEG_LS_NEAR_LOSSLESS, "dcmcjpls", ("+en", "+md", "2"),
                          None, "ISO_14495_1")


def build_encapsulated_uncompressed() -> dict[str, bytes]:
    """Encapsulated Uncompressed Explicit VR LE (PS3.5 A.4.11): each Frame, as it would be
    in Native Format, in exactly one Fragment; RGB 8-bit."""
    cid = "W7-TS-ENCAPSULATED-UNCOMPRESSED"
    ds, native = build_dataset(Spec(cid))
    _encapsulate(ds, native, ENCAPSULATED_UNCOMPRESSED)
    return {f"{cid}.dcm": _bytes(ds)}


def build_deflated_data_set() -> dict[str, bytes]:
    """Deflated Explicit VR Little Endian (PS3.5 A.5): the whole Data Set after the File Meta
    Information is one raw Deflate (RFC 1951) bit stream; RGB 8-bit native Pixel Data."""
    cid = "W7-TS-DEFLATED-EVRLE"
    ds, native = build_dataset(Spec(cid))
    ds.file_meta.TransferSyntaxUID = UID(DEFLATED_EVRLE)
    data = _bytes(ds)
    check = pydicom.dcmread(io.BytesIO(data))
    if bytes(check.PixelData) != b"".join(native):
        raise RuntimeError(f"{cid}: the deflated Data Set does not inflate to the native Frames")
    return {f"{cid}.dcm": data}


def _deflate(frame: bytes) -> bytes:
    compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS, 9, zlib.Z_DEFAULT_STRATEGY)
    stream = compressor.compress(frame) + compressor.flush()
    if zlib.decompress(stream, -zlib.MAX_WBITS) != frame:
        raise RuntimeError("raw Deflate round trip failed")
    return stream


def build_deflated_image_frames() -> dict[str, bytes]:
    """Deflated Image Frame Compression (PS3.5 A.4.13, 8.2.16): each Frame separately raw
    Deflated (RFC 1951) into one Fragment, an odd stream padded by one trailing NULL; RGB."""
    cid = "W7-TS-DEFLATED-IMAGE-FRAME"
    ds, native = build_dataset(Spec(cid))
    _encapsulate(ds, [_deflate(frame) for frame in native], DEFLATED_IMAGE_FRAME)
    return {f"{cid}.dcm": _bytes(ds)}


def _pnm(frame: bytes, rows: int, columns: int, samples: int, bits: int) -> bytes:
    """A binary PGM/PPM of one native Frame (PNM samples are big-endian when 16-bit)."""
    if bits == 16:
        frame = b"".join(frame[i + 1 : i + 2] + frame[i : i + 1] for i in range(0, len(frame), 2))
    magic = b"P6" if samples == 3 else b"P5"
    return magic + f"\n{columns} {rows}\n{(1 << bits) - 1}\n".encode() + frame


def _encode_frames(native: list[bytes], ds: Dataset, command) -> list[bytes]:
    """Encode each native Frame with ``command(source, target)`` through PNM files."""
    out = []
    with tempfile.TemporaryDirectory() as temporary:
        for index, frame in enumerate(native):
            source = Path(temporary) / f"f{index}.{'ppm' if ds.SamplesPerPixel == 3 else 'pgm'}"
            source.write_bytes(_pnm(frame, ds.Rows, ds.Columns, ds.SamplesPerPixel, ds.BitsAllocated))
            target = Path(temporary) / f"f{index}.out"
            _run(command(str(source), str(target)))
            out.append(target.read_bytes())
    return out


def _decode_frames(encoded: list[bytes], suffix: str, command) -> list[bytes]:
    """Decode each Frame with ``command(source, target)`` to PNM and return the raw samples."""
    out = []
    with tempfile.TemporaryDirectory() as temporary:
        for index, frame in enumerate(encoded):
            source, target = Path(temporary) / f"f{index}{suffix}", Path(temporary) / f"f{index}.pnm"
            source.write_bytes(frame)
            _run(command(str(source), str(target)))
            data = target.read_bytes()
            fields, position = [], 0
            while len(fields) < 4:  # magic, width, height, maxval, then one whitespace byte
                while data[position : position + 1].isspace() or data[position : position + 1] == b"#":
                    if data[position : position + 1] == b"#":  # a comment runs to the line end
                        position = data.index(b"\n", position)
                    position += 1
                start = position
                while not data[position : position + 1].isspace():
                    position += 1
                fields.append(data[start:position])
            out.append(data[position + 1 :])
    return out


def build_htj2k_rpcl() -> dict[str, bytes]:
    """HTJ2K Lossless RPCL with 128x128 Frames (OpenJPH ojph_compress): RPCL progression, 5
    decomposition levels (a 4x4 base resolution, at most 64 as PS3.5 A.4.4 requires), TLM
    markers with tile-parts per resolution, 64x64 code blocks, the reversible color transform,
    hence YBR_RCT. Decoded bit-exactly by ojph_expand."""
    cid = "W7-TS-HTJ2K-RPCL-128"
    spec = Spec(cid, rows=128, columns=128, total_rows=128, total_columns=256, spacing=0.0005,
                photometric="YBR_RCT")
    ds, native = build_dataset(spec)
    frames = _encode_frames(native, ds, _ojph)
    decoded = _decode_frames(frames, ".j2c", _ojph_expand)
    if decoded != [bytes(f) for f in native]:
        raise RuntimeError(f"{cid}: ojph_expand does not recover the native Frames bit-exactly")
    _encapsulate(ds, frames, HTJ2K_LOSSLESS_RPCL)
    return {f"{cid}.dcm": _bytes(ds)}


def _ojph(source: str, target: str) -> list[str]:
    # OpenJPH picks formats by file suffix, so the call is wrapped to write the named target.
    return ["sh", "-c", 'ojph_compress -i "$1" -o "$2.j2c" -reversible true -colour_trans true '
            '-prog_order RPCL -num_decomps 5 -block_size "{64,64}" -tlm_marker true -tileparts R '
            '&& mv "$2.j2c" "$2"', "ojph", source, target]


def _ojph_expand(source: str, target: str) -> list[str]:
    return ["sh", "-c", 'cp "$1" "$1.j2c" && ojph_expand -i "$1.j2c" -o "$2.ppm" && mv "$2.ppm" "$2"',
            "ojph", source, target]


def _cjxl(*options: str):
    return lambda source, target: [
        "sh", "-c", 'src="$1"; dst="$2"; shift 2; cjxl "$src" "$dst.jxl" "$@" && mv "$dst.jxl" "$dst"',
        "cjxl", source, target, *options]


def _djxl(suffix: str):
    return lambda source, target: [
        "sh", "-c", 'cp "$1" "$1.jxl" && djxl "$1.jxl" "$2' + suffix + '" && mv "$2' + suffix + '" "$2"',
        "djxl", source, target]


def build_jpeg_xl_lossless() -> dict[str, bytes]:
    """JPEG XL Lossless (cjxl -d 0, modular, no XYB); RGB; decoded bit-exactly by djxl."""
    cid = "W7-TS-JXL-LOSSLESS-RGB"
    ds, native = build_dataset(Spec(cid))
    frames = _encode_frames(native, ds, _cjxl("-d", "0", "-e", "7", "--quiet"))
    if _decode_frames(frames, ".jxl", _djxl(".ppm")) != native:
        raise RuntimeError(f"{cid}: djxl does not recover the native Frames bit-exactly")
    _encapsulate(ds, frames, JPEG_XL_LOSSLESS)
    return {f"{cid}.dcm": _bytes(ds)}


def build_jpeg_xl_lossy() -> dict[str, bytes]:
    """JPEG XL lossy (cjxl -d 1, VarDCT) MONOCHROME2 8-bit under the JPEG XL Transfer Syntax.

    MONOCHROME2 is listed for 1.2.840.10008.1.2.4.112 by PS3.5 Table 8.2.15-1; a lossy color
    JPEG XL codestream is XYB-encoded, and XYB is not an Enumerated Value of the WSI Image
    Module, so the lossy control is monochrome."""
    cid = "W7-TS-JXL-LOSSY-MONO8"
    spec = Spec(cid, samples=1, photometric="MONOCHROME2", rows=16, columns=16, total_rows=32,
                total_columns=32)
    ds, native = build_dataset(spec)
    frames = _encode_frames(native, ds, _cjxl("-d", "1.0", "-e", "7", "--quiet"))
    _encapsulate(ds, frames, JPEG_XL)
    _lossy(ds, _native_size(ds), frames, "ISO_18181_1")
    return {f"{cid}.dcm": _bytes(ds)}


def build_jpeg_xl_recompression() -> dict[str, bytes]:
    """JPEG XL JPEG Recompression (cjxl --lossless_jpeg=1) of JPEG Baseline YBR_FULL_422 Frames
    (dcmcjpeg +eb +cy +s2): each JPEG is reconstructed bit-exactly by djxl. The lossy history is
    that of the JPEG (ISO_10918_1); the transcoding adds none (PS3.5 A.4.12)."""
    cid = "W7-TS-JXL-JPEG-RECOMPRESSION"
    spec = Spec(cid, rows=16, columns=16, total_rows=32, total_columns=32, photometric="RGB")
    ds, native = build_dataset(spec)
    transfer_syntax, jpegs = _dcmtk_frames(ds, "dcmcjpeg", "+eb", "+cy", "+s2", "+q", "85")
    if transfer_syntax != JPEG_BASELINE:
        raise RuntimeError(f"{cid}: dcmcjpeg wrote {transfer_syntax}")
    jpegs = [j[: j.rindex(b"\xff\xd9") + 2] for j in jpegs]  # drop the even-length pad
    with tempfile.TemporaryDirectory() as temporary:
        frames = []
        for index, jpeg in enumerate(jpegs):
            source = Path(temporary) / f"f{index}.jpg"
            source.write_bytes(jpeg)
            target = Path(temporary) / f"f{index}.jxl"
            _run(["cjxl", str(source), str(target), "--lossless_jpeg=1", "--quiet"])
            back = Path(temporary) / f"f{index}.back.jpg"
            _run(["djxl", str(target), str(back)])
            if back.read_bytes() != jpeg:
                raise RuntimeError(f"{cid}: djxl does not reconstruct JPEG Frame {index + 1}")
            frames.append(target.read_bytes())
    ds.PhotometricInterpretation = "YBR_FULL_422"
    _encapsulate(ds, frames, JPEG_XL_JPEG_RECOMPRESSION)
    _lossy(ds, _native_size(ds), jpegs, "ISO_10918_1")
    return {f"{cid}.dcm": _bytes(ds)}


def _opj_control(control_id: str, transfer_syntax: str, photometric: str, options: tuple[str, ...],
                 lossy: bool) -> dict[str, bytes]:
    spec = Spec(control_id, rows=16, columns=16, total_rows=32, total_columns=32,
                photometric=photometric)
    ds, native = build_dataset(spec)
    frames = _encode_frames(native, ds, lambda s, d: [
        "sh", "-c", 'src="$1"; dst="$2"; shift 2; opj_compress -i "$src" -o "$dst.j2k" "$@" '
        '> /dev/null && mv "$dst.j2k" "$dst"', "opj", s, d, *options])
    for frame in frames:
        # SGcod multiple component transformation: the Part 1 RCT (5-3) or ICT (9-7).
        cod = frame.index(b"\xff\x52")
        if frame[cod + 8] != 1:
            raise RuntimeError(f"{control_id}: the codestream applies no Part 1 color transform")
    if not lossy:
        decoded = _decode_frames(frames, ".j2k", lambda s, d: [
            "sh", "-c", 'cp "$1" "$1.j2k" && opj_decompress -i "$1.j2k" -o "$2.ppm" > /dev/null '
            '&& mv "$2.ppm" "$2"', "opj", s, d])
        if decoded != native:
            raise RuntimeError(f"{control_id}: opj_decompress does not recover the native Frames")
    _encapsulate(ds, frames, transfer_syntax)
    if lossy:
        _lossy(ds, _native_size(ds), frames, "ISO_15444_1")
    return {f"{control_id}.dcm": _bytes(ds)}


def build_j2k_rct() -> dict[str, bytes]:
    """JPEG 2000 Lossless Only, Part 1 reversible color transform (opj_compress, 5-3): the
    components are YBR_RCT (PS3.5 8.2.4); decoded bit-exactly by opj_decompress."""
    return _opj_control("W7-TS-J2K-PART1-RCT", J2K_LOSSLESS, "YBR_RCT", ("-n", "3"), lossy=False)


def build_j2k_ict() -> dict[str, bytes]:
    """JPEG 2000, Part 1 irreversible color transform (opj_compress -I, 9-7, rate 4): YBR_ICT."""
    return _opj_control("W7-TS-J2K-PART1-ICT", J2K, "YBR_ICT", ("-n", "3", "-I", "-r", "4"),
                        lossy=True)


# libopenjp2 exposes the Part 2 array-based MCT only through its API (opj_set_MCT); the
# opj_compress and grk_compress command lines of OpenJPEG 2.5.4 and Grok 20.3 do not accept a
# custom MCT. This program is compiled with clang against the installed libopenjp2 at build time.
PART2_MCT_ENCODER = r"""/* Encode one 8-bit 3-component frame as a JPEG 2000 Part 2 codestream with an array-based
 * multiple component transformation (ISO/IEC 15444-2 Annex J) through libopenjp2.
 * usage: mct in.raw out.j2k width height reversible(0|1) rate m00 m01 ... m22 */
#include <openjpeg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void quiet(const char *m, void *d) { (void)m; (void)d; }
static void loud(const char *m, void *d) { (void)d; fprintf(stderr, "%s", m); }
int main(int argc, char **argv) {
    if (argc != 16) { fprintf(stderr, "bad arguments\n"); return 2; }
    int w = atoi(argv[3]), h = atoi(argv[4]), reversible = atoi(argv[5]);
    float rate = (float)atof(argv[6]);
    OPJ_FLOAT32 matrix[9]; OPJ_INT32 shift[3] = {0, 0, 0};
    for (int i = 0; i < 9; i++) matrix[i] = (OPJ_FLOAT32)atof(argv[7 + i]);
    FILE *f = fopen(argv[1], "rb"); if (!f) return 3;
    unsigned char *raw = malloc((size_t)w * h * 3);
    if (fread(raw, 1, (size_t)w * h * 3, f) != (size_t)w * h * 3) return 4; fclose(f);
    opj_image_cmptparm_t cp[3]; memset(cp, 0, sizeof cp);
    for (int c = 0; c < 3; c++) { cp[c].dx = cp[c].dy = 1; cp[c].w = w; cp[c].h = h; cp[c].prec = 8; cp[c].sgnd = 0; }
    opj_image_t *image = opj_image_create(3, cp, OPJ_CLRSPC_UNSPECIFIED);
    image->x0 = 0; image->y0 = 0; image->x1 = w; image->y1 = h;
    for (int i = 0; i < w * h; i++) for (int c = 0; c < 3; c++) image->comps[c].data[i] = raw[i * 3 + c];
    opj_cparameters_t p; opj_set_default_encoder_parameters(&p);
    p.tcp_numlayers = 1; p.tcp_rates[0] = rate; p.cp_disto_alloc = 1;
    p.numresolution = 3; p.cblockw_init = 16; p.cblockh_init = 16;
    if (!opj_set_MCT(&p, matrix, shift, 3)) return 5;
    p.irreversible = reversible ? 0 : 1;
    opj_codec_t *codec = opj_create_compress(OPJ_CODEC_J2K);
    opj_set_error_handler(codec, loud, NULL); opj_set_warning_handler(codec, quiet, NULL);
    if (!opj_setup_encoder(codec, &p, image)) return 6;
    opj_stream_t *s = opj_stream_create_default_file_stream(argv[2], OPJ_FALSE);
    if (!s || !opj_start_compress(codec, image, s) || !opj_encode(codec, s) || !opj_end_compress(codec, s)) return 7;
    opj_stream_destroy(s); opj_destroy_codec(codec); opj_image_destroy(image); free(raw);
    return 0;
}
"""

# The ICT of ISO/IEC 15444-1 G.3 as a Part 2 array-based decorrelation (rows: Y, Cb, Cr).
ICT_MATRIX = ("0.299", "0.587", "0.114", "-0.168736", "-0.331264", "0.5", "0.5", "-0.418688",
              "-0.081312")


def build_j2k_part2_ict() -> dict[str, bytes]:
    """JPEG 2000 Part 2 (1.2.840.10008.1.2.4.93): each Frame one codestream (its own component
    collection) whose three components are decorrelated by an array-based multiple component
    transformation (MCT, MCC, MCO and CBD marker segments, Rsiz Part 2 with the Annex J
    capability, SGcod MCT 2) equal to the ICT, with the irreversible 9-7 wavelet; the encoded
    components are Y, Cb, Cr of the ICT, so Photometric Interpretation is YBR_ICT."""
    cid = "W7-TS-J2K-PART2-ICT"
    spec = Spec(cid, rows=16, columns=16, total_rows=32, total_columns=32, photometric="YBR_ICT")
    ds, native = build_dataset(spec)
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        (work / "mct.c").write_text(PART2_MCT_ENCODER)
        _run(["clang", "-O1", "-I/opt/homebrew/include/openjpeg-2.5", "mct.c", "-L/opt/homebrew/lib",
              "-lopenjp2", "-o", "mct"], cwd=work)
        frames = []
        for index, frame in enumerate(native):
            (work / f"f{index}.raw").write_bytes(frame)
            _run([str(work / "mct"), f"f{index}.raw", f"f{index}.j2k", str(ds.Columns), str(ds.Rows),
                  "0", "3", *ICT_MATRIX], cwd=work)
            frames.append((work / f"f{index}.j2k").read_bytes())
    for frame in frames:
        rsiz = int.from_bytes(frame[6:8], "big")
        if rsiz & 0x8100 != 0x8100 or b"\xff\x75" not in frame:
            raise RuntimeError(f"{cid}: the codestream is not Part 2 with an MCC marker segment")
    _encapsulate(ds, frames, J2K_PART2)
    _lossy(ds, _native_size(ds), frames, "ISO_15444_1")
    return {f"{cid}.dcm": _bytes(ds)}


# --- 6. Digital Signatures ----------------------------------------------------------------------

# The keys exist only in a temporary directory for the duration of one build. The signer
# certificate is embedded in each Digital Signatures Sequence Item (Certificate of Signer), and
# the TSA certificate in the Certified Timestamp (CMS SignedData). notBefore is in the past
# because dcmsign 3.7.0 compares a certificate made "now" against the local-time Digital
# Signature DateTime and rejects it as not yet valid.
_VALIDITY = ("-not_before", "20260101000000Z", "-not_after", "21251231235959Z")
_TSA_CONFIG = """[ req ]
distinguished_name = dn
prompt = no
[ dn ]
CN = wsi-dicom-bench ephemeral TSA
[ tsa_ext ]
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature
extendedKeyUsage = critical,timeStamping
subjectKeyIdentifier = hash
[ tsa ]
default_tsa = tsa_config
[ tsa_config ]
serial = ./tsaserial
crypto_device = builtin
signer_digest = sha256
default_policy = 1.2.3.4.1
digests = sha256, sha384, sha512
accuracy = secs:1
ordering = yes
tsa_name = no
ess_cert_id_chain = no
ess_cert_id_alg = sha256
"""

# The Data Elements a tag-list signature covers: the identities the Base RSA Digital
# Signature Profile names (PS3.15 C.1), the Image Pixel description and Pixel Data.
SIGNED_TAGS = ("SOPClassUID", "SOPInstanceUID", "StudyInstanceUID", "SeriesInstanceUID",
               "FrameOfReferenceUID", "ImageType", "SamplesPerPixel", "PhotometricInterpretation",
               "Rows", "Columns", "BitsAllocated", "NumberOfFrames", "7fe0,0010")


def _signed(control_id: str, sign_options: list[str], timestamp: bool = False) -> dict[str, bytes]:
    ds, _ = build_dataset(Spec(control_id))
    unsigned = _bytes(ds)
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        (work / "in.dcm").write_bytes(unsigned)
        _run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "key.pem",
              "-out", "cert.pem", *_VALIDITY, "-subj", "/CN=wsi-dicom-bench ephemeral signer"],
             cwd=work)
        options = [*(o.replace("{key}", "key.pem").replace("{cert}", "cert.pem") for o in sign_options),
                   "+m2", "+sp", "1"]
        if not timestamp:
            _run(["dcmsign", *options, "in.dcm", "signed.dcm"], cwd=work)
        else:
            (work / "tsa.cnf").write_text(_TSA_CONFIG)
            (work / "tsaserial").write_text("01\n")
            _run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "tsa-key.pem",
                  "-out", "tsa-cert.pem", *_VALIDITY, "-config", "tsa.cnf", "-extensions", "tsa_ext"],
                 cwd=work)
            _run(["dcmsign", *options, "+ts", "query.tsq", "uid.txt", "in.dcm", "pending.dcm"], cwd=work)
            _run(["openssl", "ts", "-reply", "-config", "tsa.cnf", "-queryfile", "query.tsq",
                  "-signer", "tsa-cert.pem", "-inkey", "tsa-key.pem", "-out", "reply.tsr"], cwd=work)
            _run(["openssl", "ts", "-verify", "-queryfile", "query.tsq", "-in", "reply.tsr",
                  "-CAfile", "tsa-cert.pem"], cwd=work)
            _run(["dcmsign", "--insert-timestamp", "query.tsq", "reply.tsr", "uid.txt", "pending.dcm",
                  "signed.dcm"], cwd=work)
        data = (work / "signed.dcm").read_bytes()
    verify_signatures(control_id, data, require_timestamp=timestamp)
    if len(data) > MAX_CONTROL_BYTES:
        raise RuntimeError(f"{control_id}: control is {len(data)} bytes")
    return {f"{control_id}.dcm": data}


def _signature_items(dataset: Dataset):
    for element in dataset:
        if element.VR != "SQ":
            continue
        for item in element.value:
            if element.tag == 0xFFFAFFFA:
                yield item
            else:
                yield from _signature_items(item)


def verify_signatures(control_id: str, data: bytes, require_timestamp: bool = False) -> int:
    """``dcmsign --verify`` with the embedded signer (and TSA) certificates given via +cf;
    every signature, and its certified timestamp where present, must verify."""
    ds = pydicom.dcmread(io.BytesIO(data))
    items = list(_signature_items(ds))
    if not items:
        raise RuntimeError(f"{control_id}: no Digital Signatures Sequence Item")
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        (work / "signed.dcm").write_bytes(data)
        trust = []
        for index, item in enumerate(items):
            (work / f"signer{index}.der").write_bytes(bytes(item.CertificateOfSigner))
            _run(["openssl", "x509", "-inform", "DER", "-in", f"signer{index}.der", "-out",
                  f"signer{index}.pem"], cwd=work)
            trust += ["+cf", f"signer{index}.pem"]
            if "CertifiedTimestamp" in item:
                (work / f"ts{index}.der").write_bytes(bytes(item.CertifiedTimestamp))
                _run(["openssl", "pkcs7", "-inform", "DER", "-in", f"ts{index}.der", "-print_certs",
                      "-out", f"tsa{index}.pem"], cwd=work)
                trust += ["+cf", f"tsa{index}.pem"]
        output = _run(["dcmsign", "--verify", *trust, *(["+tr"] if require_timestamp else []),
                       "signed.dcm"], cwd=work)
    if output.count("Signature Verification : OK") != len(items):
        raise RuntimeError(f"{control_id}: dcmsign --verify did not verify every signature: {output}")
    if require_timestamp and "Timestamp Verification : OK" not in output:
        raise RuntimeError(f"{control_id}: the certified timestamp did not verify: {output}")
    return len(items)


def build_signed_data_set() -> dict[str, bytes]:
    """An RSA signature (SHA-256 MAC, Base RSA Digital Signature Profile enforced by dcmsign
    +pb) over every signable Data Element of the top-level Data Set."""
    return _signed("W7-SIGNED-DATASET", ["--sign", "{key}", "{cert}", "+pb"])


def build_signed_tags() -> dict[str, bytes]:
    """An RSA signature over a selected tag list that includes Pixel Data (dcmsign -t)."""
    options = ["--sign", "{key}", "{cert}"]
    for tag in SIGNED_TAGS:
        options += ["-t", tag]
    return _signed("W7-SIGNED-TAGLIST-PIXELDATA", options)


def build_signed_item() -> dict[str, bytes]:
    """An RSA signature inside the Specimen Description Sequence Item: the Digital Signatures
    Macro, with its MAC Parameters Sequence, in a Sequence Item (PS3.3 C.12.1.1.3)."""
    return _signed("W7-SIGNED-SEQUENCE-ITEM",
                   ["--sign-item", "{key}", "{cert}", "SpecimenDescriptionSequence[0]"])


def build_signed_timestamp() -> dict[str, bytes]:
    """An RSA signature with a Certified Timestamp (CMS_TSP) from a local OpenSSL TSA
    (openssl ts -reply), inserted with dcmsign --insert-timestamp."""
    return _signed("W7-SIGNED-CERTIFIED-TIMESTAMP", ["--sign", "{key}", "{cert}"], timestamp=True)


# --- registry and command line ------------------------------------------------------------------

# Builders by control id; each returns {relative path: bytes}. CONTROLS (at the end of the
# module) records what each control exercises and the SHA-256 of every file it writes.
BUILDERS = {
    SET_ID: build_image_type_set,
    "W7-TILED-SPARSE-5OF9": build_tiled_sparse,
    "W7-TILED-NOTYPE-4F": build_absent_organization,
    "W7-ZSTACK-3P-TILED-FULL": build_z_stack,
    "W7-OPTICAL-PATHS-2-MONO": build_optical_paths,
    "W7-EDF-5P": build_extended_depth_of_field,
    "W7-3D-ORGANIZATION-3P": build_3d_organization,
    CONCATENATION_ID: build_concatenation,
    "W7-TS-RLE-RGB": build_rle,
    "W7-TS-JPEG-LOSSLESS-P14-SV6": build_jpeg_lossless,
    "W7-TS-JPEG-LOSSLESS-SV1": build_jpeg_lossless_sv1,
    "W7-TS-JPEG-EXTENDED-MONO8": build_jpeg_extended,
    "W7-TS-JPEG-BASELINE-YBR422": build_jpeg_baseline_422,
    "W7-TS-JPEG-LS-LOSSLESS-RGB": build_jpeg_ls_lossless,
    "W7-TS-JPEG-LS-NEAR-RGB": build_jpeg_ls_near_lossless,
    "W7-TS-ENCAPSULATED-UNCOMPRESSED": build_encapsulated_uncompressed,
    "W7-TS-DEFLATED-EVRLE": build_deflated_data_set,
    "W7-TS-DEFLATED-IMAGE-FRAME": build_deflated_image_frames,
    "W7-TS-HTJ2K-RPCL-128": build_htj2k_rpcl,
    "W7-TS-JXL-LOSSLESS-RGB": build_jpeg_xl_lossless,
    "W7-TS-JXL-JPEG-RECOMPRESSION": build_jpeg_xl_recompression,
    "W7-TS-JXL-LOSSY-MONO8": build_jpeg_xl_lossy,
    "W7-TS-J2K-PART1-RCT": build_j2k_rct,
    "W7-TS-J2K-PART1-ICT": build_j2k_ict,
    "W7-TS-J2K-PART2-ICT": build_j2k_part2_ict,
    "W7-MONO8-FLUO-PALETTE": build_mono8_palette,
    "W7-MONO16-FLUO": build_mono16,
    "W7-RGB16-EVRLE": build_rgb16,
    "W7-SIGNED-DATASET": build_signed_data_set,
    "W7-SIGNED-TAGLIST-PIXELDATA": build_signed_tags,
    "W7-SIGNED-SEQUENCE-ITEM": build_signed_item,
    "W7-SIGNED-CERTIFIED-TIMESTAMP": build_signed_timestamp,
}


def build_all(selected: list[str] | None = None) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for control_id, builder in BUILDERS.items():
        if selected and control_id not in selected:
            continue
        for relative, data in builder().items():
            if relative in files:
                raise RuntimeError(f"two controls write {relative}")
            files[relative] = data
    return files


def build(output: Path, selected: list[str] | None = None) -> dict[str, str]:
    """Write the controls into ``output`` (which must not exist) atomically."""
    if output.exists():
        raise RuntimeError(f"output already exists: {output}")
    files = build_all(selected)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent) as temporary:
        staging = Path(temporary) / output.name
        for relative, data in files.items():
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        shutil.move(staging, output)
    return {relative: hashlib.sha256(data).hexdigest() for relative, data in files.items()}


def verify(committed: Path = OUTPUT) -> list[str]:
    """Rebuild every reproducible control and compare it with ``committed`` and ``CONTROLS``."""
    problems = []
    rebuilt = build_all([c["id"] for c in CONTROLS if c["reproducible"]])
    for control in CONTROLS:
        for relative, digest in control["sha256"].items():
            on_disk = committed / relative
            if not on_disk.is_file():
                problems.append(f"{control['id']}: {relative} is missing")
                continue
            if hashlib.sha256(on_disk.read_bytes()).hexdigest() != digest:
                problems.append(f"{control['id']}: {relative} differs from its recorded SHA-256")
            if control["reproducible"] and hashlib.sha256(rebuilt[relative]).hexdigest() != digest:
                problems.append(f"{control['id']}: {relative} no longer rebuilds byte-identically")
            committed_bytes = on_disk.read_bytes()
            for problem in frame_offset_problems(pydicom.dcmread(io.BytesIO(committed_bytes))):
                problems.append(f"{control['id']}: {relative}: {problem}")
            if not control["reproducible"]:
                try:
                    verify_signatures(control["id"], committed_bytes,
                                      require_timestamp="TIMESTAMP" in control["id"])
                except RuntimeError as error:
                    problems.append(str(error))
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build")
    build_parser.add_argument("output", type=Path)
    build_parser.add_argument("--only", nargs="*")
    sub.add_parser("verify")
    args = parser.parse_args()
    if args.command == "build":
        for relative, digest in build(args.output, args.only).items():
            print(f"{digest}  {relative}")
        return 0
    problems = verify()
    for problem in problems:
        print(problem)
    return 1 if problems else 0


# What each control exercises. "iod" is VL Whole Slide Microscopy Image for every entry.
_EXERCISES = {
    SET_ID: dict(
        configuration="study set: VOLUME pyramid of 3 levels (TILED_FULL), THUMBNAIL apex, "
        "OVERVIEW with the Series Frame of Reference, LABEL without Frame of Reference; one "
        "Series, one Pyramid UID for VOLUME and THUMBNAIL",
        transfer_syntax=EVRLE, scope="set; derived members reference their source"),
    "W7-TILED-SPARSE-5OF9": dict(
        configuration="TILED_SPARSE, 5 of 9 tiles, out of raster order, Tiles Overlap NONE, "
        "anisotropic pixels (0.0005 mm rows, 0.00025 mm columns)",
        transfer_syntax=EVRLE, scope="instance"),
    "W7-TILED-NOTYPE-4F": dict(
        configuration="Dimension Organization Type absent, explicit Plane Position (Slide)",
        transfer_syntax=EVRLE, scope="instance"),
    "W7-ZSTACK-3P-TILED-FULL": dict(
        configuration="TILED_FULL, 3 focal planes 1 um apart (Spacing Between Slices)",
        transfer_syntax=EVRLE, scope="instance"),
    "W7-OPTICAL-PATHS-2-MONO": dict(
        configuration="TILED_FULL, 2 epifluorescence optical paths, MONOCHROME2 8-bit, "
        "Channel Description Code Sequence",
        transfer_syntax=EVRLE, scope="instance"),
    "W7-EDF-5P": dict(
        configuration="Extended Depth of Field YES, 5 acquisition planes 0.5 um apart",
        transfer_syntax=EVRLE, scope="instance"),
    "W7-3D-ORGANIZATION-3P": dict(
        configuration="Dimension Organization Type 3D: 3 whole-matrix Frames, 1.5 um apart",
        transfer_syntax=EVRLE, scope="instance"),
    CONCATENATION_ID: dict(
        configuration="Concatenation of 2 Instances split from one 8-Frame TILED_FULL level",
        transfer_syntax=EVRLE, scope="set (one Concatenation)"),
    "W7-TS-RLE-RGB": dict(configuration="TILED_FULL RGB 8-bit, 4 Frames",
                          transfer_syntax=RLE, scope="instance"),
    "W7-TS-JPEG-LOSSLESS-P14-SV6": dict(configuration="TILED_FULL RGB 8-bit, Selection Value 6",
                                        transfer_syntax=JPEG_LOSSLESS, scope="instance"),
    "W7-TS-JPEG-LOSSLESS-SV1": dict(configuration="TILED_FULL RGB 8-bit",
                                    transfer_syntax=JPEG_LOSSLESS_SV1, scope="instance"),
    "W7-TS-JPEG-EXTENDED-MONO8": dict(configuration="TILED_FULL MONOCHROME2 8-bit, lossy",
                                      transfer_syntax=JPEG_EXTENDED, scope="instance"),
    "W7-TS-JPEG-BASELINE-YBR422": dict(
        configuration="TILED_FULL YBR_FULL_422 (4:2:2 subsampled), 16x16 tiles, lossy",
        transfer_syntax=JPEG_BASELINE, scope="instance"),
    "W7-TS-JPEG-LS-LOSSLESS-RGB": dict(configuration="TILED_FULL RGB 8-bit",
                                       transfer_syntax=JPEG_LS_LOSSLESS, scope="instance"),
    "W7-TS-JPEG-LS-NEAR-RGB": dict(configuration="TILED_FULL RGB 8-bit, NEAR=2, lossy",
                                   transfer_syntax=JPEG_LS_NEAR_LOSSLESS, scope="instance"),
    "W7-TS-ENCAPSULATED-UNCOMPRESSED": dict(configuration="TILED_FULL RGB 8-bit",
                                            transfer_syntax=ENCAPSULATED_UNCOMPRESSED,
                                            scope="instance"),
    "W7-TS-DEFLATED-EVRLE": dict(configuration="TILED_FULL RGB 8-bit, deflated Data Set",
                                 transfer_syntax=DEFLATED_EVRLE, scope="instance"),
    "W7-TS-DEFLATED-IMAGE-FRAME": dict(configuration="TILED_FULL RGB 8-bit, deflated Frames",
                                       transfer_syntax=DEFLATED_IMAGE_FRAME, scope="instance"),
    "W7-TS-HTJ2K-RPCL-128": dict(
        configuration="TILED_FULL YBR_RCT, 2 Frames of 128x128, RPCL, 5 levels, TLM",
        transfer_syntax=HTJ2K_LOSSLESS_RPCL, scope="instance"),
    "W7-TS-JXL-LOSSLESS-RGB": dict(configuration="TILED_FULL RGB 8-bit",
                                   transfer_syntax=JPEG_XL_LOSSLESS, scope="instance"),
    "W7-TS-JXL-JPEG-RECOMPRESSION": dict(
        configuration="TILED_FULL YBR_FULL_422, transcoded JPEG Baseline, lossy history",
        transfer_syntax=JPEG_XL_JPEG_RECOMPRESSION, scope="instance"),
    "W7-TS-JXL-LOSSY-MONO8": dict(configuration="TILED_FULL MONOCHROME2 8-bit, VarDCT lossy",
                                  transfer_syntax=JPEG_XL, scope="instance"),
    "W7-TS-J2K-PART1-RCT": dict(configuration="TILED_FULL YBR_RCT (Part 1 RCT, 5-3), 16x16 tiles",
                                transfer_syntax=J2K_LOSSLESS, scope="instance"),
    "W7-TS-J2K-PART1-ICT": dict(
        configuration="TILED_FULL YBR_ICT (Part 1 ICT, 9-7), 16x16 tiles, lossy",
        transfer_syntax=J2K, scope="instance"),
    "W7-TS-J2K-PART2-ICT": dict(
        configuration="TILED_FULL YBR_ICT, Part 2 array-based MCT equal to the ICT, 9-7, lossy",
        transfer_syntax=J2K_PART2, scope="instance"),
    "W7-MONO8-FLUO-PALETTE": dict(
        configuration="TILED_FULL MONOCHROME2 8-bit epifluorescence, Palette Color Lookup Table "
        "Sequence and ICC Profile in the Optical Path", transfer_syntax=EVRLE, scope="instance"),
    "W7-MONO16-FLUO": dict(configuration="TILED_FULL MONOCHROME2 16-bit epifluorescence",
                           transfer_syntax=EVRLE, scope="instance"),
    "W7-RGB16-EVRLE": dict(configuration="TILED_FULL RGB 16-bit", transfer_syntax=EVRLE,
                           scope="instance"),
    "W7-SIGNED-DATASET": dict(
        configuration="TILED_FULL RGB 8-bit; RSA-2048 signature, SHA-256 MAC, whole Data Set, "
        "Base RSA profile", transfer_syntax=EVRLE, scope="instance"),
    "W7-SIGNED-TAGLIST-PIXELDATA": dict(
        configuration="TILED_FULL RGB 8-bit; RSA-2048 signature over a tag list with Pixel Data",
        transfer_syntax=EVRLE, scope="instance"),
    "W7-SIGNED-SEQUENCE-ITEM": dict(
        configuration="TILED_FULL RGB 8-bit; RSA-2048 signature in the Specimen Description "
        "Sequence Item", transfer_syntax=EVRLE, scope="instance"),
    "W7-SIGNED-CERTIFIED-TIMESTAMP": dict(
        configuration="TILED_FULL RGB 8-bit; RSA-2048 signature with a CMS_TSP Certified "
        "Timestamp", transfer_syntax=EVRLE, scope="instance"),
}

# SHA-256 of every committed file, by path relative to controls-v7/wsi.
SHA256 = {
    "W7-SET-PYRAMID-3L-LOT/level-0.dcm": "450fe26a40d8d8c7817ff9a106e123a46a6e66ec1de12b97e0bd40ab654dce9f",
    "W7-SET-PYRAMID-3L-LOT/level-1.dcm": "d903934b199355c0d636081e15e99dfb26eec1ab3a59496c60c50ed5eb798437",
    "W7-SET-PYRAMID-3L-LOT/level-2.dcm": "8a6c389b0d4e5a81c78c8c3b8e84123fd248eda69db158bc258e2d4d231d223d",
    "W7-SET-PYRAMID-3L-LOT/thumbnail.dcm": "05bb6c7165d450f732609ebbc6274bbc4f35f31ec1e663a1dfdcb12225f4e250",
    "W7-SET-PYRAMID-3L-LOT/overview.dcm": "91ef51a2a7ec876d43f85067d4fc07a0e2a8bdf39518f2b3fd9b0355e744aa92",
    "W7-SET-PYRAMID-3L-LOT/label.dcm": "ce32c6c8e0f0677ae5b533ee06846952b4519236bd569122909f349b6b5f8b30",
    "W7-TILED-SPARSE-5OF9.dcm": "5b03056e5897fc0e1b7fd3c5975a6e4a78192fc5a33b57642fcfb35b6c6e60b2",
    "W7-TILED-NOTYPE-4F.dcm": "9e9c99ff4e947bb3bd80af3b8baa418c959b261141f7bad2905bbaacd6cf385c",
    "W7-ZSTACK-3P-TILED-FULL.dcm": "fc9abede7c142beccee85ed9c1ad033c530dc0b63ee6a5d6d95a9d0dfabcccab",
    "W7-OPTICAL-PATHS-2-MONO.dcm": "69938ca89b7f54343336abcce461a615877f4d375a13de38b8aef8c9eb68a919",
    "W7-EDF-5P.dcm": "26cd4e6e0fc2ab0e7ebd19a71d6b97f79e3633f51eab94fc1ef1761f4e9b6fba",
    "W7-3D-ORGANIZATION-3P.dcm": "85b5d8c322285317db5037f1bc2975f914776f7ac9eb736d1dab126196d48caa",
    "W7-CONCATENATION-2X4F/part-1.dcm": "18b5ef567c69cc0742551e6ca9bf1e7235f6deca947800d9abae2f35516f04b5",
    "W7-CONCATENATION-2X4F/part-2.dcm": "17ff70d1627f06bd19f16fa37a1091b22919628c1c8099abc728ae116c3ac8da",
    "W7-TS-RLE-RGB.dcm": "b3a5eb1d994d349640124a9a764c1212bac6484ec3a1bb73ceb29ffc0760a9f4",
    "W7-TS-JPEG-LOSSLESS-P14-SV6.dcm": "e5773056a85f5b4b28be4a7225e6b2772849bb8f5db1e76abb4c689162a72c8c",
    "W7-TS-JPEG-LOSSLESS-SV1.dcm": "d6dd09b702a0d540985e29919f607229dfc71c0e93a57a1a0520be85db337a53",
    "W7-TS-JPEG-EXTENDED-MONO8.dcm": "a7b947e493e8da6dcc5b220ea0a64ab4fd318e18398300512983cd781363e486",
    "W7-TS-JPEG-BASELINE-YBR422.dcm": "5fc3427f87dd5462a89de2d79d7636505bced96afdef8b207dd37ba6e31926f2",
    "W7-TS-JPEG-LS-LOSSLESS-RGB.dcm": "50862ff2795737749b3eb5229a5de9052f1ab5e359bf082a681f7af047747e6a",
    "W7-TS-JPEG-LS-NEAR-RGB.dcm": "02b759c4b2315081ad92579106a237695491bd4d733a3ba6486f4c56b040ef8d",
    "W7-TS-ENCAPSULATED-UNCOMPRESSED.dcm": "bf8d891065072e7e3a30a143910795556638a43533029f475b5af5476b4ce81d",
    "W7-TS-DEFLATED-EVRLE.dcm": "e6db657f88666cda2c3d7b74d789484812e0c97546e5b0b449e95e7d26879ea1",
    "W7-TS-DEFLATED-IMAGE-FRAME.dcm": "bb42e65f58c1463c7ab722136931a36ac452b93bc819f7d40415de66b5b20f07",
    "W7-TS-HTJ2K-RPCL-128.dcm": "4c4d1077ac9d6938902b3def4cfb4bc073bfad1a2b27b0aedade32aac50ebd89",
    "W7-TS-JXL-LOSSLESS-RGB.dcm": "aa09fe70b4e3dc8a1bc0ba2480d5aae8966b0151a8d192e0d667196eaee33b8b",
    "W7-TS-JXL-JPEG-RECOMPRESSION.dcm": "ada83a501a08f8633e8ae284eb3eb2a3835d34ca6df087729dfe4f59f950b159",
    "W7-TS-JXL-LOSSY-MONO8.dcm": "7a042c786677a6154b1702ed1ccebff59f2d667a63adc62598b1ce25ac109eae",
    "W7-TS-J2K-PART1-RCT.dcm": "1ce01dcfbd5e93379a130ffa2d9ed89487863131475f6a99af8dee0ae2f60d09",
    "W7-TS-J2K-PART1-ICT.dcm": "45cad9f2c850786db98fac3a1c5968868fed3bf98d286140d9030e07cbc476be",
    "W7-TS-J2K-PART2-ICT.dcm": "b33bace47ace8373db64a24a2e22b4660b48599f36d2e954714be74316002850",
    "W7-MONO8-FLUO-PALETTE.dcm": "377e3a87a380bc7cdfa11f862e1438634bcdff4dfae5b0cf751910105a159d1c",
    "W7-MONO16-FLUO.dcm": "48c08f2fb361adee76d553d4beefbdf55bd1a4fba6fb7317b01874d25cd592ec",
    "W7-RGB16-EVRLE.dcm": "a1454c7df87a8c844c4ed387877b479c29f021533e30e5af37ef702120736e76",
    "W7-SIGNED-DATASET.dcm": "510926c923ed89796f9d4b3721930bf008193c52d73385681c5a745f89145591",
    "W7-SIGNED-TAGLIST-PIXELDATA.dcm": "8e43c2c5a493eb2ddb13944fa11a71912641d6c30eb9ae82e6d0fb8276799925",
    "W7-SIGNED-SEQUENCE-ITEM.dcm": "b64ce59b6534fc872360de1067f911b3f1c21d1e7d446d12883b2b4b96d5b872",
    "W7-SIGNED-CERTIFIED-TIMESTAMP.dcm": "aebfa800f63345d975f59f7b65292c65ec0d1f78191ab358c5e3f01bfccaa75d",
}

# Configurations 2026d allows that no control covers, with the exact blocker.
NOT_BUILT = {
    J2K_PART2_LOSSLESS: "JPEG 2000 Part 2 Lossless (and so YBR_RCT under Part 2) needs a reversible "
    "Annex J multiple component transformation (an array-based dependency transform or the "
    "reversible wavelet-based transform). libopenjp2 2.5.4 encodes only an irreversible float "
    "array-based decorrelation (opj_set_MCT sets the MCC irreversible flag and the 9-7 wavelet), "
    "opj_compress 2.5.4 rejects -m (\"Invalid option m\"), grk_compress 20.3 aborts on -m (\"Custom "
    "MCT has been set but no array-based MCT has been provided\"), and no Part 2 decoder is "
    "available to check a hand-made codestream (opj_decompress and grk_decompress both reject "
    "SGcod MCT 2).",
    "1.2.840.10008.1.2.2": "Explicit VR Big Endian was retired in 2006; PS3.5 2026d A.3 keeps only "
    "its title and refers to PS3.5 2016b, so 2026d does not define it for new objects.",
}

# Signed with an ephemeral key at a real time: verified by signature, not by bytes.
NOT_REPRODUCIBLE: frozenset[str] = frozenset(
    {"W7-SIGNED-DATASET", "W7-SIGNED-TAGLIST-PIXELDATA", "W7-SIGNED-SEQUENCE-ITEM",
     "W7-SIGNED-CERTIFIED-TIMESTAMP"}
)

CONTROLS: tuple[dict, ...] = tuple(
    {
        "id": control_id,
        "paths": tuple(sorted(r for r in SHA256 if r.split("/")[0].removesuffix(".dcm") == control_id)),
        "iod": "VL Whole Slide Microscopy Image (1.2.840.10008.5.1.4.1.1.77.1.6)",
        **_EXERCISES[control_id],
        "built_by": f"{BUILDERS[control_id].__name__}: {BUILDERS[control_id].__doc__.split(chr(10))[0]}",
        "reproducible": control_id not in NOT_REPRODUCIBLE,
        "sha256": {r: SHA256[r] for r in SHA256 if r.split("/")[0].removesuffix(".dcm") == control_id},
    }
    for control_id in BUILDERS
)


if __name__ == "__main__":
    raise SystemExit(main())
