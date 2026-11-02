"""Run DICOMweb statement cases through the shipped candidate CLI."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .http_origin import HttpOrigin, INSTANCE_UID, SERIES_UID, STORE_PATH, STUDY_UID


SKIPS = {
    "capabilities": "search,metadata,frames,bulkdata,rendered,thumbnail,instance",
    "search": "metadata,frames,bulkdata,rendered,thumbnail,instance",
    "metadata": "search,frames,bulkdata,rendered,thumbnail,instance",
    "search-metadata": "frames,bulkdata,rendered,thumbnail,instance",
    "frames": "search,bulkdata,rendered,thumbnail,instance",
    "rendered": "search,frames,bulkdata,thumbnail,instance",
    "thumbnail": "search,frames,bulkdata,rendered,instance",
    "bulkdata": "search,frames,rendered,thumbnail,instance",
    "instance": "search,frames,bulkdata,rendered,thumbnail",
    "instance-bulkdata": "search,frames,rendered,thumbnail",
    "search-instance": "frames,bulkdata,rendered,thumbnail",
    "search-frames": "bulkdata,rendered,thumbnail,instance",
    "store": "search,metadata,frames,bulkdata,rendered,thumbnail,instance",
}


def run_scenario(
    candidate: Path,
    scenario: str,
    *,
    profile: str = "capabilities",
    thumbnail: bool = False,
    probe_error_responses: bool = False,
    allow_store: bool = False,
) -> dict:
    skip = SKIPS[profile]
    if thumbnail:
        skip = skip.replace(",thumbnail", "")
    with HttpOrigin(scenario) as origin:
        command = [
            str(candidate),
            "dicomweb",
            origin.base_url,
            "--study",
            STUDY_UID,
            "--series",
            SERIES_UID,
            "--instance",
            INSTANCE_UID,
            "--skip",
            skip,
            "--timeout-secs",
            "2",
            "--max-requests",
            "192"
            if profile.startswith("search")
            else "64"
            if profile == "rendered"
            else "32",
            "--json",
        ]
        if probe_error_responses:
            command.append("--probe-error-responses")
        if allow_store:
            command.extend(("--allow-store", str(STORE_PATH)))
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        report = json.loads(result.stdout)
        report["execution"] = {
            "return_code": result.returncode,
            "stderr": result.stderr,
            "requests": [list(request) for request in origin.requests],
        }
        return report


def check(report: dict, name: str) -> dict:
    return next(item for item in report["checks"] if item["name"] == name)


def observe_case(candidate: Path, case: dict) -> dict:
    """Return positive-baseline and broken-response evidence for one case."""
    options = case.get("options", {})
    baseline = run_scenario(
        candidate,
        case.get("baseline_scenario", "capabilities"),
        **options,
    )
    observed = run_scenario(candidate, case["scenario"], **options)
    target = case["expected_check"]
    return {
        "baseline_status": check(baseline, target)["status"],
        "baseline_advisories": check(baseline, target).get("advisories", []),
        "observed_status": check(observed, target)["status"],
        "observed_message": check(observed, target)["message"],
        "observed_advisories": check(observed, target).get("advisories", []),
        "failed_checks": sorted(
            item["name"] for item in observed["checks"] if item["status"] == "failed"
        ),
        "baseline_failed_checks": sorted(
            item["name"] for item in baseline["checks"] if item["status"] == "failed"
        ),
        "request_count": len(observed["execution"]["requests"]),
        "candidate_contract": {
            "schema_version": observed["schema_version"],
            "dicom_edition": observed["dicom_edition"],
        },
    }


def observe_cases(candidate: Path, cases) -> dict:
    """Builder API: observe an explicit sequence of HTTP cases."""
    observations = {case["case_id"]: observe_case(candidate, case) for case in cases}
    contracts = {tuple(item["candidate_contract"].items()) for item in observations.values()}
    if len(contracts) != 1:
        raise ValueError("HTTP observations use different candidate contracts")
    contract = dict(next(iter(contracts)))
    return {
        "schema_version": "wsi-dicom-http-statement-observations-v7-draft",
        "candidate_report_schema_version": contract["schema_version"],
        "dicom_edition": contract["dicom_edition"],
        "cases": observations,
    }
