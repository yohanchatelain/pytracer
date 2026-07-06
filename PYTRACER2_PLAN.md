# Pytracer 2 — Clean-Slate Implementation Plan (v2)

*Supersedes the previous draft. Clean slate only: no legacy namespace, no
migration tooling, no compatibility with `.__pytracercache__`, old pickle/HDF5
traces, or the old CLI. Pytracer 1 remains archived as reference.*

## 0. Mission and positioning

Pytracer 2 is a **numerical-stability profiler** for Python scientific
programs: it observes repeated (stochastically perturbed) executions,
localizes where floating-point variability originates and amplifies, and
presents it through static reports and an interactive dashboard.

Positioning in the ecosystem — Pytracer does **not** perturb arithmetic.
Perturbation engines (Verificarlo, Verrou, fuzzy libmath containers, PRISM)
make runs vary; Pytracer is the **observability layer**: it orchestrates the
repeated runs, records what happened at every observed call, aligns runs,
computes significance metrics, and attributes digit loss to functions and
callsites. State of the art here means three things no existing Python tool
combines:

1. **Coverage-honest tracing across the Python/C boundary** — every report
   states what fraction of the numerical work was observed, at which tier,
   and what was invisible. Absence of an instability signal is never
   presented as evidence of stability.
2. **Digit-loss attribution, not just digit counting** — per aligned call,
   compare input precision to output precision across runs and rank
   functions by *amplification* (Δsig), separating functions that destroy
   precision from those that merely propagate noisy inputs.
3. **A numerical-CI workflow** — `pytracer check` with thresholds and exit
   codes, so stability becomes a regression-testable property.

Core architecture:

```
instrumentation tiers → event stream → durable capture → Parquet/Zarr
        → call alignment → aggregation/attribution → report / dashboard / CI gate
```

---

## 1. The instrumentation problem, stated honestly

The central tension: **transparency** (see every numerical operation without
the user changing code) versus **specificity** (each interception mechanism
only works for particular kinds of callables, and the aggressive mechanisms
break the semantics of the traced program — Pytracer 1's global
`builtins.type` patch is the cautionary tale).

Why one mechanism cannot work:

- `numpy.sum`, `numpy.linalg.solve`, `scipy.optimize.minimize` are Python
  functions — ordinary attribute patching works.
- `numpy.add`, `numpy.exp`, … are **ufunc objects** implemented in C. They
  are not wrappable as plain functions, they carry semantically important
  methods (`reduce`, `accumulate`, `outer`, `at`), user code does
  `isinstance(f, np.ufunc)`, and — critically — **operator dispatch
  (`a + b`) never reads the `numpy.add` module attribute**; it goes through
  the ndarray C type slots. Attribute patching of ufuncs is therefore
  structurally incomplete no matter how well it is done.
- scipy/sklearn hot loops call BLAS/LAPACK **from compiled code**
  (e.g. sklearn Cython `cimport`s `scipy.linalg.cython_blas` — those `dgemm`
  calls never touch any Python object). No Python-level mechanism can see
  them.
- Aliases escape attribute patching: a module that did
  `from numpy import sum` before patching keeps the raw function forever.

Pytracer 2 resolves this with a **tiered stack**. Each tier is a separate
module with a declared contract: what it can see, what it cannot, its
overhead class, and its risk class. Tiers compose; the default is safe; the
deeper tiers are opt-in and their blind spots are *measured and reported*.

### 1.1 Tier T1 — Boundary patching (default)

`instrumentation/patcher.py`. Attribute patching of **Python-level**
functions and methods using `wrapt.wrap_function_wrapper` /
`wrapt.FunctionWrapper`.

- Targets: plugin lists + user `--target` globs (`numpy.linalg.*`,
  `mymodule.*`). Method targets (`sklearn...LinearRegression.fit`) patch on
  the owning class; unpatching restores the exact original attribute
  (including the "inherited method patched onto subclass" case: delete, don't
  assign).
- `wrapt` is chosen over a homegrown wrapper because its `ObjectProxy`
  transparently forwards `__name__`, `__qualname__`, `__doc__`,
  `inspect.signature`, and passes `isinstance` via the `__class__` property.
- Wrapped call protocol: new `call_id` → input events → call original →
  output events → re-raise on exception with an exception event. Result
  object returned **unchanged** (never copied, never proxied) in T1.
- Sees: every future lookup through the patched module/class attribute.
- Blind: pre-existing aliases, operator dispatch, C-internal calls.
- Overhead: per-call, proportional to summary cost; zero for unpatched code.
- Risk: low. This is the only tier enabled by default together with T4.

### 1.2 Tier T2 — Ufunc interception (default for numpy plugin)

`instrumentation/ufunc.py`. A dedicated `UfuncProxy(wrapt.ObjectProxy)`
around each targeted ufunc, assigned to the module attribute
(`numpy.add = UfuncProxy(numpy.add, …)`).

Contract:

- Intercepts `__call__`, `reduce`, `reduceat`, `accumulate`, `outer`, `at`
  — each emits events tagged with the ufunc method name (a `reduce` is
  numerically a different operation than an elementwise call and must be
  distinguishable in analysis).
- Forwards `nin/nout/ntypes/types/identity/signature` and everything else via
  the proxy; `isinstance(numpy.add, np.ufunc)` remains `True`
  (`ObjectProxy.__class__` reports the wrapped class).
- `out=` arguments handled: when the caller supplies `out`, summarize the
  buffer *after* the call and flag the event `inplace=True`.
- **Declared blind spot:** `ndarray.__add__` and friends (operator dispatch),
  and internal C consumers of the ufunc. These are covered by T3/T5, and the
  coverage report says so explicitly.
- NumPy ≥ 2.0 note: module attribute assignment on `numpy` works but must be
  tested against numpy's lazy `__getattr__`; the patcher resolves the
  attribute once (forcing materialization) before replacing it.

This tier is the concrete answer to "specificity of packages like numpy
ufunc": ufuncs get a bespoke interceptor with full method coverage instead of
being either skipped (Pytracer 1 excluded them) or naively wrapped (breaking
`isinstance` and `reduce`).

### 1.3 Tier T3 — Tracer arrays (opt-in transparency mode)

`instrumentation/tracer_array.py`. A `TracedArray(np.ndarray)` subclass (plus
`__array_wrap__`) implementing **`__array_ufunc__`** and
**`__array_function__`**. Selected entry points (script inputs, outputs of
T1-wrapped calls, or values the user tags with `pytracer.taint(x)`) are
wrapped; from then on **every** NumPy operation *on those arrays* — including
operators, ufunc methods, and most of the public NumPy API — dispatches
through the protocol and is observed, **regardless of aliasing**, because
protocol dispatch keys on the operand type, not on how the function was
looked up.

- Sees: all ufunc calls and NumPy API calls whose operands carry the taint,
  including `a + b`, `a @ b`, in-place ops, and calls made from third-party
  *Python* code that received the arrays.
- Blind / hazards: `np.asarray` (not `asanyarray`) strips the subclass —
  common at scipy entry points — so taint dies at some C boundaries. Two
  mitigations: (a) T1 wrappers **re-taint** their outputs when T3 is active,
  so taint is re-seeded at every known boundary; (b) *taint-loss telemetry*:
  when a T1-wrapped call receives tainted inputs and produces untainted
  intermediate protocol traffic afterward drops to zero for those objects,
  the coverage report records a taint-loss at that callsite. Some C
  extensions may also choke on subclasses; hence opt-in.
- Overhead: high (every elementwise op emits an event); mitigations:
  per-callsite sampling (`trace 1 of N occurrences`), event coalescing for
  loops (same callsite+shapes collapsed with a count), and a hard event
  budget with explicit truncation notice.
- Risk: medium — semantics-altering for code doing exact `type(x) is
  np.ndarray` checks. Never default; designed for drilling into a region
  after T1/T2 localized it.

### 1.4 Tier T4 — Runtime monitor (default, structure only)

`instrumentation/monitor.py`, built on `sys.monitoring` (PEP 669, hence the
Python ≥ 3.12 floor).

- Purpose: **call-graph and control-flow only** — `PY_START/PY_RETURN/RAISE`
  for Python frames and `CALL` events (which fire for calls to C callables
  too, so the monitor *sees that* `numpy.add` was called even when no wrapper
  is installed — it just cannot see the operands).
- Maintains the ambient **call context** (`call_context.py`, a contextvar
  stack) that gives every T1/T2/T3 event its `parent_call_id`. This is the
  join key that makes the call graph, flame graph, and digit-loss attribution
  possible. (The event schema keeps `parent_call_id`; dropping it — as an
  earlier draft did — makes call-graph reconstruction impossible.)
- Scoped: monitoring is filtered to the target script's code objects and
  configured module prefixes; stdlib and pytracer frames are disabled at the
  `sys.monitoring` level (per-code-object DISABLE) to keep overhead
  acceptable on sklearn-sized workloads.
- Also produces the **line-level divergence signal**: per (code object,
  line) execution counts per run; cross-run count differences localize
  where perturbation changed control flow, independent of any wrapper.

### 1.5 Tier T5 — Native kernel census (opt-in, Linux)

`instrumentation/native/` — a small `LD_PRELOAD` shim interposing the
dynamic symbols of BLAS/LAPACK (`dgemm_`, `sgemm_`, `dgemv_`, `dnrm2_`,
`dgesv_`, `dgesdd_`, … plus their cblas aliases).

- Records, per kernel call: symbol, dimensions (m, n, k, lda…), thread id,
  monotonic timestamp — appended lock-free to a per-process binary ring
  buffer flushed to `runs/run-XXX/native_kernels.bin`. Optionally (config)
  computes cheap output norms by calling back into BLAS (`dnrm2`) — off by
  default, measurable cost.
- Joined offline with the T4 timeline (timestamp + thread id) to annotate
  Python-level calls with the native kernels they triggered. This is what
  finally makes sklearn's Cython→BLAS traffic *visible*: not the values, but
  **which kernels ran, how big, under which Python call** — the census that
  the coverage report is built on.
- Explicit limits, documented: requires dynamically linked BLAS (OpenBLAS,
  netlib, most MKL setups; not static links), Linux only, `--instrument
  native` opt-in, no operand values. It is a coverage/attribution instrument,
  not a value tracer. Value-level perturbation of these kernels is the job of
  Verificarlo/Verrou, and the docs say exactly that.

### 1.6 The tradeoff, as the user-facing contract

| Tier | Sees | Blind to | Overhead | Risk | Default |
|------|------|----------|----------|------|---------|
| T1 patch | targeted Python functions/methods | aliases, operators, C-internal | low | low | **on** |
| T2 ufunc | targeted ufuncs incl. `reduce`/`accumulate`/`out=` | operator dispatch, C-internal | low-med | low | **on** (numpy plugin) |
| T3 tracer array | *all* NumPy ops on tainted data, alias-proof | taint stripped at `asarray`/C entry | high | med | off (`--instrument taint`) |
| T4 monitor | call graph, C-call *occurrence*, line coverage | operand values, C-internal frames | med | low | **on** |
| T5 native census | BLAS/LAPACK kernel calls + shapes from anywhere incl. Cython | operand values, non-BLAS C code | low | low-med | off (`--instrument native`) |

`instrumentation = "hybrid"` (default) = T1+T2+T4.
`pytracer run --instrument taint` adds T3; `--instrument native` adds T5.

**Coverage accounting** (`analysis/coverage.py`) is the piece that turns
this table from documentation into a feature: for each run it computes
(a) events observed per tier, (b) C-callable invocations seen by T4 that had
no T1/T2 wrapper (missed Python-boundary work, with counts per function —
this doubles as the *target-suggestion* list), (c) native kernels from T5
with no correlated traced call (invisible-to-Python work), (d) taint-loss
sites from T3. The report renders this as an "Observed / Unobserved" section
with percentages. This is the plan's core scientific-integrity feature.

### 1.7 Discovery workflow (restores Pytracer 1's localization mission)

Targeted tracing can only confirm suspicions; the discovery loop finds them:

```
pytracer run script.py --repeat 5 --discover
    # T4(+T5) only: cheap; ranks numerical callables by call count,
    # data volume (T5 dims), and line-divergence proximity
pytracer suggest-targets .pytracer/runs/<id>   # emits a targets block
pytracer run script.py --repeat 20 --targets-from suggested_targets.toml
```

`suggest-targets` output is ranked by expected information gain: functions
whose call counts differ across runs (control-flow divergence) first, then by
native-kernel volume attributed beneath them, then by call frequency.

---

## 2. Execution model

**One subprocess per repetition. No exceptions.** In-process repeats share
module caches, RNG state, joblib pools, and perturbation-backend seeds; they
are not statistically independent and one crash kills the experiment.

`pytracer run script.py --repeat 10 -- --script-arg 1`:

1. Parent (`cli/run.py`) loads config, resolves plugins/targets, creates the
   experiment directory, snapshots resolved config as `config.toml`.
2. For each run *k*: spawn `python -m pytracer._bootstrap` with the run
   directory, target list, and script path in a temp spec file; the child
   installs tiers **before** importing the target script, sets `sys.argv`,
   executes the script as `__main__` (`runpy` semantics), flushes and closes
   the writer in a `finally:`. Child exit code recorded; nonzero stops the
   experiment unless `--continue-on-error` (failed runs keep their partial
   trace + exception metadata and are excluded from alignment by default).
3. **Perturbation orchestration**: `--perturb <profile>` applies per-run
   environment from a profile table (e.g. Verificarlo: rotate
   `VFC_BACKENDS`/seed per run; fuzzy: container/env preset; `none`:
   identical env → determinism check). Profiles live in
   `pytracer/perturb/profiles/` and are user-extensible in `pytracer.toml`.
   Pytracer never implements perturbation itself.
4. After runs: align → aggregate → report in the parent.

Every run directory gets `RunMetadata`; the environment capture is
**allowlist-only** (`PATH`, `PYTHON*`, `OMP_*`, `OPENBLAS_*`, `MKL_*`,
`VFC_*`, `LD_PRELOAD`, locale) — never the raw environment; secrets must not
end up in shareable trace directories. Full-env capture is
`--capture-env=all` with a warning.

---

## 3. Event and data model

`trace/event.py`, msgspec `Struct`s (msgspec is a core dep; faster than
dataclasses and validates on decode).

```python
Phase = Literal["input", "output", "exception", "call"]     # "call" = T4 structural
PayloadKind = Literal["none", "summary", "array_ref"]

class SourceRef(msgspec.Struct):       # interned: one table per run
    file_id: int; lineno: int

class NumericSummary(msgspec.Struct):
    dtype: str; shape: tuple[int, ...]; size: int
    mean: float; std: float; min: float; max: float
    l2_norm: float; linf_norm: float
    nan_count: int; inf_count: int; zero_count: int; subnormal_count: int
    cancellation: float | None      # e.g. |sum(x)| / sum(|x|) for reductions
    fingerprint: str | None         # blake2b over ≤1MB strided sample

class TraceEvent(msgspec.Struct):
    schema_version: str             # "2.0.0"
    run_id: str
    event_id: int                   # per-run, writer-local, thread-safe
    call_id: int                    # unique per call within run
    parent_call_id: int | None      # from T4 call context
    tier: Literal["t1","t2","t3","t4"]
    occurrence: int                 # per-callsite counter (see §5)
    phase: Phase
    module: str; qualname: str
    ufunc_method: str | None        # "__call__" | "reduce" | ...
    arg_name: str | None
    inplace: bool
    payload_kind: PayloadKind
    summary: NumericSummary | None
    payload_ref: str | None         # zarr path when arrays stored
    source: SourceRef | None
```

Design notes:

- **Calls are the unit of analysis**; events are the wire format. The reader
  reassembles `CallRecord` objects (inputs, outputs, exception, children).
- Source *text* is never stored per event: a per-run `sources.json` interning
  table maps `file_id → path`, and copied source files (opt-in) go under the
  run dir.
- `subnormal_count` and `cancellation` are cheap and are leading indicators
  of precision loss — they belong in the summary from day one.
- Complex arrays: absolute-value summaries in MVP, `real/imag` split later;
  the summary records `dtype` so analysis knows the caveat applies.

### 3.1 Summaries and true significant digits

Two metric classes, never conflated:

1. **Summary-statistic stability** (default, cheap): across runs, for each
   aligned scalar summary field, compute `sig_of_mean = -log2(std/|mean|)`
   (guarded for `mean=0`, `std=0`, NaN/Inf; reported in **bits** everywhere).
   Reports label this `sig(mean)` — the stability *of the mean*, an
   optimistic proxy. Rationale documented: element permutations across runs
   are invisible to it.
2. **Element-wise significant digits** (the real thing): requires arrays.
   `store_arrays` policy defaults to `"auto"`: arrays with
   `size ≤ array_store_threshold` (default 1e6 elements) are stored to Zarr
   (zstd-compressed, chunked) and element-wise sig across runs is computed
   exactly — via the `significantdigits` package (CNH and general methods)
   behind `analysis/significant_digits.py`. Above threshold: summary only,
   flagged `sig_basis = "summary"` in every derived metric.

Element-wise results yield per-argument sig **distributions**
(min/median/p05) and, for array data with spatial meaning, **sig maps**
(exported as arrays; the neuroimaging use case reads them as images).

### 3.2 Digit-loss attribution (the headline metric)

For each aligned call with element-wise or summary sig on inputs and outputs:

```
amplification = min_sig(inputs) − min_sig(outputs)     # bits lost in this call
```

Aggregated per function: `mean/max amplification`, `n_calls`, weighted by
data size. The report's "Top unstable functions" is ranked by amplification
first, absolute output sig second, control-flow divergence third — this
separates *sources* of instability from *victims* of noisy inputs, which is
the question users actually have.

---

## 4. Storage

- **Capture format = append-safe.** During a run the writer appends
  length-prefixed msgspec frames (or JSONL with `--storage jsonl` for
  human debugging) to `events.bin` — crash of the traced program loses at
  most the last partial frame. Parquet is **not** written during capture
  (row-group buffering + crashes = truncated files).
- **Finalize step** (child `finally:` + parent fallback): convert capture to
  `events.parquet` (summary fields flattened to columns; `shape` as
  `list<int64>`). If the child died, the parent finalizes from `events.bin`
  and marks the run `dirty=true`.
- Arrays: `runs/run-XXX/arrays.zarr/<call_id>/<arg_name>`.
- Native census: `native_kernels.bin` → `native_kernels.parquet` at finalize.
- No pickle anywhere in the MVP. If a full-object debug mode is ever added it
  is `--mode debug-object`, loudly documented as unsafe for untrusted traces.

Experiment layout:

```
.pytracer/runs/<experiment_id>/          # timestamped; `latest` symlink updated
  config.toml  metadata.json  sources/
  runs/run-000/{metadata.json, events.parquet, arrays.zarr/, native_kernels.parquet}
  analysis/{alignment.json, coverage.json, function_summary.parquet,
            argument_summary.parquet, amplification.parquet, divergence.json,
            sig_maps.zarr/}
  report/{report.html, report.md, report.json}
```

`pytracer clean` deletes only directories containing the
`.pytracer-experiment` marker file it wrote — never an arbitrary configured
path (Pytracer 1 lesson).

---

## 5. Alignment

Unit of alignment: **calls**, not events (aligning input/output events
independently mismatches them when counts diverge).

- `occurrence` is a **per-callsite deterministic counter**
  (`(module, qualname, source, ufunc_method)` → 0,1,2,…), maintained
  per-thread then merged; never derived from the global event counter.
- Modes:
  - `strict`: identical call sequences required; first divergence is an
    error pointing at the callsite. (Also the determinism test mode.)
  - `callsite` (default): match by callsite key + occurrence index. Known
    limitation stated in docs: an inserted early call shifts later
    occurrences at that callsite.
  - `fuzzy`: per-callsite **LCS matching** over occurrence sequences, using
    input-summary shape/dtype (and fingerprints when deterministic) as match
    hints; unmatched calls become missing/extra records instead of cascading
    misalignment.
- `alignment.json` reports matched/missing/extra per callsite and per run,
  plus `divergence_score = (missing+extra)/expected` per function, and the
  T4 line-count divergence table (which localizes control-flow divergence
  even inside untraced code).

---

## 6. Analysis outputs

Per function and per argument/output (`function_summary.parquet`,
`argument_summary.parquet`, `amplification.parquet`):

`n_runs, n_calls, n_events, sig_basis, min/median/p05 significant bits,
sig(mean) proxies, mean/max amplification, max_abs_std, nan_instability,
inf_instability, subnormal_rate, cancellation_worst, divergence_score,
native_kernel_volume (from T5), coverage_tier`.

`analysis/coverage.json` (§1.6) and `analysis/top_unstable.json` (the ranked
list the terminal prints).

---

## 7. Reports, visualization, CI gate

### 7.1 Static report (required before any dashboard)

Markdown + self-contained HTML (Jinja2; Plotly figures inlined, no CDN):

1. Summary (runs, events, matched %, perturbation profile, tiers active)
2. **Coverage: what was observed / what was not** (tier table, unwrapped
   C-callable top-list, taint losses, native kernels without Python
   attribution)
3. Top unstable functions (ranked by amplification; bits, with sig_basis)
4. Top unstable arguments/outputs
5. Control-flow divergence (callsites + line-level)
6. NaN/Inf/subnormal/cancellation incidents
7. Reproducibility appendix (versions, allowlisted env, seeds, command)
8. Recommendations (auto-generated: suggested targets, suggested
   `--instrument taint` drill-downs, threshold suggestions for `check`)

### 7.2 Dashboard (optional, `[gui]` extra, after reports are stable)

Pages, in build order:

1. Overview + coverage
2. Function/argument tables (sortable by amplification, sig, divergence)
3. **Instability flame graph**: T4 call tree, width = time or data volume,
   color = amplification (digit-loss cascade at a glance) — this is the
   signature visualization
4. Callsite drill-down: per-occurrence sig across runs, input vs output
   distributions, native kernels underneath
5. **Sig maps**: element-wise significance rendered as heatmaps/slices for
   2D/3D arrays (neuroimaging-ready)
6. Divergence timeline (runs × callsites, missing/extra markers)
7. Metadata

Perfetto export (`pytracer export perfetto <run_dir>`) emits a trace-event
JSON timeline with sig/amplification annotations — timeline UX for free.

### 7.3 Numerical CI

```
pytracer check .pytracer/runs/<id> --min-sig-bits 20 --max-divergence 0.01
pytracer diff  .pytracer/runs/<A> .pytracer/runs/<B>   # A/B: lib versions, flags
```

`check` exits nonzero with a focused summary when thresholds are violated
(threshold file supported: `pytracer-thresholds.toml`). `diff` compares two
experiments function-by-function (sig deltas, new divergences) — numerical
regression testing across library upgrades is a first-class use case.

---

## 8. Configuration and CLI

Priority: CLI > `pytracer.toml` (cwd) > built-in defaults. No mandatory env
vars. `pytracer init` writes the default TOML (via `tomli-w` or a template
string — stdlib `tomllib` is read-only).

```toml
[trace]
plugins = ["numpy"]
targets = []                       # explicit adds; globs allowed
instrumentation = "hybrid"         # t1+t2+t4
sample_rate = 1                    # 1/N per-callsite sampling for T2/T3
store_arrays = "auto"              # auto | always | never
array_store_threshold = 1_000_000

[perturb]
profile = "none"                   # none | verificarlo | fuzzy | custom.*

[storage]
backend = "parquet"                # capture is always append-safe binary/jsonl
output_dir = ".pytracer/runs"

[analysis]
alignment = "callsite"
significant_digits = "cnh"         # cnh | general — used when arrays stored
                                   # summary-only data is always labeled sig(mean)
[report]
formats = ["markdown", "html", "json"]
```

CLI: `init, run, analyze, report, dashboard, check, diff, suggest-targets,
plugins list|targets, config show|validate, doctor, clean,
export perfetto`.

`pytracer doctor` checks: Python ≥3.12, numpy version + ABI, optional deps
(pyarrow/zarr/dash/significantdigits), **which BLAS is loaded and whether it
is dynamically linked** (T5 feasibility), writability, config validity,
plugin target resolvability (imports each target, reports missing/renamed —
"known incompatible targets" seeded with ufunc-method edge cases), and
whether a perturbation backend is detectable (`VFC_BACKENDS`, preloads).

---

## 9. Plugins

`plugins/base.py` as before (`TraceTarget(import_path, kind, tags)`), with
two additions: `kind: Literal["function","method","ufunc"]` (routes to
T1 vs T2) and per-plugin `summarize()` hooks for library-specific containers
(e.g. scipy sparse: summarize `.data`; pandas: summarize numeric blocks).

- **numpy**: Python-level (`sum, mean, std, dot, matmul, linalg.{norm, solve,
  det, eig, svd, lstsq, inv, cholesky, qr}`) as T1; ufuncs (`add, subtract,
  multiply, divide, exp, log, sqrt, …` — configurable set) as T2. `numpy`
  is the only library imported eagerly.
- **scipy** (lazy): `linalg.{solve, lu, qr, svd, eigh}`,
  `optimize.{minimize, root, least_squares}`, `integrate.{quad, solve_ivp}`,
  `interpolate.interp1d`, `ndimage.affine_transform`, sparse-aware
  summarizer. Documented: `LowLevelCallable` and `cython_blas` paths are
  T5-only territory.
- **sklearn** (lazy): estimator-level `fit/predict/transform` on the usual
  suspects; documented: joblib **worker processes are not traced** (parent
  only) — a limitation until a child-bootstrap hook is added post-beta.
- Post-beta: torch (via `__torch_function__`/`torch.library` — the T3
  analogue is native there), JAX (jaxpr interception), nibabel/BIDS.

Plugins import their library lazily; **scipy/sklearn/pandas are NOT core
dependencies**. A tracer must not constrain the versions of the libraries it
studies.

---

## 10. Packaging

```toml
[project]
name = "pytracer"                  # verify PyPI name availability first
version = "2.0.0a0"
requires-python = ">=3.12"
dependencies = [
  "numpy>=1.26", "wrapt>=1.16", "msgspec>=0.18",
  "pyarrow>=15", "jinja2>=3.1", "tomli-w>=1.0", "tqdm>=4.66",
]
[project.optional-dependencies]
arrays  = ["zarr>=2.18", "numcodecs>=0.12"]
sig     = ["significantdigits>=0.2"]
gui     = ["dash>=2.17", "plotly>=5.22", "dash-cytoscape>=1.0", "pandas>=2.1"]
dev     = ["pytest>=8", "pytest-console-scripts", "ruff>=0.6", "mypy>=1.10",
           "pre-commit>=3.7", "hypothesis>=6"]
```

`src/` layout as in the previous draft, with `instrumentation/` split into
`patcher.py, ufunc.py, tracer_array.py, monitor.py, call_context.py,
native/` and new modules `analysis/coverage.py`, `perturb/`, `cli/check.py`,
`cli/diff.py`.

Hard rules (CI-enforced):

- `python -c "import pytracer"` with no config, no env vars, in an empty
  directory: succeeds silently, creates nothing. (Import-side-effect test.)
- No `sys.exit` outside `cli/`; library raises `PytracerError` subclasses.
- Every artifact carries `schema_version`; schema changes bump it and add a
  reader shim within 2.x.
- Redacted-env rule (§2) tested.

---

## 11. Testing

**Unit**: config, summaries (empty/scalar/NaN/Inf/complex/object-dtype/
Fortran-order/strided; hypothesis property tests: summary never raises,
never copies >max_bytes), event round-trip, capture-file recovery from
truncation, patch/unpatch (idempotence, exception-safety, signature
preservation, inherited-method case), **UfuncProxy conformance**
(`isinstance`, `reduce/accumulate/outer/at`, `out=`, dtype kwargs),
TracedArray (operators, protocol dispatch, taint propagation and loss),
occurrence determinism under threads, alignment (missing/extra/reordered;
LCS), amplification math, coverage accounting, report generation.

**Integration** (`tests/programs/`): `simple_numpy.py`,
`ufunc_operators.py` (validates the T2-blind/T3-covered boundary — assert
the coverage report flags operator ops in hybrid mode and captures them with
`--instrument taint`), `scipy_solve.py`, `sklearn_fit.py`,
`control_flow_divergence.py` (seeded RNG variation), `exception_case.py`,
`threads.py`.

**Golden invariants**:
- Determinism test: `--repeat 3 --perturb none` ⇒ zero divergence, max sig,
  `strict` alignment passes. (Regression net for the whole pipeline.)
- Injected-instability test: a program with a known catastrophic
  cancellation under seeded perturbation ⇒ that function ranks #1 by
  amplification. (The tool detects what it exists to detect.)
- Transparency test: patched functions preserve results bit-for-bit vs
  unpatched run (`--perturb none`, compare fingerprints).

**Performance** (`benchmarks/`): overhead ratio per tier (T1/T2/T4 target:
<2× on numpy-heavy code with default targets; T3 unbounded but reported),
events/sec, trace size/event, capture-vs-finalize timing. Benchmarked in CI
weekly, not per-PR.

**Native (T5)**: separate CI job on ubuntu with OpenBLAS: shim intercepts
`dgemm` from a `numpy @` and from a Cython extension test module; join with
timeline verified.

---

## 12. PR sequence

1. Skeleton: src layout, pyproject, CLI stub, CI, import-side-effect test.
2. Config system + `init`/`config show|validate` (+ tomli-w).
3. Event schema (msgspec) + capture writer/reader + truncation recovery.
4. Numeric summaries (+ hypothesis tests).
5. T1 patcher + target resolver (globs) + transparency tests.
6. **T2 UfuncProxy** + conformance suite.
7. T4 monitor + call context (`parent_call_id`) + line counters.
8. `pytracer run`: subprocess bootstrap, `--repeat`, perturbation profiles,
   finalize-to-Parquet, `latest` symlink, exit-code semantics.
9. Alignment (strict/callsite/fuzzy-LCS) + `alignment.json`.
10. Aggregation + amplification + coverage accounting.
11. Reports (md/html/json) + terminal summary + `doctor`.
12. `check` + `diff` (CI gate).
13. Zarr array storage (`auto` policy) + element-wise sig via
    `significantdigits` adapter + sig maps.
14. **T3 tracer arrays** + taint telemetry + sampling/coalescing.
15. **T5 native census** + timeline join + doctor BLAS checks.
16. `suggest-targets` discovery workflow.
17. Dashboard (overview/tables → flame graph → sig maps → divergence).
18. Perfetto export; plugin summarizers for scipy-sparse/pandas.

MVP = PRs 1–11 (alpha). Beta = +12–16. Dashboard completes the SOTA claim.

Every PR: code + tests + docs; gates: `ruff check`, `pytest -q`,
`pytracer --help`, import-side-effect test.

---

## 13. Definition of done

**Alpha**: `pytracer run examples/cancellation.py --repeat 5 --perturb none`
and a documented Verificarlo/fuzzy example both work end-to-end on Python
3.12/3.13; hybrid tier default; coverage section in report; determinism and
injected-instability golden tests pass.

**Beta**: element-wise sig with Zarr; T3 and T5 opt-ins working with their
conformance suites; `check`/`diff` usable in CI; discovery workflow;
overhead benchmarks published in docs; limitations page (aliasing, joblib
workers, static BLAS, taint stripping) complete.

**SOTA claim** (1.0): flame graph + sig maps in dashboard; Perfetto export;
torch or JAX plugin; a worked neuroimaging case study reproducing a known
instability result with the discovery→drill-down→attribution loop.

---

## 14. Risks

| Risk | Mitigation |
|------|-----------|
| numpy 2.x internals shift (lazy attrs, ufunc changes) | T2 conformance suite in CI against numpy matrix (1.26, 2.x); doctor detects unresolvable targets |
| T3 breaks third-party code on exact-type checks | opt-in, documented, taint telemetry shows where; never default |
| T5 unlinkable (static MKL, macOS) | doctor reports feasibility; census is optional by design; coverage report degrades gracefully |
| Overhead scares users off | per-callsite sampling, event budgets, tier table with measured ratios in docs |
| Occurrence cascades under heavy divergence | fuzzy-LCS mode; divergence localized by T4 line counts independent of wrappers |
| `sig(mean)` proxy misread as real precision | naming, `sig_basis` column, report labeling, `auto` array storage making element-wise the common case |
