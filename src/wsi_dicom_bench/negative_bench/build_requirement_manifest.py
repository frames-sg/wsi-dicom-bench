"""Build the v6 requirement-statement manifest from the frozen v5 specification.

The v5 manifest, controls-v4, and core profile v3 are read and never written. Every v5
evaluation, development, and control entry is carried forward with the same mutation. Two
controls are replaced by their controls-v6 corrections (Photometric Interpretation YBR_ICT
for the irreversible ICT their Frames apply), and the cases built on them are rebased onto
the corrected files. Each failure of a v6 rule that the frozen candidate produced on a
carried-forward case was checked against the DICOM 2026c text and is recorded (in
requirement_cases.CARRIED_FORWARD_V6) as an expected failing rule or an adjudicated cascade;
a v5 expected rule whose requirement a v6 rule now enforces is recorded as superseded,
with its replacement.

The requirement-statement cohort adds single-defect cases. Their expected rules are the
rules that report the authored defect: the targeted v6 rule, plus any other catalog rule
that independently reports the same defect. These expectations were set by running the
frozen candidate and adjudicating each result against the standard; they are not blinded.
Core profile v4 is profile v3 plus one row per v6 rule, mapped to the cohort's cases.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

import pydicom

from wsi_dicom_bench.core_profile import intrinsic_rule_ids
from wsi_dicom_bench.file_digest import sha256_file
from wsi_dicom_bench.negative_bench.build_core_profile_controls import ICT_CONTROLS
from wsi_dicom_bench.negative_bench.build_iod_structure_manifest import _render, _severity
from wsi_dicom_bench.negative_bench.build_iod_structure_manifest import build_lock as _build_lock
from wsi_dicom_bench.negative_bench.iod_amendment_cases import full_rule_id
from wsi_dicom_bench.negative_bench.identifiers import manifest_identifier_items
from wsi_dicom_bench.negative_bench.requirement_cases import (
    CARRIED_FORWARD_V6,
    PROFILE_POSITIVE_CONTROLS,
    PROFILE_REMAPS,
    PROFILE_ROWS,
    REQUIREMENT_CASES,
)


PACKAGE = Path(__file__).resolve().parent
RULES = PACKAGE.parent / "rules"
SOURCE_MANIFEST = PACKAGE / "manifest-v5.json"
CONTROLS_V6 = PACKAGE / "controls-v6"
MANIFEST = PACKAGE / "manifest-v6.json"
LOCK = PACKAGE / "expected-results-lock-v6.json"
PROTOCOL = PACKAGE / "protocol-v6.md"
SOURCE_CATALOG = RULES / "wsi-dicom-bench-rules-2026c-v5.json"
CATALOG = RULES / "wsi-dicom-bench-rules-2026c-v6.json"
SOURCE_PROFILE = RULES / "wsi-dicom-core-profile-2026c-v3.json"
PROFILE = RULES / "wsi-dicom-core-profile-2026c-v4.json"

CHALLENGE_ID = "wsi-dicom-negative-bench-v6"
CREATED_DATE = "2026-10-23"
COHORT = "requirement-statement-evaluation-v1"
SEED = "wsi-dicom-requirement-statements-v1"
PROFILE_ID = "wsi-dicom-core-profile-2026c-v4"
CANDIDATE = {
    "executable": "wsi-dicom",
    "version": "wsi-dicom 0.9.0",
    "sha256": "e9efedc70aec4d4d15f91e799ea96c9b3fa3e76b21a929f2a3cee65ce4c9b774",
    "rule_set_ids": {
        "core-2026c": PROFILE_ID,
        "general": "wsi-dicom-general-v3",
    },
}
CORRECTION = (
    "Photometric Interpretation YBR_RCT corrected to YBR_ICT, the irreversible multiple "
    "component transformation its Frames apply (PS3.5 2026c 8.2.4 and 8.2.14); new SOP "
    "Instance UID, Frames unchanged"
)


def _new_rule_ids(catalog: dict) -> list[str]:
    known = {rule["rule_id"] for rule in json.loads(SOURCE_CATALOG.read_text(encoding="utf-8"))["rules"]}
    return [rule["rule_id"] for rule in catalog["rules"] if rule["rule_id"] not in known]


def _corrected_control(control: dict) -> dict:
    path = CONTROLS_V6 / f"{control['control_id']}.dcm"
    dataset = pydicom.dcmread(path, stop_before_pixels=True)
    return {
        **control,
        "correction": CORRECTION,
        "original_path": f"bench/negative_bench/controls-v6/{path.name}",
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "sop_instance_uid": str(dataset.SOPInstanceUID),
    }


def _carry_forward(case: dict, intrinsic: set[str], rebased: dict[str, str]) -> dict:
    entry = copy.deepcopy(case)
    (source,) = entry["source_control_ids"]
    if source in rebased:
        entry["source_control_sha256"] = rebased[source]
    adjudications = CARRIED_FORWARD_V6.get(case["case_id"], [])
    by_disposition = {
        disposition: [item["rule_id"] for item in adjudications if item["disposition"] == disposition]
        for disposition in ("expected_failing_rule", "adjudicated_cascade", "superseded_expected_rule")
    }
    added, cascades = by_disposition["expected_failing_rule"], by_disposition["adjudicated_cascade"]
    superseded = by_disposition["superseded_expected_rule"]
    if not set(superseded) <= set(case["expected_failing_rules"]):
        raise ValueError(f"{case['case_id']} supersedes a rule it did not expect: {superseded}")
    kept = [rule for rule in case["expected_failing_rules"] if rule not in superseded]
    entry["expected_failing_rules"] = [*kept, *added]
    all_cascades = [*case.get("adjudicated_cascade_rules", []), *cascades]
    if all_cascades:
        entry["adjudicated_cascade_rules"] = all_cascades
    excluded = set(entry["expected_failing_rules"]) | set(all_cascades)
    entry["expected_unaffected_rules"] = sorted(intrinsic - excluded)
    if adjudications:
        entry["requirement_rule_adjudications"] = adjudications
    return entry


def _requirement_case(spec: dict, controls: dict, by_id: dict, intrinsic: set[str]) -> dict:
    expected = [full_rule_id(short) for short in spec["expected"]]
    target = by_id[expected[0]]
    return {
        "adjudication_rationale": spec["rationale"],
        "case_id": spec["case_id"],
        "clinical_severity": _severity(by_id, expected, "clinical_severity"),
        "cohort": COHORT,
        "deterministic_seed": f"{SEED}:{spec['case_id']}",
        "dicom_citation": spec["citation"],
        "domain": target["primary_domain"],
        "exact_attributes_or_bytes_changed": spec["changed"],
        "expected_failing_rules": expected,
        "expected_outcome": {
            "domain_localized": True,
            "rule_localized": True,
            "wsi_dicom_bench": "failed",
        },
        "expected_unaffected_rules": sorted(intrinsic - set(expected)),
        "likely_fix_owner": target["likely_fix_owners"][0],
        "mutation_name": spec["mutation_name"],
        "mutation_parameters": spec["mutation_parameters"],
        "operational_severity": _severity(by_id, expected, "operational_severity"),
        "requirement_ids": spec["requirement_ids"],
        "source_control_ids": [spec["control"]],
        "source_control_sha256": controls[spec["control"]]["sha256"],
        "target_rule_family": expected[0],
    }


def build_manifest(source: Path = SOURCE_MANIFEST, catalog_path: Path = CATALOG) -> dict:
    """Return manifest v6 built from the frozen v5 specification."""
    v5 = json.loads(source.read_text(encoding="utf-8"))
    if v5.get("schema_version") != "wsi-dicom-negative-bench-manifest-v5":
        raise ValueError("the v6 amendment is built from the frozen v5 specification")
    controls, cases = manifest_identifier_items(v5)
    unknown = sorted(set(CARRIED_FORWARD_V6) - {case["case_id"] for case in cases})
    if unknown:
        raise ValueError(f"adjudications name unknown v5 cases: {unknown}")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    by_id = {rule["rule_id"]: rule for rule in catalog["rules"]}
    intrinsic = intrinsic_rule_ids(catalog["rules"])
    controls = [
        _corrected_control(control) if control["control_id"] in ICT_CONTROLS else control
        for control in controls
    ]
    by_control = {control["control_id"]: control for control in controls}
    rebased = {control_id: by_control[control_id]["sha256"] for control_id in ICT_CONTROLS}
    requirement = [_requirement_case(spec, by_control, by_id, intrinsic) for spec in REQUIREMENT_CASES]
    if any("package_paths" in by_control[case["source_control_ids"][0]] for case in requirement):
        raise ValueError("requirement-statement cases must use single-file controls")
    manifest = copy.deepcopy(v5)
    manifest.update(
        {
            "authorship": {
                **v5["authorship"],
                "requirement_statement_expectations": (
                    "set by running the frozen candidate and adjudicating each result "
                    "against DICOM 2026c; not blinded"
                ),
            },
            "challenge_id": CHALLENGE_ID,
            "cohorts": {**v5["cohorts"], "requirement_statements": COHORT},
            "control_generation": {
                **v5["control_generation"],
                "commands": [
                    *v5["control_generation"]["commands"],
                    ".venv-bench/bin/python bench/negative_bench/build_core_profile_controls.py "
                    "bench/negative_bench/controls-v4 bench/negative_bench/controls-v6 "
                    "--correct-lossy-photometric",
                ],
            },
            "core_profile": {"path": f"rules/{PROFILE.name}", "profile_id": PROFILE_ID},
            "created_date": CREATED_DATE,
            "evaluation_cases": [
                *(_carry_forward(case, intrinsic, rebased) for case in cases),
                *requirement,
            ],
            "expectation_provenance": {
                "blinded": False,
                "candidate": CANDIDATE,
                "carried_forward_cases": (
                    "v5 mutations and expected rules unchanged; cases on the corrected "
                    "controls rebased onto them; candidate v6-rule failures adjudicated in "
                    "requirement_rule_adjudications"
                ),
                "method": (
                    "Each case was generated and run through the frozen candidate; every "
                    "failing rule was checked against the cited DICOM 2026c text before it "
                    "was recorded as expected or as an adjudicated cascade."
                ),
            },
            "expected_results_lock": LOCK.name,
            "protocol": PROTOCOL.name,
            "resource_limits": {**v5["resource_limits"], "max_cases": 360},
            "rule_catalog": {
                "catalog_version": catalog["catalog_version"],
                "path": f"rules/{CATALOG.name}",
                "required_new_rule_ids": _new_rule_ids(catalog),
            },
            "schema_version": "wsi-dicom-negative-bench-manifest-v6",
            "state": "expected-results-locked-after-candidate-adjudication-before-final-evaluation",
            "title": "WSI-DICOM Core Profile, IOD and Requirement-Statement Negative Bench v6",
            "valid_controls": controls,
        }
    )
    manifest_identifier_items(manifest)
    return manifest


def build_profile(catalog_path: Path = CATALOG) -> dict:
    """Return core profile v4: profile v3, with its remapped rows, plus one row per v6 rule."""
    v3 = json.loads(SOURCE_PROFILE.read_text(encoding="utf-8"))
    catalog = {rule["rule_id"] for rule in json.loads(catalog_path.read_text(encoding="utf-8"))["rules"]}
    carried = copy.deepcopy(v3["requirements"])
    remapped = {row["requirement_id"] for row in carried} & set(PROFILE_REMAPS)
    if remapped != set(PROFILE_REMAPS):
        raise ValueError(f"profile remaps name unknown v3 rows: {sorted(set(PROFILE_REMAPS) - remapped)}")
    for row in carried:
        if row["requirement_id"] in PROFILE_REMAPS:
            row["enforcement"]["rule_ids"] = [full_rule_id(PROFILE_REMAPS[row["requirement_id"]])]
    rows = []
    for identifier, part, section, kind, statement, rule in PROFILE_ROWS:
        rule_id = full_rule_id(rule)
        if rule_id not in catalog:
            raise ValueError(f"profile row {identifier} names a rule outside catalog v6: {rule_id}")
        cases = [spec["case_id"] for spec in REQUIREMENT_CASES if rule in spec["expected"]]
        if not cases:
            raise ValueError(f"profile row {identifier} has no negative case")
        rows.append({
            "requirement_id": identifier,
            "part": part,
            "section": section,
            "requirement_type": kind,
            "applicability": "required",
            "statement": statement,
            "enforcement": {"rule_ids": [rule_id], "external_check_names": []},
            "positive_control_ids": list(PROFILE_POSITIVE_CONTROLS),
            "negative_case_ids": cases,
        })
    return {
        **v3,
        "profile_id": PROFILE_ID,
        "profile_version": "4",
        "title": "DICOM 2026c selected VL WSI rule-family, IOD and requirement-statement challenge profile",
        "requirements": [*carried, *rows],
    }


def build_lock(manifest_path: Path = MANIFEST, profile_path: Path = PROFILE) -> dict:
    """Return the expected-results lock binding protocol, manifest, catalog, and profile."""
    return _build_lock(
        manifest_path,
        profile_path,
        schema_version="wsi-dicom-negative-bench-expected-results-lock-v6",
        locked_at_date=CREATED_DATE,
        protocol=PROTOCOL,
        manifest=MANIFEST,
        catalog=CATALOG,
        profile=PROFILE,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="rewrite profile v4, manifest-v6 and its lock")
    args = parser.parse_args(argv)
    profile_text = _render(build_profile(), sort_keys=False)
    manifest_text = _render(build_manifest(), sort_keys=True)
    if args.write:
        PROFILE.write_text(profile_text, encoding="utf-8")
        MANIFEST.write_text(manifest_text, encoding="utf-8")
        LOCK.write_text(_render(build_lock(), sort_keys=False), encoding="utf-8")
        return 0
    stale = None
    if PROFILE.read_text(encoding="utf-8") != profile_text:
        stale = PROFILE.name
    elif not MANIFEST.is_file() or MANIFEST.read_text(encoding="utf-8") != manifest_text:
        stale = MANIFEST.name
    elif not LOCK.is_file() or LOCK.read_text(encoding="utf-8") != _render(build_lock(), sort_keys=False):
        stale = LOCK.name
    if stale:
        print(f"out of date: {stale}; rerun with --write", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
