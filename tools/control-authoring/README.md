# Frozen-control authoring tool

This optional Rust program authors the ten seed controls used to derive the frozen suite.
It depends on exactly `wsi-dicom = 0.7.5`; `Cargo.lock` fixes its complete dependency graph.
Normal benchmark execution consumes packaged frozen controls and never invokes this tool or
regenerates controls with the candidate under evaluation.

Build and run it explicitly:

```sh
cargo build --release --locked \
  --manifest-path tools/control-authoring/Cargo.toml
cargo run --release --locked \
  --manifest-path tools/control-authoring/Cargo.toml -- \
  /new/control-output-directory
```

The output directory must not already exist. Control changes require a new authored suite
and expectation lock; they must not overwrite or relabel the frozen v4 resources.
