# WSI-DICOM Bench

[![CI](https://github.com/frames-sg/wsi-dicom-bench/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/frames-sg/wsi-dicom-bench/actions/workflows/ci.yml?query=branch%3Amain)

[DICOM whole-slide workflow](https://frames-sg.com/dicom-whole-slide-conversion/)

`wsi-dicom-bench` is the controlled-failure benchmark for an explicitly supplied
[`wsi-dicom`](https://github.com/frames-sg/wsi-dicom) executable. It owns frozen
controls, deterministic mutations, locked expectations, orchestration, analysis,
and acceptance policy. Installing or running the converter does not require this
package.

Build and install the pinned benchmark commit as a local wheel, then run the locked suite.
Keeping the wheel at its installation path lets the benchmark retain that exact distribution
inside the evidence package:

```sh
python -m pip wheel --no-deps \
  "git+https://github.com/frames-sg/wsi-dicom-bench@968b25ded082a7e7e0a20d4ca5b3283fb636588b" \
  --wheel-dir ./benchmark-wheelhouse
python -m pip install ./benchmark-wheelhouse/wsi_dicom_bench-*.whl "dicom-validator==0.8.3"
mkdir -p .dicom-validator-init
validate_iods --edition 2026d .dicom-validator-init
suite_path="$(python -c 'import importlib.resources; print(importlib.resources.files("wsi_dicom_bench.negative_bench").joinpath("manifest-v7.json"))')"
wsi-dicom-bench challenge run \
  --suite "$suite_path" \
  --wsi-dicom /absolute/path/to/wsi-dicom \
  --output /new/evidence-directory
```

V7 requires `dciodvfy`, `dcentvfy`, and `validate_iods` on `PATH`. The setup above prepares
the validator's DICOM 2026d definitions at its default `~/dicom-validator` location.

The locked `manifest-v7.json` is an installed package resource. Build the candidate with
`--features dicomweb` to include the JSON and HTTP commands. V7 requires DICOM edition 2026d,
general rule set `wsi-dicom-general-v4`, core rule set `wsi-dicom-core-profile-v5`, and the
`wsi-dicom-dicomweb-report-v1` HTTP report contract. An existing evidence directory can be
checked without modifying it:

```sh
wsi-dicom-bench challenge check --evidence /path/to/evidence
```

Exit code `0` means the locked acceptance policy passed, `1` means a complete
evaluation violated the policy, and `2` means execution, integrity, or converter
contract compatibility failed. Invalid DICOM rejection is an expected successful
outcome for negative cases.

The benchmark, not `wsi-dicom`, runs the independent decoders. For each instance
it decodes the first `--max-pixel-frames` frames (default 1) with `djpeg`
(JPEG Baseline), `opj_decompress` (JPEG 2000), or an HTJ2K decoder
(`--htj2k-decoder`, otherwise `grk_decompress` on `PATH`). It then checks the
decoded size, sample count and bit depth against the DICOM header. Those decoders
must be installed unless `--allow-missing-tools` is given. `wsi-dicom` releases
through 0.8.0 still decode frames themselves. The workbench detects them and
passes `--max-pixel-frames 0`, so frames are decoded once.

## Locked DICOM 2026d v7 challenge

The edition-neutral catalog v7 and `statement-coverage-v7.json` account for all 886 statements
currently classified as checked: 690 file/object statements, 188 DICOMweb statements, and 8
DICOM JSON statements. The locked suite has
927 inputs (66 valid controls, 697 general negative cases, 3 core cases, 3 advisory cases, 16 JSON
cases, and 142 HTTP cases) and no uncovered checked statement IDs.

Seven requirements remain unchecked in 16 IOD scope pairs: five MPEG2
stream/audio/display-aspect requirements and two JPIP Data Set byte-order requirements. Inspect the
machine-readable frozen contract from an installed wheel with:

```sh
python -m wsi_dicom_bench.negative_bench.freeze_v7 --json
```

The locked `manifest-v7.json` retains those gaps as a known acceptance-policy failure. A complete
v7 run against the current candidate evaluates every checked statement and then exits `1` because
of those gaps; execution or integrity failures exit `2`. Per-input reports retain candidate,
independent-validator and supported-decoder evidence. Known independent-tool limitations include
dciodvfy's Concatenation model and OpenJPEG/Grok support for JPEG 2000 Part 2 transforms.

The protocol (`protocol-v7.md`) describes the scope and limitations. These engineered cases are
not a prevalence sample, certification, or an independent blinded replication. The draft
authoring resources remain available, and the intrinsic-only diagnostic can be reproduced with:

```sh
python -m wsi_dicom_bench.negative_bench.draft_diagnostic \
  --candidate /absolute/path/to/wsi-dicom \
  --output /new/v7-diagnostic.json
```

For disconnected reproduction, add the `pydicom==3.0.2` wheel to the retained
benchmark wheelhouse, verify it against `reproduction/requirements.lock`, then install with
`python -m pip install --no-index --find-links /path/to/wheelhouse wsi-dicom-bench`.
Complete evidence contains the exact benchmark wheel and a hash-pinned acquisition
requirement for pydicom; it does not rename or rebuild third-party wheels.

The earlier locked `manifest-v6.json` and `protocol-v6.md` remain available. For compatibility,
passing the packaged suite directory without a manifest still selects v6; select the v7 manifest
explicitly as shown above. V6 uses `wsi-dicom-core-profile-2026c-v4` or `wsi-dicom-general-v3`.

The optional
[control-authoring tool](tools/control-authoring/README.md) is separate from normal runs.

## Converter speed and format coverage

Two further harnesses measure a `wsi-dicom` build instead of judging it against the locked
acceptance policy. Run them from the `wsi-dicom` checkout under test: the GDC harness records that
checkout's Git commit and crate version, and both default to its `target/release/wsi-dicom`.

The GDC harness runs the same local GDC/TCGA slides through `wsi-dicom` and `wsidicomizer`. Its
`--wsidicomizer-command` and `--python-command` default to `./.venv/bin/` in the working directory;
that environment is pinned by `src/wsi_dicom_bench/gdc/requirements.txt`. Use `--dry-run` first to
inspect the exact command matrix:

```sh
wsi-dicom-bench-gdc \
  --out /path/to/results \
  --downloads-root ~/Downloads \
  --probe-slide-metadata \
  --tools wsi-dicom-cpu wsi-dicom-device wsidicomizer \
  --profile htj2k-lossless-rpcl \
  --scope base \
  --runs 1 \
  --system-label macos-metal \
  --device-preflight \
  --validate
```

Run the same command on the Metal and CUDA hosts with host-specific release binaries,
`--run-label`, and `--system-label` values, then combine result directories with
`--merge-results`. Publish failed, timed-out, and unsupported rows, transfer syntax, frame geometry,
tool versions, and host details with any performance claim. The `htj2k-lossless-rpcl` profile maps
wsidicomizer to its HTJ2K option because that CLI does not expose RPCL-specific control.

The format-coverage runner converts bounded native levels from a checksummed OpenSlide test-data
manifest, runs the workbench on successful conversions, and retains exact unsupported-format
outcomes. The output path must not already exist. `--backend require-device` fails unless each
manifest-declared encode case reports device encoding:

```sh
metal_manifest="$(python -c 'import importlib.resources; print(importlib.resources.files("wsi_dicom_bench.format_coverage").joinpath("format-coverage-metal-v2.json"))')"
wsi-dicom-bench-format-coverage \
  --corpus-root /absolute/path/to/openslide-testdata \
  --manifest "$metal_manifest" \
  --output /new/format-coverage-metal \
  --wsi-dicom target/metal/release/wsi-dicom \
  --backend require-device
wsi-dicom-bench-format-coverage \
  --corpus-root /absolute/path/to/openslide-testdata \
  --manifest "$metal_manifest" \
  --output /new/format-coverage-cpu \
  --backend cpu
wsi-dicom-bench-format-compare \
  --cpu /new/format-coverage-cpu \
  --metal /new/format-coverage-metal \
  --output /new/format-coverage-comparison
```

Without `--manifest`, the runner uses the bundled `format-coverage-v2.json`.
