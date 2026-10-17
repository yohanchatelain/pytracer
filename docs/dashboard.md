# Interactive Dashboard Guide

```bash
uv pip install -e ".[gui]"
pytracer dashboard EXPERIMENT_DIR [--compare EXPERIMENT_B] [--host 127.0.0.1] [--port 8050]
```

The Pytracer Dashboard is an interactive Dash + Plotly web application that visualizes a **completed, analyzed experiment**. Aggregates are loaded directly from `analysis/*.json` without recomputation, while call-level records, element-wise array stacks, source snippets, and execution spans load lazily on demand.

## Table of Contents

- [Header & KPI Cards](#header--kpi-cards)
- [Dashboard Tabs](#dashboard-tabs)
  - [1. Overview Tab](#1-overview-tab)
  - [2. Explorer Tab](#2-explorer-tab)
  - [3. Call Graph Tab](#3-call-graph-tab)
  - [4. Call Timeline Tab](#4-call-timeline-tab)
  - [5. Coverage Tab](#5-coverage-tab)
  - [6. Runs Tab](#6-runs-tab)
- [A/B Comparison Mode (`--compare`)](#ab-comparison-mode---compare)
- [Internal Architecture](#internal-architecture)

---

## Header & KPI Cards

Always visible at the top of the page:
- **Experiment Metadata**: Traced script, experiment ID, run count, alignment mode (`strict`, `callsite`, `fuzzy`), and active instrumentation mode.
- **Status-Colored KPI Cards**: Runs, aligned call groups, matched vs. divergent groups, **min output significance (bits)**, **max amplification (bits)**, and NaN/Inf-unstable function counts. Cards are color-coded by severity (`< 10` bits = critical red, `24` bits = `float32` orange landmark, `53` bits = exact green).

---

## Dashboard Tabs

### 1. Overview Tab

- **Digit-Loss Amplification Ranking**: Bar chart showing bits of precision destroyed per call ($\min \text{sig}_{\text{in}} - \min \text{sig}_{\text{out}}$) for each function—separating *sources* of instability from downstream *victims*. Clicking any bar jumps directly to the **Explorer** tab filtered to that function.
- **Worst-Case Output Significance**: Per-function minimum output significant bits with `float32` (24-bit) and `float64` exact (53-bit) reference lines.
- **Functions & Arguments Tables**: Sortable, filterable tables displaying `sig_basis` (`element` vs `summary` proxy), min/median output sig bits, max amplification, divergence score, and NaN/Inf flags.
- **Control-Flow Divergence & Truncated Runs**: Highlights functions missing in specific runs and warns if any subprocess exited non-zero mid-capture.

### 2. Explorer Tab

- **Per-Invocation Timeline**: Plots one marker per `(aligned call group × argument × phase)` in program invocation order:
  - **Metrics**: Significant bits (`sig(mean)` proxy), element-wise min significant bits, mean, std of per-run means, min/max across runs, and NaN/Inf counts.
  - **Visual Grammar**: Inputs are `▲`, outputs are `▼`, exceptions are `✕` (red), and divergent call groups are `★` (orange). Automatically switches to WebGL rendering above 5,000 points.
  - **Export**: Download the currently filtered selection as CSV.
- **Click-to-Drill-Down**: Clicking any point on the timeline opens four synchronized panels:
  1. **Per-Run Summaries Table**: `dtype`, `shape`, `mean`, `std`, `min`, `max`, $L_2$/$L_\infty$ norms, NaN/Inf/zero/subnormal counts, and value fingerprint per run.
  2. **Per-Run Mean Chart**: Cross-run mean drift with within-run standard deviation whiskers.
  3. **Element-Wise Heatmap & Histogram** (when captured with `store_arrays = "auto"` or `"always"`): 2D heatmap of per-element significant bits (`0`–`53` scale), mean, or cross-run std, with configurable colormaps (`blues`, `diverging`, `viridis`), linear/$\log_2$/$\log_{10}$ z-scales, and a linked distribution histogram.
  4. **Source Context**: Displays the calling source file (`±7` lines) with the exact callsite line highlighted.

### 3. Call Graph Tab

- **Data-Flow DAG**: Layered left-to-right graph where nodes are traced functions (plus a synthetic `<script>` root) and directed edges `A → B` indicate that `B` was invoked inside `A`.
- **Traffic-Light Precision Encoding**: Nodes and edges are colored by worst cross-run output significance (red = severe precision loss, yellow ≈ 24 bits / `float32`, green = 53 bits / exact). Numeric bit values are printed inside every node for colorblind accessibility.
- **Interactive Navigation**: Clicking any node opens that function in the **Explorer** tab.

### 4. Call Timeline Tab

- **Per-Run Gantt Chart**: Displays traced call spans reconstructed from monotonic timestamps (`ts_ns`), colored by instrumentation tier (`t1`–`t4`) with hover details for duration, call depth, and exceptions (capped at the 400 longest spans in-browser; for full multi-run flamegraphs, run `pytracer export EXP_DIR --format perfetto` and open in [ui.perfetto.dev](https://ui.perfetto.dev)).

### 5. Coverage Tab

- **Tier Breakdown**: Call counts captured by Tier 1 (functions/methods), Tier 2 (NumPy ufuncs), Tier 3 (`TracedArray` taint), and Tier 4 (`sys.monitoring`).
- **Native BLAS Census (T5)**: Kernel call counts (`dgemm_`, `dgesv_`, etc.) when run with `--native`.
- **Untraced Numerical Callables**: Lists C-callables observed by `sys.monitoring` that were not wrapped, with copy-pasteable `pytracer suggest-targets` guidance.

### 6. Runs Tab

- **Subprocess Audit Table**: Exit codes, timestamps, Python/NumPy versions, platform info, captured environment variables (`VFC_*`, `PYTRACER_*`), and a reproducibility command block.

---

## A/B Comparison Mode (`--compare`)

Pass `--compare EXPERIMENT_B` to compare a baseline experiment (`EXPERIMENT_DIR`) against a candidate experiment (`EXPERIMENT_B`) directly in the UI:

```bash
pytracer dashboard .pytracer/runs/<baseline> --compare .pytracer/runs/<candidate>
```

---

## Internal Architecture

```text
capture (events.jsonl, arrays/, metadata.json)
        │ pytracer analyze         ──► writes analysis/*.json
        ▼
report.model.build_report_data     ──► loads precomputed aggregates
        │
dashboard.data.ExperimentData      ──► lazy call-group alignment, array stacking,
        │                              span reconstruction, and source lookup
        ▼
dashboard.layout ⇄ dashboard.callbacks ⇄ dashboard.figures / dashboard.theme
```

- [`src/pytracer/dashboard/data.py`](../src/pytracer/dashboard/data.py): Only dashboard module that reads from disk; caches element-wise array stacks, source snippets, and per-run spans.
- [`src/pytracer/dashboard/figures.py`](../src/pytracer/dashboard/figures.py) & [`theme.py`](../src/pytracer/dashboard/theme.py): Pure Plotly figure builders and accessible color palettes.
- [`src/pytracer/dashboard/app.py`](../src/pytracer/dashboard/app.py): Exposes `build_app()` and `run_dashboard()`.
