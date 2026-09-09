# WSI-DICOM validation workbench

The workbench evaluates DICOM VL WSI objects with intrinsic checks, bounded pixel
decoding, and independent validators. The current challenge contains 69 authored
negative cases and 14 controls across 18 selected rule families. It does not establish
exhaustive normative coverage, certification, or clinical sensitivity.

Install the package and evaluate one input with an explicit converter executable:

```sh
wsi-dicom-bench-workbench /path/to/dicom \
  --output /new/workbench-evidence \
  --wsi-dicom /absolute/path/to/wsi-dicom \
  --catalog /path/to/wsi-dicom-bench-rules-2026c-v4.json \
  --profile /path/to/wsi-dicom-core-profile-2026c-v2.json
```

Required validators are `dciodvfy`, `dcentvfy`, and `validate_iods`. JPEG,
JPEG 2000, and HTJ2K inputs also require their applicable decoders. Exploratory
`--allow-missing-tools` runs record limitations and cannot satisfy the acceptance gate.

The frozen manifest, protocol, expectation lock, controls, catalogs, and profile are
package resources under `wsi_dicom_bench/negative_bench` and `wsi_dicom_bench/rules`.
Versioned historical paths inside the frozen manifest remain unchanged because the lock
binds their exact bytes; the generator resolves those paths to packaged resources without
rewriting the manifest.

Run the full locked challenge with:

```sh
wsi-dicom-bench challenge run \
  --suite /path/to/manifest-v4.json \
  --wsi-dicom /absolute/path/to/wsi-dicom \
  --output /new/challenge-evidence
```

The command verifies the suite, materializes cases, executes the supplied candidate,
analyzes observations, applies the locked acceptance policy, and seals accepted evidence.
Exit `0` means accepted, `1` means complete evidence violated the policy, and `2` means
execution, integrity, or contract compatibility failed. Check retained evidence without
writing to it using:

```sh
wsi-dicom-bench challenge check --evidence /path/to/evidence
```

Reports retain catalog/profile identities, input and candidate hashes, process outcomes,
commands, validator provenance, and bounded stdout/stderr. Timeouts, crashes, launch
errors, missing mandatory checks or tools, invalid JSON, truncation, and unmapped checks
are execution failures and never count as detection. A negative case must fail every
expected rule and its declared domain; extra intrinsic failures require an authored
cascade adjudication. Every control must pass all required validators.

The retained baseline detected and localized 69/69 defects, accepted 14/14 controls,
and had no execution failures or unmapped findings. Engineered cases are not a prevalence
sample. Source fidelity, calibrated color accuracy, sparse tiling, all compressed 16-bit
combinations, DICOMweb behavior, and clinical utility remain outside this challenge.
