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
  "git+https://github.com/frames-sg/wsi-dicom-bench@<published-commit>" \
  --wheel-dir ./benchmark-wheelhouse
python -m pip install ./benchmark-wheelhouse/wsi_dicom_bench-*.whl
wsi-dicom-bench challenge run \
  --suite /path/to/manifest-v4.json \
  --wsi-dicom /absolute/path/to/wsi-dicom \
  --output /new/evidence-directory
```

The bundled v4 suite manifest is available through the installed package at
`wsi_dicom_bench/negative_bench/manifest-v4.json`. An existing evidence directory
can be checked without modifying it:

```sh
suite_path="$(python -c 'import importlib.resources; print(importlib.resources.files("wsi_dicom_bench.negative_bench").joinpath("manifest-v4.json"))')"
```

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
