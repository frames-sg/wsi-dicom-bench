"""Apply the v7 pre-freeze completeness gate without weakening catalog scope."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from wsi_dicom_bench.file_digest import sha256_file

from .build_v7 import CATALOG, COVERAGE, MANIFEST, REQUIREMENTS, load_requirements


PACKAGE = Path(__file__).resolve().parent
PROTOCOL = PACKAGE / "protocol-v7.md"
FINAL_MANIFEST = PACKAGE / "manifest-v7.json"
LOCK = PACKAGE / "expected-results-lock-v7.json"


class FreezeGateError(RuntimeError):
    """The v7 draft is not eligible for a locked challenge package."""


def assess_readiness() -> dict:
    requirements = load_requirements(REQUIREMENTS)
    coverage = json.loads(COVERAGE.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    unchecked = []
    for entry in requirements["requirements"]:
        for iod in entry["iods"]:
            disposition = entry.get("iod_dispositions", {}).get(iod, entry["disposition"])
            if disposition.get("kind") == "unchecked":
                unchecked.append({
                    "id": entry.get("id"), "iod": iod, "family": disposition["detail"],
                })
    blockers = []
    for field in (
        "uncovered_file_object_statements",
        "dicom_json_statements_requiring_json_cases",
        "dicomweb_statements_requiring_http_cases",
    ):
        if coverage.get(field) != 0:
            blockers.append({"field": field, "count": coverage.get(field)})
    policy_gaps = []
    if unchecked:
        policy_gaps.append({
            "field": "unchecked_statement_scope_pairs",
            "count": len(unchecked),
            "ids": sorted({item["id"] for item in unchecked}),
            "families": sorted({item["family"] for item in unchecked}),
        })
    recorded = manifest.get("freeze_gate", {})
    if recorded.get("unchecked_statement_scope_pairs") != len(unchecked):
        raise FreezeGateError("manifest freeze gate differs from the requirement snapshot")
    return {
        "schema_version": "wsi-dicom-negative-bench-v7-freeze-readiness-v1",
        "status": "blocked" if blockers else (
            "ready_with_known_policy_failure" if policy_gaps else "ready"
        ),
        "blockers": blockers,
        "policy_gaps": policy_gaps,
        "unchecked": unchecked,
        "draft_manifest": MANIFEST.name,
    }


def build_frozen_manifest() -> dict:
    readiness = assess_readiness()
    if readiness["blockers"]:
        raise FreezeGateError(f"v7 freeze has infrastructure blockers: {readiness['blockers']}")
    draft = json.loads(MANIFEST.read_text(encoding="utf-8"))
    frozen = copy.deepcopy(draft)
    frozen.update({
        "schema_version": "wsi-dicom-negative-bench-manifest-v7",
        "challenge_id": "wsi-dicom-negative-bench-v7",
        "title": "WSI-DICOM Negative Bench v7: pathology DICOM 2026d",
        "status": "frozen_with_known_policy_failure",
        "protocol": PROTOCOL.name,
        "expected_results_lock": LOCK.name,
        "freeze_gate": {
            "status": readiness["status"],
            "unchecked_statement_scope_pairs": len(readiness["unchecked"]),
            "unchecked_statement_ids": sorted({item["id"] for item in readiness["unchecked"]}),
            "known_policy_failure": bool(readiness["policy_gaps"]),
        },
    })
    return frozen


def build_lock(manifest_path: Path = FINAL_MANIFEST) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = (PROTOCOL, manifest_path, CATALOG, REQUIREMENTS, COVERAGE)
    package_paths = (
        f"bench/negative_bench/{PROTOCOL.name}",
        f"bench/negative_bench/{manifest_path.name}",
        f"rules/{CATALOG.name}",
        f"rules/{REQUIREMENTS.name}",
        f"bench/negative_bench/{COVERAGE.name}",
    )
    return {
        "schema_version": "wsi-dicom-negative-bench-expected-results-lock-v7",
        "challenge_id": manifest["challenge_id"],
        "locked_at_date": "2026-10-24",
        "lock_state": "frozen_checked_coverage_with_known_policy_failure",
        "files": [
            {"path": relative, "sha256": sha256_file(path)}
            for relative, path in zip(package_paths, paths, strict=True)
        ],
        "expected_counts": {
            field: len(manifest.get(field, []))
            for field in (
                "valid_controls", "evaluation_cases", "core_profile_evaluation_cases",
                "advisory_cases", "json_evaluation_cases", "http_evaluation_cases",
            )
        },
        "known_policy_failure": manifest["freeze_gate"],
    }


def write_frozen() -> None:
    FINAL_MANIFEST.write_text(
        json.dumps(build_frozen_manifest(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    LOCK.write_text(json.dumps(build_lock(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = assess_readiness()
        if args.write:
            write_frozen()
    except (FreezeGateError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"v7 freeze readiness failed: {error}", file=sys.stderr)
        return 2
    rendered = json.dumps(result, indent=2, sort_keys=True) if args.json else (
        f"v7 freeze {result['status']}: "
        f"{sum(item['count'] for item in result['blockers'])} blocking item(s)"
    )
    print(rendered)
    return 2 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
