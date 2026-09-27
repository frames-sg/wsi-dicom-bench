"""Single namespace for the modular GDC WSI converter benchmark harness."""

from __future__ import annotations

from wsi_dicom_bench.gdc.cli import default_python_command, main, parse_args
from wsi_dicom_bench.gdc.commands import (
    build_wsi_dicom_command,
    build_wsi_dicom_profile_command,
    build_wsidicomizer_command,
    command_for_tool,
)
from wsi_dicom_bench.gdc.discovery import (
    discover_gdc_slides,
    manifest_entry_for_slide,
    parse_manifest,
    read_slide_metadata,
    select_slides,
    slide_to_json,
)
from wsi_dicom_bench.gdc.environment import (
    cargo_package_version,
    collect_environment,
    command_output,
    host_accelerator_info,
    python_package_version,
)
from wsi_dicom_bench.gdc.models import (
    PROFILE_CHOICES,
    SCOPE_CHOICES,
    SUPPORTED_SUFFIXES,
    TOOL_CHOICES,
    ManifestEntry,
    Slide,
    safe_slug,
    split_command,
)
from wsi_dicom_bench.gdc.outputs import (
    collect_dicom_outputs,
    count_output_files,
    dicom_metadata_from_dataset,
)
from wsi_dicom_bench.gdc.preflight import (
    evaluate_device_preflight,
    preflight_failure_row,
    run_device_preflight,
)
from wsi_dicom_bench.gdc.reporting import (
    append_jsonl,
    attach_result_context,
    average_passed_seconds,
    completed_result_keys,
    format_seconds,
    format_speedup,
    has_rows_for_cell,
    infer_result_label,
    read_jsonl,
    render_markdown_summary,
    result_label_sort_key,
    rows_from_result_dirs,
    status_summary,
    write_csv,
    write_json,
    write_planned_commands,
)
from wsi_dicom_bench.gdc.runner import run_command
from wsi_dicom_bench.gdc.trial import benchmark_trial
from wsi_dicom_bench.gdc.validation import (
    first_text_line,
    profile_metric,
    read_profile_report,
    validate_output,
    validation_failure_message,
)


if __name__ == "__main__":
    raise SystemExit(main())
