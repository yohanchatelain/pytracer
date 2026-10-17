# Agent & Data Format Guide

This guide provides structured workflows, exit codes, directory layouts, and JSON/Parquet schemas so **AI coding agents**, **CI pipelines**, and **developers** can operate Pytracer and parse its outputs without human intervention.

## Table of Contents

- [Agent Diagnostic Workflow](#agent-diagnostic-workflow)
- [Exit Codes](#exit-codes)
- [Experiment Directory Layout](#experiment-directory-layout)
- [JSON & Parquet Schemas](#json--parquet-schemas)
  - [`analysis/function_summary.json`](#analysisfunction_summaryjson)
  - [`analysis/argument_summary.json`](#analysisargument_summaryjson)
  - [`analysis/top_unstable.json`](#analysistop_unstablejson)
  - [`analysis/alignment.json`](#analysisalignmentjson)
  - [`analysis/coverage.json`](#analysiscoveragejson)
  - [`runs/run-XXX/events.jsonl` & `events.parquet`](#runsrun-xxxeventsjsonl--eventsparquet)
- [Automated Remediation Loop](#automated-remediation-loop)

---

## Agent Diagnostic Workflow

When tasked with diagnosing or fixing numerical instability in a Python script or library, follow this non-interactive 5-step workflow:

```bash
# 1. Verify environment & dependencies
pytracer doctor

# 2. Run repeated executions (use >= 5 repetitions; pass script args after --)
pytracer run path/to/script.py --repeat 5 --plugins numpy scipy -- --arg1 val1

# 3. Inspect machine-readable stability rankings & coverage
cat .pytracer/runs/latest/analysis/top_unstable.json
cat .pytracer/runs/latest/analysis/coverage.json

# 4. (If coverage shows untraced callables) Expand targets or enable taint mode
pytracer suggest-targets .pytracer/runs/latest
pytracer run path/to/script.py --repeat 5 --instrument taint --target "my_module.*"

# 5. Compare baseline vs. fixed implementation and gate CI
pytracer diff .pytracer/runs/<baseline_id> .pytracer/runs/latest --tolerance-bits 1.0 --fail-on-regression
pytracer check .pytracer/runs/latest --min-sig-bits 24 --no-nan --no-inf
```

> **Tip for AI Agents**: Prefer reading `.pytracer/runs/latest/analysis/top_unstable.json` and `.pytracer/runs/latest/report/report.md` rather than opening `.html` reports or launching `pytracer dashboard` (which starts a blocking web server).

---

## Exit Codes

| Command | Exit `0` | Exit `1` | Exit `2` |
|---|---|---|---|
| `pytracer run` | All repetitions exited `0` | One or more repetitions failed or `PytracerError` raised | Invalid CLI arguments |
| `pytracer check` | All stability thresholds satisfied | One or more stability violations found | No thresholds provided |
| `pytracer diff` | Completed (or no regressions when `--fail-on-regression` set) | Regressions exceeded `--tolerance-bits` with `--fail-on-regression` | Invalid CLI arguments |
| `pytracer doctor` | All required environment checks passed | A required check failed (e.g. invalid `pytracer.toml`) | Invalid CLI arguments |

---

## Experiment Directory Layout

By default, every `pytracer run` creates a UTC-timestamped directory under `.pytracer/runs/` and updates the `.pytracer/runs/latest` symlink:

```text
.pytracer/runs/
├── latest -> 2026-10-17T16-00-00.000Z
└── 2026-10-17T16-00-00.000Z/
    ├── .pytracer-experiment          # Ownership marker required by `pytracer clean`
    ├── config.toml                   # Resolved PytracerConfig snapshot
    ├── experiment.json               # Script path, args, repeat count, targets, instrumentation
    ├── runs/
    │   ├── run-000/
    │   │   ├── spec.json             # Per-run execution spec consumed by _bootstrap
    │   │   ├── metadata.json         # Exit code, duration, Python/NumPy versions, env allowlist
    │   │   ├── events.jsonl          # Line-delimited TraceEvent stream (crash-safe)
    │   │   ├── events.parquet        # Columnar Parquet archive of events.jsonl
    │   │   ├── monitor.json          # Tier 4 sys.monitoring C-callable & line census
    │   │   ├── native_kernels.log    # Tier 5 BLAS/LAPACK calls (when --native is used)
    │   │   └── arrays/               # Stored array payloads (e.g. e000001.npy or .zarr)
    │   └── run-001/ ...
    ├── analysis/
    │   ├── alignment.json            # Call-group alignment details & divergence summary
    │   ├── function_summary.json     # Per-function stability & amplification metrics
    │   ├── argument_summary.json     # Per-(function, arg_name, phase) stability metrics
    │   ├── top_unstable.json         # Functions ranked by amplification & precision loss
    │   └── coverage.json             # Tier call counts & untraced numerical callables
    └── report/
        ├── report.md                 # Concise Markdown report
        ├── report.html               # Standalone interactive HTML report
        ├── report.json               # Combined JSON bundle of all experiment + analysis data
        └── trace.perfetto.json       # Written by `pytracer export`
```

---

## JSON & Parquet Schemas

All artifacts carry `"schema_version": "2.0.0"`.

### `analysis/function_summary.json`

Array of `FunctionRow` objects summarizing each traced function across aligned runs:

```json
[
  {
    "function": " __main__.naive_variance",
    "n_call_groups": 1,
    "n_matched": 1,
    "divergence_score": 0.0,
    "min_output_sig_bits": 11.42,
    "median_output_sig_bits": 11.42,
    "max_amplification_bits": 31.58,
    "mean_amplification_bits": 31.58,
    "nan_instability": false,
    "inf_instability": false,
    "sig_basis": "element",
    "tiers": ["t1"]
  }
]
```

| Field | Type | Meaning |
|---|---|---|
| `function` | `str` | Fully qualified function name (`<module>.<qualname>`) |
| `n_call_groups` | `int` | Total aligned call groups for this function |
| `n_matched` | `int` | Call groups present across all runs |
| `divergence_score` | `float` | `1.0 - (n_matched / n_call_groups)`; `0.0` means identical control flow |
| `min_output_sig_bits` | `float \| null` | Worst output significant bits (`0.0`–`53.0`) across all calls |
| `median_output_sig_bits` | `float \| null` | Median output significant bits across all calls |
| `max_amplification_bits` | `float \| null` | Maximum precision destroyed in a single call ($\min \text{sig}_{\text{in}} - \min \text{sig}_{\text{out}}$) |
| `mean_amplification_bits` | `float \| null` | Mean amplification bits across calls |
| `nan_instability` / `inf_instability` | `bool` | `true` if NaN or Inf occurred in any run |
| `sig_basis` | `"element" \| "summary"` | `"element"` when computed from stored arrays; `"summary"` when computed from scalar means |
| `tiers` | `list[str]` | Instrumentation tiers that recorded this function (`["t1"]`, `["t2"]`, `["t3"]`) |

---

### `analysis/argument_summary.json`

Array of `ArgumentRow` objects broken down by `(function, arg_name, phase)`:

```json
[
  {
    "function": "numpy.linalg.solve",
    "arg_name": "return",
    "phase": "output",
    "n_runs": 5,
    "n_call_groups": 1,
    "sig_basis": "element",
    "sig_mean_bits": 14.8,
    "sig_min_bits": 9.2,
    "sig_p05_bits": 10.1,
    "sig_median_bits": 13.5,
    "mean_of_means": 1.00000012,
    "std_of_means": 3.4e-5,
    "nan_instability": false,
    "inf_instability": false
  }
]
```

- Inputs have `"phase": "input"` and parameter names (e.g. `"a"`, `"b"`, `"arg0"`).
- Outputs have `"phase": "output"` and `"arg_name": "return"` (or `"return[0]"` for tuple returns, or the mutated parameter name when `inplace = true`).

---

### `analysis/top_unstable.json`

Top 10 unstable `FunctionRow` entries sorted by:
1. Highest `max_amplification_bits` (true sources of precision destruction first)
2. Lowest `min_output_sig_bits`
3. Highest `divergence_score`

---

### `analysis/alignment.json`

Contains alignment metadata (`mode`, `runs`, `total_call_groups`, `matched_call_groups`, `divergent_call_groups`, `per_function_divergence`) and the full list of aligned call groups mapping each `group_id` to `per_run_call_ids`.

---

### `analysis/coverage.json`

Reports observability coverage and blind spots:
- `traced_calls_by_tier`: Call counts per tier (`t1`, `t2`, `t3`, `t4`).
- `native_kernel_calls`: Dict of BLAS/LAPACK symbol counts (`dgemm_`, `dgesv_`, etc.) when `--native` is active.
- `untraced_numerical_callables`: List of `{"function": "<qualname>", "calls": <int>}` observed by `sys.monitoring` (`T4`) that were not traced by `T1`–`T3`.

---

### `runs/run-XXX/events.jsonl` & `events.parquet`

Each line in `events.jsonl` (and row in `events.parquet`) is a `TraceEvent`:

| Column / Key | Type | Description |
|---|---|---|
| `schema_version` | `str` | `"2.0.0"` |
| `run_id` | `str` | `"run-000"`, `"run-001"`, ... |
| `event_id` | `int` | Monotonic event counter within the run |
| `call_id` | `int` | Groups all `"input"`, `"output"`, and `"exception"` events of a single call |
| `parent_call_id` | `int \| null` | Enclosing `call_id` when nested |
| `occurrence` | `int` | Per-`(module, qualname, source)` counter within the run |
| `phase` | `str` | `"input"`, `"output"`, or `"exception"` |
| `module`, `qualname` | `str` | Target module and qualified callable name |
| `tier` | `str` | `"t1"`, `"t2"`, `"t3"`, or `"t4"` |
| `arg_name` | `str \| null` | Bound parameter name or `"return"` |
| `inplace` | `bool` | `true` for in-place mutations (`out=`, `ufunc.at`) |
| `payload_kind` | `str` | `"none"`, `"summary"`, or `"array_ref"` |
| `summary` | `NumericSummary \| null` | `dtype`, `shape`, `size`, `mean`, `std`, `min`, `max`, `l2_norm`, `linf_norm`, `nan_count`, `inf_count`, `zero_count`, `subnormal_count`, `cancellation`, `fingerprint` |
| `payload_ref` | `str \| null` | Relative path under `run-XXX/` to stored `.npy` or `.zarr` payload |
| `source` | `{"file": str, "lineno": int}` | User callsite file and line number |
| `ts_ns` | `int \| null` | `time.monotonic_ns()` timestamp |

---

## Automated Remediation Loop

1. **Locate the root-cause function**: Look for the function with the highest `max_amplification_bits` in `analysis/top_unstable.json` (not merely the lowest `min_output_sig_bits`, which could be a downstream consumer).
2. **Pinpoint the callsite**: Match the function in `analysis/alignment.json` or `runs/run-000/events.jsonl` and inspect the `source.file` and `source.lineno` fields.
3. **Identify the numerical pathology**:
   - High `cancellation` on `numpy.subtract` or `E[x²] - E[x]²` → rewrite using Welford's algorithm, `math.expm1`, `math.log1p`, or algebraically factored forms.
   - High amplification in `numpy.linalg.solve` / `inv` → check matrix conditioning; replace explicit `inv(A) @ b` with `solve(A, b)`, `lstsq`, QR/SVD, or Tikhonov regularization.
   - Drift in `numpy.sum` / reduction loops → use `math.fsum` or pairwise/Kahan summation.
4. **Verify the fix**: Re-run `pytracer run` and validate with `pytracer diff <old_exp> .pytracer/runs/latest --fail-on-regression`.
