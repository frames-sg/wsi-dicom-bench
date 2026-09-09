"""Refresh control provenance from the current authored challenge specification.

The locked manifest owns case definitions. This builder updates inventory in a new
output without changing expectations or overwriting the source lock.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pydicom
from wsi_dicom_bench.negative_bench.identifiers import manifest_identifier_items


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _control_record(control_id: str, path: Path, original_path: str) -> dict:
    dataset = pydicom.dcmread(path, stop_before_pixels=True)
    return {
        "cohort": "core-profile-controls-v1",
        "control_id": control_id,
        "expected_outcome": {
            "configured_independent_validators": "passed",
            "wsi_dicom_bench": "passed",
        },
        "number_of_frames": int(dataset.NumberOfFrames),
        "original_path": original_path,
        "package_path": f"controls/{control_id}.dcm",
        "series_instance_uid": str(dataset.SeriesInstanceUID),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
        "sop_class_uid": str(dataset.SOPClassUID),
        "sop_instance_uid": str(dataset.SOPInstanceUID),
        "source_kind": "repository_generated_synthetic_no_patient_data",
        "study_instance_uid": str(dataset.StudyInstanceUID),
        "transfer_syntax_uid": str(dataset.file_meta.TransferSyntaxUID),
    }

def _multifile_control_record(control_id: str, paths: list[Path], original_paths: list[str]) -> dict:
    datasets = [pydicom.dcmread(path, stop_before_pixels=True) for path in paths]
    return {
        "cohort": "core-profile-controls-v1",
        "control_id": control_id,
        "expected_outcome": {
            "configured_independent_validators": "passed",
            "wsi_dicom_bench": "passed",
        },
        "object_count": len(paths),
        "original_paths": original_paths,
        "package_paths": [f"controls/{control_id}/{path.name}" for path in paths],
        "series_instance_uid": str(datasets[0].SeriesInstanceUID),
        "sha256": [_sha256(path) for path in paths],
        "size_bytes": [path.stat().st_size for path in paths],
        "sop_class_uid": str(datasets[0].SOPClassUID),
        "sop_instance_uids": [str(dataset.SOPInstanceUID) for dataset in datasets],
        "source_kind": "repository_generated_synthetic_no_patient_data",
        "study_instance_uid": str(datasets[0].StudyInstanceUID),
        "transfer_syntax_uids": sorted(
            {str(dataset.file_meta.TransferSyntaxUID) for dataset in datasets}
        ),
    }


def build_manifest(source_manifest: Path, controls_root: Path, output: Path) -> dict:
    source_manifest = source_manifest.resolve()
    controls_root = controls_root.resolve()
    output = output.resolve()
    if output.exists():
        raise RuntimeError(f"output already exists: {output}")
    manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    controls, cases = manifest_identifier_items(manifest)
    if manifest.get("schema_version") != "wsi-dicom-negative-bench-manifest-v4":
        raise ValueError("inventory rebuild requires the current challenge specification")
    refreshed = []
    for control in controls:
        identifier = control["control_id"]
        if "package_paths" in control:
            paths = [controls_root / identifier / Path(path).name for path in control["package_paths"]]
            refreshed.append(
                _multifile_control_record(identifier, paths, control["original_paths"])
            )
        else:
            refreshed.append(
                _control_record(
                    identifier,
                    controls_root / f"{identifier}.dcm",
                    control["original_path"],
                )
            )
    controls_by_id = {control["control_id"]: control for control in refreshed}
    for case in cases:
        case["source_control_sha256"] = controls_by_id[case["source_control_ids"][0]]["sha256"]
    manifest["valid_controls"] = refreshed
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, default=Path(__file__).with_name("manifest-v4.json"))
    parser.add_argument("--controls", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build_manifest(args.source_manifest, args.controls, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
