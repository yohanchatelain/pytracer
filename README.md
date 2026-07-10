# Pytracer

**Pytracer is a numerical variability profiler for Python scientific
programs.** It runs your script several times under a stochastic-arithmetic
or otherwise perturbed environment, records the inputs and outputs of
selected numerical functions, aligns the runs, and tells you **which
functions lose significant digits, amplify perturbations, or change control
flow** — as a static report, machine-readable JSON, and Parquet tables.

Pytracer does **not** perturb arithmetic itself. Pair it with a perturbation
engine such as [Verificarlo](https://github.com/verificarlo/verificarlo),
[Verrou](https://github.com/edf-hpc/verrou), or a fuzzy libmath environment.
Pytracer is the observability layer: it localizes and attributes the
variability those tools create.

> This is Pytracer 2, a clean-slate rewrite. It is not compatible with
> Pytracer 1 traces, configuration, or CLI. Pytracer 1 is archived on the
> `master` branch history.

## Quick start

```bash
pip install -e ".[dev]"

pytracer init                          # optional: writes pytracer.toml
pytracer run examples/cancellation.py --repeat 5
open .pytracer/runs/latest/report/report.html
```

`examples/` is a gallery of classical numerical-accuracy pathologies —
catastrophic cancellation (variance, quadratic formula, expm1/log1p,
polynomial evaluation near a root), summation-order non-associativity,
ill-conditioning (Hilbert matrix), and the finite-difference step-size
dilemma — each pairing an unstable formulation with its stable fix. They
double as pytracer's detection regression suite: CI asserts the unstable
variant of every pathology loses significantly more bits than its stable
twin. See `examples/README.md`.

Typical output:

```
Pytracer run complete
Runs: 5
Call groups: 42 (matched: 42, divergent: 0)
Top functions (sig(mean) bits | amplification bits | divergence):
1. mymodule.naive_variance      sig:  3.1  amp: 41.2  div: 0.000
2. numpy.linalg.solve           sig: 18.4  amp: 12.0  div: 0.000
Report: .pytracer/runs/<experiment_id>/report/report.html
```

## How it works

```
instrumentation tiers → event stream → append-safe capture → Parquet
        → call alignment → aggregation & digit-loss attribution → reports
```

- Each repetition is an **independent subprocess**; instrumentation is
  installed before your script is imported.
- Selected functions are wrapped (tier T1); NumPy **ufuncs** get a dedicated
  proxy that intercepts `__call__`, `reduce`, `accumulate`, `outer`, and
  `at` while keeping `isinstance(np.add, np.ufunc)` true (tier T2); on
  Python 3.12+, `sys.monitoring` records a census of *untraced* C callables
  and per-line execution counts for control-flow divergence (tier T4).
- `--instrument taint` adds **tracer arrays** (tier T3): tainted values
  (`pytracer.taint(x)`, plus outputs of traced calls) dispatch every NumPy
  operation — including `a + b` and `a @ b` operator syntax and calls from
  third-party code, immune to aliasing — through the array protocol.
  High overhead, alters `type(x)` checks; the drill-down tool, not the
  default.
- Every event is schema-versioned. Capture is JSON-lines (crash-safe);
  each run is also finalized to `events.parquet` for pandas/duckdb.
- Runs are aligned **call-by-call** (module, function, callsite, occurrence)
  and aggregated into per-function metrics, including **amplification**:
  the bits of precision a call destroys between its inputs and outputs.

### Coverage honesty

The report always includes a coverage section: which tiers were active, how
many calls each observed, and which numerical callables were *seen but not
traced* (candidates for `--target`). Two structural blind spots are always
stated: operator dispatch on ndarrays (`a + b`) and calls made inside
compiled extensions. Absence of an instability signal is not evidence of
stability.

### Metric honesty

Two significance bases, never conflated (`sig_basis` on every metric row):

- **element**: element-wise significant digits across runs, computed from
  arrays stored during capture (`store_arrays = "auto"`, the default,
  stores numeric arrays up to `array_store_threshold` elements as .npy
  payloads). This is the real measurement.
- **summary**: `sig(mean)` — the cross-run stability of the argument's
  mean, used when payloads were not stored. It is an *optimistic proxy*:
  element permutations across runs are nearly invisible to it (a pinned
  test demonstrates >40 proxy bits vs <8 element-wise bits).

## CLI

```
pytracer init                      write a default pytracer.toml
pytracer run SCRIPT [opts] [-- script args]
    --repeat N                     independent runs (default 1)
    --target PATH                  extra target, repeatable; globs allowed
                                   (numpy.linalg.*, mymodule.solver)
    --plugins numpy scipy sklearn  plugin target sets
    --instrument hybrid|patch|monitor|taint
    --store-arrays auto|always|never
    --alignment strict|callsite|fuzzy (fuzzy = per-callsite LCS matching)
    --native                       BLAS kernel census via LD_PRELOAD (T5)
    --continue-on-error
pytracer analyze EXPERIMENT_DIR    (re)run alignment + aggregation
pytracer report EXPERIMENT_DIR     (re)generate reports
pytracer check EXPERIMENT_DIR --min-sig-bits 20 --max-divergence 0.01
                                   CI gate: nonzero exit on violations;
                                   also reads ./pytracer-thresholds.toml
pytracer diff EXPERIMENT_A EXPERIMENT_B [--fail-on-regression]
                                   A/B comparison (library upgrades, flags)
pytracer suggest-targets EXPERIMENT_DIR
                                   propose --target entries from the T4 census
pytracer dashboard EXPERIMENT_DIR  interactive dashboard (pip install pytracer[gui]);
                                   overview, per-call explorer with element-wise
                                   drill-down, call timeline, coverage, runs
                                   (see DASHBOARD.md)
pytracer export EXPERIMENT_DIR     Perfetto/Chrome-Tracing timeline
                                   (open at https://ui.perfetto.dev)
pytracer plugins list|targets NAME
pytracer config show|validate
pytracer doctor                    environment / config / BLAS checks
pytracer clean                     delete pytracer-created experiment dirs
```

You can also instrument your own functions explicitly:

```python
import pytracer

@pytracer.trace_function
def solve_step(A, b):
    ...
```

The decorator is a no-op outside `pytracer run`, so decorated code works
everywhere.

## Configuration

`pytracer.toml` in the working directory (all keys optional; unknown keys
are errors, not silently ignored):

```toml
[trace]
plugins = ["numpy"]
targets = []
instrumentation = "hybrid"
mode = "summary"
capture_backtrace = true
store_arrays = "auto"          # enables element-wise significant digits
array_store_threshold = 100000
array_backend = "auto"         # zarr (compressed) when installed, else npy

[storage]
output_dir = ".pytracer/runs"

[analysis]
alignment = "callsite"

# Per-run environment for an external perturbation backend
# ({run_index} and {run_id} are substituted per run):
# [perturb.env]
# VFC_BACKENDS = "libinterflop_mca.so --mode=mca --seed={run_index}"

[report]
formats = ["markdown", "html", "json"]
```

No environment variables are required. The captured run metadata includes
an **allowlisted** subset of the environment only (`OMP_*`, `VFC_*`,
`PATH`, …) — never the raw environment.

## Overhead

Measure the local installation with:

```bash
python benchmarks/bench.py --iterations 2000 --repeats 5 --markdown
```

The benchmark reports T1, T2, T3, T4/hybrid, metadata-only, and the default
array-storage path separately. It uses repeated medians and reports artifact
file count so filesystem costs cannot be hidden. Representative Python 3.12 /
NumPy 2.5 results on a development host are:

| Workload | Mode | Overhead | Throughput |
|---|---|---|---|
| tiny `numpy.sum` calls | T1 summary | ~80x | ~11.5k events/s |
| tiny `numpy.sum` calls | T1 metadata | ~18x | ~50k events/s |
| 2M-element `numpy.sum` calls | T1 summary | ~28x | summary passes dominate |
| operator loop under taint | T3 summary | ~250x | ~12k events/s |
| operator loop under taint | T3 metadata | ~40x | ~70k events/s |

The per-call cost is the summaries (mean/std/min/max/norms/fingerprint × 2
events) — the measurements *are* the product. Scalar summaries use a direct
path, events from one call phase are batch-written, and repeated small array
payloads are content-deduplicated. Use targeted tracing for hot loops,
`mode = "metadata"` to skip summaries entirely, and T3 taint only to drill
into a region T1/T2 already localized. Exact ratios remain hardware- and
workload-dependent.

## Verificarlo / stochastic arithmetic

See `examples/verificarlo/` for the full workflow: a `pytracer.toml` that
rotates the MCA seed per run via `[perturb.env]`, run inside a
`verificarlo/fuzzy` container. Element-wise significant digits across those
runs directly estimate the MCA significant bits of every traced value.

## Limitations

- Pytracer does not perturb arithmetic; identical deterministic runs will
  (correctly) show zero variability.
- In the default hybrid mode, attribute patching cannot see operator
  dispatch (`a + b`); use `--instrument taint` to close that gap for
  tainted data (taint is stripped by `np.asarray` at many C entry points —
  traced-call outputs are re-tainted to re-seed it).
- Calls made inside C/Cython extensions are invisible to every Python
  tier at the value level. `--native` (Linux + C compiler) adds a BLAS
  kernel census via an LD_PRELOAD shim: it records which GEMM/GESV kernels
  ran and their dimensions — including calls from Cython — but not operand
  values. Both standard BLAS symbols and the prefixed ILP64 symbols of
  numpy/scipy wheels are interposed.
- Only the parent process is traced; joblib/multiprocessing workers are not.
- The T4 monitor requires Python ≥ 3.12.

## Development

```bash
pip install -e ".[dev]"
ruff check src tests
pytest -q
```

See `PYTRACER2_PLAN.md` for the full architecture and roadmap, and
`TECHNICAL_REVIEW.md` for the review of Pytracer 1 that motivated the
rewrite.
