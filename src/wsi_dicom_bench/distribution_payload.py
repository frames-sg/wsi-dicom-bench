"""Retain the exact wheel backing an installed benchmark distribution."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import shutil
import tempfile
import zipfile
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from urllib.parse import unquote, urlparse

from .file_digest import sha256_file


class DistributionPayloadError(RuntimeError):
    """An installed distribution cannot supply a trustworthy wheel payload."""


def _direct_wheel(document: dict) -> tuple[Path, str]:
    parsed = urlparse(document.get("url", ""))
    if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
        raise DistributionPayloadError(
            "installed wsi-dicom-bench does not reference a local wheel"
        )
    wheel = Path(unquote(parsed.path))
    if wheel.suffix != ".whl" or not wheel.is_file():
        raise DistributionPayloadError(
            "installed wsi-dicom-bench local wheel is missing or invalid"
        )
    archive = document.get("archive_info")
    if not isinstance(archive, dict):
        raise DistributionPayloadError("installed wheel lacks PEP 610 archive metadata")
    expected = archive.get("hashes", {}).get("sha256")
    if expected is None and isinstance(archive.get("hash"), str):
        algorithm, separator, value = archive["hash"].partition("=")
        expected = value if separator and algorithm == "sha256" else None
    if not isinstance(expected, str) or len(expected) != 64:
        raise DistributionPayloadError("installed wheel lacks a SHA-256 identity")
    actual = sha256_file(wheel)
    if actual != expected:
        raise DistributionPayloadError("installed wheel SHA-256 does not match direct_url.json")
    return wheel, actual


def retain_installed_distribution(output_dir: Path) -> dict:
    """Copy the verified installed benchmark wheel into a new payload directory."""
    try:
        return _retain_installed_distribution(output_dir)
    except DistributionPayloadError:
        raise
    except (KeyError, OSError, PackageNotFoundError, TypeError) as exc:
        raise DistributionPayloadError(
            f"cannot retain installed wsi-dicom-bench distribution: {exc}"
        ) from exc


def _retain_installed_distribution(output_dir: Path) -> dict:
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise DistributionPayloadError(f"distribution payload already exists: {output_dir}")
    installed = distribution("wsi-dicom-bench")
    try:
        direct_url = json.loads(installed.read_text("direct_url.json") or "")
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise DistributionPayloadError(
            "installed wsi-dicom-bench lacks valid direct_url.json"
        ) from exc
    if not isinstance(direct_url, dict):
        raise DistributionPayloadError("installed direct_url.json must be an object")
    wheel, wheel_sha256 = _direct_wheel(direct_url)
    record_entry = next(
        (entry for entry in installed.files or () if str(entry).endswith(".dist-info/RECORD")),
        None,
    )
    if record_entry is None:
        raise DistributionPayloadError("installed wsi-dicom-bench lacks RECORD")
    with zipfile.ZipFile(wheel) as archive:
        wheel_record = archive.read(str(record_entry))
    with io.StringIO(wheel_record.decode("utf-8"), newline="") as stream:
        for relative, encoded_digest, _size in csv.reader(stream):
            if not encoded_digest:
                continue
            algorithm, separator, value = encoded_digest.partition("=")
            if algorithm != "sha256" or not separator:
                raise DistributionPayloadError("installed RECORD uses an unsupported digest")
            installed_file = Path(installed.locate_file(Path(relative)))
            actual = bytes.fromhex(sha256_file(installed_file))
            expected = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
            if actual != expected:
                raise DistributionPayloadError(
                    f"installed distribution differs from RECORD: {relative}"
                )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{output_dir.name}.staging-", dir=output_dir.parent
    ) as temporary:
        staging = Path(temporary)
        retained = staging / wheel.name
        shutil.copyfile(wheel, retained)
        if sha256_file(retained) != wheel_sha256:
            raise DistributionPayloadError("retained benchmark wheel SHA-256 differs")
        os.replace(staging, output_dir)
    return {
        "schema_version": "wsi-dicom-bench-distribution-payload-v1",
        "name": installed.metadata["Name"],
        "version": installed.version,
        "requires": list(installed.requires or ()),
        "record_sha256": hashlib.sha256(wheel_record).hexdigest(),
        "wheel": {"path": wheel.name, "sha256": wheel_sha256},
    }
