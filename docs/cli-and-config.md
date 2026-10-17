# CLI & Configuration Reference

## Table of Contents

- [Global Options](#global-options)
- [Subcommands](#subcommands)
  - [`pytracer run`](#pytracer-run)
  - [`pytracer analyze`](#pytracer-analyze)
  - [`pytracer report`](#pytracer-report)
  - [`pytracer check`](#pytracer-check)
  - [`pytracer diff`](#pytracer-diff)
  - [`pytracer dashboard`](#pytracer-dashboard)
  - [`pytracer export`](#pytracer-export)
  - [`pytracer suggest-targets`](#pytracer-suggest-targets)
  - [`pytracer plugins`](#pytracer-plugins)
  - [`pytracer config`](#pytracer-config)
  - [`pytracer init`](#pytracer-init)
  - [`pytracer doctor`](#pytracer-doctor)
  - [`pytracer clean`](#pytracer-clean)
- [Configuration (`pytracer.toml`)](#configuration-pytracertoml)
- [Stability Thresholds (`pytracer-thresholds.toml`)](#stability-thresholds-pytracer-thresholdstoml)
- [Perturbation Backends](#perturbation-backends)

---

## Global Options

All subcommands accept `-c` / `--config` either before or after the subcommand name:

| Flag | Description |
|---|---|
| `-c PATH`, `--config PATH` | Path to a `pytracer.toml` configuration file (default: `./pytracer.toml` if present) |
| `--version` | Print `pytracer <version>` and exit |
| `-h`, `--help` | Show help message and exit |

**Configuration Precedence**: CLI flags > explicit `--config FILE` (or `./pytracer.toml`) > built-in defaults. Unknown sections or keys in TOML files raise a `ConfigError` immediately.

---

## Subcommands

### `pytracer run`

Execute a Python script across `N` independent subprocess repetitions, align the captured call streams, compute stability metrics, and write reports.

```bash
pytracer run SCRIPT [options] [-- SCRIPT_ARGS...]
```

| Option | Default | Description |
|---|---|---|
| `--repeat N` | `1` | Number of independent subprocess runs (`>= 1`) |
| `--target PATH` | `[]` | Extra import path or glob to trace (repeatable, e.g., `--target numpy.linalg.solve --target "my_pkg.solver.*"`) |
| `--plugins [NAME ...]` | `["numpy"]` | Built-in target plugins to enable (`numpy`, `scipy`, `sklearn`) |
| `--instrument MODE` | `"hybrid"` | Instrumentation stack: `hybrid` (T1+T2+T4), `patch` (T1+T2), `monitor` (T4 only), `taint` (T1+T2+T3+T4) |
| `--alignment MODE` | `"callsite"` | Call alignment mode: `strict`, `callsite`, or `fuzzy` |
| `--store-arrays MODE` | `"auto"` | Store array payloads for element-wise sig bits: `auto`, `always`, `never` |
| `--output-dir DIR` | `".pytracer/runs"` | Parent directory for experiment outputs |
| `--native` | `false` | Enable Tier 5 native BLAS `LD_PRELOAD` kernel census (Linux + C compiler) |
| `--continue-on-error` | `false` | Continue remaining repetitions if a subprocess exits non-zero |
| `--no-report` | `false` | Capture raw traces only; skip `analyze` and `report` |
| `--cwd DIR` | Current directory | Working directory for the traced script subprocess |
| `-- SCRIPT_ARGS...` | `[]` | Arguments after literal `--` are forwarded verbatim to `SCRIPT` |

**Example with script arguments**:
```bash
pytracer run sim.py --repeat 10 --target "sim.kernels.*" -- --steps 500 --dt 1e-4
```

---

### `pytracer analyze`

Run or re-run sequence alignment and statistical aggregation on an existing experiment directory (for example, to switch alignment strategies without re-running the workload).

```bash
pytracer analyze EXPERIMENT_DIR [--alignment {strict,callsite,fuzzy}]
```

Writes `alignment.json`, `function_summary.json`, `argument_summary.json`, `top_unstable.json`, and `coverage.json` under `EXPERIMENT_DIR/analysis/`.

---

### `pytracer report`

Generate or regenerate terminal and file reports from an analyzed experiment.

```bash
pytracer report EXPERIMENT_DIR [--formats [markdown] [html] [json]]
```

Writes `report.md`, `report.html`, and/or `report.json` under `EXPERIMENT_DIR/report/`.

---

### `pytracer check`

Gate CI pipelines on numerical stability criteria. Exits `0` if all checks pass, `1` if any violation is detected, or `2` if no thresholds are specified.

```bash
pytracer check EXPERIMENT_DIR \
  [--min-sig-bits BITS] \
  [--max-divergence SCORE] \
  [--no-nan] \
  [--no-inf] \
  [--thresholds FILE]
```

| Option | Description |
|---|---|
| `--min-sig-bits BITS` | Fail if any function's `min_output_sig_bits` is below `BITS` (or `None` when outputs could not be measured) |
| `--max-divergence SCORE` | Fail if any function's `divergence_score` (`0.0`–`1.0`) exceeds `SCORE` |
| `--no-nan` | Fail if any function exhibits NaN instability across runs |
| `--no-inf` | Fail if any function exhibits Inf instability across runs |
| `--thresholds FILE` | Path to a thresholds TOML file (auto-loads `./pytracer-thresholds.toml` if present) |

---

### `pytracer diff`

Compare two analyzed experiments (`A` = baseline, `B` = candidate) and report per-function changes in output significant bits, amplification, and divergence.

```bash
pytracer diff EXPERIMENT_A EXPERIMENT_B [--tolerance-bits 1.0] [--fail-on-regression]
```

- `--tolerance-bits FLOAT` (default `1.0`): Minimum drop in `min_output_sig_bits` from `A` to `B` required to flag a regression.
- `--fail-on-regression`: Exit `1` if one or more regressions exceed `--tolerance-bits`.

---

### `pytracer dashboard`

Launch the interactive Dash/Plotly web application (requires `pytracer[gui]`).

```bash
pytracer dashboard EXPERIMENT_DIR [--compare EXP_B] [--host 127.0.0.1] [--port 8050] [--debug]
```

See [Interactive Dashboard (`docs/dashboard.md`)](dashboard.md) for details on each tab.

---

### `pytracer export`

Export per-run call spans to Chrome Trace / [Perfetto](https://ui.perfetto.dev) JSON format.

```bash
pytracer export EXPERIMENT_DIR [--format perfetto] [-o OUTPUT_PATH]
```

Defaults to `EXPERIMENT_DIR/report/trace.perfetto.json`.

---

### `pytracer suggest-targets`

Inspect `analysis/coverage.json` from a completed run and emit a ready-to-paste `targets = [...]` list of untraced numerical callables observed by the Tier 4 `sys.monitoring` census.

```bash
pytracer suggest-targets EXPERIMENT_DIR [--top 15]
```

---

### `pytracer plugins`

List built-in domain target plugins (`numpy`, `scipy`, `sklearn`) or inspect the exact functions/ufuncs/methods a plugin instruments.

```bash
pytracer plugins list
pytracer plugins targets numpy
```

---

### `pytracer config`

Print the resolved configuration as JSON or validate `pytracer.toml`.

```bash
pytracer config show [-c path/to/pytracer.toml]
pytracer config validate [-c path/to/pytracer.toml]
```

---

### `pytracer init`

Write a starter `pytracer.toml` in the current directory.

```bash
pytracer init [--force]
```

---

### `pytracer doctor`

Run environment health checks (Python version, `sys.monitoring` availability, `pytracer.toml` validity, C compiler & BLAS discovery for `--native`, and active `VFC_*` perturbation variables).

```bash
pytracer doctor [-c path/to/pytracer.toml]
```

---

### `pytracer clean`

Remove experiment directories inside `output_dir` that contain the `.pytracer-experiment` ownership marker, and unlink `output_dir/latest`.

```bash
pytracer clean [--output-dir DIR]
```

---

## Configuration (`pytracer.toml`)

All fields are optional. Below is the complete schema with built-in defaults:

```toml
[trace]
plugins = ["numpy"]             # Built-in plugins: "numpy", "scipy", "sklearn"
targets = []                    # Extra import paths or globs, e.g. ["numpy.linalg.*", "mymod.solve"]
instrumentation = "hybrid"      # "hybrid" | "patch" | "monitor" | "taint"
mode = "summary"                # "summary" (compute NumericSummary) | "metadata" (shapes/dtypes only)
capture_backtrace = true        # Record caller file & line number on each event
store_arrays = "auto"           # "auto" | "always" | "never"
array_store_threshold = 100000  # Max array elements saved per event when store_arrays = "auto"
array_backend = "auto"          # "auto" | "npy" | "zarr" (zarr requires pytracer[arrays])
native_census = false           # Enable Tier 5 LD_PRELOAD BLAS census

[storage]
output_dir = ".pytracer/runs"

[analysis]
alignment = "callsite"          # "strict" | "callsite" | "fuzzy"

[perturb.env]
# Environment variables formatted per run with {run_index} (0..N-1) and {run_id} ("run-000"..)
# VFC_BACKENDS = "libinterflop_mca.so --mode=mca --precision-binary64=53 --seed={run_index}"

[report]
formats = ["markdown", "html", "json"]
```

---

## Stability Thresholds (`pytracer-thresholds.toml`)

Used by `pytracer check`. Global limits apply to every traced function unless overridden by a `[function."<qualname>"]` table:

```toml
min_sig_bits = 24.0       # Require at least float32 precision globally
max_divergence = 0.0      # Require identical control flow across runs
allow_nan = false         # Fail if NaN appears in any run
allow_inf = false         # Fail if Inf appears in any run

[function."numpy.linalg.solve"]
min_sig_bits = 15.0       # Relax threshold for a known ill-conditioned linear solve
```

---

## Perturbation Backends

Pytracer measures variability across runs; to inject floating-point perturbations into deterministic code, pair Pytracer with a stochastic arithmetic backend via `[perturb.env]`:

1. **[Verificarlo](https://github.com/verificarlo/verificarlo) / Fuzzy Docker Environments**:
   ```toml
   [perturb.env]
   VFC_BACKENDS = "libinterflop_mca.so --mode=mca --precision-binary64=53 --seed={run_index}"
   ```
2. **[Verrou](https://github.com/edf-hpc/verrou)** or Custom Seed Injection:
   ```toml
   [perturb.env]
   PYTRACER_SEED = "{run_index}"
   ```
   Your script or test harness can read `os.environ["PYTRACER_SEED"]` (or `os.environ["PYTRACER_RUN_ID"]`, which Pytracer always sets automatically) to Perturb initial conditions or random seeds per repetition.
