"""Build the unfrozen, edition-neutral v7 challenge draft and coverage ledger.

V6 remains the runnable frozen suite. V7 has no expected-results lock or candidate digest: its
carried cases need adjudication against the candidate that will be frozen, and its coverage ledger
keeps every remaining file, JSON, and HTTP statement visible.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from wsi_dicom_bench.file_digest import sha256_file
from wsi_dicom_bench.negative_bench import (
    basic_image_statement_cases,
    controls_v7_iods,
    controls_v7_lossy_pathology,
    controls_v7_mutation_sources,
    controls_v7_wsi,
    deidentification_statement_cases,
    existing_statement_mappings,
    file_set_statement_cases,
    generic_iod_statement_cases,
    http_statement_cases,
    http_statement_runner,
    iod_statement_cases,
    jpip_statement_cases,
    json_statement_cases,
    metadata_statement_cases,
    motion_statement_cases,
    parser_statement_cases,
    pathology_statement_cases,
    pixel_structure_statement_cases,
    residual_metadata_statement_cases,
    residual_codestream_cases,
    residual_statement_cases,
    requirement_cases,
    signature_statement_cases,
)
from wsi_dicom_bench.negative_bench.mutations import generate_case

PACKAGE = Path(__file__).resolve().parent
RULES = PACKAGE.parent / "rules"
V6_MANIFEST = PACKAGE / "manifest-v6.json"
V6_CATALOG = RULES / "wsi-dicom-bench-rules-2026c-v6.json"
REQUIREMENTS = RULES / "wsi-dicom-requirements-v1.json"
CATALOG = RULES / "wsi-dicom-bench-rules-v7.json"
MANIFEST = PACKAGE / "manifest-v7-draft.json"
COVERAGE = PACKAGE / "statement-coverage-v7.json"
OBSERVATIONS = PACKAGE / "existing-statement-mapping-observations-v7.json"
CARRIED_OBSERVATIONS = PACKAGE / "carried-case-observations-v7.json"
STATEMENT_OBSERVATIONS = PACKAGE / "statement-case-observations-v7.json"
HTTP_OBSERVATIONS = PACKAGE / "http-statement-observations-v7.json"
PROTOCOL = PACKAGE / "protocol-v7-draft.md"

SCHEMA_VERSION = "wsi-dicom-negative-bench-manifest-v7-draft"
CHALLENGE_ID = "wsi-dicom-negative-bench-v7-draft"
CATALOG_VERSION = "wsi-dicom-bench-rules-v7"
DICOM_EDITION = "2026d"

# General-profile checks that enforce table bindings or grouped profile behavior and therefore
# own no sentence ID in the requirement catalog.
GENERAL_RULES_WITHOUT_STATEMENTS = {
    "intrinsic-wsi-dicom-identity-set",
    "intrinsic-wsi-dicom-iod-value-sets",
    "intrinsic-wsi-dicom-monochrome-presentation",
    "intrinsic-wsi-dicom-pyramid-geometry",
    "intrinsic-wsi-dicom-slide-coordinate-system",
    "intrinsic-wsi-dicom-source-relationship",
    "intrinsic-wsi-dicom-specimen-identity",
    "intrinsic-wsi-dicom-tile-geometry",
}

TOOL_LIMITS = {
    "dciodvfy-concatenation-plane-position": (
        "dciodvfy 1.00.snapshot.20260927113651 -new exits 0 on each member of "
        "W7-CONCATENATION-2X4F but warns that Plane Position (Slide) Sequence and its X, Y, Z, "
        "Column Position and Row Position attributes are not present in the standard IOD. They "
        "are the legal Plane Position (Slide) Functional Group Macro. The same warnings occur on "
        "other controls with explicit slide positions, so this is a dicom3tools functional-group "
        "model limit, not a defect in the Concatenation."
    ),
    "part2-mct-independent-decoders": (
        residual_codestream_cases.CONTROL_TOOL_LIMITS["V7-J2K-TWO-STAGE"]
        + " Grok grk_decompress likewise rejects MCT=2 in both controls; agreement between "
          "those decoders does not override the Annex J multiple-component-transform syntax."
    ),
}

EXISTING_STATEMENT_MAPPINGS = {
    **existing_statement_mappings.MAPPINGS,
    **{
        identifier: mapping
        for identifier, mapping in residual_metadata_statement_cases.MAPPINGS.items()
        if identifier != "Ps10_8_6_6f3918"
    },
}

# Cases whose former profile-family target is not part of the general-v4 observation.  Each
# replacement is the statement-level general rule that directly reports the same authored defect;
# every other newly failing intrinsic rule is retained as an adjudicated cascade.
CARRIED_GENERAL_REPLACEMENTS = {
    "CP-CF-002": "intrinsic-wsi-dicom-wsi-image",
    "CP-GE-004": "intrinsic-wsi-dicom-wsi-image",
    "CP-CL-001": "intrinsic-wsi-dicom-wsi-image",
}

# These v6 cascade expectations are no longer emitted for the same mutations by either current
# profile.  Another original target still detects each defect; retain the exact v6 rule here
# instead of silently dropping it during readjudication.
CARRIED_UNOBSERVED_SUPERSEDED = {
    "IOD-MOD-005": {"intrinsic-wsi-dicom-tile-geometry"},
    "IOD-MOD-006": {"intrinsic-wsi-dicom-tile-geometry"},
    "REQ-WSI-011": {"intrinsic-wsi-dicom-tile-geometry"},
}

CARRIED_CANDIDATE_GAPS: dict[str, str] = {}

ALLOWED_COERCION_CASE_ID = "NB-ID-005"
TRUE_UID_REUSE_CASE_ID = "NB-ID-005-DIVERGENT-PIXEL"


def _write_json(path: Path, document: object) -> None:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _v7_carried_case(case: dict) -> dict:
    """Replace the v6 allowed-coercion case with a true divergent-object UID reuse."""
    if case["case_id"] != ALLOWED_COERCION_CASE_ID:
        return case
    return {
        **copy.deepcopy(case),
        "case_id": TRUE_UID_REUSE_CASE_ID,
        "mutation_name": "duplicate_sop_uid_different_pixels",
        "exact_attributes_or_bytes_changed": (
            "Create two native images with the same SOP Instance UID and change the first Pixel "
            "Data byte of the second image."
        ),
        "adjudication_rationale": (
            "The same SOP Instance UID identifies two objects whose Pixel Data differs; unlike "
            "an allowed coerced copy, these are genuinely different objects."
        ),
    }


def snapshot_requirements(candidate: Path) -> dict:
    result = subprocess.run(
        [str(candidate), "requirements", "--json"], capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise RuntimeError(f"candidate requirements failed ({result.returncode}): {result.stderr}")
    document = json.loads(result.stdout)
    _validate_requirements(document)
    return document


def _validate_requirements(document: object) -> None:
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != "wsi-dicom-requirements-v1"
        or document.get("dicom_edition") != DICOM_EDITION
        or not isinstance(document.get("requirements"), list)
    ):
        raise ValueError("requirement catalog is not the expected DICOM 2026d schema")


def load_requirements(path: Path = REQUIREMENTS) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    _validate_requirements(document)
    return document


def load_mapping_observations(path: Path = OBSERVATIONS) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != "wsi-dicom-existing-mapping-observations-v7-draft":
        raise ValueError(f"{path} is not the v7 mapping observation record")
    return document


def load_carried_observations(path: Path = CARRIED_OBSERVATIONS) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != "wsi-dicom-carried-case-observations-v7-draft":
        raise ValueError(f"{path} is not the v7 carried-case observation record")
    return document


def load_statement_observations(path: Path = STATEMENT_OBSERVATIONS) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != "wsi-dicom-statement-case-observations-v7-draft":
        raise ValueError(f"{path} is not the v7 statement-case observation record")
    return document


def load_http_observations(path: Path = HTTP_OBSERVATIONS) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != "wsi-dicom-http-statement-observations-v7-draft":
        raise ValueError(f"{path} is not the v7 HTTP statement observation record")
    return document


def _source_paths(control: dict) -> list[Path]:
    originals = control.get("original_paths") or [control.get("original_path")]
    paths = []
    for original in originals:
        path = Path(original)
        if not path.is_file():
            try:
                path = PACKAGE / path.relative_to("bench/negative_bench")
            except ValueError:
                path = PACKAGE / path
        if not path.is_file():
            raise ValueError(f"mutation source does not exist: {path}")
        paths.append(path)
    return paths


def _source_target(paths: list[Path]) -> Path:
    if len(paths) == 1:
        return paths[0]
    common = Path(os.path.commonpath(paths))
    return common if common.is_dir() else common.parent


def _generation_source(mutation_name: str, paths: list[Path]) -> Path:
    return _source_target(paths) if mutation_name == "iod_set_edits" else paths[0]


def _candidate_intrinsic(candidate: Path, path: Path, profile: str) -> tuple[dict, set[str]]:
    result = subprocess.run(
        [str(candidate), "validate", "--profile", profile, "--json", "--optional", str(path)],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(f"candidate failed to validate {path}: {result.stderr}")
    report = json.loads(result.stdout)
    failed = {
        _rule_id(check["name"])
        for check in report["checks"]
        if check["status"] == "failed" and check["name"].startswith("intrinsic-")
    }
    return report, failed


def _optional_advisories(report: dict) -> list[str]:
    return [
        advisory
        for item in report.get("optional", [])
        for advisory in item.get("advisories", [])
    ]


def observe_existing_mappings(candidate: Path) -> dict:
    """Run only the carried cases claimed by explicit statement mappings."""
    manifest = json.loads(V6_MANIFEST.read_text(encoding="utf-8"))
    cases = {case["case_id"]: case for case in manifest["evaluation_cases"]}
    controls = {control["control_id"]: control for control in manifest["valid_controls"]}
    selected = sorted({case_id for mapping in EXISTING_STATEMENT_MAPPINGS.values()
                       for case_id in mapping["cases"]})
    observations = {}
    baselines = {}
    identity = None
    with tempfile.TemporaryDirectory(prefix="wsi-dicom-v7-mapped-cases-") as temporary:
        root = Path(temporary)
        for case_id in selected:
            case = cases[case_id]
            control = controls[case["source_control_ids"][0]]
            source = _source_paths(_mutation_source(control))[0]
            output = root / case_id
            output.mkdir()
            generate_case(case, source, output)
            def validate(path: Path) -> dict:
                result = subprocess.run(
                    [str(candidate), "validate", "--profile", "general", "--json", str(path)],
                    capture_output=True, text=True, timeout=300,
                )
                if result.returncode not in {0, 1}:
                    raise RuntimeError(
                        f"mapped case {case_id} failed to execute: {result.stderr}"
                    )
                return json.loads(result.stdout)

            control_id = case["source_control_ids"][0]
            if control_id not in baselines:
                baselines[control_id] = validate(source)
            baseline = baselines[control_id]
            report = validate(output)
            current = (report.get("dicom_edition"), report.get("rule_set_id"))
            identity = identity or current
            if current != identity:
                raise ValueError("mapped-case observations came from different candidate contracts")
            baseline_failed = {
                check["name"] for check in baseline["checks"]
                if check["status"] == "failed" and check["name"].startswith("intrinsic-")
            }
            failed = {
                check["name"] for check in report["checks"]
                if check["status"] == "failed" and check["name"].startswith("intrinsic-")
            }
            observations[case_id] = {
                "source_control_id": control_id,
                "baseline_failed_rules": sorted(baseline_failed),
                "failed_rules": sorted(failed),
                "new_failed_rules": sorted(failed - baseline_failed),
            }
    return {
        "schema_version": "wsi-dicom-existing-mapping-observations-v7-draft",
        "dicom_edition": identity[0],
        "candidate_rule_set_id": identity[1],
        "cases": observations,
    }


def observe_carried_cases(candidate: Path, catalog: dict) -> dict:
    """Generate every v6 case on its v7 source and observe general and needed core checks."""
    frozen = json.loads(V6_MANIFEST.read_text(encoding="utf-8"))
    mutation_sources = [_mutation_source(control) for control in frozen["valid_controls"]]
    controls = {control["control_id"]: control for control in mutation_sources}
    catalog_by_id = {rule["rule_id"]: rule for rule in catalog["rules"]}
    baselines = {}
    observations = {}
    advisory_observations = {}
    identities = {}
    with tempfile.TemporaryDirectory(prefix="wsi-dicom-v7-carried-cases-") as temporary:
        root = Path(temporary)
        for frozen_case in frozen["evaluation_cases"]:
            case = _v7_carried_case(frozen_case)
            control_id = case["source_control_ids"][0]
            source_paths = _source_paths(controls[control_id])
            if control_id not in baselines:
                report, failed = _candidate_intrinsic(
                    candidate, _source_target(source_paths), "general"
                )
                if failed:
                    raise ValueError(
                        f"rebased mutation source {control_id} fails intrinsic rules: "
                        f"{sorted(failed)}"
                    )
                baselines[control_id] = failed
                identities["general"] = (
                    report.get("dicom_edition"), report.get("rule_set_id")
                )
            output = root / case["case_id"]
            output.mkdir()
            generate_case(case, _generation_source(case["mutation_name"], source_paths), output)
            general_report, general_failed = _candidate_intrinsic(candidate, output, "general")
            current_general = (
                general_report.get("dicom_edition"), general_report.get("rule_set_id")
            )
            if identities.get("general", current_general) != current_general:
                raise ValueError("carried-case observations use different general contracts")
            identities["general"] = current_general
            expected = {_neutral(rule) for rule in case["expected_failing_rules"]}
            missing_intrinsic = {
                rule for rule in expected - general_failed
                if rule.startswith("intrinsic-")
                and catalog_by_id.get(rule, {}).get("rule_kind") != "independent_decoder"
            }
            core_failed: set[str] = set()
            if missing_intrinsic:
                core_report, core_failed = _candidate_intrinsic(candidate, output, "core")
                current_core = (core_report.get("dicom_edition"), core_report.get("rule_set_id"))
                if identities.get("core", current_core) != current_core:
                    raise ValueError("carried-case observations use different core contracts")
                identities["core"] = current_core
            observations[case["case_id"]] = {
                "source_control_id": control_id,
                "general_failed_rules": sorted(general_failed),
                "core_failed_rules": sorted(core_failed),
            }
        allowed = next(
            case for case in frozen["evaluation_cases"]
            if case["case_id"] == ALLOWED_COERCION_CASE_ID
        )
        source_paths = _source_paths(controls[allowed["source_control_ids"][0]])
        output = root / ALLOWED_COERCION_CASE_ID
        output.mkdir()
        generate_case(allowed, _generation_source(allowed["mutation_name"], source_paths), output)
        report, failed = _candidate_intrinsic(candidate, output, "general")
        if failed:
            raise ValueError(
                f"allowed coercion case unexpectedly fails intrinsic rules: {sorted(failed)}"
            )
        identity_checks = [
            check for check in report["checks"]
            if check["name"] == "intrinsic-wsi-dicom-identity-set" and check["path"] is None
        ]
        if len(identity_checks) != 1 or "PS3.4 2026d B.4.1.3" not in identity_checks[0]["message"]:
            raise ValueError("allowed coercion case lacks the expected identity-set advisory")
        advisory_observations[ALLOWED_COERCION_CASE_ID] = {
            "source_control_id": allowed["source_control_ids"][0],
            "general_failed_rules": [],
            "identity_set_status": identity_checks[0]["status"],
            "identity_set_message": identity_checks[0]["message"],
        }
    return {
        "schema_version": "wsi-dicom-carried-case-observations-v7-draft",
        "dicom_edition": identities["general"][0],
        "general_rule_set_id": identities["general"][1],
        "core_rule_set_id": identities.get("core", (None, None))[1],
        "cases": observations,
        "advisory_cases": advisory_observations,
    }


def observe_statement_cases(candidate: Path) -> dict:
    """Observe every ready file-object statement case against a valid source baseline."""
    frozen = json.loads(V6_MANIFEST.read_text(encoding="utf-8"))
    mutation_sources = [_mutation_source(control) for control in frozen["valid_controls"]]
    valid_controls = [
        *(_new_control(control, "wsi") for control in controls_v7_wsi.CONTROLS),
        *(_new_control(control, "iods") for control in controls_v7_iods.CONTROLS),
        *_deidentification_controls(),
        *_document_file_set_controls(),
        *_signature_controls(),
        *_motion_controls(),
        *_lossy_pathology_controls(),
        *_residual_codec_controls(),
    ]
    controls = {control["control_id"]: control
                for control in [*mutation_sources, *valid_controls]}
    specs = [*iod_statement_cases.CASES, *basic_image_statement_cases.CASES,
             *generic_iod_statement_cases.CASES,
             *metadata_statement_cases.CASES,
             *motion_statement_cases.CASES, *pathology_statement_cases.CASES,
             *pixel_structure_statement_cases.CASES,
             *file_set_statement_cases.CASES]
    specs.extend([*deidentification_statement_cases.CASES, *parser_statement_cases.CASES,
                  *residual_codestream_cases.CASES,
                  *residual_metadata_statement_cases.CASES,
                  *residual_statement_cases.CASES, *signature_statement_cases.CASES])
    specs = [spec for spec in specs if spec["case_id"] not in iod_statement_cases.BLOCKED_CASES]
    observations = {}
    baselines = {}
    baseline_advisories = {}
    identity = None
    with tempfile.TemporaryDirectory(prefix="wsi-dicom-v7-statement-cases-") as temporary:
        root = Path(temporary)
        for spec in specs:
            control_id = spec["control"]
            source_paths = _source_paths(controls[control_id])
            if control_id not in baselines:
                report, failed = _candidate_intrinsic(
                    candidate, _source_target(source_paths), "general"
                )
                if failed:
                    raise ValueError(
                        f"statement source {control_id} fails intrinsic rules: {sorted(failed)}"
                    )
                baselines[control_id] = failed
                baseline_advisories[control_id] = _optional_advisories(report)
                current = (report.get("dicom_edition"), report.get("rule_set_id"))
                identity = identity or current
                if current != identity:
                    raise ValueError("statement baselines use different candidate contracts")
            output = root / spec["case_id"]
            output.mkdir()
            case = {
                **spec,
                "deterministic_seed":
                    f"wsi-dicom-requirement-statements-v2:{spec['case_id']}",
            }
            generate_case(case, _generation_source(case["mutation_name"], source_paths), output)
            report, failed = _candidate_intrinsic(candidate, output, "general")
            current = (report.get("dicom_edition"), report.get("rule_set_id"))
            identity = identity or current
            if current != identity:
                raise ValueError("statement cases use different candidate contracts")
            expected = {_expected_rule_id(rule) for rule in spec["expected"]}
            advisory = spec.get("expected_evidence") == "advisory"
            advisories = _optional_advisories(report)
            advisory_fragment = spec.get("expected_advisory_contains")
            localized_advisory = (
                advisory
                and not failed
                and advisory_fragment is not None
                and any(advisory_fragment in message for message in advisories)
                and not any(advisory_fragment in message
                            for message in baseline_advisories[control_id])
            )
            if advisory and not localized_advisory:
                raise ValueError(
                    f"{spec['case_id']} does not produce its assigned advisory evidence"
                )
            if not advisory and not expected <= failed:
                raise ValueError(
                    f"{spec['case_id']} does not fail its assigned rules: "
                    f"{sorted(expected - failed)}"
                )
            observations[spec["case_id"]] = {
                "source_control_id": control_id,
                "failed_rules": sorted(failed),
                **({"observed_advisories": advisories,
                    "baseline_advisories": baseline_advisories[control_id]}
                   if advisory else {}),
            }
    return {
        "schema_version": "wsi-dicom-statement-case-observations-v7-draft",
        "dicom_edition": identity[0],
        "candidate_rule_set_id": identity[1],
        "cases": observations,
    }


def _neutral(value: str) -> str:
    return value.replace("-2026c-", "-").replace(" 2026c", f" {DICOM_EDITION}")


def _checked_rules(entry: dict) -> set[str]:
    dispositions = [entry["disposition"], *entry.get("iod_dispositions", {}).values()]
    return {item["detail"] for item in dispositions if item.get("kind") == "checked"}


def _rule_id(check_name: str) -> str:
    return ("intrinsic-wsi-dicom-pixel-structure"
            if check_name == "intrinsic-pixel-structure" else check_name)


def _expected_rule_id(rule: str) -> str:
    if rule.startswith(("intrinsic-", "dicomweb-")):
        return _rule_id(rule)
    return f"intrinsic-wsi-dicom-{rule}"


def _coverage_rules(entry: dict) -> set[str]:
    return {_rule_id(check_name) for check_name in _checked_rules(entry)}


def _citation(rule: str, entries: list[dict]) -> list[dict]:
    citations = []
    for part in sorted({entry["part"] for entry in entries}):
        selected = [entry for entry in entries if entry["part"] == part]
        number = part.removeprefix("PS3.")
        citations.append(
            {
                "edition": DICOM_EDITION,
                "part": part,
                "section": ", ".join(dict.fromkeys(entry["section"] for entry in selected[:4])),
                "requirement": f"{len(selected)} checked statement(s) assigned to {rule}.",
                "url": (
                    "https://dicom.nema.org/medical/dicom/current/output/chtml/"
                    f"part{int(number):02d}/PS3.{number}.html"
                ),
            }
        )
    return citations or [{
        "edition": DICOM_EDITION,
        "part": "PS3.3",
        "section": "pathology object profile",
        "requirement": "Grouped conformance behavior exercised by the v7 pathology corpus.",
        "url": "https://dicom.nema.org/medical/dicom/current/output/chtml/part03/PS3.3.html",
    }]


def _domain(check: str) -> str:
    if any(word in check for word in ("pixel", "codestream", "image-metadata")):
        return "pixel"
    if any(word in check for word in ("dimension", "geometry", "slide-coordinate")):
        return "geometry"
    if "icc" in check or "monochrome" in check:
        return "color"
    if any(word in check for word in ("identity", "deidentification", "specimen")):
        return "identity"
    return "conformance"


def build_catalog(requirements: dict, base_path: Path = V6_CATALOG) -> dict:
    """Build the edition-neutral catalog for the candidate's general file-object profile."""
    by_rule: dict[str, list[dict]] = defaultdict(list)
    for entry in requirements["requirements"]:
        for rule in _checked_rules(entry):
            if rule.startswith("intrinsic-") and rule != "intrinsic-wsi-dicom-json-model":
                by_rule[rule].append(entry)
    checks = set(by_rule) | GENERAL_RULES_WITHOUT_STATEMENTS

    reusable = {}
    decoder_rules = []
    for source in json.loads(base_path.read_text(encoding="utf-8"))["rules"]:
        rule = copy.deepcopy(source)
        rule["rule_id"] = _neutral(rule["rule_id"])
        rule["check_names"] = [_neutral(name) for name in rule["check_names"]]
        rule["summary"] = _neutral(rule["summary"])
        rule["applicability"] = _neutral(rule["applicability"])
        for citation in rule["citations"]:
            citation["edition"] = DICOM_EDITION
            citation["requirement"] = _neutral(citation["requirement"])
            citation["url"] = citation["url"].replace("/2026c/", "/current/")
        if len(rule["check_names"]) == 1:
            reusable[rule["check_names"][0]] = rule
        elif rule["rule_kind"] == "independent_decoder":
            decoder_rules.append(rule)

    rules = []
    for check in sorted(checks):
        if check in reusable:
            rules.append(reusable[check])
            continue
        selected = by_rule.get(check, [])
        rules.append({
            "rule_id": ("intrinsic-wsi-dicom-pixel-structure"
                        if check == "intrinsic-pixel-structure" else check),
            "check_names": [check],
            "rule_kind": ("intrinsic_set"
                          if check.endswith("-set") or check.endswith("-file-set") else "intrinsic"),
            "primary_domain": _domain(check),
            "summary": f"Checks the DICOM {DICOM_EDITION} pathology requirements assigned to {check}.",
            "applicability": "Each pathology object or evaluated set to which the candidate emits this check.",
            "clinical_severity": "minor",
            "clinical_severity_rationale": "Impact depends on the violated statement and is adjudicated per case.",
            "operational_severity": "major",
            "operational_severity_rationale": "A failed normative check can cause receiver rejection or misinterpretation.",
            "likely_fix_owners": ["converter", "validator"],
            "citations": _citation(check, selected),
        })
    rules.extend(decoder_rules)
    for check in ("dciodvfy", "dcentvfy", "validate_iods", "dcmvalidate"):
        if check in reusable:
            rules.append(reusable[check])
    return {
        "catalog_schema_version": "wsi-dicom-bench-rule-catalog-v1",
        "catalog_version": CATALOG_VERSION,
        "dicom_edition": DICOM_EDITION,
        "validation_profile": "general",
        "candidate_rule_set_id": "wsi-dicom-general-v4",
        "scope": "DICOM pathology-slide file objects and File-sets in the v7 corpus",
        "coverage_scope": (
            "Every intrinsic general-profile check emitted for the pathology file-object corpus. "
            "DICOM JSON and DICOMweb statements require separate JSON and HTTP cases and are "
            "counted in statement-coverage-v7.json. This draft does not claim complete coverage."
        ),
        "rules": rules,
    }


def _case_definitions() -> list[dict]:
    return [*requirement_cases.REQUIREMENT_CASES, *iod_statement_cases.CASES,
            *basic_image_statement_cases.CASES,
            *generic_iod_statement_cases.CASES,
            *metadata_statement_cases.CASES, *pathology_statement_cases.CASES,
            *motion_statement_cases.CASES,
            *pixel_structure_statement_cases.CASES,
            *file_set_statement_cases.CASES, *deidentification_statement_cases.CASES,
            *parser_statement_cases.CASES, *residual_codestream_cases.CASES,
            *residual_metadata_statement_cases.CASES,
            *residual_statement_cases.CASES,
            *signature_statement_cases.CASES, *json_statement_cases.CASES,
            *jpip_statement_cases.CASES]


def build_statement_coverage(requirements: dict, observations: dict | None = None) -> dict:
    """Account for every checked statement without treating a gap as evidence."""
    by_id = {entry["id"]: entry for entry in requirements["requirements"] if entry.get("id")}
    checked = {identifier: _coverage_rules(entry) for identifier, entry in by_id.items()}
    checked = {identifier: rules for identifier, rules in checked.items() if rules}
    references: dict[str, list[dict]] = defaultdict(list)
    for case in _case_definitions():
        if case["case_id"] in iod_statement_cases.BLOCKED_CASES:
            continue
        expected = {_expected_rule_id(rule) for rule in case["expected"]}
        for identifier in case.get("requirement_ids", []):
            references[identifier].append({"case_id": case["case_id"], "expected_rules": expected})
    for case in http_statement_cases.CASES:
        for identifier in case["requirement_ids"]:
            references[identifier].append({
                "case_id": case["case_id"],
                "expected_rules": {case["expected_check"]},
            })
    observations = observations or load_mapping_observations()
    observed = observations["cases"]
    v6_cases = {case["case_id"]: case for case in
                json.loads(V6_MANIFEST.read_text(encoding="utf-8"))["evaluation_cases"]}
    for identifier, mapping in EXISTING_STATEMENT_MAPPINGS.items():
        if identifier not in checked:
            raise ValueError(f"existing statement mapping names unknown requirement {identifier}")
        for case_id in mapping["cases"]:
            if case_id not in v6_cases:
                raise ValueError(f"existing statement mapping names unknown case {case_id}")
            expected = {
                _rule_id(rule)
                for rule in observed.get(case_id, {}).get("new_failed_rules", [])
            }
            if not checked[identifier] & expected:
                raise ValueError(
                    f"mapped case {case_id} did not fail the rule assigned to {identifier}"
                )
            references[identifier].append({"case_id": case_id, "expected_rules": expected})
    matched_rules = {
        identifier: set().union(*(
            rules & reference["expected_rules"]
            for reference in references.get(identifier, [])
        ))
        for identifier, rules in checked.items()
    }
    file_ids = {identifier for identifier, rules in checked.items()
                if any(rule.startswith("intrinsic-") and
                       rule != "intrinsic-wsi-dicom-json-model" for rule in rules)}
    web_ids = {identifier for identifier, rules in checked.items()
               if any(rule.startswith("dicomweb-") for rule in rules)}
    json_ids = {identifier for identifier, rules in checked.items()
                if "intrinsic-wsi-dicom-json-model" in rules}
    direct_file = {
        identifier for identifier in file_ids
        if any(rule.startswith("intrinsic-") and
               rule != "intrinsic-wsi-dicom-json-model"
               for rule in matched_rules[identifier])
    }
    direct_json = {
        identifier for identifier in json_ids
        if "intrinsic-wsi-dicom-json-model" in matched_rules[identifier]
    }
    direct_web = {
        identifier for identifier in web_ids
        if any(rule.startswith("dicomweb-") for rule in matched_rules[identifier])
    }
    file_recommendations = {identifier for identifier in file_ids
                            if by_id[identifier]["strength"] == "should"}
    unchecked_pairs = []
    for entry in requirements["requirements"]:
        for iod in entry["iods"]:
            disposition = entry.get("iod_dispositions", {}).get(iod, entry["disposition"])
            if disposition.get("kind") == "unchecked":
                unchecked_pairs.append({
                    "id": entry.get("id"), "iod": iod,
                    "family": disposition["detail"], "part": entry["part"],
                    "section": entry["section"], "text": entry["text"],
                })

    normalize = lambda text: re.sub(r"\s+", " ", text).strip().casefold()
    duplicate_index: dict[tuple[str, str], list[str]] = defaultdict(list)
    for identifier in direct_file:
        for rule in matched_rules[identifier]:
            if rule.startswith("intrinsic-"):
                duplicate_index[(normalize(by_id[identifier]["text"]), rule)].append(identifier)
    duplicate_mappings = {}
    for identifier in file_ids - direct_file:
        matches = sorted({source for rule in checked[identifier]
                          for source in duplicate_index.get(
                              (normalize(by_id[identifier]["text"]), rule), [])})
        if matches:
            duplicate_mappings[identifier] = matches
    uncovered = sorted(file_ids - direct_file - set(duplicate_mappings))
    covered_rules = {rule for identifier in direct_file for rule in matched_rules[identifier]}
    existing_family = {identifier for identifier in uncovered
                       if checked[identifier] & covered_rules}
    blocked_ids = {identifier for case in iod_statement_cases.CASES
                   if case["case_id"] in iod_statement_cases.BLOCKED_CASES
                   for identifier in case["requirement_ids"]}
    gap_counts = Counter(rule for identifier in uncovered for rule in checked[identifier]
                         if rule.startswith("intrinsic-") and
                         rule != "intrinsic-wsi-dicom-json-model")
    all_blockers = {
        **requirement_cases.UNCOVERED,
        **pathology_statement_cases.UNCOVERED,
        **residual_statement_cases.UNCOVERED,
    }
    for case in iod_statement_cases.CASES:
        reason = iod_statement_cases.BLOCKED_CASES.get(case["case_id"])
        if reason:
            for identifier in case["requirement_ids"]:
                all_blockers[identifier] = reason
    documented_blockers = {
        identifier: reason for identifier, reason in all_blockers.items()
        if identifier in uncovered
    }
    unknown_blockers = set(documented_blockers) - set(uncovered)
    if unknown_blockers:
        raise ValueError(
            f"pathology blockers do not identify current uncovered statements: "
            f"{sorted(unknown_blockers)}"
        )
    return {
        "schema_version": "wsi-dicom-statement-coverage-v7-draft",
        "dicom_edition": requirements["dicom_edition"],
        "checked_statements": len(checked),
        "unchecked_statement_scope_pairs": len(unchecked_pairs),
        "unchecked_statement_ids": sorted({pair["id"] for pair in unchecked_pairs}),
        "unchecked_by_family": dict(sorted(Counter(
            pair["family"] for pair in unchecked_pairs
        ).items())),
        "unchecked": unchecked_pairs,
        "file_object_checked_statements": len(file_ids),
        "file_object_mandatory_statements": len(file_ids - file_recommendations),
        "file_object_recommendations": len(file_recommendations),
        "directly_named_statements": len(direct_file),
        "mapped_to_existing_case_statements": len(EXISTING_STATEMENT_MAPPINGS),
        "blocked_authored_statements": len(blocked_ids),
        "blocked_cases": iod_statement_cases.BLOCKED_CASES,
        "duplicate_text_and_rule_mappings": len(duplicate_mappings),
        "duplicate_mappings": duplicate_mappings,
        "uncovered_file_object_statements": len(uncovered),
        "uncovered_mandatory_file_object_statements": len(set(uncovered) - file_recommendations),
        "uncovered_file_object_recommendations": len(set(uncovered) & file_recommendations),
        "uncovered_with_existing_mutation_family": len(existing_family),
        "uncovered_requiring_new_mutation_family": len(uncovered) - len(existing_family),
        "uncovered_by_rule": dict(sorted(gap_counts.items())),
        "uncovered": [{
            "id": identifier,
            "rules": sorted(checked[identifier]),
            "part": by_id[identifier]["part"],
            "section": by_id[identifier]["section"],
            "text": by_id[identifier]["text"],
            **({"blocker": documented_blockers[identifier]}
               if identifier in documented_blockers else {}),
            "work": (
                "documented blocker"
                if identifier in documented_blockers
                else
                "author an advisory case"
                if identifier in file_recommendations
                else "extend an existing mutation family"
                if identifier in existing_family
                else "author a new mutation family"
            ),
        } for identifier in uncovered],
        "dicomweb_checked_statements": len(web_ids),
        "directly_named_dicomweb_statements": len(direct_web),
        "directly_named_dicomweb_statement_ids": sorted(direct_web),
        "dicomweb_statements_requiring_http_cases": len(web_ids - direct_web),
        "dicomweb_statement_ids_requiring_cases": sorted(web_ids - direct_web),
        "dicom_json_checked_statements": len(json_ids),
        "directly_named_dicom_json_statements": len(direct_json),
        "directly_named_dicom_json_statement_ids": sorted(direct_json),
        "dicom_json_statements_requiring_json_cases": len(json_ids - direct_json),
        "dicom_json_statement_ids_requiring_cases": sorted(json_ids - direct_json),
    }


def _new_control(control: dict, directory: str) -> dict:
    paths = list(control["paths"])
    root = PACKAGE / "controls-v7" / directory
    return {
        "control_id": control["id"],
        "original_paths": [f"bench/negative_bench/controls-v7/{directory}/{path}"
                           for path in paths],
        "package_paths": [f"controls/{control['id']}/{path}" for path in paths],
        "size_bytes": [(root / path).stat().st_size for path in paths],
        "sha256": [control["sha256"][path] for path in paths],
        "iod": control["iod"],
        "v7_status": "positive_control",
    }


def _deidentification_controls() -> list[dict]:
    specifications = (
        (deidentification_statement_cases.CONTROL_ID,
         (deidentification_statement_cases.CONTROL_PATH,),
         "VL Whole Slide Microscopy Image, Basic Profile with Retain UIDs"),
        (deidentification_statement_cases.ENCRYPTED_CONTROL_ID,
         (deidentification_statement_cases.ENCRYPTED_CONTROL_PATH,),
         "VL Whole Slide Microscopy Image with Encrypted Attributes"),
        (deidentification_statement_cases.FILESET_CONTROL_ID,
         deidentification_statement_cases.FILESET_CONTROL_PATHS,
         "Basic Directory File-set of a Basic Profile protected WSI"),
    )
    controls = []
    for control_id, relative_paths, iod in specifications:
        paths = [PACKAGE / relative for relative in relative_paths]
        prefix = "controls-v7/iods/deid-fileset/"
        package_paths = [
            f"controls/{control_id}/"
            f"{relative.removeprefix(prefix) if len(relative_paths) > 1 else Path(relative).name}"
            for relative in relative_paths
        ]
        controls.append({
            "control_id": control_id,
            "original_paths": [f"bench/negative_bench/{relative}"
                               for relative in relative_paths],
            "package_paths": package_paths,
            "size_bytes": [path.stat().st_size for path in paths],
            "sha256": [sha256_file(path) for path in paths],
            "iod": iod,
            "v7_status": "positive_control",
        })
    return controls


def _signature_controls() -> list[dict]:
    auxiliary = PACKAGE / signature_statement_cases.MUTATIONS_PATH
    controls = []
    for control_id, relative in (
        (signature_statement_cases.CONTROL_ID, signature_statement_cases.CONTROL_PATH),
        (signature_statement_cases.TIMESTAMP_CONTROL_ID,
         signature_statement_cases.TIMESTAMP_CONTROL_PATH),
    ):
        path = PACKAGE / relative
        controls.append({
            "control_id": control_id,
            "original_paths": [f"bench/negative_bench/{relative}"],
            "package_paths": [f"controls/{control_id}/{Path(relative).name}"],
            "size_bytes": [path.stat().st_size],
            "sha256": [sha256_file(path)],
            "auxiliary_files": [{
                "original_path":
                    f"bench/negative_bench/{signature_statement_cases.MUTATIONS_PATH}",
                "package_path": f"controls/{control_id}/{auxiliary.name}",
                "size_bytes": auxiliary.stat().st_size,
                "sha256": sha256_file(auxiliary),
            }],
            "iod": "VL Whole Slide Microscopy Image with verified Digital Signature",
            "v7_status": "positive_control",
        })
    return controls


def _document_file_set_controls() -> list[dict]:
    relative_paths = file_set_statement_cases.DOCUMENT_CONTROL_PATHS
    prefix = "controls-v7/iods/document-fileset/"
    paths = [PACKAGE / relative for relative in relative_paths]
    return [{
        "control_id": file_set_statement_cases.DOCUMENT_CONTROL_ID,
        "original_paths": [f"bench/negative_bench/{relative}"
                           for relative in relative_paths],
        "package_paths": [
            f"controls/{file_set_statement_cases.DOCUMENT_CONTROL_ID}/"
            f"{relative.removeprefix(prefix)}"
            for relative in relative_paths
        ],
        "size_bytes": [path.stat().st_size for path in paths],
        "sha256": [sha256_file(path) for path in paths],
        "iod": "Basic Directory File-set with WSI, Comprehensive SR and KOS Documents",
        "v7_status": "positive_control",
    }]


def _motion_controls() -> list[dict]:
    controls = []
    for control_id, relative in motion_statement_cases.CONTROL_PATHS.items():
        path = PACKAGE / relative
        controls.append({
            "control_id": control_id,
            "original_paths": [f"bench/negative_bench/{relative}"],
            "package_paths": [f"controls/{control_id}/{path.name}"],
            "size_bytes": [path.stat().st_size],
            "sha256": [sha256_file(path)],
            "iod": "VL Whole Slide Microscopy Image with single-component MPEG2 Pixel Data",
            "v7_status": "positive_control",
        })
    return controls


def _lossy_pathology_controls() -> list[dict]:
    descriptions = {
        "V7-SEG-FRACTIONAL-MPEG2": "Fractional Segmentation with lossy MPEG2 frames",
        "V7-PM-JPEGLS-NEAR": "Parametric Map with near-lossless JPEG-LS frames",
    }
    controls = []
    for control_id, relative in controls_v7_lossy_pathology.CONTROL_PATHS.items():
        path = PACKAGE / relative
        controls.append({
            "control_id": control_id,
            "original_paths": [f"bench/negative_bench/{relative}"],
            "package_paths": [f"controls/{control_id}/{path.name}"],
            "size_bytes": [path.stat().st_size],
            "sha256": [sha256_file(path)],
            "iod": descriptions[control_id],
            "v7_status": "positive_control",
        })
    return controls


def _residual_codec_controls() -> list[dict]:
    descriptions = {
        "V7-RLE-PACKETS": "VL WSI with independently encoded RLE packets",
        "V7-J2K-TWO-STAGE": "VL WSI with a two-stage JPEG 2000 Part 2 MCT",
        "V7-WAVEFORM-8": "Ambulatory ECG Waveform with signed eight-bit samples",
    }
    controls = []
    for control_id, relative in residual_codestream_cases.CONTROL_PATHS.items():
        path = PACKAGE / relative
        controls.append({
            "control_id": control_id,
            "original_paths": [f"bench/negative_bench/{relative}"],
            "package_paths": [f"controls/{control_id}/{path.name}"],
            "size_bytes": [path.stat().st_size],
            "sha256": [sha256_file(path)],
            "iod": descriptions[control_id],
            "v7_status": "positive_control",
        })
    return controls


def _mutation_source(control: dict) -> dict:
    value = {**copy.deepcopy(control), "v7_status": "mutation_source_needs_rebase"}
    paths = controls_v7_mutation_sources.SOURCES.get(control["control_id"])
    if paths is None:
        return value
    originals = [
        f"bench/negative_bench/controls-v7/mutation-sources/{path}" for path in paths
    ]
    sizes = [(controls_v7_mutation_sources.CONTROLS_DIR / path).stat().st_size for path in paths]
    digests = [controls_v7_mutation_sources.SHA256[path] for path in paths]
    if len(paths) == 1:
        value.update(original_path=originals[0], size_bytes=sizes[0], sha256=digests[0])
    else:
        value.update(original_paths=originals, size_bytes=sizes, sha256=digests)
    value["v7_status"] = "mutation_source_rebased"
    return value


def _allowed_coercion_case(case: dict, sources: dict[str, dict]) -> dict:
    value = copy.deepcopy(case)
    value["source_control_sha256"] = sources[case["source_control_ids"][0]]["sha256"]
    value["expected_failing_rules"] = []
    value["expected_unaffected_rules"] = []
    value["expected_outcome"] = {
        "intrinsic-wsi-dicom-identity-set": "passed_with_advisory",
        "wsi_dicom_bench": "passed",
    }
    value["dicom_citation"] = {
        "edition": DICOM_EDITION,
        "part": "PS3.4",
        "section": "B.4.1.3 Table B.4-1 and Note 4",
        "url": "https://dicom.nema.org/medical/dicom/current/output/chtml/part04/sect_B.4.html",
    }
    value["adjudication_rationale"] = (
        "The files have identical Pixel Data, SOP Class and Transfer Syntax and differ only in "
        "Series Instance UID. PS3.4 B.4.1.3 permits a Storage SCP to coerce that Attribute while "
        "retaining SOP Instance UID, so they are copies of one object rather than a UID reuse."
    )
    value["v7_observation"] = CARRIED_OBSERVATIONS.name
    value["v7_status"] = "standards_allowed_coercion_advisory"
    return value


def _neutralize_case(case: dict, checked: dict[str, set[str]], mapping_observations: dict,
                     carried_observation: dict, sources: dict[str, dict], catalog: dict) -> dict:
    value = copy.deepcopy(case)
    for field in ("expected_failing_rules", "expected_unaffected_rules",
                  "adjudicated_cascade_rules"):
        if field in value:
            value[field] = [_neutral(rule) for rule in value[field]]
    value["source_control_sha256"] = sources[case["source_control_ids"][0]]["sha256"]
    mapped = [identifier for identifier, mapping in EXISTING_STATEMENT_MAPPINGS.items()
              if case["case_id"] in mapping["cases"]]
    if mapped:
        value["requirement_ids"] = sorted(set(value.get("requirement_ids", [])) | set(mapped))
        added_rules = {
            _rule_id(rule)
            for rule in mapping_observations[case["case_id"]]["new_failed_rules"]
        } & {
            rule for identifier in mapped for rule in checked[identifier]
        }
        value["expected_failing_rules"] = sorted(set(value["expected_failing_rules"]) | added_rules)
        value["expected_unaffected_rules"] = sorted(
            set(value.get("expected_unaffected_rules", [])) - added_rules
        )
    original_expected = set(value["expected_failing_rules"])
    general_failed = set(carried_observation["general_failed_rules"])
    core_failed = set(carried_observation["core_failed_rules"])
    catalog_by_id = {rule["rule_id"]: rule for rule in catalog["rules"]}
    independent = {
        rule for rule in original_expected
        if catalog_by_id.get(rule, {}).get("rule_kind") == "independent_decoder"
    }
    observed_targets = original_expected & general_failed
    missing_intrinsic = original_expected - observed_targets - independent
    profile_specific = missing_intrinsic & core_failed
    unresolved = missing_intrinsic - profile_specific
    if unresolved:
        allowed = CARRIED_UNOBSERVED_SUPERSEDED.get(case["case_id"], set())
        if unresolved != allowed and (general_failed or independent):
            raise ValueError(
                f"{case['case_id']} has expectations unobserved in general, core or an "
                f"independent decoder: {sorted(unresolved)}"
            )
        if not general_failed and not independent:
            if case["case_id"] not in CARRIED_CANDIDATE_GAPS:
                raise ValueError(f"unreviewed candidate detection gap: {case['case_id']}")
            value["known_gap_expected_rules"] = sorted(unresolved)
            value["candidate_gap_reason"] = CARRIED_CANDIDATE_GAPS[case["case_id"]]
            value.pop("expected_unaffected_rules", None)
            value.pop("adjudicated_cascade_rules", None)
            value["v7_original_expected_failing_rules"] = sorted(original_expected)
            value["v7_observation"] = CARRIED_OBSERVATIONS.name
            value["v7_status"] = "candidate_detection_gap"
            return value
    targets = observed_targets | independent
    replacement = CARRIED_GENERAL_REPLACEMENTS.get(case["case_id"])
    if replacement is not None:
        if targets - independent or replacement not in general_failed:
            raise ValueError(f"invalid general replacement for {case['case_id']}: {replacement}")
        targets.add(replacement)
    if not general_failed and profile_specific and not independent:
        value["expected_failing_rules"] = sorted(profile_specific)
        value.pop("expected_unaffected_rules", None)
        value.pop("adjudicated_cascade_rules", None)
        value["validation_profile"] = "core"
        value["candidate_rule_set_id"] = "wsi-dicom-core-profile-v5"
        value["v7_original_expected_failing_rules"] = sorted(original_expected)
        value["v7_observation"] = CARRIED_OBSERVATIONS.name
        value["v7_status"] = "candidate_readjudicated_core_profile"
        return value
    if not targets:
        raise ValueError(f"{case['case_id']} has no observed general target or replacement")
    cascades = general_failed - targets
    intrinsic = {
        rule["rule_id"] for rule in catalog["rules"]
        if rule["rule_kind"].startswith("intrinsic")
    }
    value["expected_failing_rules"] = sorted(targets)
    value["adjudicated_cascade_rules"] = sorted(cascades)
    value["expected_unaffected_rules"] = sorted(intrinsic - targets - cascades)
    value["v7_original_expected_failing_rules"] = sorted(original_expected)
    if profile_specific:
        value["core_profile_expected_rules"] = sorted(profile_specific)
    superseded = original_expected - targets - independent
    if superseded:
        value["v7_superseded_general_expected_rules"] = sorted(superseded)
    if replacement is not None:
        value["target_rule_family"] = replacement
    value["v7_observation"] = CARRIED_OBSERVATIONS.name
    value["v7_status"] = "candidate_readjudicated"
    return value


def _draft_case(spec: dict, sources: dict[str, dict], catalog: dict,
                observation: dict) -> dict:
    expected = [_expected_rule_id(rule) for rule in spec["expected"]]
    observed = set(observation["failed_rules"])
    advisory = spec.get("expected_evidence") == "advisory"
    if not advisory and not set(expected) <= observed:
        raise ValueError(f"{spec['case_id']} observation misses an assigned rule")
    if advisory and observed:
        raise ValueError(f"{spec['case_id']} advisory mutation also fails checks")
    cascades = observed - set(expected)
    by_id = {rule["rule_id"]: rule for rule in catalog["rules"]}
    target = by_id[expected[0]]
    intrinsic = {rule["rule_id"] for rule in catalog["rules"]
                 if rule["rule_kind"].startswith("intrinsic")}
    source = sources[spec["control"]]
    source_digest = source["sha256"]
    if isinstance(source_digest, list) and len(source_digest) == 1:
        source_digest = source_digest[0]
    citation = copy.deepcopy(spec["citation"])
    citation["edition"] = DICOM_EDITION
    citation["url"] = citation["url"].replace("/2026c/", "/current/")
    value = {
        "adjudication_rationale": spec["rationale"],
        "case_id": spec["case_id"],
        "clinical_severity": target["clinical_severity"],
        "cohort": "requirement-statement-evaluation-v2",
        "deterministic_seed": f"wsi-dicom-requirement-statements-v2:{spec['case_id']}",
        "dicom_citation": citation,
        "domain": target["primary_domain"],
        "exact_attributes_or_bytes_changed": spec["changed"],
        "expected_failing_rules": [] if advisory else expected,
        "expected_outcome": {"domain_localized": True, "rule_localized": True,
                             "wsi_dicom_bench": "passed" if advisory else "failed"},
        "expected_unaffected_rules": sorted(intrinsic - set(expected) - cascades),
        "likely_fix_owner": target["likely_fix_owners"][0],
        "mutation_name": spec["mutation_name"],
        "mutation_parameters": spec["mutation_parameters"],
        "operational_severity": target["operational_severity"],
        "requirement_ids": spec["requirement_ids"],
        "source_control_ids": [spec["control"]],
        "source_control_sha256": source_digest,
        "target_rule_family": expected[0],
        "adjudicated_cascade_rules": sorted(cascades),
        "v7_observation": STATEMENT_OBSERVATIONS.name,
        "v7_status": "candidate_readjudicated",
    }
    if advisory:
        value["expected_advisory_rules"] = expected
        value["expected_advisory_contains"] = spec["expected_advisory_contains"]
        value["expected_unaffected_rules"] = sorted(intrinsic - set(expected))
    return value


def _json_draft_case(spec: dict, sources: dict[str, dict]) -> dict:
    source = sources[spec["source_control_id"]]
    citation = copy.deepcopy(spec["citation"])
    citation["url"] = citation["url"].replace(f"/{DICOM_EDITION}/", "/current/")
    document_builder = spec.get("document_builder", "json_statement_cases.build_document")
    if document_builder not in {
        "json_statement_cases.build_document", "jpip_statement_cases.build_document",
    }:
        raise ValueError(f"unsupported JSON document builder: {document_builder}")

    return {
        "adjudicated_cascade_rules": spec["expected_cascades"],
        "adjudication_rationale": spec["rationale"],
        "case_id": spec["case_id"],
        "cohort": "dicom-json-statement-evaluation-v1",
        "dicom_citation": citation,
        "document_builder": document_builder,
        "exact_attributes_or_bytes_changed": spec["changed"],
        "expected_failing_rules": [_expected_rule_id(rule) for rule in spec["expected"]],
        "expected_outcome": {"rule_localized": True, "wsi_dicom_bench": "failed"},
        "requirement_ids": spec["requirement_ids"],
        "source_control_ids": [spec["source_control_id"]],
        "source_control_sha256": source["sha256"],
        "transfer_syntax": spec.get("transfer_syntax", json_statement_cases.TRANSFER_SYNTAX),
        **({"json_operation": spec["operation"]} if "operation" in spec else {}),
        "v7_status": "needs_candidate_adjudication",
    }


def _http_draft_case(spec: dict, observation: dict) -> dict:
    target = spec["expected_check"]
    failed = set(observation["failed_checks"])
    advisory = spec.get("expected_evidence") == "advisory"
    cascades = set(spec.get("expected_cascade_checks", []))
    advisories = observation["observed_advisories"]
    baseline_advisories = observation.get("baseline_advisories", [])
    advisory_fragment = spec.get("expected_advisory_contains")
    target_advisory = bool(advisories) and (
        advisory_fragment is None
        or (
            any(advisory_fragment in message for message in advisories)
            and not any(advisory_fragment in message for message in baseline_advisories)
        )
    )
    localized = (
        observation["observed_status"] == "passed"
        and target_advisory
        if advisory else
        observation["observed_status"] == "failed" and target in failed
    )
    if (observation["baseline_status"] != "passed"
            or observation["baseline_failed_checks"] or not localized
            or (advisory and failed != cascades)):
        raise ValueError(f"HTTP observation does not localize {spec['case_id']} to {target}")
    return {
        **copy.deepcopy(spec),
        "adjudicated_cascade_checks": sorted(
            cascades if advisory else failed - {target}
        ),
        "expected_advisory_checks": [target] if advisory else [],
        "expected_failing_checks": [] if advisory else [target],
        "v7_observation": HTTP_OBSERVATIONS.name,
        "v7_status": "candidate_readjudicated",
    }


def build_manifest(requirements: dict | None = None, catalog: dict | None = None,
                   observations: dict | None = None,
                   carried_observations: dict | None = None,
                   statement_observations: dict | None = None,
                   http_observations: dict | None = None) -> dict:
    requirements = requirements or load_requirements()
    catalog = catalog or build_catalog(requirements)
    observations = observations or load_mapping_observations()
    carried_observations = carried_observations or load_carried_observations()
    statement_observations = statement_observations or load_statement_observations()
    http_observations = http_observations or load_http_observations()
    frozen = json.loads(V6_MANIFEST.read_text(encoding="utf-8"))
    mutation_sources = [_mutation_source(control) for control in frozen["valid_controls"]]
    valid_controls = [
        *(_new_control(control, "wsi") for control in controls_v7_wsi.CONTROLS),
        *(_new_control(control, "iods") for control in controls_v7_iods.CONTROLS),
        *_deidentification_controls(),
        *_document_file_set_controls(),
        *_signature_controls(),
        *_motion_controls(),
        *_lossy_pathology_controls(),
        *_residual_codec_controls(),
    ]
    source_index = {control["control_id"]: control
                    for control in [*mutation_sources, *valid_controls]}
    new_specs = [*iod_statement_cases.CASES, *basic_image_statement_cases.CASES,
                 *generic_iod_statement_cases.CASES,
                 *metadata_statement_cases.CASES,
                 *motion_statement_cases.CASES, *pathology_statement_cases.CASES,
                 *pixel_structure_statement_cases.CASES,
                 *file_set_statement_cases.CASES,
                 *deidentification_statement_cases.CASES, *parser_statement_cases.CASES,
                 *residual_codestream_cases.CASES,
                 *residual_metadata_statement_cases.CASES, *residual_statement_cases.CASES]
    new_specs.extend(signature_statement_cases.CASES)
    ready = [spec for spec in new_specs
             if spec["case_id"] not in iod_statement_cases.BLOCKED_CASES]
    advisory_ready = [
        spec for spec in ready if spec.get("expected_evidence") == "advisory"
    ]
    failing_ready = [
        spec for spec in ready if spec.get("expected_evidence") != "advisory"
    ]
    coverage = build_statement_coverage(requirements, observations)
    checked = {entry["id"]: _coverage_rules(entry) for entry in requirements["requirements"]
               if entry.get("id")}
    summary_fields = (
        "file_object_checked_statements", "directly_named_statements",
        "file_object_mandatory_statements", "file_object_recommendations",
        "blocked_authored_statements", "duplicate_text_and_rule_mappings",
        "mapped_to_existing_case_statements",
        "uncovered_file_object_statements", "uncovered_with_existing_mutation_family",
        "uncovered_mandatory_file_object_statements", "uncovered_file_object_recommendations",
        "uncovered_requiring_new_mutation_family", "dicomweb_statements_requiring_http_cases",
        "dicomweb_checked_statements", "directly_named_dicomweb_statements",
        "dicom_json_checked_statements", "directly_named_dicom_json_statements",
        "dicom_json_statements_requiring_json_cases",
        "unchecked_statement_scope_pairs", "unchecked_statement_ids",
        "unchecked_by_family",
    )
    carried = [
        _neutralize_case(
            case, checked, observations["cases"],
            carried_observations["cases"][case["case_id"]], source_index, catalog,
        )
        for frozen_case in frozen["evaluation_cases"]
        for case in (_v7_carried_case(frozen_case),)
    ]
    allowed_coercion_case = _allowed_coercion_case(
        next(case for case in frozen["evaluation_cases"]
             if case["case_id"] == ALLOWED_COERCION_CASE_ID),
        source_index,
    )
    core_profile_cases = [
        case for case in carried if case.get("validation_profile") == "core"
    ]
    candidate_gap_cases = [
        case for case in carried if case.get("v7_status") == "candidate_detection_gap"
    ]
    evaluation_cases = [
        *(case for case in carried
          if case.get("validation_profile") != "core"
          and case.get("v7_status") != "candidate_detection_gap"),
        *(_draft_case(
            spec, source_index, catalog, statement_observations["cases"][spec["case_id"]]
        ) for spec in failing_ready),
    ]
    catalog_rules = {rule["rule_id"] for rule in catalog["rules"]}
    outside_catalog: dict[str, list[str]] = defaultdict(list)
    for case in evaluation_cases:
        for rule in case["expected_failing_rules"]:
            if rule not in catalog_rules:
                outside_catalog[rule].append(case["case_id"])
    return {
        "schema_version": SCHEMA_VERSION,
        "challenge_id": CHALLENGE_ID,
        "status": "draft_unfrozen",
        "title": "WSI-DICOM Negative Bench v7 draft: pathology DICOM 2026d",
        "dicom_edition": DICOM_EDITION,
        "protocol": PROTOCOL.name,
        "rule_catalog": {"catalog_version": CATALOG_VERSION,
                         "path": f"rules/{CATALOG.name}"},
        "requirement_catalog": {"path": f"rules/{REQUIREMENTS.name}",
                                "sha256": sha256_file(REQUIREMENTS)},
        "expectation_provenance": {
            "frozen": False,
            "candidate": {"version": "wsi-dicom 0.9.0", "sha256": None,
                          "rule_set_id": "wsi-dicom-general-v4"},
            "remaining_work": (
                "Adjudicate the new statement cases against the candidate that will be frozen, "
                "resolve or retain every statement-ledger blocker, then write the profile and "
                "expected-results lock."
            ),
        },
        "statement_coverage": {key: coverage[key] for key in summary_fields}
                              | {"path": COVERAGE.name},
        "freeze_gate": {
            "status": ("ready_with_known_policy_failure"
                       if coverage["unchecked_statement_scope_pairs"] else "ready"),
            "unchecked_statement_scope_pairs":
                coverage["unchecked_statement_scope_pairs"],
            "unchecked_statement_ids": coverage["unchecked_statement_ids"],
            "unchecked_by_family": coverage["unchecked_by_family"],
            "reason": (
                "Every checked statement has evidence. The Unchecked statement/scope pairs are "
                "frozen as a known acceptance-policy failure, not an infrastructure blocker."
                if coverage["unchecked_statement_scope_pairs"] else
                "Every checked statement has evidence and no Unchecked statement/scope pair remains."
            ),
        },
        "tool_limits": TOOL_LIMITS,
        "resource_limits": {**frozen["resource_limits"], "max_controls": 80,
                            "max_cases": 1200},
        "valid_controls": valid_controls,
        "mutation_sources": mutation_sources,
        "carried_expectations_outside_v7_catalog": {
            rule: sorted(case_ids) for rule, case_ids in sorted(outside_catalog.items())
        },
        "development_cases": frozen["development_cases"],
        "blocked_cases": [{
            "case_id": spec["case_id"],
            "reason": iod_statement_cases.BLOCKED_CASES[spec["case_id"]],
            "requirement_ids": spec["requirement_ids"],
        } for spec in new_specs if spec["case_id"] in iod_statement_cases.BLOCKED_CASES],
        "evaluation_cases": evaluation_cases,
        "core_profile_evaluation_cases": core_profile_cases,
        "candidate_gap_cases": candidate_gap_cases,
        "advisory_cases": [
            allowed_coercion_case,
            *(_draft_case(
                spec, source_index, catalog,
                statement_observations["cases"][spec["case_id"]],
            ) for spec in advisory_ready),
        ],
        "json_evaluation_cases": [
            _json_draft_case(spec, source_index)
            for spec in [*json_statement_cases.CASES, *jpip_statement_cases.CASES]
        ],
        "http_evaluation_cases": [
            _http_draft_case(spec, http_observations["cases"][spec["case_id"]])
            for spec in http_statement_cases.CASES
        ],
        "compound_cases": [],
    }


def write_draft(candidate: Path | None = None) -> None:
    if candidate is not None:
        _write_json(REQUIREMENTS, snapshot_requirements(candidate))
    requirements = load_requirements()
    catalog = build_catalog(requirements)
    if candidate is not None:
        _write_json(OBSERVATIONS, observe_existing_mappings(candidate))
        _write_json(CARRIED_OBSERVATIONS, observe_carried_cases(candidate, catalog))
        _write_json(STATEMENT_OBSERVATIONS, observe_statement_cases(candidate))
        _write_json(
            HTTP_OBSERVATIONS,
            http_statement_runner.observe_cases(candidate, http_statement_cases.CASES),
        )
    observations = load_mapping_observations()
    carried_observations = load_carried_observations()
    statement_observations = load_statement_observations()
    http_observations = load_http_observations()
    _write_json(CATALOG, catalog)
    _write_json(COVERAGE, build_statement_coverage(requirements, observations))
    _write_json(
        MANIFEST,
        build_manifest(
            requirements, catalog, observations, carried_observations,
            statement_observations,
            http_observations,
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.check:
            requirements = load_requirements()
            observations = load_mapping_observations()
            carried_observations = load_carried_observations()
            statement_observations = load_statement_observations()
            http_observations = load_http_observations()
            expected = ((CATALOG, build_catalog(requirements)),
                        (COVERAGE, build_statement_coverage(requirements, observations)),
                        (MANIFEST, build_manifest(
                            requirements,
                            observations=observations,
                            carried_observations=carried_observations,
                            statement_observations=statement_observations,
                            http_observations=http_observations,
                        )))
            for path, document in expected:
                if json.loads(path.read_text(encoding="utf-8")) != document:
                    raise ValueError(f"{path.name} differs from the v7 builder")
        else:
            write_draft(args.candidate)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"v7 draft build failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
