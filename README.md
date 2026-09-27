# WSI-DICOM Bench

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
  "git+https://github.com/frames-sg/wsi-dicom-bench@1987f59efd6fb1387b3d3aa9d655197141b914bb" \
  --wheel-dir ./benchmark-wheelhouse
python -m pip install ./benchmark-wheelhouse/wsi_dicom_bench-*.whl
suite_path="$(python -c 'import importlib.resources; print(importlib.resources.files("wsi_dicom_bench.negative_bench").joinpath("manifest-v4.json"))')"
wsi-dicom-bench challenge run \
  --suite "$suite_path" \
  --wsi-dicom /absolute/path/to/wsi-dicom \
  --output /new/evidence-directory
```

The bundled v4 suite manifest is an installed package resource. An existing evidence
directory can be checked without modifying it:

```sh
wsi-dicom-bench challenge check --evidence /path/to/evidence
```

Exit code `0` means the locked acceptance policy passed, `1` means a complete
evaluation violated the policy, and `2` means execution, integrity, or converter
contract compatibility failed. Invalid DICOM rejection is an expected successful
outcome for negative cases.

The v4 protocol describes the benchmark scope and limitations. The engineered
cases are not a prevalence sample, certification, or an independent blinded
replication.

For disconnected reproduction, add the `pydicom==3.0.2` wheel to the retained
benchmark wheelhouse, verify it against `reproduction/requirements.lock`, then install with
`python -m pip install --no-index --find-links /path/to/wheelhouse wsi-dicom-bench`.
Accepted evidence contains the exact benchmark wheel and a hash-pinned acquisition
requirement for pydicom; it does not rename or rebuild third-party wheels.

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
