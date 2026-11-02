"""Independent-validator and decoder evidence for every frozen v7 file input.

Candidate-native expectation checking remains in the specialized v7 diagnostic.  This adapter
runs the same materialized file controls and cases through the full workbench so PATH-visible
independent validators and bench-owned decoders remain part of the retained challenge evidence.
JSON and HTTP cases use their specialized harnesses and are intentionally absent here.
"""

from __future__ import annotations

import copy
import concurrent.futures
import hashlib
import importlib.resources
import json
import os
from pathlib import Path

from wsi_dicom_bench.file_digest import sha256_file
from wsi_dicom_bench.path_identifiers import require_portable_identifier
from wsi_dicom_bench.workbench.catalog import load_catalog, validate_catalog

from .run import ChallengeRunError, _run_one_input


SCHEMA = "wsi-dicom-negative-bench-v7-file-evaluation-v1"
INPUT_SCHEMA = "wsi-dicom-negative-bench-v7-file-evaluation-input-v1"
MANIFEST_SCHEMA = "wsi-dicom-negative-bench-manifest-v7"
CORE_CATALOG_VERSION = "wsi-dicom-bench-rules-v7-core"
CORE_CATALOG_NAME = f"{CORE_CATALOG_VERSION}.json"
WORKERS = 4
STANDARD_PATH_ENV = "WSI_DICOM_BENCH_DICOM_VALIDATOR_STANDARD_PATH"
EXPECTED_COUNTS = {
    "valid-control": 66,
    "general-file": 697,
    "core-file": 3,
    "advisory-file": 3,
}
CORE_RULES = {
    "intrinsic-wsi-dicom-2026c-clinical-identity-set":
        "intrinsic-wsi-dicom-clinical-identity-set",
    "intrinsic-wsi-dicom-2026c-core-image-profile":
        "intrinsic-wsi-dicom-core-image-profile",
    "intrinsic-wsi-dicom-2026c-optical-path-structure":
        "intrinsic-wsi-dicom-optical-path-structure",
    "intrinsic-wsi-dicom-2026c-specimen-container":
        "intrinsic-wsi-dicom-specimen-container",
}
CORE_EXCLUDED_CHECKS = frozenset({
    "intrinsic-wsi-dicom-bulk-annotations",
    "intrinsic-wsi-dicom-key-object-selection",
    "intrinsic-wsi-dicom-parametric-map",
    "intrinsic-wsi-dicom-segmentation",
    "intrinsic-wsi-dicom-structured-report",
    "intrinsic-wsi-dicom-synchronization",
})


class FileEvaluationError(RuntimeError):
    """The external file evaluation is incomplete or internally inconsistent."""


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise FileEvaluationError(f"cannot read file-evaluation JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise FileEvaluationError(f"file-evaluation JSON must be an object: {path}")
    return value


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _document_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def derive_core_catalog(base: dict) -> dict:
    """Derive the exact core-v5 rule contract from the locked v7 general catalog."""
    validate_catalog(base)
    if (
        base.get("catalog_version") != "wsi-dicom-bench-rules-v7"
        or base.get("dicom_edition") != "2026d"
    ):
        raise FileEvaluationError("core catalog derivation needs the locked 2026d v7 catalog")
    rules_root = Path(str(importlib.resources.files("wsi_dicom_bench.rules")))
    source_path = rules_root / "wsi-dicom-bench-rules-2026c-v6.json"
    source = load_catalog(source_path)
    by_id = {rule["rule_id"]: rule for rule in source["rules"]}
    supplements = []
    for old, new in sorted(CORE_RULES.items(), key=lambda item: item[1]):
        rule = by_id.get(old)
        if rule is None or rule.get("check_names") != [old]:
            raise FileEvaluationError(f"core supplement source rule is missing or changed: {old}")
        updated = copy.deepcopy(rule)
        updated["rule_id"] = new
        updated["check_names"] = [new]
        updated["applicability"] = updated["applicability"].replace(
            "public 2026c core profile", "candidate 2026d core profile"
        )
        for citation in updated["citations"]:
            citation["edition"] = "2026d"
        supplements.append(updated)
    removed = [
        rule for rule in base["rules"]
        if CORE_EXCLUDED_CHECKS.intersection(rule["check_names"])
    ]
    removed_checks = {
        check for rule in removed for check in rule["check_names"]
        if check in CORE_EXCLUDED_CHECKS
    }
    if removed_checks != CORE_EXCLUDED_CHECKS or len(removed) != len(CORE_EXCLUDED_CHECKS):
        raise FileEvaluationError("locked v7 catalog core exclusions changed")
    removed_ids = sorted(rule["rule_id"] for rule in removed)
    supplemental = [
        {"rule_id": rule["rule_id"], "sha256": _document_digest(rule)}
        for rule in supplements
    ]
    derived = copy.deepcopy(base)
    derived.update({
        "catalog_version": CORE_CATALOG_VERSION,
        "validation_profile": "core",
        "candidate_rule_set_id": "wsi-dicom-core-profile-v5",
        "scope": "DICOM pathology-slide file objects evaluated by the v7 core profile",
        "coverage_scope": (
            "The core-v5 subset of the locked v7 general catalog plus exactly its four "
            "core-only WSI checks."
        ),
        "core_derivation": {
            "base_catalog_version": base["catalog_version"],
            "removed_rule_ids": removed_ids,
            "supplemental_rules": supplemental,
        },
        "rules": [
            *(rule for rule in derived["rules"] if rule["rule_id"] not in removed_ids),
            *supplements,
        ],
    })
    validate_catalog(derived)
    return derived


def _write_core_catalog(base_path: Path, destination: Path) -> tuple[str, str]:
    base = _read(base_path)
    derived = derive_core_catalog(base)
    if destination.exists():
        raise FileEvaluationError(f"derived core catalog already exists: {destination}")
    _write(destination, derived)
    return sha256_file(base_path), sha256_file(destination)


def _file_inputs(manifest: dict, package: Path) -> list[dict]:
    collections = (
        ("valid-control", "general", "valid_controls", "control_id"),
        ("general-file", "general", "evaluation_cases", "case_id"),
        ("core-file", "core", "core_profile_evaluation_cases", "case_id"),
        ("advisory-file", "general", "advisory_cases", "case_id"),
    )
    inputs = []
    seen = set()
    for cohort, profile, field, key in collections:
        items = manifest.get(field)
        if not isinstance(items, list) or len(items) != EXPECTED_COUNTS[cohort]:
            raise FileEvaluationError(
                f"v7 {field} count differs: expected {EXPECTED_COUNTS[cohort]}"
            )
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise FileEvaluationError(f"v7 {field}[{index}] is not an object")
            try:
                identifier = require_portable_identifier(
                    item.get(key), f"v7 {field}[{index}].{key}"
                )
            except ValueError as error:
                raise FileEvaluationError(str(error)) from error
            if identifier in seen:
                raise FileEvaluationError(f"v7 file-evaluation ID is duplicated: {identifier}")
            seen.add(identifier)
            if cohort == "valid-control":
                dicom = (
                    package / "controls" / identifier
                    if "package_paths" in item
                    else package / "controls" / f"{identifier}.dcm"
                )
            else:
                dicom = package / "cases" / identifier / "input"
            inputs.append({
                "id": identifier,
                "cohort": cohort,
                "validation_profile": profile,
                "dicom": dicom,
            })
    return inputs


def _limits(manifest: dict) -> dict:
    limits = manifest.get("resource_limits")
    if not isinstance(limits, dict):
        raise FileEvaluationError("v7 manifest resource_limits must be an object")
    for key in (
        "max_command_output_bytes", "max_pixel_frames", "command_timeout_secs",
        "case_timeout_secs",
    ):
        value = limits.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise FileEvaluationError(f"v7 resource_limits.{key} must be positive")
    return limits


def _relative_file(package: Path, raw: str, label: str) -> Path:
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        raise FileEvaluationError(f"unsafe {label} path: {raw!r}")
    path = package / relative
    try:
        path.resolve().relative_to(package.resolve())
    except ValueError as error:
        raise FileEvaluationError(f"unsafe {label} path: {raw!r}") from error
    if path.is_symlink() or not path.is_file():
        raise FileEvaluationError(f"{label} is missing or a symlink: {raw}")
    return path


def _input_observation(package: Path, item: dict, execution: dict) -> tuple[dict, dict]:
    report_path = _relative_file(
        package, execution["workbench_report"], f"{item['id']} workbench report"
    )
    report = _read(report_path)
    stdout_path = _relative_file(
        package, execution["launcher_stdout"], f"{item['id']} launcher stdout"
    )
    stderr_path = _relative_file(
        package, execution["launcher_stderr"], f"{item['id']} launcher stderr"
    )
    observation = {
        "schema_version": INPUT_SCHEMA,
        "id": item["id"],
        "cohort": item["cohort"],
        "validation_profile": item["validation_profile"],
        "execution": execution,
        "workbench_report_sha256": sha256_file(report_path),
        "launcher_stdout_sha256": sha256_file(stdout_path),
        "launcher_stderr_sha256": sha256_file(stderr_path),
        "workbench_status": report.get("status"),
        "doctor_tools": report.get("doctor", {}).get("tools", []),
        "decoders": report.get("software", {}).get("bench_decoders", []),
        "validator_provenance":
            report.get("software", {}).get("validators_and_decoders", []),
        "validator_comparison": report.get("validator_comparison", {}),
        "limitations": report.get("limitations", {}),
    }
    return observation, report


def _tool_summary(observations: list[dict]) -> dict:
    tools: dict[str, dict] = {}
    decoders: dict[str, set[str]] = {}
    provenance: dict[str, set[str]] = {}
    for observation in observations:
        for tool in observation["doctor_tools"]:
            name = tool.get("name")
            if not isinstance(name, str) or not name:
                continue
            record = tools.setdefault(name, {"statuses": set(), "required": set()})
            record["statuses"].add(str(tool.get("status")))
            record["required"].add(bool(tool.get("required")))
        for decoder in observation["decoders"]:
            family = decoder.get("family")
            if isinstance(family, str) and family:
                decoders.setdefault(family, set()).add(
                    json.dumps(decoder, sort_keys=True, separators=(",", ":"))
                )
        for tool in observation["validator_provenance"]:
            name = tool.get("name")
            if isinstance(name, str) and name:
                provenance.setdefault(name, set()).add(
                    json.dumps(tool, sort_keys=True, separators=(",", ":"))
                )
    return {
        "validators": {
            name: {
                "statuses": sorted(record["statuses"]),
                "required": sorted(record["required"]),
            }
            for name, record in sorted(tools.items())
        },
        "decoders": {
            family: [json.loads(value) for value in sorted(values)]
            for family, values in sorted(decoders.items())
        },
        "validator_provenance": {
            name: [json.loads(value) for value in sorted(values)]
            for name, values in sorted(provenance.items())
        },
    }


def _validate_required_tool_evidence(tool_evidence: object) -> None:
    if not isinstance(tool_evidence, dict):
        raise FileEvaluationError("v7 file-evaluation tool evidence is missing")
    validators = tool_evidence.get("validators", {})
    for name in ("dciodvfy", "dcentvfy", "validate_iods"):
        record = validators.get(name) if isinstance(validators, dict) else None
        if record != {"statuses": ["available"], "required": [True]}:
            raise FileEvaluationError(f"required independent validator is unavailable: {name}")
    provenance = tool_evidence.get("validator_provenance", {})
    validate = provenance.get("validate_iods") if isinstance(provenance, dict) else None
    if not isinstance(validate, list) or len(validate) != 1:
        raise FileEvaluationError("validate_iods provenance is not stable across inputs")
    runtime = validate[0].get("runtime") if isinstance(validate[0], dict) else None
    packages = runtime.get("packages", {}) if isinstance(runtime, dict) else {}
    definitions = runtime.get("definitions", {}) if isinstance(runtime, dict) else {}
    files = definitions.get("files", []) if isinstance(definitions, dict) else []
    file_names = {
        item.get("path") for item in files if isinstance(item, dict)
        and isinstance(item.get("sha256"), str) and len(item["sha256"]) == 64
    }
    if (
        packages.get("dicom-validator", {}).get("version") != "0.8.3"
        or packages.get("pydicom", {}).get("version") != "3.0.2"
        or definitions.get("edition") != "2026d"
        or not {
            "2026d/json/dict_info.json", "2026d/json/iod_info.json",
            "2026d/json/module_info.json", "2026d/json/uid_info.json",
            "2026d/json/version",
        } <= file_names
    ):
        raise FileEvaluationError("validate_iods runtime or 2026d definitions are not pinned")


def run_file_evaluation(
    package: Path,
    candidate: Path,
    reports_dir: Path,
    dicom_validator_standard_path: Path | None = None,
) -> dict:
    """Run all 769 frozen v7 file inputs through the external-tool workbench."""
    package, candidate, reports_dir = package.resolve(), candidate.resolve(), reports_dir.resolve()
    if reports_dir.exists():
        raise FileEvaluationError(f"file-evaluation reports path already exists: {reports_dir}")
    try:
        reports_dir.relative_to(package)
    except ValueError as error:
        raise FileEvaluationError("file-evaluation reports path must be inside the package") from error
    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise FileEvaluationError(f"candidate is not executable: {candidate}")
    if dicom_validator_standard_path is None:
        raw_standard_path = os.environ.get(STANDARD_PATH_ENV)
        dicom_validator_standard_path = (
            Path(raw_standard_path) if raw_standard_path else Path.home() / "dicom-validator"
        )
    dicom_validator_standard_path = dicom_validator_standard_path.resolve()
    if not dicom_validator_standard_path.is_dir():
        raise FileEvaluationError(
            f"dicom-validator standard path does not exist: {dicom_validator_standard_path}"
        )
    manifest = _read(package / "manifest.json")
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise FileEvaluationError("file evaluation needs a frozen v7 package")
    inputs = _file_inputs(manifest, package)
    limits = _limits(manifest)
    base_catalog = package / "expected-results" / Path(manifest["rule_catalog"]["path"]).name
    if not base_catalog.is_file():
        raise FileEvaluationError(f"locked v7 catalog is missing: {base_catalog}")
    core_catalog = package / "validator-results" / CORE_CATALOG_NAME
    base_digest, core_digest = _write_core_catalog(base_catalog, core_catalog)
    core_derivation = _read(core_catalog)["core_derivation"]
    reports_dir.mkdir(parents=True)
    input_reports = reports_dir / "inputs"
    input_reports.mkdir()
    candidate_before = sha256_file(candidate)
    executions: list[dict | None] = [None] * len(inputs)
    observations: list[dict | None] = [None] * len(inputs)
    try:
        def evaluate(index: int, item: dict) -> tuple[int, dict, dict]:
            catalog = core_catalog if item["validation_profile"] == "core" else base_catalog
            execution = _run_one_input(
                package, candidate, catalog, None, limits, item["id"], item["cohort"],
                item["dicom"], item["validation_profile"], dicom_validator_standard_path,
            )
            observation, _report = _input_observation(package, item, execution)
            _write(input_reports / f"{item['id']}.json", observation)
            return index, execution, observation

        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = [pool.submit(evaluate, index, item) for index, item in enumerate(inputs)]
            for future in concurrent.futures.as_completed(futures):
                index, execution, observation = future.result()
                executions[index] = execution
                observations[index] = observation
    except (ChallengeRunError, OSError, ValueError) as error:
        raise FileEvaluationError(f"v7 file input execution failed: {error}") from error
    if any(item is None for item in executions) or any(item is None for item in observations):
        raise FileEvaluationError("v7 file evaluation did not retain every execution")
    retained_executions = [item for item in executions if item is not None]
    retained_observations = [item for item in observations if item is not None]
    candidate_after = sha256_file(candidate)
    if candidate_after != candidate_before:
        raise FileEvaluationError("candidate binary changed during v7 file evaluation")
    cohort_ids = {
        cohort: [item["id"] for item in inputs if item["cohort"] == cohort]
        for cohort in EXPECTED_COUNTS
    }
    summary = {
        "schema_version": SCHEMA,
        "challenge_id": manifest.get("challenge_id"),
        "status": "complete",
        "workers": WORKERS,
        "candidate_sha256": candidate_before,
        "candidate_sha256_before": candidate_before,
        "candidate_sha256_after": candidate_after,
        "execution_count": len(retained_executions),
        "execution_ids": [item["id"] for item in inputs],
        "cohorts": {
            cohort: {"count": len(identifiers), "ids": identifiers}
            for cohort, identifiers in cohort_ids.items()
        },
        "catalogs": {
            "general": {
                "path": str(base_catalog.relative_to(package)), "sha256": base_digest,
            },
            "core": {
                "path": str(core_catalog.relative_to(package)), "sha256": core_digest,
                "base_catalog_sha256": base_digest,
                "removed_rule_ids": core_derivation["removed_rule_ids"],
                "supplemental_rules": core_derivation["supplemental_rules"],
            },
        },
        "tool_evidence": _tool_summary(retained_observations),
        "known_tool_limits": copy.deepcopy(manifest.get("tool_limits", {})),
        "input_reports": str(input_reports.relative_to(package)),
    }
    _write(reports_dir / "summary.json", summary)
    validate_file_evaluation(package, reports_dir, candidate_before)
    return summary


def validate_file_evaluation(
    package: Path, reports_dir: Path, expected_candidate_sha256: str
) -> dict:
    """Validate the exact identity and retained evidence of a completed file evaluation."""
    package, reports_dir = package.resolve(), reports_dir.resolve()
    try:
        reports_dir.relative_to(package)
    except ValueError as error:
        raise FileEvaluationError("file-evaluation reports path must be inside the package") from error
    if (
        len(expected_candidate_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_candidate_sha256)
    ):
        raise FileEvaluationError("expected candidate SHA-256 is invalid")
    manifest = _read(package / "manifest.json")
    inputs = _file_inputs(manifest, package)
    summary = _read(reports_dir / "summary.json")
    expected_ids = [item["id"] for item in inputs]
    cohort_ids = {
        cohort: [item["id"] for item in inputs if item["cohort"] == cohort]
        for cohort in EXPECTED_COUNTS
    }
    expected_cohorts = {
        cohort: {"count": len(identifiers), "ids": identifiers}
        for cohort, identifiers in cohort_ids.items()
    }
    if (
        summary.get("schema_version") != SCHEMA
        or summary.get("challenge_id") != manifest.get("challenge_id")
        or summary.get("status") != "complete"
        or summary.get("workers") != WORKERS
        or summary.get("candidate_sha256") != expected_candidate_sha256
        or summary.get("candidate_sha256_before") != expected_candidate_sha256
        or summary.get("candidate_sha256_after") != expected_candidate_sha256
        or summary.get("execution_count") != len(inputs)
        or summary.get("execution_ids") != expected_ids
        or summary.get("cohorts") != expected_cohorts
        or summary.get("known_tool_limits") != manifest.get("tool_limits", {})
    ):
        raise FileEvaluationError("v7 file-evaluation summary identity differs")
    catalogs = summary.get("catalogs")
    general_catalog = catalogs.get("general") if isinstance(catalogs, dict) else None
    core_catalog = catalogs.get("core") if isinstance(catalogs, dict) else None
    if not isinstance(general_catalog, dict) or not isinstance(core_catalog, dict):
        raise FileEvaluationError("v7 file-evaluation catalog records are missing")
    base_path = _relative_file(
        package, general_catalog.get("path", ""), "general catalog"
    )
    core_path = _relative_file(
        package, core_catalog.get("path", ""), "core catalog"
    )
    base_digest, core_digest = sha256_file(base_path), sha256_file(core_path)
    expected_core = derive_core_catalog(_read(base_path))
    if (
        _read(core_path) != expected_core
        or general_catalog.get("sha256") != base_digest
        or core_catalog.get("sha256") != core_digest
        or core_catalog.get("base_catalog_sha256") != base_digest
        or core_catalog.get("removed_rule_ids")
        != expected_core["core_derivation"]["removed_rule_ids"]
        or core_catalog.get("supplemental_rules")
        != expected_core["core_derivation"]["supplemental_rules"]
    ):
        raise FileEvaluationError("derived v7 core catalog identity differs")
    input_dir = reports_dir / "inputs"
    expected_files = {reports_dir / "summary.json", *(
        input_dir / f"{identifier}.json" for identifier in expected_ids
    )}
    actual_files = set()
    for path in reports_dir.rglob("*"):
        if path.is_symlink():
            raise FileEvaluationError(f"file-evaluation evidence contains a symlink: {path}")
        if path.is_file():
            actual_files.add(path)
    if actual_files != expected_files:
        raise FileEvaluationError("v7 file-evaluation retained file set differs")
    actual_report_ids = {path.stem for path in input_dir.glob("*.json") if path.is_file()}
    if actual_report_ids != set(expected_ids):
        raise FileEvaluationError("v7 file-evaluation input report IDs differ")
    observations = []
    by_id = {item["id"]: item for item in inputs}
    for identifier in expected_ids:
        path = input_dir / f"{identifier}.json"
        if path.is_symlink():
            raise FileEvaluationError(f"input report is a symlink: {identifier}")
        observation = _read(path)
        item = by_id[identifier]
        execution = observation.get("execution", {})
        if not isinstance(execution, dict):
            raise FileEvaluationError(f"v7 file-evaluation execution is invalid: {identifier}")
        report_path = _relative_file(
            package, execution.get("workbench_report", ""), f"{identifier} workbench report"
        )
        stdout_path = _relative_file(
            package, execution.get("launcher_stdout", ""), f"{identifier} launcher stdout"
        )
        stderr_path = _relative_file(
            package, execution.get("launcher_stderr", ""), f"{identifier} launcher stderr"
        )
        report = _read(report_path)
        expected_catalog = core_digest if item["validation_profile"] == "core" else base_digest
        if (
            observation.get("schema_version") != INPUT_SCHEMA
            or observation.get("id") != identifier
            or observation.get("cohort") != item["cohort"]
            or observation.get("validation_profile") != item["validation_profile"]
            or execution.get("id") != identifier
            or execution.get("cohort") != item["cohort"]
            or execution.get("input") != str(item["dicom"].relative_to(package))
            or execution.get("returncode") not in {0, 1}
            or execution.get("timed_out") is not False
            or observation.get("workbench_report_sha256") != sha256_file(report_path)
            or observation.get("launcher_stdout_sha256") != sha256_file(stdout_path)
            or observation.get("launcher_stderr_sha256") != sha256_file(stderr_path)
            or observation.get("workbench_status") != report.get("status")
            or report.get("schema_version") != "wsi-dicom-bench-workbench-report-v2"
            or report.get("contract_errors") != []
            or report.get("evaluation_policy", {}).get("validation_profile")
            != item["validation_profile"]
            or report.get("catalog", {}).get("sha256") != expected_catalog
            or report.get("software", {}).get("wsi_dicom", {}).get("sha256")
            != expected_candidate_sha256
            or observation.get("doctor_tools") != report.get("doctor", {}).get("tools", [])
            or observation.get("decoders")
            != report.get("software", {}).get("bench_decoders", [])
            or observation.get("validator_provenance")
            != report.get("software", {}).get("validators_and_decoders", [])
            or observation.get("validator_comparison") != report.get("validator_comparison", {})
            or observation.get("limitations") != report.get("limitations", {})
        ):
            raise FileEvaluationError(f"v7 file-evaluation report differs: {identifier}")
        observations.append(observation)
    if summary.get("tool_evidence") != _tool_summary(observations):
        raise FileEvaluationError("v7 file-evaluation tool summary differs")
    _validate_required_tool_evidence(summary.get("tool_evidence"))
    return summary
