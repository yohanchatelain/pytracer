<p align="center">
  <img src="images/logo.png" alt="Pytracer Logo" width="260">
</p>

<h1 align="center">Pytracer</h1>

<p align="center">
  <strong>Numerical variability profiler for Python scientific programs</strong>
</p>

<p align="center">
  <a href="https://github.com/yohanchatelain/pytracer/releases"><img src="https://img.shields.io/badge/release-v2.0.0-blue.svg" alt="Release"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12%20%7C%203.13-blue.svg" alt="Python Version"></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/badge/package%20manager-uv-purple.svg" alt="uv"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License"></a>
</p>

---

**Pytracer is an observability and profiling layer for numerical stability.** It runs your Python scientific workloads under perturbed arithmetic (e.g. stochastic arithmetic via [Verificarlo](https://github.com/verificarlo/verificarlo), [Verrou](https://github.com/edf-hpc/verrou), or fuzzy libmath), records input/output distributions across repeated executions, aligns call sequences, and pinpoints **which functions destroy significant digits, amplify numerical noise, or cause control-flow divergence**.

> **Note**: This is Pytracer 2, a clean-slate rewrite designed for modern Python (≥ 3.12). Legacy Pytracer 1 traces and configuration are archived in the repository history.

---

## Quick Start

### 1. Installation

Pytracer recommends [**`uv`**](https://github.com/astral-sh/uv) for fast, reliable environment management:

```bash
# Create and activate virtual environment
uv venv
source .venv/bin/activate

# Install pytracer in editable mode with all extras
uv pip install -e ".[dev,arrays,sig,gui]"
```

### 2. Run Tracing & Generate Report

```bash
# Run 5 independent perturbed repetitions on a numerical pathology example
uv run pytracer run examples/cancellation.py --repeat 5

# Open the generated standalone HTML report
open .pytracer/runs/latest/report/report.html
```

### 3. Launch Interactive Dashboard

```bash
uv run pytracer dashboard .pytracer/runs/latest
```

---

## How It Works

```
Instrumentation Tiers (T1–T5) ──► Event Stream ──► Append-Safe JSONL ──► Parquet Archive
                                                            │
                                                            ▼
Reports & Dashboard ◄── Aggregation & Digit Attribution ◄── Call Alignment (LCS)
```

- **Subprocess Isolation**: Every repetition executes in an independent, fresh subprocess; instrumentation hooks attach before user scripts import.
- **5-Tier Instrumentation Stack**:
  - **T1 (Functions & Methods)**: Boundary patching with transparent `wrapt` wrappers.
  - **T2 (NumPy Ufuncs)**: Dedicated proxy intercepting `__call__`, `reduce`, `accumulate`, `outer`, `at`, and `out=` in-place writes while preserving `isinstance(..., np.ufunc)`.
  - **T3 (Tracer Arrays / Taint Mode)**: `TracedArray` protocol wrapping for `a + b`, `@` matmul syntax, and unpatched third-party code.
  - **T4 (PEP 669 Runtime Monitor)**: `sys.monitoring` census of untraced C-callables and per-line branch divergence.
  - **T5 (Native BLAS Shim)**: Zero-overhead C shim via `LD_PRELOAD` interposing GEMM/GESV across LP64/ILP64 libraries.
- **Sequence Alignment**: Deterministic callsite hashing and Longest Common Subsequence (LCS) matching to prevent cascade misalignment during loop divergence.
- **Digit-Loss Attribution**: Evaluates **amplification bits** ($\min \text{sig}_{\text{in}} - \min \text{sig}_{\text{out}}$) to separate true precision destroyers from victim functions.

---

## Metric & Coverage Honesty

- **Element-wise vs Summary Proxy**:
  - `element`: Element-wise significant bits evaluated across captured `.npy` / `.zarr` array payloads (`store_arrays = "auto"`).
  - `summary`: `sig(mean)` proxy when payloads are omitted; prominently marked in reports so scalar summaries are never confused with full array stability.
- **Declared Blind Spots**: Pytracer explicitly reports calls observed versus calls traced, and documents C extensions and operator dispatch blind spots in its coverage ledger.

---

## CLI Reference

| Command | Description |
|---|---|
| `pytracer init` | Generate a default `pytracer.toml` configuration |
| `pytracer run SCRIPT [opts]` | Execute repeated runs under tracing (`--repeat N`, `--target`, `--plugins`) |
| `pytracer analyze EXP_DIR` | Recompute sequence alignment and statistical aggregations |
| `pytracer report EXP_DIR` | (Re)generate HTML, Markdown, and JSON summary reports |
| `pytracer check EXP_DIR` | CI gating: exit nonzero on precision loss (`--min-sig-bits`, `--max-divergence`) |
| `pytracer diff EXP_A EXP_B` | A/B regression detection between two experiments |
| `pytracer dashboard EXP_DIR` | Multi-tab interactive Dash app (Explorer, Call Graph, Timeline, Coverage) |
| `pytracer export EXP_DIR` | Export execution spans to Chrome / [Perfetto](https://ui.perfetto.dev) trace format |
| `pytracer suggest-targets EXP` | Suggest target candidates from the T4 C-callable census |
| `pytracer plugins list` | List available domain target plugins (`numpy`, `scipy`, `sklearn`) |
| `pytracer doctor` | Verify interpreter, sys.monitoring, BLAS, and compiler environment |
| `pytracer clean` | Remove `.pytracer/runs/` experiment directories |

---

## Configuration (`pytracer.toml`)

```toml
[trace]
plugins = ["numpy", "scipy"]
targets = ["numpy.linalg.*", "scipy.linalg.solve"]
instrumentation = "hybrid"      # hybrid | patch | monitor | taint
mode = "summary"                # summary | metadata
capture_backtrace = true
store_arrays = "auto"           # auto | always | never
array_store_threshold = 100000
array_backend = "auto"          # auto | zarr | npy

[storage]
output_dir = ".pytracer/runs"

[analysis]
alignment = "callsite"          # callsite | fuzzy | strict

[report]
formats = ["markdown", "html", "json"]

# Dynamic environment substitution per run for perturbation engines
# [perturb.env]
# VFC_BACKENDS = "libinterflop_mca.so --mode=mca --seed={run_index}"
```

---

## Examples Gallery

The `examples/` directory contains paired implementations of classical numerical accuracy pathologies and their stable remediations:

- **Catastrophic Cancellation**: Naive variance vs Welford's algorithm (`cancellation.py`).
- **Quadratic Formula**: Standard formula vs stable alternate root formula.
- **Ill-Conditioning**: Hilbert matrix solve vs Tikhonov regularization.
- **Summation Order**: Non-associative naive sum vs Kahan compensated summation.
- **Finite Differences**: Step-size dilemma vs central difference / complex step.
- **Verificarlo MCA**: Ready-to-run Monte Carlo Arithmetic profiling workflow (`examples/verificarlo/`).

---

## Overhead

Measured with `uv run python benchmarks/bench.py`:

| Workload | Tier | Overhead | Throughput |
|---|---|---|---|
| 20k tiny `numpy.sum` calls | T1 | ~110x (~190 µs/call) | ~12k–16k events/s |
| 2M-element `numpy.sum` calls | T1 | ~13x–28x | Summary stats dominate |
| Operator loop under taint | T3 | ~260x–300x | Drill-down tier by design |

---

## Development

```bash
# Install development dependencies with uv
uv pip install -e ".[dev,arrays,sig,gui]"

# Run code linter
uv run ruff check src tests

# Run static type checker
uv run mypy src

# Run test suite
uv run pytest -q

# Run micro-benchmarks
uv run python benchmarks/bench.py --markdown
```

---

## License

Pytracer is licensed under the [MIT License](LICENSE).

