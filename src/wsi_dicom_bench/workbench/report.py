"""Workbench report assembly, verdicts, and summaries."""

from __future__ import annotations

import argparse
from pathlib import Path

from wsi_dicom_bench.file_digest import sha256_file

from .catalog import DOMAINS, catalog_index
from .contract import doctor_contract_errors, validation_contract_errors
from .dicom_facts import inspect_dicom_set
from .execution import WorkbenchError
from .tool_provenance import software_inventory


STATUS_PRIORITY = {"execution_error": 4, "failed": 3, "passed": 2, "skipped": 1}
INTRINSIC_KINDS = {"intrinsic", "intrinsic_set", "independent_decoder"}
EXTERNAL_KINDS = {"independent_validator"}


def map_findings(validation: dict, catalog: dict) -> list[dict]:
    """Attach catalog citations, severity, and ownership to validation checks."""
    index = catalog_index(catalog)
    findings = []
    for check in validation.get("checks", []):
        check_name = str(check.get("name", ""))
        rule = index.get(check_name)
        execution = check.get("execution")
        status = check.get("status", "failed")
        if status == "failed" and isinstance(execution, dict) and execution.get("failure"):
            status = "execution_error"
        finding = {
            "check_name": check_name,
            "path": check.get("path"),
            "status": status,
            "execution": execution,
            "command": list(check.get("command") or []),
            "message": str(check.get("message", "")),
            "stdout": str(check.get("stdout", "")),
            "stderr": str(check.get("stderr", "")),
        }
        if rule is None:
            finding.update(
                {
                    "catalog_status": "unmapped",
                    "rule_id": None,
                    "rule_kind": None,
                    "primary_domain": "conformance",
                    "clinical_severity": None,
                    "operational_severity": None,
                    "likely_fix_owners": [],
                    "citations": [],
                }
            )
        else:
            finding.update(
                {
                    "catalog_status": "mapped",
                    "rule_id": rule["rule_id"],
                    "rule_kind": rule["rule_kind"],
                    "primary_domain": rule["primary_domain"],
                    "clinical_severity": rule["clinical_severity"],
                    "clinical_severity_rationale": rule["clinical_severity_rationale"],
                    "operational_severity": rule["operational_severity"],
                    "operational_severity_rationale": rule[
                        "operational_severity_rationale"
                    ],
                    "likely_fix_owners": list(rule["likely_fix_owners"]),
                    "citations": list(rule["citations"]),
                }
            )
        findings.append(finding)
    return findings


def summarize_domains(findings: list[dict]) -> dict[str, dict]:
    """Summarize rule outcomes in the five workbench domains."""
    summaries = {}
    for domain in sorted(DOMAINS):
        selected = [finding for finding in findings if finding["primary_domain"] == domain]
        statuses = [str(finding["status"]) for finding in selected]
        unmapped = sum(finding["catalog_status"] == "unmapped" for finding in selected)
        if not selected:
            status = "not_evaluated"
        elif "execution_error" in statuses:
            status = "execution_error"
        elif unmapped or "failed" in statuses:
            status = "failed"
        elif "passed" in statuses:
            status = "passed"
        else:
            status = "skipped"
        summaries[domain] = {
            "status": status,
            "finding_count": len(selected),
            "passed": statuses.count("passed"),
            "failed": statuses.count("failed"),
            "execution_errors": statuses.count("execution_error"),
            "skipped": statuses.count("skipped"),
            "unmapped": unmapped,
        }
    return summaries


def validator_comparison(findings: list[dict]) -> dict:
    """Compare intrinsic/decoder findings with each independent validator."""
    intrinsic_findings = [
        finding for finding in findings if finding.get("rule_kind") in INTRINSIC_KINDS
    ]
    external_findings = [
        finding for finding in findings if finding.get("rule_kind") in EXTERNAL_KINDS
    ]
    intrinsic = aggregate_status(intrinsic_findings)
    external: dict[str, str] = {}
    for check_name in sorted({finding["check_name"] for finding in external_findings}):
        external[check_name] = aggregate_status(
            [finding for finding in external_findings if finding["check_name"] == check_name]
        )
    evaluated_external = [status for status in external.values() if status in {"passed", "failed"}]
    disagreement = (
        intrinsic in {"passed", "failed"}
        and bool(evaluated_external)
        and any(status != intrinsic for status in evaluated_external)
    )
    return {
        "intrinsic": intrinsic,
        "external": external,
        "disagreement": disagreement,
        "interpretation": (
            "adjudication_required"
            if disagreement
            else "no_aggregate_disagreement_observed"
        ),
    }


def aggregate_status(findings: list[dict]) -> str:
    statuses = [str(finding.get("status", "failed")) for finding in findings]
    if not statuses:
        return "not_evaluated"
    if any(finding.get("catalog_status") == "unmapped" for finding in findings):
        return "failed"
    return max(statuses, key=lambda status: STATUS_PRIORITY.get(status, 4))


def build_report(
    args: argparse.Namespace,
    catalog: dict,
    profile: dict | None,
    doctor: dict,
    validation: dict,
    doctor_execution: dict,
    validation_execution: dict,
) -> dict:
    doctor_errors = doctor_contract_errors(doctor)
    contract_errors = list(doctor_errors)
    validation_errors = validation_contract_errors(validation, catalog, profile is not None)
    contract_errors.extend(validation_errors)
    for name, execution in (("doctor", doctor_execution), ("validation", validation_execution)):
        if execution.get("document_error"):
            contract_errors.append(f"{name}: {execution['document_error']}")
    findings = [] if validation_errors else map_findings(validation, catalog)
    domains = summarize_domains(findings)
    comparison = validator_comparison(findings)
    slide = {"slide_id": None, "instance_count": 0, "instances": []}
    software = {}
    if not contract_errors:
        try:
            software = software_inventory(args, doctor)
            slide = inspect_dicom_set([Path(path) for path in validation["files"]])
        except (WorkbenchError, OSError, ValueError) as exc:
            contract_errors.append(f"report enrichment failed: {exc}")
    failed_findings = sum(finding["status"] == "failed" for finding in findings)
    unmapped_findings = sum(
        finding["catalog_status"] == "unmapped" for finding in findings
    )
    if (
        contract_errors
        or doctor_execution["returncode"] != 0
        or validation_execution["returncode"] not in {0, 1}
        or any(finding["status"] == "execution_error" for finding in findings)
    ):
        status = "execution_error"
    elif failed_findings or unmapped_findings or validation_execution["returncode"] == 1:
        status = "failed"
    else:
        status = "passed"
    return {
        "schema_version": "wsi-dicom-bench-workbench-report-v2",
        "contract_errors": contract_errors,
        "status": status,
        "catalog": {
            "version": catalog["catalog_version"],
            "dicom_edition": catalog["dicom_edition"],
            "path": str(args.catalog),
            "sha256": sha256_file(args.catalog),
        },
        "profile": (
            {
                "id": profile["profile_id"],
                "version": profile["profile_version"],
                "dicom_edition": profile["dicom_edition"],
                "path": str(args.profile),
                "sha256": sha256_file(args.profile),
            }
            if profile is not None
            else None
        ),
        "evaluation_policy": {
            "strict_external_tools": not args.allow_missing_tools,
            "max_pixel_frames_per_transfer_syntax": args.max_pixel_frames,
            "command_timeout_secs": args.command_timeout_secs,
            "evaluation_timeout_secs": args.evaluation_timeout_secs,
        },
        "software": software,
        "slide": slide,
        "domains": domains,
        "findings": findings,
        "validator_comparison": comparison,
        "doctor": doctor,
        "execution": {
            "doctor": doctor_execution,
            "validation": validation_execution,
        },
        "limitations": _limitations(doctor if not doctor_errors else {"tools": []}, findings),
    }


def _limitations(doctor: dict, findings: list[dict]) -> dict:
    return {
        "unavailable_tools": [
            {
                "name": tool.get("name"),
                "status": tool.get("status"),
                "required": tool.get("required"),
                "message": tool.get("message"),
            }
            for tool in doctor.get("tools", [])
            if tool.get("status") != "available"
        ],
        "skipped_checks": [
            {
                "check_name": finding["check_name"],
                "path": finding["path"],
                "message": finding["message"],
            }
            for finding in findings
            if finding["status"] == "skipped"
        ],
        "unmapped_checks": sorted(
            {
                finding["check_name"]
                for finding in findings
                if finding["catalog_status"] == "unmapped"
            }
        ),
        "source_pixel_fidelity": "not_evaluated_by_this_dicom_only_entry_point",
        "dicomweb_receiver_behavior": "not_evaluated_by_this_entry_point",
    }


def render_summary(report: dict) -> str:
    slide = report["slide"]
    lines = [
        "# WSI-DICOM Bench workbench report",
        "",
        f"- Status: `{report['status']}`",
        f"- Slide: `{slide['slide_id']}`",
        f"- DICOM instances: {slide['instance_count']}",
        f"- Rule catalog: `{report['catalog']['version']}`",
        f"- DICOM edition: `{report['catalog']['dicom_edition']}`",
        f"- Core profile: `{report['profile']['id'] if report['profile'] else 'not selected'}`",
    ]
    if report["contract_errors"]:
        lines.extend(["", "Execution errors:"])
        lines.extend(f"- {error}" for error in report["contract_errors"])
    lines.extend([
        "",
        "## Domain results",
        "",
        "| Domain | Status | Passed | Failed | Skipped | Unmapped |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ])
    for domain, summary in sorted(report["domains"].items()):
        lines.append(
            f"| {domain} | {summary['status']} | {summary['passed']} | "
            f"{summary['failed']} | {summary['skipped']} | {summary['unmapped']} |"
        )
    comparison = report["validator_comparison"]
    lines.extend(
        [
            "",
            "## Independent validator comparison",
            "",
            f"- Intrinsic/decoder aggregate: `{comparison['intrinsic']}`",
            f"- Aggregate disagreement: `{str(comparison['disagreement']).lower()}`",
            "",
            "| Validator | Status |",
            "| --- | --- |",
        ]
    )
    for validator, status in comparison["external"].items():
        lines.append(f"| {validator} | {status} |")
    lines.extend(
        [
            "",
            "## Explicit limitations",
            "",
            f"- Source pixel fidelity: `{report['limitations']['source_pixel_fidelity']}`",
            f"- DICOMweb receiver behavior: `{report['limitations']['dicomweb_receiver_behavior']}`",
            f"- Unavailable or unconfigured tools: {len(report['limitations']['unavailable_tools'])}",
            f"- Skipped checks: {len(report['limitations']['skipped_checks'])}",
            f"- Unmapped checks: {len(report['limitations']['unmapped_checks'])}",
            "",
        ]
    )
    return "\n".join(lines)
