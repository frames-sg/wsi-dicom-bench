# Execution contract

The benchmark executes the exact `wsi-dicom` path supplied by `--wsi-dicom` and records
its SHA-256 in the run summary and every workbench report. Candidate validation uses
`doctor --json --strict` followed by `validate <input> --profile core-2026c --json --strict`.
The selected catalog is `wsi-dicom-bench-rules-2026c-v4`; the selected profile is
`wsi-dicom-core-profile-2026c-v2`.

Versioned converter output has these identities:

| Command | `schema_version` | Required rule-set field |
| --- | --- | --- |
| `doctor --json` | `wsi-dicom-doctor-report-v1` | none |
| `validate --profile core-2026c --json` | `wsi-dicom-validation-report-v1` | `rule_set_id: wsi-dicom-core-profile-2026c-v2` |
| `validate --profile general --json` | `wsi-dicom-validation-report-v1` | `rule_set_id: wsi-dicom-general-v1` |

Unknown schemas, a JSON `null` schema, and wrong or missing rule-set identities fail as
compatibility errors. The explicit legacy path accepts only reports where
`schema_version` and `rule_set_id` are both absent. Those reports must still satisfy the
same exact object, array, status, selected-profile, known-check, and required-check rules;
the benchmark does not infer a schema or profile from partial metadata.

Doctor tool statuses are `available`, `missing`, `failed`, and `skipped`. Converter
validation check statuses are `passed`, `failed`, and `skipped`. The workbench uses
`execution_error` when a process timeout, launch error, truncation, invalid JSON, crash,
or other incomplete execution prevents a scientific verdict. Catalog check names and
rule IDs are stable identifiers. Every emitted check must map to the frozen catalog, and
every required per-instance intrinsic check must be present. Required independent tools
are `dciodvfy`, `dcentvfy`, and `validate_iods`; applicable JPEG, JPEG 2000, and HTJ2K
decoders are also mandatory for strict evidence.

The per-input workbench returns `0` for a passed validation, `1` for a completed validation
with findings, and `2` for execution or compatibility failure. Converter command behavior
and exit meanings remain owned by `wsi-dicom`. The challenge command interprets results in
the benchmark context:

| Exit | Meaning |
| --- | --- |
| `0` | Complete evidence satisfies the locked acceptance policy. |
| `1` | Complete evidence violates an expected-failure, control, unaffected-rule, domain, or cascade policy. |
| `2` | Suite integrity, execution, evidence integrity, or converter compatibility failed. |

Rejecting an authored invalid DICOM is an expected successful observation. Missing tools,
checks, mappings, or process evidence never count as detection. Read-only `challenge check`
verifies the generation lock, final seal when present, candidate digest binding, input
digests, and the same acceptance policy without modifying retained evidence.

An accepted new run retains the exact locally installed benchmark wheel inside
`reproduction/wheelhouse`, verifies the installed package bytes against that wheel's
`RECORD`, and seals the wheel with the evidence. `reproduction/requirements.lock` supplies
the hash-pinned `pydicom==3.0.2` acquisition requirement. Install a pinned commit through a
local wheel as shown in the repository README; a Git checkout or nonlocal direct install
cannot create strict reproducible evidence.

The benchmark owns its hashing, JSON, identifier, and process-evidence helpers. The
converter temporarily retains the tested copies needed by its GDC and format-coverage
harnesses. This narrow duplication avoids coupling normal converter operation to the
benchmark and will remain until those converter-owned harnesses no longer need the helpers.
