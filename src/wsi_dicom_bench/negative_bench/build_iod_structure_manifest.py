"""Build the v5 amendment manifest from the frozen v4 specification.

The v4 manifest, controls, and expectations are read and never written. Every v4
evaluation, development, and control entry is carried forward with the same mutation.
Each failure of a v5 IOD requirement rule that the frozen candidate produced on a
carried-forward case was checked against the DICOM 2026c text and is recorded (in iod_amendment_cases) as
either an expected failing rule (the rule reports the mutated Attribute, or the
inconsistency that the case defines) or an adjudicated cascade (the rule reports an
unchanged Attribute or Module whose conditional requirement the mutation changed).

The IOD structure cohort adds single-defect cases. Their expected rules are the rules
that report the authored defect: the targeted IOD rule, plus a catalog-v4 rule where
that rule independently reports the same defect. These expectations were set by running
the frozen candidate and adjudicating each result against the standard; they are not
blinded.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from wsi_dicom_bench.core_profile import intrinsic_rule_ids
from wsi_dicom_bench.file_digest import sha256_file
from wsi_dicom_bench.negative_bench.identifiers import manifest_identifier_items
from wsi_dicom_bench.negative_bench.iod_amendment_cases import (
    CARRIED_FORWARD,
    IOD_RULES,
    STRUCTURE_CASES,
    full_rule_id,
)


PACKAGE = Path(__file__).resolve().parent
RULES = PACKAGE.parent / "rules"
SOURCE_MANIFEST = PACKAGE / "manifest-v4.json"
MANIFEST = PACKAGE / "manifest-v5.json"
LOCK = PACKAGE / "expected-results-lock-v5.json"
PROTOCOL = PACKAGE / "protocol-v5.md"
CATALOG = RULES / "wsi-dicom-bench-rules-2026c-v5.json"
PROFILE = RULES / "wsi-dicom-core-profile-2026c-v3.json"

CHALLENGE_ID = "wsi-dicom-negative-bench-v5"
CREATED_DATE = "2026-10-22"
STRUCTURE_COHORT = "iod-structure-evaluation-v1"
STRUCTURE_SEED = "wsi-dicom-iod-structure-v1"
CANDIDATE = {
    "executable": "wsi-dicom-iod",
    "version": "wsi-dicom 0.9.0",
    "sha256": "e4c5561ae73cf5a79c8186f8b78dd9ef1753b074495c8f7fec16bf50092e2b25",
    "rule_set_ids": {
        "core-2026c": "wsi-dicom-core-profile-2026c-v3",
        "general": "wsi-dicom-general-v2",
    },
}
SEVERITY_ORDER = ("none", "minor", "major", "critical")


def _severity(by_id: dict, rule_ids: list[str], field: str) -> str:
    """The most severe ``field`` among ``rule_ids``, looked up in the catalog index ``by_id``."""
    return max((by_id[rule][field] for rule in rule_ids), key=SEVERITY_ORDER.index)


def _carry_forward(case: dict, intrinsic: set[str]) -> dict:
    entry = copy.deepcopy(case)
    adjudications = CARRIED_FORWARD.get(case["case_id"], [])
    added = [item["rule_id"] for item in adjudications if item["disposition"] == "expected_failing_rule"]
    cascades = [item["rule_id"] for item in adjudications if item["disposition"] == "adjudicated_cascade"]
    entry["expected_failing_rules"] = [*case["expected_failing_rules"], *added]
    all_cascades = [*case.get("adjudicated_cascade_rules", []), *cascades]
    if all_cascades:
        entry["adjudicated_cascade_rules"] = all_cascades
    excluded = set(entry["expected_failing_rules"]) | set(all_cascades)
    entry["expected_unaffected_rules"] = sorted(intrinsic - excluded)
    entry["iod_rule_adjudications"] = adjudications
    return entry


def _structure_case(spec: dict, controls: dict, by_id: dict, intrinsic: set[str]) -> dict:
    expected = [full_rule_id(short) for short in spec["expected"]]
    control = controls[spec["control"]]
    return {
        "adjudication_rationale": spec["rationale"],
        "case_id": spec["case_id"],
        "clinical_severity": _severity(by_id, expected, "clinical_severity"),
        "cohort": STRUCTURE_COHORT,
        "deterministic_seed": f"{STRUCTURE_SEED}:{spec['case_id']}",
        "dicom_citation": spec["citation"],
        "domain": "conformance",
        "exact_attributes_or_bytes_changed": spec["changed"],
        "expected_failing_rules": expected,
        "expected_outcome": {
            "domain_localized": True,
            "rule_localized": True,
            "wsi_dicom_bench": "failed",
        },
        "expected_unaffected_rules": sorted(intrinsic - set(expected)),
        "likely_fix_owner": "converter",
        "mutation_name": spec["mutation_name"],
        "mutation_parameters": spec["mutation_parameters"],
        "operational_severity": _severity(by_id, expected, "operational_severity"),
        "source_control_ids": [spec["control"]],
        "source_control_sha256": control["sha256"],
        "target_rule_family": expected[0],
    }


def build_manifest(source: Path = SOURCE_MANIFEST, catalog_path: Path = CATALOG) -> dict:
    """Return manifest v5 built from the frozen v4 specification."""
    v4 = json.loads(source.read_text(encoding="utf-8"))
    if v4.get("schema_version") != "wsi-dicom-negative-bench-manifest-v4":
        raise ValueError("the v5 amendment is built from the frozen v4 specification")
    controls, cases = manifest_identifier_items(v4)
    unknown = sorted(set(CARRIED_FORWARD) - {case["case_id"] for case in cases})
    if unknown:
        raise ValueError(f"adjudications name unknown v4 cases: {unknown}")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    by_id = {rule["rule_id"]: rule for rule in catalog["rules"]}
    intrinsic = intrinsic_rule_ids(catalog["rules"])
    by_control = {control["control_id"]: control for control in controls}
    structure = [_structure_case(spec, by_control, by_id, intrinsic) for spec in STRUCTURE_CASES]
    if any("package_paths" in by_control[case["source_control_ids"][0]] for case in structure):
        raise ValueError("IOD structure cases must use single-file controls")
    manifest = copy.deepcopy(v4)
    manifest.update(
        {
            "authorship": {
                **v4["authorship"],
                "iod_structure_expectations": (
                    "set by running the frozen candidate and adjudicating each result "
                    "against DICOM 2026c; not blinded"
                ),
            },
            "challenge_id": CHALLENGE_ID,
            "cohorts": {**v4["cohorts"], "iod_structure": STRUCTURE_COHORT},
            "core_profile": {
                "path": f"rules/{PROFILE.name}",
                "profile_id": "wsi-dicom-core-profile-2026c-v3",
            },
            "created_date": CREATED_DATE,
            "evaluation_cases": [*(_carry_forward(case, intrinsic) for case in cases), *structure],
            "expectation_provenance": {
                "blinded": False,
                "carried_forward_cases": (
                    "v4 mutations and expected rules unchanged; candidate IOD-rule failures "
                    "adjudicated in iod_rule_adjudications"
                ),
                "candidate": CANDIDATE,
                "method": (
                    "Each case was generated and run through the frozen candidate; every "
                    "failing rule was checked against the cited DICOM 2026c text before it "
                    "was recorded as expected or as an adjudicated cascade."
                ),
            },
            "expected_results_lock": LOCK.name,
            "protocol": PROTOCOL.name,
            "resource_limits": {**v4["resource_limits"], "max_cases": 160},
            "rule_catalog": {
                "catalog_version": catalog["catalog_version"],
                "path": f"rules/{CATALOG.name}",
                "required_new_rule_ids": list(IOD_RULES),
            },
            "schema_version": "wsi-dicom-negative-bench-manifest-v5",
            "state": "expected-results-locked-after-candidate-adjudication-before-final-evaluation",
            "title": "WSI-DICOM Core Profile and IOD Negative Bench v5",
        }
    )
    manifest_identifier_items(manifest)
    return manifest


def build_lock(
    manifest_path: Path = MANIFEST,
    profile_path: Path = PROFILE,
    *,
    schema_version: str = "wsi-dicom-negative-bench-expected-results-lock-v5",
    locked_at_date: str = CREATED_DATE,
    protocol: Path = PROTOCOL,
    manifest: Path = MANIFEST,
    catalog: Path = CATALOG,
    profile: Path = PROFILE,
) -> dict:
    """Return the expected-results lock binding protocol, manifest, catalog, and profile.

    ``manifest_path`` and ``profile_path`` are the files read and digested; ``protocol``,
    ``manifest``, ``catalog`` and ``profile`` are the package files the lock names. The
    defaults are the v5 files; later amendments pass their own.
    """
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    profile_document = json.loads(profile_path.read_text(encoding="utf-8"))
    profile_digest = sha256_file(profile_path)
    return {
        "schema_version": schema_version,
        "challenge_id": document["challenge_id"],
        "locked_at_date": locked_at_date,
        "lock_state": "frozen_after_candidate_adjudication_before_final_evaluation",
        "core_profile": {
            "profile_id": profile_document["profile_id"],
            "version": profile_document["profile_version"],
            "sha256": profile_digest,
        },
        "files": [
            {"path": f"bench/negative_bench/{protocol.name}", "sha256": sha256_file(protocol)},
            {"path": f"bench/negative_bench/{manifest.name}", "sha256": sha256_file(manifest_path)},
            {"path": f"rules/{catalog.name}", "sha256": sha256_file(catalog)},
            {"path": f"rules/{profile.name}", "sha256": profile_digest},
        ],
        "expected_counts": {
            "development_cases": len(document.get("development_cases", [])),
            "evaluation_cases": len(document["evaluation_cases"]),
            "valid_controls": len(document["valid_controls"]),
            "compound_cases": len(document.get("compound_cases", [])),
        },
    }


def _render(document: dict, sort_keys: bool) -> str:
    return json.dumps(document, indent=2, sort_keys=sort_keys, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="rewrite manifest-v5 and its lock")
    args = parser.parse_args(argv)
    manifest_text = _render(build_manifest(), sort_keys=True)
    if args.write:
        MANIFEST.write_text(manifest_text, encoding="utf-8")
        LOCK.write_text(_render(build_lock(), sort_keys=False), encoding="utf-8")
        return 0
    stale = None
    if not MANIFEST.is_file() or MANIFEST.read_text(encoding="utf-8") != manifest_text:
        stale = MANIFEST.name
    elif not LOCK.is_file() or LOCK.read_text(encoding="utf-8") != _render(build_lock(), sort_keys=False):
        stale = LOCK.name
    if stale:
        print(f"out of date: {stale}; rerun with --write", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
