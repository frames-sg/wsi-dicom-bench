"""Build the v6 negative-bench manifest, its expected-results lock, and core profile v4.

manifest-v6.json is the frozen record of the controls, the development entries, and the
core-profile cohort; the builder reads them from it and never changes them. Two of the
controls are the controls-v6 corrections (Photometric Interpretation YBR_ICT for the
irreversible ICT their Frames apply), and every case built on them names the corrected file.

The builder regenerates the two cohorts it owns from their case definitions: the IOD
structure cohort (iod_amendment_cases.STRUCTURE_CASES) and the requirement-statement cohort
(requirement_cases.REQUIREMENT_CASES). Their expected rules are the rules that report the
authored defect: the targeted rule, plus any other catalog rule that independently reports the
same defect. A structure case also records the adjudication of each requirement-statement
rule that the frozen candidate failed on it: an expected failing rule, or an authored expected
rule whose requirement that rule now enforces, recorded as superseded with its replacement.
These expectations were set by running the frozen candidate and adjudicating each result
against the standard; they are not blinded.

Core profile v4 is read the same way: its rows are frozen except the one row per
requirement-statement rule, which is regenerated and mapped to that cohort's cases.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from wsi_dicom_bench.core_profile import intrinsic_rule_ids
from wsi_dicom_bench.file_digest import sha256_file
from wsi_dicom_bench.negative_bench.identifiers import manifest_identifier_items
from wsi_dicom_bench.negative_bench.iod_amendment_cases import STRUCTURE_CASES, full_rule_id
from wsi_dicom_bench.negative_bench.requirement_cases import (
    PROFILE_POSITIVE_CONTROLS,
    PROFILE_ROWS,
    REQUIREMENT_CASES,
)


PACKAGE = Path(__file__).resolve().parent
RULES = PACKAGE.parent / "rules"
MANIFEST = PACKAGE / "manifest-v6.json"
LOCK = PACKAGE / "expected-results-lock-v6.json"
PROTOCOL = PACKAGE / "protocol-v6.md"
CATALOG = RULES / "wsi-dicom-bench-rules-2026c-v6.json"
PROFILE = RULES / "wsi-dicom-core-profile-2026c-v4.json"

SCHEMA_VERSION = "wsi-dicom-negative-bench-manifest-v6"
CHALLENGE_ID = "wsi-dicom-negative-bench-v6"
CREATED_DATE = "2026-10-23"
STRUCTURE_COHORT = "iod-structure-evaluation-v1"
STRUCTURE_SEED = "wsi-dicom-iod-structure-v1"
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
SEVERITY_ORDER = ("none", "minor", "major", "critical")


def _severity(by_id: dict, rule_ids: list[str], field: str) -> str:
    """The most severe ``field`` among ``rule_ids``, looked up in the catalog index ``by_id``."""
    return max((by_id[rule][field] for rule in rule_ids), key=SEVERITY_ORDER.index)


def _adjudicated_rules(spec: dict, authored: list[str]) -> list[str]:
    """Return the expected failing rules of ``authored`` after the case's adjudications."""
    adjudications = spec.get("adjudications", [])
    by_disposition = {
        disposition: [item["rule_id"] for item in adjudications if item["disposition"] == disposition]
        for disposition in ("expected_failing_rule", "superseded_expected_rule")
    }
    if sum(map(len, by_disposition.values())) != len(adjudications):
        raise ValueError(f"{spec['case_id']} has an adjudication that is neither expected nor superseded")
    superseded = by_disposition["superseded_expected_rule"]
    if not set(superseded) <= set(authored):
        raise ValueError(f"{spec['case_id']} supersedes a rule it did not expect: {superseded}")
    kept = [rule for rule in authored if rule not in superseded]
    return [*kept, *by_disposition["expected_failing_rule"]]


def _structure_case(spec: dict, controls: dict, by_id: dict, intrinsic: set[str]) -> dict:
    authored = [full_rule_id(short) for short in spec["expected"]]
    expected = _adjudicated_rules(spec, authored)
    case = {
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
        "source_control_sha256": controls[spec["control"]]["sha256"],
        # The rule family the case was authored against, even where a later rule supersedes it.
        "target_rule_family": authored[0],
    }
    if spec.get("adjudications"):
        case["requirement_rule_adjudications"] = spec["adjudications"]
    return case


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


def build_manifest(source: Path = MANIFEST, catalog_path: Path = CATALOG) -> dict:
    """Return manifest v6: the frozen entries of ``source`` and the cohorts the builder owns."""
    frozen = json.loads(source.read_text(encoding="utf-8"))
    if frozen.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"{source.name} is not the frozen v6 specification")
    controls, cases = manifest_identifier_items(frozen)
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    by_id = {rule["rule_id"]: rule for rule in catalog["rules"]}
    intrinsic = intrinsic_rule_ids(catalog["rules"])
    by_control = {control["control_id"]: control for control in controls}
    owned = [
        *(_structure_case(spec, by_control, by_id, intrinsic) for spec in STRUCTURE_CASES),
        *(_requirement_case(spec, by_control, by_id, intrinsic) for spec in REQUIREMENT_CASES),
    ]
    if any("package_paths" in by_control[case["source_control_ids"][0]] for case in owned):
        raise ValueError("structure and requirement-statement cases must use single-file controls")
    kept = [case for case in cases if case["cohort"] not in {STRUCTURE_COHORT, COHORT}]
    manifest = {
        **frozen,
        "challenge_id": CHALLENGE_ID,
        "core_profile": {"path": f"rules/{PROFILE.name}", "profile_id": PROFILE_ID},
        "created_date": CREATED_DATE,
        "evaluation_cases": [*kept, *owned],
        "expectation_provenance": {
            "blinded": False,
            "candidate": CANDIDATE,
            "carried_forward_cases": (
                "core-profile and IOD structure cases keep their authored mutations and seeds; "
                "cases on the corrected controls are rebased onto them; candidate failures of "
                "the requirement-statement rules are adjudicated in requirement_rule_adjudications"
            ),
            "method": (
                "Each case was generated and run through the frozen candidate; every "
                "failing rule was checked against the cited DICOM 2026c text before it "
                "was recorded as expected or as an adjudicated cascade."
            ),
        },
        "expected_results_lock": LOCK.name,
        "protocol": PROTOCOL.name,
        "rule_catalog": {
            "catalog_version": catalog["catalog_version"],
            "path": f"rules/{CATALOG.name}",
            # The rules of the requirement-statement families, one per profile row below.
            "required_new_rule_ids": [full_rule_id(row[-1]) for row in PROFILE_ROWS],
        },
    }
    manifest_identifier_items(manifest)
    return manifest


def build_profile(source: Path = PROFILE, catalog_path: Path = CATALOG) -> dict:
    """Return core profile v4: the frozen rows of ``source``, plus one row per requirement-statement rule."""
    frozen = json.loads(source.read_text(encoding="utf-8"))
    catalog = {rule["rule_id"] for rule in json.loads(catalog_path.read_text(encoding="utf-8"))["rules"]}
    owned = {row[0] for row in PROFILE_ROWS}
    carried = [row for row in frozen["requirements"] if row["requirement_id"] not in owned]
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
        **frozen,
        "profile_id": PROFILE_ID,
        "profile_version": "4",
        "title": "DICOM 2026c selected VL WSI rule-family, IOD and requirement-statement challenge profile",
        "requirements": [*carried, *rows],
    }


def build_lock(manifest_path: Path = MANIFEST, profile_path: Path = PROFILE) -> dict:
    """Return the expected-results lock binding protocol, manifest, catalog, and profile.

    ``manifest_path`` and ``profile_path`` are the files read and digested; the lock names
    them by their package paths.
    """
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    profile_document = json.loads(profile_path.read_text(encoding="utf-8"))
    profile_digest = sha256_file(profile_path)
    return {
        "schema_version": "wsi-dicom-negative-bench-expected-results-lock-v6",
        "challenge_id": document["challenge_id"],
        "locked_at_date": CREATED_DATE,
        "lock_state": "frozen_after_candidate_adjudication_before_final_evaluation",
        "core_profile": {
            "profile_id": profile_document["profile_id"],
            "version": profile_document["profile_version"],
            "sha256": profile_digest,
        },
        "files": [
            {"path": f"bench/negative_bench/{PROTOCOL.name}", "sha256": sha256_file(PROTOCOL)},
            {"path": f"bench/negative_bench/{MANIFEST.name}", "sha256": sha256_file(manifest_path)},
            {"path": f"rules/{CATALOG.name}", "sha256": sha256_file(CATALOG)},
            {"path": f"rules/{PROFILE.name}", "sha256": profile_digest},
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
    elif MANIFEST.read_text(encoding="utf-8") != manifest_text:
        stale = MANIFEST.name
    elif not LOCK.is_file() or LOCK.read_text(encoding="utf-8") != _render(build_lock(), sort_keys=False):
        stale = LOCK.name
    if stale:
        print(f"out of date: {stale}; rerun with --write", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
