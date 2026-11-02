"""Build the v7 replacements for legacy mutation sources with wrong slide offsets.

The v4 files remain unchanged.  These copies preserve their identities and every
attribute except X/Y Offset in Slide Coordinate System, which is recomputed from
the matrix origin, orientation, Pixel Spacing, and each Frame's row/column position.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

import pydicom

from wsi_dicom_bench.negative_bench.controls_v7_wsi import slide_offset


PACKAGE = Path(__file__).resolve().parent
SOURCE_DIR = PACKAGE / "controls-v4"
CONTROLS_DIR = PACKAGE / "controls-v7" / "mutation-sources"

SOURCES = {
    "CP01-EVRLE-4F-ANISO": ("CP01-EVRLE-4F-ANISO.dcm",),
    "CP11-MONO-EVRLE-4F": ("CP11-MONO-EVRLE-4F.dcm",),
    "CP12-PYRAMID-2L": ("CP12-PYRAMID-2L/level-0.dcm", "CP12-PYRAMID-2L/level-1.dcm"),
    "CP14-MONO16-EVRLE": ("CP14-MONO16-EVRLE.dcm",),
}

SHA256 = {
    "CP01-EVRLE-4F-ANISO.dcm":
        "4155b3b5e42b8e474c81ad7a295340c084908a1a6785b9a07a08a5c3e69fa993",
    "CP11-MONO-EVRLE-4F.dcm":
        "77cf14e1e3648e6a008b15fc9638ce0c4b4bd4eb9b77963ab8ce72f391abfba9",
    "CP12-PYRAMID-2L/level-0.dcm":
        "027ae7cfb897542d431c387313a037063a26eee3f4fc558aed563876697bd904",
    "CP12-PYRAMID-2L/level-1.dcm":
        "5b7ae5d4613196d008f629d74595147b98ee193951e2d0e9df9ea8d8425cd0a4",
    "CP14-MONO16-EVRLE.dcm":
        "bf16ddf0d1c26035bf6157d3063bbde8e248d512635a4fcc17978f5f075e127a",
}


def _correct_offsets(dataset) -> int:
    origin = dataset.TotalPixelMatrixOriginSequence[0]
    origin_xy = (
        float(origin.XOffsetInSlideCoordinateSystem),
        float(origin.YOffsetInSlideCoordinateSystem),
    )
    orientation = [float(value) for value in dataset.ImageOrientationSlide]
    spacing = [
        float(value)
        for value in dataset.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0].PixelSpacing
    ]
    changed = 0
    for group in dataset.PerFrameFunctionalGroupsSequence:
        position = group.PlanePositionSlideSequence[0]
        x, y = slide_offset(
            origin_xy,
            orientation,
            spacing,
            int(position.RowPositionInTotalImagePixelMatrix),
            int(position.ColumnPositionInTotalImagePixelMatrix),
        )
        for keyword, expected in (
            ("XOffsetInSlideCoordinateSystem", x),
            ("YOffsetInSlideCoordinateSystem", y),
        ):
            if abs(float(getattr(position, keyword)) - expected) > 1e-12:
                setattr(position, keyword, f"{expected:.12g}")
                changed += 1
    return changed


def build(output: Path) -> dict[str, str]:
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    digests = {}
    with tempfile.TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent) as temporary:
        staging = Path(temporary)
        for paths in SOURCES.values():
            for relative in paths:
                source = SOURCE_DIR / relative
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                dataset = pydicom.dcmread(source)
                _correct_offsets(dataset)
                dataset.save_as(destination, enforce_file_format=True)
                digests[relative] = hashlib.sha256(destination.read_bytes()).hexdigest()
        shutil.move(staging, output)
    return digests


def verify(directory: Path = CONTROLS_DIR) -> list[str]:
    problems = []
    expected_paths = {path for paths in SOURCES.values() for path in paths}
    if set(SHA256) != expected_paths:
        problems.append("SHA256 registry does not name every corrected mutation source")
    for relative, expected in SHA256.items():
        path = directory / relative
        if not path.is_file():
            problems.append(f"missing {relative}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            problems.append(f"digest differs for {relative}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("output", type=Path, nargs="?")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            if args.output is None:
                raise ValueError("build needs an output directory")
            for path, digest in sorted(build(args.output).items()):
                print(f"{digest}  {path}")
        else:
            problems = verify(args.output or CONTROLS_DIR)
            if problems:
                raise ValueError("; ".join(problems))
    except (OSError, ValueError) as error:
        print(f"mutation-source {args.command} failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
