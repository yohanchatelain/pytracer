# Architecture, Instrumentation & Metrics

## Table of Contents

- [Execution Pipeline](#execution-pipeline)
- [5-Tier Instrumentation Stack](#5-tier-instrumentation-stack)
- [Programmatic Instrumentation API](#programmatic-instrumentation-api)
- [Call-Sequence Alignment](#call-sequence-alignment)
- [Numerical Stability Metrics](#numerical-stability-metrics)
  - [Significant Bits (`sig_bits`)](#significant-bits-sig_bits)
  - [Metric Basis: `element` vs. `summary`](#metric-basis-element-vs-summary)
  - [Digit-Loss Amplification](#digit-loss-amplification)
  - [NaN, Inf & Cancellation Diagnostics](#nan-inf--cancellation-diagnostics)
- [Coverage & Declared Blind Spots](#coverage--declared-blind-spots)

---

## Execution Pipeline

```
Subprocess Run 0..N-1
  └── pytracer._bootstrap (attaches T1–T5 before user script imports)
        ├──runs/run-XXX/events.jsonl + events.parquet
        ├──runs/run-XXX/arrays/*.{npy,zarr}
        └──runs/run-XXX/monitor.json
              │
              ▼
      pytracer analyze
        ├── Call Reassembly & Sequence Alignment (strict | callsite | fuzzy LCS)
        ├── Cross-Run Statistical Aggregation & Element-wise Sig Calculation
        └── Digit-Loss Amplification & Coverage Ledger (analysis/*.json)
              │
              ▼
      pytracer report / check / diff / dashboard / export
```

Every repetition in `pytracer run --repeat N` executes in a **fresh Python subprocess** invoked via `python -m pytracer._bootstrap <spec.json>`. Instrumentation attaches before the target script is imported, preventing cross-run state leakage and ensuring module-level imports bind to wrapped callables.

---

## 5-Tier Instrumentation Stack

Pytracer combines five complementary tiers controlled by `--instrument` (`hybrid`, `patch`, `monitor`, `taint`) and `--native`:

| Tier | Mechanism | What It Captures | Enabled In |
|---|---|---|---|
| **T1: Functions & Methods** | Transparent `wrapt` boundary proxies + import-hook rebinding across already-imported modules | Python functions, C-extension functions (`numpy.linalg.solve`, `scipy.*`), class methods (`sklearn.*.fit`), and `@pytracer.trace_function` | `hybrid`, `patch`, `taint` |
| **T2: NumPy Ufuncs** | `wrapt.ObjectProxy` subclass registering as `isinstance(u, np.ufunc)` | Direct ufunc calls (`np.add(a, b)`), `.reduce`, `.accumulate`, `.reduceat`, `.outer`, `.at`, and `out=` in-place mutations | `hybrid`, `patch`, `taint` |
| **T3: Tracer Arrays (Taint)** | `TracedArray(np.ndarray)` implementing `__array_ufunc__` and `__array_function__` | Operator expressions (`a + b`, `a @ b`), aliased references, and unpatched third-party library internals operating on tainted arrays | `taint` (or explicit `pytracer.taint(x)`) |
| **T4: Runtime Monitor** | PEP 669 (`sys.monitoring`) low-overhead C-call and branch listener | Census of *untraced* numerical C-callables (feeding `pytracer suggest-targets`) and line-level execution counts | `hybrid`, `monitor`, `taint` |
| **T5: Native BLAS Shim** | `LD_PRELOAD` C shared library interposing `cblas_*` / Fortran BLAS & LAPACK symbols (`dgemm_`, `dgesv_`, etc.) | Native kernel invocation counts below Python/C-extension boundaries | `--native` (`trace.native_census = true`) |

**Re-entrancy Protection**: While a T1/T2/T3 wrapper is executing an inner library call, nested calls are tracked via `parent_call_id` without corrupting input/output attribution of the outer boundary call.

---

## Programmatic Instrumentation API

Importing `pytracer` has **zero side effects** and does not import NumPy or read configuration until needed. Decorators and taint wrappers act as no-ops when run outside `pytracer run`.

```python
import numpy as np
import pytracer

@pytracer.trace_function
def solve_step(A: np.ndarray, b: np.ndarray) -> np.ndarray:
    # Explicitly traced as Tier T1 whenever executed under `pytracer run`
    return np.linalg.solve(A, b)

def operator_heavy_pipeline(x: np.ndarray) -> np.ndarray:
    # Opt into Tier T3 protocol tracing for operator expressions (+, -, @) on x
    tx = pytracer.taint(x)
    return (tx @ tx.T) + 1e-6
```

---

## Call-Sequence Alignment

Before comparing numerical values across `N` runs, Pytracer aligns the sequence of `CallRecord`s from each run into matched **Call Groups**:

1. **`strict`**: Requires every run to emit the exact same sequence of `(module, qualname, callsite)` records at identical indices. Fastest mode; ideal for verifying determinism.
2. **`callsite` (default)**: Groups calls by `(module, qualname, source_file, source_line, occurrence_index)`. Resilient to unrelated calls inserted elsewhere in the program.
3. **`fuzzy`**: Uses Longest Common Subsequence (LCS) dynamic programming within each `(module, qualname)` stream to align calls even when loop trip counts or branches diverge across runs.

**Divergence Score**: For each function, `divergence_score = 1.0 - (n_matched / n_call_groups)`, ranging from `0.0` (every call group appeared in all runs) to `1.0` (completely divergent control flow).

---

## Numerical Stability Metrics

### Significant Bits (`sig_bits`)

For any scalar quantity $X$ sampled across $N \ge 2$ runs with sample mean $\mu$ and sample standard deviation $\sigma$:

$$\text{sig\_bits}(X) = \text{clamp}\left(-\log_2\!\left(\frac{\sigma}{|\mu|}\right),\; 0,\; 53\right)$$

- **53.0 bits**: Bit-for-bit identical across all runs ($\sigma = 0$, full IEEE 754 `binary64` mantissa precision).
- **~24.0 bits**: Equivalent to IEEE 754 `binary32` (`float32`) single precision.
- **< 10.0 bits**: Severe precision loss (fewer than ~3 significant decimal digits).
- **0.0 bits**: Pure noise ($\sigma \ge |\mu|$, or $\mu = 0$ with $\sigma > 0$, or finite/non-finite mismatch across runs).

### Metric Basis: `element` vs. `summary`

Pytracer never conflates scalar summary stability with element-wise array stability. Every function and argument row explicitly declares its `sig_basis`:

| `sig_basis` | How It Is Computed | When Used |
|---|---|---|
| **`"element"`** | Loads stored `.npy` / `.zarr` arrays across all runs, stacks them along a run axis, and computes per-element significant bits (reporting `sig_min_bits`, `sig_p05_bits`, and `sig_median_bits`). Uses `significantdigits` when installed, or vectorized $-\log_2(\sigma_i / |\mu_i|)$. | Whenever `store_arrays` is `"always"`, or `"auto"` and array size $\le$ `array_store_threshold` (`100,000` elements) with consistent shape across runs. |
| **`"summary"`** | Computes `sig_mean_bits` = $\text{sig\_bits}(\{\text{mean}_r\}_{r=0}^{N-1})$ from the lightweight scalar `NumericSummary` captured in `events.jsonl`. | Fallback when arrays exceed `array_store_threshold`, when `store_arrays = "never"`, or for scalar values. |

### Digit-Loss Amplification

A function whose output has only 8 significant bits is not necessarily buggy—it may simply have been fed inputs that already had only 8 significant bits. To separate **sources of instability** from downstream **victims**, Pytracer computes **amplification bits** for every aligned call group $g$:

$$\text{amplification}(g) = \min_{a \in \text{inputs}(g)} \text{sig}(a) \;-\; \min_{o \in \text{outputs}(g)} \text{sig}(o)$$

- **$\text{amplification} \gg 0$**: The function actively destroyed significant bits (e.g. catastrophic cancellation, ill-conditioned solve).
- **$\text{amplification} \le 0$**: The function preserved or smoothed precision; any low output significance was inherited from its inputs.

Functions in `top_unstable.json` and the Overview dashboard are ranked by `max_amplification_bits` first, then lowest `min_output_sig_bits`.

### NaN, Inf & Cancellation Diagnostics

- **`nan_instability` / `inf_instability`**: Flagged `true` if `nan_count` or `inf_count` is non-zero in any run or varies across runs.
- **Cancellation estimate**: On subtraction events (`numpy.subtract`), Pytracer records $-\log_2(|a - b| / \max(|a|, |b|))$ to quantify immediate mantissa bit loss in a single operation.

---

## Coverage & Declared Blind Spots

Pytracer writes a transparent coverage ledger to `analysis/coverage.json`:
- **Traced calls per tier** (`t1`, `t2`, `t3`, `t4`) and **native BLAS kernel counts** (`t5`).
- **`untraced_numerical_callables`**: Functions in `numpy`, `scipy`, `sklearn`, or `math` observed by `sys.monitoring` (`T4`) that were not wrapped by `T1`–`T3`. Run `pytracer suggest-targets EXP_DIR` to turn these into `targets = [...]` config entries.
- **Known Blind Spots**:
  - Pure Python `float` arithmetic (`x + y` on Python scalars) is not intercepted by NumPy ufunc/array protocols; wrap enclosing functions with `@pytracer.trace_function`.
  - C/Cython/Fortran internal calls that do not cross back into the Python interpreter require `--native` (`T5`) for BLAS/LAPACK visibility or boundary wrapping via `T1`.
