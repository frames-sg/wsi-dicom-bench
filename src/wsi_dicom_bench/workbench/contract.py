"""Check compatibility between the selected catalog and emitted validation evidence."""

from pathlib import Path

from .pixel_decode import BENCH_OWNED_CHECKS


DOCTOR_SCHEMA = "wsi-dicom-doctor-report-v1"
VALIDATION_SCHEMA = "wsi-dicom-validation-report-v1"
# The wsi-dicom rule set each catalog was written for. A binary that declares a
# different rule set emits checks the catalog does not map, so the pairing is exact.
RULE_SET_IDS_BY_CATALOG = {
    # Format-coverage runs use catalog v2 with the general profile. Its core rule set is
    # the identifier its binaries declared; no core profile pairs with catalog v2.
    "wsi-dicom-bench-rules-2026c-v2": {
        "core-2026c": "wsi-dicom-core-profile-2026c-v2",
        "general": "wsi-dicom-general-v1",
    },
    "wsi-dicom-bench-rules-2026c-v6": {
        "core-2026c": "wsi-dicom-core-profile-2026c-v4",
        "general": "wsi-dicom-general-v3",
    },
}


def expected_rule_set_id(catalog: object, profile: str) -> str | None:
    """Return the rule set a catalog requires for a profile, or None if it declares none."""
    version = catalog.get("catalog_version") if isinstance(catalog, dict) else None
    return RULE_SET_IDS_BY_CATALOG.get(version, {}).get(profile)


def _schema_errors(document: object, expected: str, kind: str) -> tuple[list[str], bool]:
    """Return schema errors and whether explicit legacy handling was selected."""
    if not isinstance(document, dict):
        return [f"{kind} report must be a JSON object"], False
    if "schema_version" not in document:
        # Compatibility is intentionally limited to the exact unversioned shape
        # validated below. Unknown versioned contracts never fall through here.
        return [], True
    schema = document["schema_version"]
    if schema != expected:
        return [f"unsupported {kind} schema_version {schema!r}"], False
    return [], False


def _record_errors(document: object, field: str, statuses: tuple[str, ...]) -> list[str]:
    if not isinstance(document, dict):
        return [f"{field} report must be a JSON object"]
    records = document.get(field)
    if not isinstance(records, list):
        return [f"{field} must be an array"]
    errors = []
    for index, record in enumerate(records):
        label = f"{field}[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{label} must be an object")
            continue
        if not isinstance(record.get("name"), str) or not record["name"]:
            errors.append(f"{label} name must be a nonempty string")
        if record.get("status") not in statuses:
            errors.append(f"{label} has invalid status {record.get('status')!r}")
        path = record.get("path")
        if path is not None and (not isinstance(path, str) or not path or "\0" in path):
            errors.append(f"{label} path must be a nonempty filename or null")
        command = record.get("command", [])
        if not isinstance(command, list) or any(not isinstance(arg, str) for arg in command):
            errors.append(f"{label} command must be an array of strings")
        if record.get("execution") is not None and not isinstance(record["execution"], dict):
            errors.append(f"{label} execution must be an object or null")
    return errors


def doctor_contract_errors(doctor: object) -> list[str]:
    errors, _legacy = _schema_errors(doctor, DOCTOR_SCHEMA, "doctor")
    errors.extend(
        _record_errors(doctor, "tools", ("available", "missing", "failed", "skipped"))
    )
    return errors


def validation_contract_errors(validation: object, catalog: dict, core: bool) -> list[str]:
    errors, legacy = _schema_errors(validation, VALIDATION_SCHEMA, "validation")
    errors.extend(_record_errors(validation, "checks", ("passed", "failed", "skipped")))
    if errors:
        return errors
    files = validation.get("files")
    if not isinstance(files, list) or not files or any(
        not isinstance(path, str) or not path or "\0" in path for path in files
    ):
        return ["validation files must be a nonempty array of filenames"]
    expected_profile = "core-2026c" if core else "general"
    if validation.get("profile") != expected_profile:
        errors.append(f"binary did not execute selected profile {expected_profile}")
    rule_set_id = expected_rule_set_id(catalog, expected_profile)
    if legacy and "rule_set_id" in validation:
        errors.append("legacy validation report must not declare rule_set_id")
    elif not legacy and rule_set_id is None:
        errors.append(
            f"catalog {catalog.get('catalog_version')!r} declares no selected rule set "
            f"for profile {expected_profile}"
        )
    elif not legacy and validation.get("rule_set_id") != rule_set_id:
        errors.append(
            f"binary did not execute selected rule set {rule_set_id}; "
            f"it declared {validation.get('rule_set_id')!r}"
        )
    checks = validation.get("checks", [])
    known = {name for rule in catalog["rules"] for name in rule["check_names"]}
    for check in checks:
        if check.get("name") in BENCH_OWNED_CHECKS:
            errors.append(
                f"binary emitted bench-owned decoder check {check['name']}; "
                "independent decoding runs in the bench"
            )
        elif check.get("name") not in known:
            errors.append(f"binary emitted an unmapped check: {check.get('name')}")
    # Every instance must have every unconditional intrinsic check. Corpus and
    # decoder rules are conditional and are checked by the evidence release gate.
    required = {
        name for rule in catalog["rules"] if rule["rule_kind"] == "intrinsic"
        for name in rule["check_names"]
    }
    if core:
        for path in validation.get("files", []):
            observed = {
                check.get("name") for check in checks
                if check.get("path") and Path(check["path"]).resolve() == Path(path).resolve()
                and check.get("status") in {"passed", "failed"}
            }
            missing = sorted(required - observed)
            if missing:
                errors.append(f"{path}: missing required checks: {', '.join(missing)}")
    return errors
