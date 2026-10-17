# pytracer Engineering Fix & Modernization Roadmap

**Document Version**: 2.0.0-ROADMAP  
**Date**: 2026-10-17  
**Target Repository**: `pytracer` (v2.0.0 Clean-Slate Architecture)  
**Author**: Pytracer Fix Roadmap Worker  
**Repository State**: Read-Only Core Library Preservation (`git status --porcelain pytracer/` is empty)  
**Authoritative Input**: `CODE_REVIEW_AND_BUGS.md` (30 Confirmed Defects)  

---

## 1. Executive Summary & Strategic Rationale

`pytracer` is an automated numerical variability profiler and perturbation analysis engine for scientific Python programs. Following the comprehensive code review and bug catalog documented in `CODE_REVIEW_AND_BUGS.md`, 30 confirmed defects across all 5 primary architectural subsystems were identified and verified.

This document establishes the **authoritative, dependency-ordered engineering roadmap** to systematically remediate all 30 defects. The roadmap is structured into 6 sequential phases (Phase 0 through Phase 5), designed to resolve prerequisite packaging blockers and instrumentation invariants before progressing to trace persistence, numerical analysis gates, user-facing visualization, and CI/CD hardening.

### 1.1 Core Engineering Principles

1. **Strict Dependency Inversion**: Low-level packaging primitives, environment diagnostic gates, and foundational instrumentation contracts must be established before downstream storage, analysis, and visualization pipelines are modified.
2. **Deterministic Taint and Mutation Preservation**: Interception tiers (T1 Patcher, T2 TracedUfunc, T3 TracedArray, T4 Monitor, T5 Native Shim) must maintain exact semantics—in-place mutations, signature parameter names, and array views must never be dropped or silently mutated.
3. **Fail-Closed Numerical Safety**: Analysis algorithms must treat non-finite values (all-NaN, all-Inf, or sporadic NaN runs) and complex array components with rigorous statistical penalization rather than silent masking or optimistic pass-through.
4. **Zero-Regression Verification**: Every work item specifies unambiguous automated verification commands (`pytest` unit/integration tests and reproduction harness commands) that demonstrate defect remediation without breaking existing capabilities.
5. **Core Library Preservation**: All remediation plans adhere to strict repository preservation during the audit phase (`git status --porcelain pytracer/` remains empty).

### 1.2 Summary Defect Coverage

All 30 defects cataloged in `CODE_REVIEW_AND_BUGS.md` are mapped 100% to concrete work items across the 6 phases:

| Phase | Phase Name | Focus Subsystems | Defect Count | Target Bug IDs |
|:---:|---|---|:---:|---|
| **Phase 0** | Modernization & Packaging Primitives | Subsystems 4 & 5 | 4 | BUG-COMPAT-003, BUG-COMPAT-002, BUG-STORE-006, BUG-CLI-002 |
| **Phase 1** | Core Instrumentation & Interception Invariants | Subsystems 1 & 5 | 11 | BUG-CORE-001, BUG-CORE-002, BUG-CORE-003, BUG-CORE-004, BUG-CORE-005, BUG-CORE-006, BUG-CORE-007, BUG-CORE-008, BUG-CORE-010, BUG-CLI-004, BUG-CLI-001 |
| **Phase 2** | Trace Storage, Serialization & Payload Integrity | Subsystems 2 | 4 | BUG-STORE-001, BUG-STORE-002, BUG-STORE-003, BUG-STORE-004 |
| **Phase 3** | Numerical Stability Analysis & CI Gate Hardening | Subsystems 3 & 5 | 6 | BUG-NUM-001, BUG-NUM-002, BUG-NUM-003, BUG-NUM-004, BUG-NUM-005, BUG-CLI-003 |
| **Phase 4** | Visualization, Reporting & User Experience | Subsystems 2 & 3 | 4 | BUG-COMPAT-001, BUG-VIS-001, BUG-VIS-002, BUG-STORE-005 |
| **Phase 5** | CI/CD, Test Suite Hardening & Long-Term Health | Subsystems 1 & 4 | 3 | BUG-CORE-009, BUG-COMPAT-001, BUG-COMPAT-002 |

*Note*: Bug IDs `BUG-STORE-006`, `BUG-COMPAT-001`, and `BUG-COMPAT-002` span multiple phases (e.g. initial dependency/format configuration in Phase 0/Phase 4, followed by storage layer fixes in Phase 2, and end-to-end integration gating in Phase 5). Every single bug ID has a designated primary owner and execution milestone.

---

## 2. Global Dependency Architecture & Sequencing Diagram

The engineering phases cannot be executed in arbitrary order. Downstream numerical analysis depends on structurally intact event streams; event streams require robust serialization and crash recovery; serialization depends on valid in-place array captures from instrumentation; and instrumentation relies on environment sanity and packaging integrity.

### 2.1 ASCII Dependency Architecture Diagram

```
+=============================================================================================================+
|                                    PHASE 0: Modernization & Packaging Primitives                             |
|  - Python < 3.12 Hard Fail (BUG-COMPAT-003)                                                                 |
|  - Dependency Sync: scikit-learn & Zarr 2/3 cleanup (BUG-COMPAT-002, BUG-STORE-006)                         |
|  - CLI Explicit Config Plumbing --config (BUG-CLI-002)                                                      |
+======================================================+======================================================+
                                                       |
                                                       v
+=============================================================================================================+
|                               PHASE 1: Core Instrumentation & Interception Invariants                       |
|  - Method Signature Binding on Unbound Calls (BUG-CORE-001)                                                 |
|  - Recursive List Taint Propagation in T3 TracedArray (BUG-CORE-002)                                        |
|  - TracedUfunc In-Place Rectification: at, __call__, reduce/accumulate (BUG-CORE-003, 004, 005)               |
|  - Non-Copying Contiguity-Aware Array Fingerprinting (BUG-CORE-006)                                         |
|  - PEP 669 Monitor: Callable Classification, Scoping & Status (BUG-CORE-007, 008, 010)                       |
|  - Patcher Class Wildcard Target Resolution (BUG-CLI-004)                                                   |
|  - Experiment Runner Child Process CWD Preservation (BUG-CLI-001)                                           |
+======================================================+======================================================+
                                                       |
                                                       v
+=============================================================================================================+
|                               PHASE 2: Trace Storage, Serialization & Payload Integrity                     |
|  - Parquet Schema Export: payload_ref column inclusion (BUG-STORE-001)                                      |
|  - Zarr 3 Store Overwrite & Collision Resilience (BUG-STORE-002, BUG-STORE-006)                             |
|  - Safe EOF Truncation vs. Syntax Corruption Parsing (BUG-STORE-003)                                        |
|  - Disambiguation of Multi-Output Unnamed Calls Ret0, Ret1 (BUG-STORE-004)                                   |
+======================================================+======================================================+
                                                       |
                                                       v
+=============================================================================================================+
|                              PHASE 3: Numerical Stability Analysis & CI Gate Hardening                      |
|  - Element-Wise Complex & Mixed-Type Array Magnitude Handling (BUG-NUM-001)                                |
|  - 100% Non-Finite (NaN/Inf) CI Gate Enforcement & None-Sig Rejection (BUG-NUM-002, BUG-CLI-003)             |
|  - Sporadic NaN Statistical Precision Penalty (BUG-NUM-003)                                                |
|  - Control-Flow Divergence & Epsilon Thresholding in Diff Engine (BUG-NUM-004, BUG-NUM-005)                 |
+======================================================+======================================================+
                                                       |
                                                       v
+=============================================================================================================+
|                                PHASE 4: Visualization, Reporting & User Experience                          |
|  - Modern AgGrid Migration & Deprecation Warning Elimination (BUG-COMPAT-001)                               |
|  - Dash Active Cell Viewport Sorting & Explorer Navigation Fix (BUG-VIS-001)                                |
|  - Semantic HTML Markdown Report Rendering & CSS Activation (BUG-VIS-002)                                  |
|  - Perfetto Chrome Trace Span Export with Unnamed Returns (BUG-STORE-005)                                   |
+======================================================+======================================================+
                                                       |
                                                       v
+=============================================================================================================+
|                                PHASE 5: CI/CD, Test Suite Hardening & Long-Term Health                      |
|  - Native BLAS Census: Single-Precision Fortran sgemm_ & scipy_sgemm_64_ (BUG-CORE-009)                     |
|  - Strict Warning Gating (-W error::Warning) in CI Test Pipeline (BUG-COMPAT-001)                           |
|  - End-to-End Scikit-Learn Integration Pipeline Validation (BUG-COMPAT-002)                                 |
|  - Full Regression Suite Execution (All 205 Tests Passing + 30 Bug Reproductions Verified)                  |
+=============================================================================================================+
```

### 2.2 Phase Transition Gating Rules

| Transition Gate | Source Phase | Target Phase | Mandatory Exit Criteria |
|---|---|---|---|
| **Gate 0 -> 1** | Phase 0 | Phase 1 | `pytracer doctor` terminates with exit code 1 on Python < 3.12; `pyproject.toml` dependencies resolve cleanly via `uv sync` / `pip install -e ".[all]"`; `--config` is recognized by CLI parser. |
| **Gate 1 -> 2** | Phase 1 | Phase 2 | All 10 core instrumentation reproduction tests pass; unbound method signatures preserve parameter names; ufunc in-place operations capture mutated arrays; zero memory duplication on F-contiguous array hashing. |
| **Gate 2 -> 3** | Phase 2 | Phase 3 | Parquet files contain non-null `payload_ref` links; Zarr 3 array writes succeed idempotently without `ContainsArrayError`; truncated crash traces decode up to the crash point without raising `PytracerError`. |
| **Gate 3 -> 4** | Phase 3 | Phase 4 | Mixed-type complex runs report genuine instability without `ComplexWarning`; 100% NaN outputs trigger CI check failures; sporadic NaNs drop significance to 0.0 bits; diff engine ignores machine epsilon jitter. |
| **Gate 4 -> 5** | Phase 4 | Phase 5 | Dash dashboard initializes with zero deprecation warnings; table sorting navigates to matching Explorer items; HTML reports render fully formatted semantic tables; Perfetto spans display function return values. |
| **Gate 5 -> Final** | Phase 5 | Production | Native BLAS shim logs single-precision Fortran kernels; all 205 baseline tests pass with zero skips (`test_sklearn_plugin_traces_fit` active); full suite passes under `-W error::Warning`. |

---

## 3. Complete Bug-to-Phase Cross-Reference Matrix & Sequencing Table

The table below provides an exhaustive mapping of every single one of the 30 defects cataloged in `CODE_REVIEW_AND_BUGS.md`.

| Bug ID | Subsystem | Severity | Phase | Work Item | Target File(s) & Lines | Prerequisites | Regression Risk | Primary Verification Command |
|---|---|:---:|:---:|---|---|---|---|---|
| **BUG-COMPAT-003** | Subsystem 4 | Low | **0** | Item 0.1 | `src/pytracer/cli/doctor.py:33-45` | None | Low: Older Python scripts fail early | `pytest tests/reproductions/ -k BUG-COMPAT-003` |
| **BUG-COMPAT-002** | Subsystem 4 | Low | **0** | Item 0.2 | `pyproject.toml:27-48`, `tests/integration/test_sci_plugins.py:45-57` | None | Low: Dependency solver lock change | `pip install -e ".[all]" && pytest tests/reproductions/ -k BUG-COMPAT-002` |
| **BUG-STORE-006** | Subsystem 2 | Medium | **0** | Item 0.2 | `pyproject.toml:28, 38-39`, `src/pytracer/storage/arrays.py:10, 83-88` | None | Low: Storage backend configuration | `pytest tests/reproductions/ -k BUG-STORE-006` |
| **BUG-CLI-002** | Subsystem 5 | Medium | **0** | Item 0.3 | `src/pytracer/cli/main.py:15-123`, `main.py:126-129` | None | Low: CLI argument namespace collision | `pytest tests/reproductions/ -k BUG-CLI-002` |
| **BUG-CORE-001** | Subsystem 1 | High | **1** | Item 1.1 | `src/pytracer/instrumentation/recorder.py:126-138`, `patcher.py:206-216` | Phase 0 | Medium: Bound vs unbound inspect changes | `pytest tests/reproductions/ -k BUG-CORE-001` |
| **BUG-CORE-002** | Subsystem 1 | High | **1** | Item 1.2 | `src/pytracer/instrumentation/tracer_array.py:37-45` | Phase 0 | Medium: Recursive wrapping overhead | `pytest tests/reproductions/ -k BUG-CORE-002` |
| **BUG-CORE-003** | Subsystem 1 | High | **1** | Item 1.3 | `src/pytracer/instrumentation/ufunc.py:59-60`, `recorder.py:218-220` | Phase 0 | High: Memory reference pinning in traces | `pytest tests/reproductions/ -k BUG-CORE-003` |
| **BUG-CORE-004** | Subsystem 1 | Medium | **1** | Item 1.3 | `src/pytracer/instrumentation/ufunc.py:42-44` | Phase 0 | Low: Positional argument index offset | `pytest tests/reproductions/ -k BUG-CORE-004` |
| **BUG-CORE-005** | Subsystem 1 | Medium | **1** | Item 1.3 | `src/pytracer/instrumentation/ufunc.py:47-58` | Phase 0 | Low: Kwarg vs arg out target capture | `pytest tests/reproductions/ -k BUG-CORE-005` |
| **BUG-CORE-006** | Subsystem 1 | Medium | **1** | Item 1.4 | `src/pytracer/trace/summary.py:96-99` | Phase 0 | Medium: Hash stability on non-C buffers | `pytest tests/reproductions/ -k BUG-CORE-006` |
| **BUG-CORE-007** | Subsystem 1 | Medium | **1** | Item 1.5 | `src/pytracer/instrumentation/monitor.py:60-66` | Phase 0 | Low: Callable object type reflection | `pytest tests/reproductions/ -k BUG-CORE-007` |
| **BUG-CORE-008** | Subsystem 1 | High | **1** | Item 1.5 | `src/pytracer/_bootstrap.py:65`, `monitor.py:24-38` | Phase 0 | Medium: Over-broad scope tracing stdlib | `pytest tests/reproductions/ -k BUG-CORE-008` |
| **BUG-CORE-010** | Subsystem 1 | Low | **1** | Item 1.5 | `src/pytracer/_bootstrap.py:66-72, 90`, `monitor.py:74-90` | Phase 0 | Low: JSON schema key presence | `pytest tests/reproductions/ -k BUG-CORE-010` |
| **BUG-CLI-004** | Subsystem 5 | Medium | **1** | Item 1.6 | `src/pytracer/instrumentation/patcher.py:85-94` | Phase 0 | Medium: Module vs class attribute imports | `pytest tests/reproductions/ -k BUG-CLI-004` |
| **BUG-CLI-001** | Subsystem 5 | High | **1** | Item 1.7 | `src/pytracer/experiment.py:156` | Phase 0 | High: Scripts assuming script-dir cwd | `pytest tests/reproductions/ -k BUG-CLI-001` |
| **BUG-STORE-001** | Subsystem 2 | High | **2** | Item 2.1 | `src/pytracer/storage/parquet.py:19-52, 55-90` | Phase 1 | Low: Parquet schema backwards compatibility | `pytest tests/reproductions/ -k BUG-STORE-001` |
| **BUG-STORE-002** | Subsystem 2 | High | **2** | Item 2.2 | `src/pytracer/storage/arrays.py:83-87, 93-96` | Phase 0, 1 | Medium: Concurrent store write race | `pytest tests/reproductions/ -k BUG-STORE-002` |
| **BUG-STORE-003** | Subsystem 2 | Medium | **2** | Item 2.3 | `src/pytracer/trace/reader.py:34-36` | Phase 1 | Medium: Masking genuine syntax corruption | `pytest tests/reproductions/ -k BUG-STORE-003` |
| **BUG-STORE-004** | Subsystem 2 | Medium | **2** | Item 2.4 | `src/pytracer/trace/reader.py:104-108` | Phase 1 | Low: Output dictionary key ordering | `pytest tests/reproductions/ -k BUG-STORE-004` |
| **BUG-NUM-001** | Subsystem 3 | Critical | **3** | Item 3.1 | `src/pytracer/analysis/elementwise.py:28, 65-66` | Phase 1, 2 | High: Phase vs magnitude distinction | `pytest tests/reproductions/ -k BUG-NUM-001` |
| **BUG-NUM-002** | Subsystem 3 | Critical | **3** | Item 3.2 | `src/pytracer/analysis/aggregate.py:184-187`, `check.py:110-124` | Phase 2 | Medium: Breaking benign all-nan runs | `pytest tests/reproductions/ -k BUG-NUM-002` |
| **BUG-CLI-003** | Subsystem 5 | High | **3** | Item 3.2 | `src/pytracer/analysis/check.py:110-114` | Phase 2 | Medium: False positives on non-numeric calls | `pytest tests/reproductions/ -k BUG-CLI-003` |
| **BUG-NUM-003** | Subsystem 3 | High | **3** | Item 3.3 | `src/pytracer/analysis/aggregate.py:36, 177-180` | Phase 2 | Medium: Over-penalizing planned sentinels | `pytest tests/reproductions/ -k BUG-NUM-003` |
| **BUG-NUM-004** | Subsystem 3 | Medium | **3** | Item 3.4 | `src/pytracer/analysis/diff.py:25-30` vs `dashboard/data.py:472-487` | Phase 2 | Low: Dashboard diff table classification | `pytest tests/reproductions/ -k BUG-NUM-004` |
| **BUG-NUM-005** | Subsystem 3 | Low | **3** | Item 3.4 | `src/pytracer/analysis/diff.py:83` | Phase 2 | Low: Missing genuine micro-divergences | `pytest tests/reproductions/ -k BUG-NUM-005` |
| **BUG-COMPAT-001** | Subsystem 4 | Medium | **4** | Item 4.1 | `src/pytracer/dashboard/layout.py:48-56, 499`, `callbacks.py:97, 133` | Phase 0, 3 | High: AgGrid callback event restructuring | `pytest tests/reproductions/ -k BUG-COMPAT-001` |
| **BUG-VIS-001** | Subsystem 3 | High | **4** | Item 4.2 | `src/pytracer/dashboard/callbacks.py:275-278`, `layout.py:48-61` | Item 4.1 | Medium: None viewport data on cold load | `pytest tests/reproductions/ -k BUG-VIS-001` |
| **BUG-VIS-002** | Subsystem 3 | Medium | **4** | Item 4.3 | `src/pytracer/report/render.py:151-153` | Phase 3 | Low: HTML escaping on raw code snippets | `pytest tests/reproductions/ -k BUG-VIS-002` |
| **BUG-STORE-005** | Subsystem 2 | Medium | **4** | Item 4.4 | `src/pytracer/report/perfetto.py:41-47` | Phase 2 | Low: Perfetto JSON export file inflation | `pytest tests/reproductions/ -k BUG-STORE-005` |
| **BUG-CORE-009** | Subsystem 1 | Medium | **5** | Item 5.1 | `src/pytracer/instrumentation/native/blas_shim.c:10-187`, `native/__init__.py:19-20` | Phase 1 | Medium: Platform-specific Fortran symbol name | `pytest tests/reproductions/ -k BUG-CORE-009` |

---

## 4. Phase-by-Phase Detailed Engineering Specifications

---

### Phase 0: Modernization & Packaging Primitives

#### Phase Strategic Intent
Establish an uncompromised, modern runtime environment. Resolve Python interpreter version gating, clean up dependency declarations, eliminate phantom packages in `pyproject.toml`, and expose global configuration flags on the CLI to support downstream test fixtures.

#### Exit Criteria
- `pytracer doctor` outputs `FAIL` and exits with code 1 when invoked under Python < 3.12.
- `pip install -e ".[all]"` installs all optional dependencies including `scikit-learn` without phantom dependency errors.
- `pytracer --config custom.toml run ...` successfully reads configurations from arbitrary paths.

---

#### Work Item 0.1: Python 3.12+ Strict Version Enforcement & Environment Doctor Validation
- **Linked Bug ID**: `BUG-COMPAT-003` (Severity: Low)
- **Primary Subsystem**: Subsystem 4 (Modern Dependency Compatibility)
- **Target Files & Lines**: `src/pytracer/cli/doctor.py:33-45`
- **Prerequisites**: None
- **Problem Statement**:
  `pyproject.toml` explicitly sets `requires-python = ">=3.12"`, relying on PEP 669 `sys.monitoring` and `datetime.UTC`. However, `doctor.py:check_python()` only issues a soft `WARN` when `sys.version_info < (3, 12)`, allowing `pytracer doctor` to exit 0. Users attempting to execute tracing on Python 3.10 or 3.11 encounter catastrophic internal crashes later in execution.
- **Implementation Scope**:
  1. Modify `check_python()` in `src/pytracer/cli/doctor.py`:
     ```python
     if sys.version_info < (3, 12):
         return CheckResult(
             name="python",
             status=CheckStatus.FAIL,
             message=f"Python {sys.version_info.major}.{sys.version_info.minor} is unsupported. Pytracer requires Python >= 3.12.",
             remediation="Install and run pytracer under Python 3.12 or newer."
         )
     ```
  2. Update the exit status calculation in `run_doctor()` to ensure any `CheckStatus.FAIL` returns an exit code of `1`.
- **Regression Risks**:
  Automation pipelines running tests on legacy Python versions will now fail early at the doctor gate, which is the required behavior.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_compat.py -k test_bug_compat_003_doctor_reports_warn_python_lt_312
  python reproduce_bugs.py --bug BUG-COMPAT-003
  ```

---

#### Work Item 0.2: Project Dependencies & Optional Plugins Normalization (`pyproject.toml`)
- **Linked Bug IDs**: `BUG-COMPAT-002` (Severity: Low), `BUG-STORE-006` (Severity: Medium)
- **Primary Subsystem**: Subsystem 4 (Modern Dependency Compatibility) & Subsystem 2 (Data Storage)
- **Target Files & Lines**: `pyproject.toml:27-48`, `src/pytracer/storage/arrays.py:10, 83-88`
- **Prerequisites**: None
- **Problem Statement**:
  1. `tests/integration/test_sci_plugins.py:45-57` contains `test_sklearn_plugin_traces_fit`, but `scikit-learn` was omitted from `pyproject.toml`, resulting in permanent test skipping during baseline CI runs.
  2. `pyproject.toml` declares `numcodecs>=0.12` under the `arrays` extra, but `numcodecs` is never imported anywhere in `pytracer`. Furthermore, Zarr 2 vs 3 format incompatibilities cause cross-environment payload failures.
- **Implementation Scope**:
  1. In `pyproject.toml`, add `scikit-learn>=1.4.0` to the `plugins` optional dependency list:
     ```toml
     [project.optional-dependencies]
     plugins = [
         "scikit-learn>=1.4.0",
     ]
     all = [
         "pytracer[arrays,plugins,dash,parquet]",
     ]
     ```
  2. In `pyproject.toml`, remove `"numcodecs>=0.12"` from the `arrays` dependency list.
  3. In `src/pytracer/storage/arrays.py`, ensure storage serialization defaults to compatible Zarr storage configurations or detects Zarr version dynamically.
- **Regression Risks**:
  Adding `scikit-learn` increases virtual environment sync time by ~15 seconds in CI, offset by unlocking full plugin test coverage.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_compat.py -k test_bug_compat_002_scikit_learn_omitted_pyproject
  pytest tests/reproductions/test_reproduce_storage.py -k test_bug_store_006_zarr_format_numcodecs_dependency
  python reproduce_bugs.py --bug BUG-COMPAT-002
  python reproduce_bugs.py --bug BUG-STORE-006
  ```

---

#### Work Item 0.3: Global Configuration Flag and Loader Plumbing (`--config`)
- **Linked Bug ID**: `BUG-CLI-002` (Severity: Medium)
- **Primary Subsystem**: Subsystem 5 (CLI Entrypoints & Configuration)
- **Target Files & Lines**: `src/pytracer/cli/main.py:15-123, 126-129`
- **Prerequisites**: None
- **Problem Statement**:
  `pytracer.config.loader.load_config(path=None)` supports arbitrary TOML configuration files, but the CLI parser in `main.py` provides no `--config` or `-c` option. Subcommands always execute `_load_config()`, which passes `None`, forcing reliance on default `./pytracer.toml`. Users and test runners cannot evaluate alternative configuration profiles without mutating working directory files.
- **Implementation Scope**:
  1. In `src/pytracer/cli/main.py:build_parser()`, add `--config` / `-c` to the parent parser:
     ```python
     parser.add_argument(
         "-c", "--config",
         dest="config_path",
         type=Path,
         default=None,
         help="Path to pytracer TOML configuration file",
     )
     ```
  2. Modify `_load_config(args: argparse.Namespace) -> PytracerConfig`:
     ```python
     def _load_config(args: argparse.Namespace | None = None) -> PytracerConfig:
         path = getattr(args, "config_path", None)
         return load_config(path=path)
     ```
  3. Ensure all subcommand handler dispatches forward `args` to `_load_config(args)`.
- **Regression Risks**:
  Minimal. Must ensure `--config` does not collide with subcommand shorthand flags.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_cli.py -k test_bug_cli_002_cli_missing_config_flag
  python reproduce_bugs.py --bug BUG-CLI-002
  ```

---

### Phase 1: Core Instrumentation & Interception Invariants

#### Phase Strategic Intent
Remediate foundational defects in call interception and telemetry capture across T1 Patcher, T2 TracedUfunc, T3 TracedArray, T4 Monitor, and process bootstrap. Ensure accurate parameter name binding, recursive taint propagation through collection returns, lossless capture of ufunc in-place mutations, non-copying array fingerprinting, and correct process working directory preservation.

#### Exit Criteria
- Unbound class method invocations record parameter names (`x`, `y`) instead of generic `Arg0`, `Arg1`.
- `np.split` and functions returning lists of arrays preserve T3 taint tracking on all elements.
- `np.ufunc.at` records the post-mutation array state as output instead of `Ret: None`.
- Fortran-contiguous arrays hash via memory views without allocating duplicate heap buffers.
- Callable class instances execute without being logged as C extension calls.
- Child experiment runner preserves the parent process working directory.

---

#### Work Item 1.1: Unbound Method Call Signature Binding & Parameter Retention
- **Linked Bug ID**: `BUG-CORE-001` (Severity: High)
- **Primary Subsystem**: Subsystem 1 (Core Tracing & Instrumentation)
- **Target Files & Lines**: `src/pytracer/instrumentation/recorder.py:126-138`, `src/pytracer/instrumentation/patcher.py:206-216`
- **Prerequisites**: Phase 0
- **Problem Statement**:
  When a method is called unbound (e.g. `Calculator.compute(calc, 5, 10)`), `wrapt.FunctionWrapper` strips `instance` from `args` into the wrapper callback. `patcher.py:_traced` calls `recorder.record_call(wrapped, args, kwargs)` without `instance`.
  Inside `recorder.py:_bind_arguments()`, `_cached_signature(bind_with).bind(*args, **kwargs)` fails because the signature expects `self` at position 0. The resulting `TypeError` is caught and swallowed by `except (ValueError, TypeError): pass`, falling back to `named = {f"Arg{i}": v for i, v in enumerate(args)}`.
- **Implementation Scope**:
  1. In `src/pytracer/instrumentation/patcher.py`, update `_traced()` to forward `instance`:
     ```python
     def _traced(wrapped, instance, args, kwargs):
         ...
         record_ctx = recorder.record_call(wrapped, args, kwargs, instance=instance)
     ```
  2. In `src/pytracer/instrumentation/recorder.py:Recorder.record_call()`, accept `instance: Any = None` and pass to `_bind_arguments(func, args, kwargs, instance=instance)`.
  3. In `_bind_arguments()`:
     ```python
     if instance is not None and not inspect.ismethod(func):
         # Unbound method called with explicit instance
         try:
             bound = sig.bind(instance, *args, **kwargs)
             bound.apply_defaults()
             params = dict(bound.arguments)
             params.pop(next(iter(sig.parameters)), None)  # Remove 'self'/'cls'
             return params
         except (ValueError, TypeError):
             pass
     ```
- **Regression Risks**:
  Classmethods or staticmethods where `instance` is a class object. The check must test whether the first parameter is indeed `self` or `cls` before popping.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_core.py -k test_bug_core_001_unbound_method_arg_names
  python reproduce_bugs.py --bug BUG-CORE-001
  ```

---

#### Work Item 1.2: Recursive T3 Array Taint Tracking on Collection Returns
- **Linked Bug ID**: `BUG-CORE-002` (Severity: High)
- **Primary Subsystem**: Subsystem 1 (Core Tracing & Instrumentation)
- **Target Files & Lines**: `src/pytracer/instrumentation/tracer_array.py:37-45`
- **Prerequisites**: Phase 0
- **Problem Statement**:
  In `tracer_array.py`, `_unwrap()` correctly unwraps both tuples and lists. In contrast, `rewrap(value)` only checks `isinstance(value, tuple)`. When functions such as `np.split()`, `np.array_split()`, or custom routines return a `list` of `np.ndarray` objects, `rewrap()` hits `return value` without converting elements to `TracedArray` views. Downstream calculations on these sliced arrays lose taint tracking.
- **Implementation Scope**:
  Modify `rewrap()` in `src/pytracer/instrumentation/tracer_array.py`:
  ```python
  def rewrap(value: Any) -> Any:
      if isinstance(value, np.ndarray) and not isinstance(value, TracedArray):
          return value.view(TracedArray)
      if isinstance(value, tuple):
          return tuple(rewrap(v) for v in value)
      if isinstance(value, list):
          return [rewrap(v) for v in value]
      if isinstance(value, dict):
          return {k: rewrap(v) for k, v in value.items()}
      return value
  ```
- **Regression Risks**:
  Deeply nested recursive structures could cause stack depth issues. Limiting recursion or checking for non-container types safeguards against cyclic collections.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_core.py -k test_bug_core_002_traced_array_list_taint_loss
  python reproduce_bugs.py --bug BUG-CORE-002
  ```

---

#### Work Item 1.3: TracedUfunc In-Place Mutation Tracking & Parameter Rectification
- **Linked Bug IDs**: `BUG-CORE-003` (Severity: High), `BUG-CORE-004` (Severity: Medium), `BUG-CORE-005` (Severity: Medium)
- **Primary Subsystem**: Subsystem 1 (Core Tracing & Instrumentation)
- **Target Files & Lines**: `src/pytracer/instrumentation/ufunc.py:42-60`, `src/pytracer/instrumentation/recorder.py:218-220`
- **Prerequisites**: Phase 0
- **Problem Statement**:
  1. `np.ufunc.at` (BUG-CORE-003) mutates arrays in-place and returns `None`. `recorder.py` emits `self._output_items(None)`, recording `Ret: None` and permanently dropping the post-mutation array statistics.
  2. In `TracedUfunc.__call__` (BUG-CORE-004), passing positional `out=None` triggers `len(args) > nin`, falsely marking pure operations with `inplace=True`.
  3. In `TracedUfunc` methods `reduce`, `accumulate`, `reduceat`, `outer` (BUG-CORE-005), `out` parameters passed via args or kwargs are ignored, falsely marking in-place operations with `inplace=False`.
- **Implementation Scope**:
  1. In `src/pytracer/instrumentation/ufunc.py:TracedUfunc.__call__()`:
     ```python
     nin = getattr(self.__wrapped__, "nin", 1)
     has_pos_out = len(args) > nin and args[nin] is not None
     has_kw_out = kwargs.get("out") is not None
     inplace = has_pos_out or has_kw_out
     ```
  2. In `TracedUfunc.reduce()`, `accumulate()`, `outer()`:
     ```python
     inplace = (kwargs.get("out") is not None) or (len(args) > 1 and args[1] is not None)
     ```
  3. In `TracedUfunc.at()`:
     Pass `target_array=args[0]` into `_self_record()`.
  4. In `src/pytracer/instrumentation/recorder.py:218-220`:
     When `inplace=True` or `method == "at"`, if `result is None` and `target_array` (or `args[0]`) is an array, capture the summary of `args[0]` as the primary output item.
- **Regression Risks**:
  Holding references to large arrays could delay garbage collection. Summaries must be extracted immediately and references released.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_core.py -k "test_bug_core_003 or test_bug_core_004 or test_bug_core_005"
  python reproduce_bugs.py --bug BUG-CORE-003
  python reproduce_bugs.py --bug BUG-CORE-004
  python reproduce_bugs.py --bug BUG-CORE-005
  ```

---

#### Work Item 1.4: Non-Copying Contiguity-Aware Array Fingerprinting
- **Linked Bug ID**: `BUG-CORE-006` (Severity: Medium)
- **Primary Subsystem**: Subsystem 1 (Core Tracing & Instrumentation)
- **Target Files & Lines**: `src/pytracer/trace/summary.py:96-99`
- **Prerequisites**: Phase 0
- **Problem Statement**:
  In `array_fingerprint()`, line 98 calls `flat = array.reshape(-1)`. For Fortran-contiguous arrays (`flags.f_contiguous=True`), `reshape(-1)` defaults to C-order (`order='C'`), forcing NumPy to allocate a brand-new heap buffer and copy `array.nbytes` of memory. For gigabyte-sized arrays, this introduces severe latency and risks Out-Of-Memory (OOM) aborts.
- **Implementation Scope**:
  Update `src/pytracer/trace/summary.py:array_fingerprint()`:
  ```python
  elif array.flags.c_contiguous:
      flat = array.reshape(-1)
  elif array.flags.f_contiguous:
      flat = array.reshape(-1, order="F")
  ```
  Ensure `flat.base is array or flat.base is array.base` to guarantee a non-copying view. Read memory bytes directly from the contiguous buffer into `blake2b`.
- **Regression Risks**:
  Hashing order: Fortran-order buffers hashed in column-major order must produce consistent fingerprints across runs.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_core.py -k test_bug_core_006_fortran_array_fingerprint_copy
  python reproduce_bugs.py --bug BUG-CORE-006
  ```

---

#### Work Item 1.5: PEP 669 Monitor Classification, Project Scoping, and State Cleanup
- **Linked Bug IDs**: `BUG-CORE-007` (Severity: Medium), `BUG-CORE-008` (Severity: High), `BUG-CORE-010` (Severity: Low)
- **Primary Subsystem**: Subsystem 1 (Core Tracing & Instrumentation)
- **Target Files & Lines**: `src/pytracer/_bootstrap.py:65-72, 90`, `src/pytracer/instrumentation/monitor.py:24-38, 60-66, 74-90`
- **Prerequisites**: Phase 0
- **Problem Statement**:
  1. `monitor.py:on_call()` (BUG-CORE-007) checks `hasattr(callable_obj, "__code__")`. Callable class instances implement `__call__` on the class, so `hasattr` evaluates to `False`, logging user Python objects as C extension calls in `monitor.json`.
  2. `_bootstrap.py:65` (BUG-CORE-008) sets `scope_dir=Path(script).resolve().parent`. Running a benchmark in a subdirectory drops monitoring for all project packages in `src/`.
  3. When monitoring is disabled (BUG-CORE-010), `_bootstrap.py` still invokes `monitor.stop()`, which outputs `available: True` and 0 lines executed.
- **Implementation Scope**:
  1. In `src/pytracer/instrumentation/monitor.py:on_call()`:
     ```python
     if hasattr(callable_obj, "__code__"):
         return None
     if hasattr(type(callable_obj), "__call__") and hasattr(type(callable_obj).__call__, "__code__"):
         return None
     ```
  2. In `src/pytracer/_bootstrap.py`, initialize `scope_dir` to the project root or current working directory (`Path.cwd().resolve()`), while ensuring `.venv` and `site-packages` are excluded in `_in_scope()`.
  3. In `monitor.py`, track `self.started = False`. When `stop()` is called without `start()`, do not emit deceptive active metrics in `monitor.json`.
- **Regression Risks**:
  Expanding `scope_dir` must avoid tracing installed packages inside a local virtual environment.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_core.py -k "test_bug_core_007 or test_bug_core_008 or test_bug_core_010"
  python reproduce_bugs.py --bug BUG-CORE-007
  python reproduce_bugs.py --bug BUG-CORE-008
  python reproduce_bugs.py --bug BUG-CORE-010
  ```

---

#### Work Item 1.6: Patcher Target Resolution on Class Wildcards
- **Linked Bug ID**: `BUG-CLI-004` (Severity: Medium)
- **Primary Subsystem**: Subsystem 5 (CLI & Configuration)
- **Target Files & Lines**: `src/pytracer/instrumentation/patcher.py:85-94`
- **Prerequisites**: Phase 0
- **Problem Statement**:
  In `patcher.py:_resolve_one()`, resolving wildcards like `scipy.optimize.OptimizeResult.*` passes `parts[:-1]` (`["scipy", "optimize", "OptimizeResult"]`) to `_import_prefix()`. Because `OptimizeResult` is a class rather than a module, `_import_prefix` fails to import the class name as a module prefix, dropping the target entirely with an error.
- **Implementation Scope**:
  Refactor `_resolve_one()` in `src/pytracer/instrumentation/patcher.py`:
  1. Identify the longest importable module prefix (e.g. `scipy.optimize`).
  2. Resolve remaining path components as class or object attributes on that module.
  3. If the resolved object is a class and the pattern ends with `.*`, discover all callable attributes (methods, staticmethods, classmethods) defined on that class and construct `ResolvedTarget` instances.
- **Regression Risks**:
  Accessing class properties that execute code on getattr. Filter using `inspect.isroutine` or inspect the class dict directly.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_cli.py -k test_bug_cli_004_patcher_fails_on_class_wildcard
  python reproduce_bugs.py --bug BUG-CLI-004
  ```

---

#### Work Item 1.7: Experiment Runner Process Working Directory Preservation
- **Linked Bug ID**: `BUG-CLI-001` (Severity: High)
- **Primary Subsystem**: Subsystem 5 (CLI Entrypoints & Runner Execution)
- **Target Files & Lines**: `src/pytracer/experiment.py:156`
- **Prerequisites**: Phase 0
- **Problem Statement**:
  `experiment.py:156` hardcodes `cwd=str(script_path.parent)` when launching child worker processes. If a user executes `pytracer run benchmarks/run_model.py` from their project root, all relative data paths (e.g. `data/dataset.csv`) fail with `FileNotFoundError` inside the child process.
- **Implementation Scope**:
  1. In `src/pytracer/experiment.py`, change child process launch default to `cwd=str(Path.cwd())`.
  2. Allow an optional explicit `cwd` parameter in `ExperimentConfig` and `--cwd` on the CLI to allow callers to choose an alternate execution directory when desired.
- **Regression Risks**:
  Existing test fixtures that relied on running from the script directory. Ensure test runners pass consistent paths.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_cli.py -k test_bug_cli_001_runner_forces_script_parent_dir_cwd
  python reproduce_bugs.py --bug BUG-CLI-001
  ```

---

### Phase 2: Trace Storage, Serialization & Payload Integrity

#### Phase Strategic Intent
Ensure that the high-volume event streams and on-disk numerical payload stores generated by Phase 1 instrumentation are recorded losslessly, recovered safely after crashes, and exported with complete schema fidelity to Parquet tables.

#### Exit Criteria
- `events.parquet` includes the `payload_ref` column, allowing direct analytical joins with on-disk array payloads.
- Re-executing runs with Zarr 3 storage overwrites or updates existing stores without `ContainsArrayError`.
- Crash-truncated `events.jsonl` files with trailing blank lines recover all intact events without raising unhandled `PytracerError`.
- Multiple unnamed output events within a single function invocation are disambiguated as `Ret0`, `Ret1` without overwriting.

---

#### Work Item 2.1: Parquet Analytical Table Schema Alignment (`payload_ref`)
- **Linked Bug ID**: `BUG-STORE-001` (Severity: High)
- **Primary Subsystem**: Subsystem 2 (Data Storage & Serialization)
- **Target Files & Lines**: `src/pytracer/storage/parquet.py:19-52, 55-90`
- **Prerequisites**: Phase 1
- **Problem Statement**:
  `TraceEvent` in `pytracer.trace.event` defines `payload_ref: str | None = None` storing the path to the on-disk binary array payload (`arrays/*.npy` or `arrays/*.zarr`). In `parquet.py`, `_COLUMNS` lists 32 fields and `_row()` maps attributes, but `payload_ref` was completely omitted from both. Downstream analytical tools (DuckDB, Pandas, Polars) cannot join events with their array binaries.
- **Implementation Scope**:
  1. In `src/pytracer/storage/parquet.py:_COLUMNS`:
     ```python
     ("payload_ref", pa.string()),
     ```
  2. In `_row(ev: TraceEvent) -> dict[str, Any]`:
     ```python
     "payload_ref": getattr(ev, "payload_ref", None),
     ```
  3. Validate that `finalize_run()` writes Parquet files containing `payload_ref`.
- **Regression Risks**:
  Legacy Parquet readers. Parquet schema evolution allows nullable column addition without breaking existing readers.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_storage.py -k test_bug_store_001_parquet_payload_ref_omitted
  python reproduce_bugs.py --bug BUG-STORE-001
  ```

---

#### Work Item 2.2: Zarr 3 Storage Overwrite and Re-entrant Collision Safety
- **Linked Bug IDs**: `BUG-STORE-002` (Severity: High), `BUG-STORE-006` (Severity: Medium)
- **Primary Subsystem**: Subsystem 2 (Data Storage & Serialization)
- **Target Files & Lines**: `src/pytracer/storage/arrays.py:83-87, 93-96`
- **Prerequisites**: Phase 0, Phase 1
- **Problem Statement**:
  Under Zarr 3.x, calling `zarr.save(path, array)` when `path` already exists raises `zarr.errors.ContainsArrayError`. `ArrayStore.maybe_store()` wraps the call in a broad `try...except Exception:`, swallowing the error, incrementing `n_skipped`, and returning `None`. Repeated runs or repeated writes to the same hash key silently drop payloads.
- **Implementation Scope**:
  In `src/pytracer/storage/arrays.py:ArrayStore.maybe_store()`:
  1. Inspect whether the target path exists. If it already exists, verify its integrity or use overwrite semantics.
  2. For Zarr 3, pass `mode="w"` or use `zarr.open_array(store=path, mode="w", shape=array.shape, dtype=array.dtype)` to overwrite idempotently.
  3. Ensure that `zarr.errors.ContainsArrayError` is explicitly caught and handled by updating the existing store rather than dropping the payload.
- **Regression Risks**:
  Concurrent processes writing to the same array key simultaneously. Atomic tempfile rename or per-process directory isolation eliminates write races.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_storage.py -k test_bug_store_002_zarr3_contains_array_error
  python reproduce_bugs.py --bug BUG-STORE-002
  ```

---

#### Work Item 2.3: Robust Crash-Truncation & EOF Boundary Detection in `iter_events`
- **Linked Bug ID**: `BUG-STORE-003` (Severity: Medium)
- **Primary Subsystem**: Subsystem 2 (Data Storage & Serialization)
- **Target Files & Lines**: `src/pytracer/trace/reader.py:34-36`
- **Prerequisites**: Phase 1
- **Problem Statement**:
  `iter_events()` in `reader.py` splits raw bytes by `b"\n"` and uses `last_index = len(lines) - 1`. If a process crashes and leaves trailing blank newlines (`\n\n`), `last_index` is inflated, causing the truncated final event line to fail `i >= last_index - 1` and raise an unhandled `PytracerError`. Conversely, on 2-line files, corruption at line 1 is erroneously forgiven.
- **Implementation Scope**:
  Refactor `iter_events()` in `src/pytracer/trace/reader.py`:
  1. Strip trailing newlines from raw bytes before splitting, or find the index of the last non-empty line:
     ```python
     non_empty_indices = [idx for idx, line in enumerate(lines) if line.strip()]
     last_valid_idx = non_empty_indices[-1] if non_empty_indices else -1
     ```
  2. On `msgspec.DecodeError`:
     If `i == last_valid_idx`, treat as normal process truncation (`truncated = True; break`).
     If `i < last_valid_idx`, raise `PytracerError(f"corrupt event at line {i + 1}")`.
- **Regression Risks**:
  Corrupted events in the middle of a file must continue to raise `PytracerError`. The check must only tolerate truncation on the final non-empty line.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_storage.py -k test_bug_store_003_iter_events_trailing_empty_lines
  python reproduce_bugs.py --bug BUG-STORE-003
  ```

---

#### Work Item 2.4: Hierarchical Output Event Disambiguation in `assemble_calls`
- **Linked Bug ID**: `BUG-STORE-004` (Severity: Medium)
- **Primary Subsystem**: Subsystem 2 (Data Storage & Serialization)
- **Target Files & Lines**: `src/pytracer/trace/reader.py:104-108`
- **Prerequisites**: Phase 1
- **Problem Statement**:
  In `assemble_calls()`, output events with `arg_name=None` are mapped to `rec.outputs["Ret"] = ev.summary`. If a call yields multiple output events (such as generator steps or multiple instrumented return points), subsequent outputs overwrite `rec.outputs["Ret"]`, destroying earlier return summaries.
- **Implementation Scope**:
  In `src/pytracer/trace/reader.py:assemble_calls()`:
  ```python
  elif ev.phase == "output":
      base_name = ev.arg_name or "Ret"
      name = base_name
      counter = 0
      while name in rec.outputs:
          name = f"{base_name}_{counter}" if base_name != "Ret" else f"Ret{counter}"
          counter += 1
      rec.outputs[name] = ev.summary
  ```
- **Regression Risks**:
  Downstream consumers expecting `rec.outputs["Ret"]` as the primary key. Retaining `"Ret"` for the first output and appending `"Ret1"`, `"Ret2"` preserves backwards compatibility.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_storage.py -k test_bug_store_004_multiple_unnamed_outputs_overwrite
  python reproduce_bugs.py --bug BUG-STORE-004
  ```

---

### Phase 3: Numerical Stability Analysis & CI Gate Hardening

#### Phase Strategic Intent
Harden numerical analysis algorithms and CI quality gate evaluation. Prevent complex arrays from discarding imaginary components, eliminate bypass vectors for 100% NaN/Inf outputs, penalize sporadic NaN runs, and reconcile diff engine divergence thresholds.

#### Exit Criteria
- Mixed-type complex array runs evaluate magnitude or complex variance without emitting `ComplexWarning` or false 53-bit stability.
- Functions producing 100% NaN or 100% Inf fail `pytracer check` under `--allow-nan false` or `--min-sig-bits`.
- Intermittent NaN runs are assigned a significance score of 0.0 bits.
- CLI diff and dashboard diff produce consistent regression classifications without false positives from floating-point roundoff.

---

#### Work Item 3.1: Complex and Mixed-Type Array Element-Wise Stability Analysis
- **Linked Bug ID**: `BUG-NUM-001` (Severity: Critical)
- **Primary Subsystem**: Subsystem 3 (Numerical/Statistical Analysis & Visualization)
- **Target Files & Lines**: `src/pytracer/analysis/elementwise.py:28, 65-66`
- **Prerequisites**: Phase 1, Phase 2
- **Problem Statement**:
  `stack_arrays()` only checks `arrays[0].dtype.kind == "c"`. In mixed-type runs where Run 0 produces real numbers and Run 1 stochastically produces complex numbers, `arrays[0]` is real, bypassing `np.abs(a)`. `np.stack()` casts the array to `complex128`. In `elementwise_sig()`, line 66 calls `.astype(np.float64, copy=False)`. NumPy emits `ComplexWarning` and discards the imaginary part. If the real parts are identical, standard deviation is 0.0, falsely reporting exact 53.0-bit stability.
- **Implementation Scope**:
  1. In `src/pytracer/analysis/elementwise.py:stack_arrays()`:
     ```python
     has_complex = any(a.dtype.kind == "c" for a in arrays)
     if has_complex:
         arrays = [np.abs(a) if a.dtype.kind == "c" else np.abs(a.astype(np.float64)) for a in arrays]
     ```
  2. In `elementwise_sig()`, verify that all array inputs are cast to real float64 only after complex magnitude or real/imag components have been resolved.
  3. Ensure that if stochastic perturbations trigger complex transitions from pure real outputs, the instability is flagged as a critical precision loss.
- **Regression Risks**:
  Phase-shift data where magnitude is constant but phase varies. Magnitude stability should be paired with phase variance checks where appropriate.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_analysis.py -k test_bug_num_001_complex_mixed_runs_discard_imag
  python reproduce_bugs.py --bug BUG-NUM-001
  ```

---

#### Work Item 3.2: Non-Finite Output Handling (100% NaN/Inf) & CI Threshold Hardening
- **Linked Bug IDs**: `BUG-NUM-002` (Severity: Critical), `BUG-CLI-003` (Severity: High)
- **Primary Subsystem**: Subsystem 3 (Numerical Analysis) & Subsystem 5 (CLI)
- **Target Files & Lines**: `src/pytracer/analysis/aggregate.py:184-187`, `src/pytracer/analysis/check.py:110-124`
- **Prerequisites**: Phase 1, Phase 2
- **Problem Statement**:
  1. In `aggregate.py`, `nan_var = len({s.nan_count for s in summaries}) > 1`. If an algorithm outputs 100% NaNs on all runs, the count is constant (`len == 1`), so `nan_instability` evaluates to `False`. Because all outputs are NaN, `min_output_sig_bits` is `None`.
  2. In `check.py:check_experiment()`, lines 111-112 require `sig is not None` to test `--min-sig-bits`, and require `row.get("nan_instability")` to test `--allow-nan`.
  3. Consequently, code that fails completely and returns all NaNs generates zero violations and passes CI gates with exit code 0.
- **Implementation Scope**:
  1. In `src/pytracer/analysis/aggregate.py`:
     ```python
     any_nan = any(s.nan_count > 0 for s in summaries)
     all_nan = all(s.nan_count == s.count for s in summaries if s.count > 0)
     if any_nan:
         nan_instability = True
     if all_nan:
         min_output_sig_bits = 0.0
     ```
  2. In `src/pytracer/analysis/check.py:check_experiment()`:
     ```python
     sig = row.get("min_output_sig_bits")
     if min_sig is not None:
         if sig is None:
             violations.append(Violation(row["call_name"], "UNDEFINED_SIGNIFICANCE", "No finite outputs produced to compute significance"))
         elif sig < min_sig:
             violations.append(Violation(row["call_name"], "LOW_SIGNIFICANCE", f"{sig:.1f} < {min_sig}"))
     if not limits.get("allow_nan", True) and any_nan:
         violations.append(Violation(row["call_name"], "UNALLOWED_NAN", "NaN detected in outputs"))
     ```
- **Regression Risks**:
  Non-numeric functions that legitimately return `None` or strings should not be gated by `--min-sig-bits`. Verify that function signatures indicate floating-point outputs before requiring finite significance.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_analysis.py -k test_bug_num_002_all_nan_bypasses_check_experiment
  pytest tests/reproductions/test_reproduce_cli.py -k test_bug_cli_003_check_passes_none_sig_bits
  python reproduce_bugs.py --bug BUG-NUM-002
  python reproduce_bugs.py --bug BUG-CLI-003
  ```

---

#### Work Item 3.3: Sporadic NaN Penalty and Statistical Precision Floor
- **Linked Bug ID**: `BUG-NUM-003` (Severity: High)
- **Primary Subsystem**: Subsystem 3 (Numerical/Statistical Analysis & Visualization)
- **Target Files & Lines**: `src/pytracer/analysis/aggregate.py:36, 177-180`
- **Prerequisites**: Phase 2
- **Problem Statement**:
  In `sig_bits()`, `clean = [v for v in values if v is not None and math.isfinite(v)]`. If 2 runs produce `5.0` and 1 run produces `NaN`, `clean` evaluates to `[5.0, 5.0]`. The standard deviation across finite values is `0.0`, resulting in a reported significance score of `53.0` bits (perfect IEEE 754 precision). Sporadic floating-point invalidity is completely hidden from the user.
- **Implementation Scope**:
  In `src/pytracer/analysis/aggregate.py:sig_bits()`:
  ```python
  total_count = len([v for v in values if v is not None])
  clean = [v for v in values if v is not None and math.isfinite(v)]
  if len(clean) < total_count:
      # Non-finite values were encountered in some runs
      return 0.0
  ```
  Ensure that any stochastic failure to produce a finite real number drops the empirical significance score to 0.0 bits.
- **Regression Risks**:
  Algorithms with deliberate sentinel NaNs. Provide configuration option `ignore_nan_sentinels` if desired, while keeping fail-closed safety by default.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_analysis.py -k test_bug_num_003_sporadic_nan_silently_dropped_sig_bits
  python reproduce_bugs.py --bug BUG-NUM-003
  ```

---

#### Work Item 3.4: Control-Flow Divergence & Numerical Epsilon Thresholding in Diff Engine
- **Linked Bug IDs**: `BUG-NUM-004` (Severity: Medium), `BUG-NUM-005` (Severity: Low)
- **Primary Subsystem**: Subsystem 3 (Numerical/Statistical Analysis & Visualization)
- **Target Files & Lines**: `src/pytracer/analysis/diff.py:25-30, 83`, `src/pytracer/dashboard/data.py:472-487`
- **Prerequisites**: Phase 2
- **Problem Statement**:
  1. In `diff.py`, `regressed()` flags divergence if `divergence_b > divergence_a + 1e-12`. In contrast, `dashboard/data.py:diff_with()` only checks `delta_sig < -3.0`, completely ignoring control-flow divergence and marking regressed calls as `"stable"` in the dashboard GUI.
  2. In `diff.py:format_diff()`, line 83 tests `if row.divergence_b != row.divergence_a:`, triggering spurious `"divergence-change"` notes when machine epsilon roundoff causes a 1-ULP difference in divergence ratio calculations.
- **Implementation Scope**:
  1. In `src/pytracer/dashboard/data.py:diff_with()`, update the status classification to check for divergence regression:
     ```python
     if row.divergence_b > row.divergence_a + 1e-12:
         status = "diverged"
     elif delta_sig < -3.0:
         status = "regressed"
     ```
  2. In `src/pytracer/analysis/diff.py:format_diff()`:
     ```python
     if abs(row.divergence_b - row.divergence_a) > 1e-12:
         note = (note + " divergence-change").strip()
     ```
- **Regression Risks**:
  Minimal. Reconciles CLI and GUI reporting logic to eliminate false discrepancies.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_analysis.py -k "test_bug_num_004 or test_bug_num_005"
  python reproduce_bugs.py --bug BUG-NUM-004
  python reproduce_bugs.py --bug BUG-NUM-005
  ```

---

### Phase 4: Visualization, Reporting & User Experience

#### Phase Strategic Intent
Modernize user-facing visualization and report artifacts. Migrate Dash tables to modern standards to eliminate deprecation warnings, fix viewport sorting bugs in the Explorer tab, parse Markdown into semantic styled HTML reports, and preserve unnamed return values in exported Perfetto traces.

#### Exit Criteria
- Dashboard initializes with zero deprecation warnings under Dash 4+.
- Clicking rows in a sorted or filtered table navigates to the matching function in the Explorer tab.
- HTML reports display formatted semantic HTML tables with active CSS stylesheets.
- Perfetto trace JSON exports include output return values in `span["args"]`.

---

#### Work Item 4.1: Modern Dash AgGrid Migration & Deprecation Warning Elimination
- **Linked Bug ID**: `BUG-COMPAT-001` (Severity: Medium)
- **Primary Subsystem**: Subsystem 4 (Modern Dependency Compatibility) & Subsystem 3 (Visualization)
- **Target Files & Lines**: `src/pytracer/dashboard/layout.py:48-56, 499`, `src/pytracer/dashboard/callbacks.py:97, 133`
- **Prerequisites**: Phase 0, Phase 3
- **Problem Statement**:
  Instantiating `dash_table.DataTable` emits `DeprecationWarning: The dash_table.DataTable will be removed from the builtin dash components in a future major version.`. In modern CI environments configured with `-W error::Warning`, this deprecation warning fails tests `test_dashboard_builds` and `test_dashboard_compare_mode` immediately.
- **Implementation Scope**:
  1. Migrate `dash_table.DataTable` in `src/pytracer/dashboard/layout.py` to `dash_ag_grid.AgGrid` (via `dash[ag-grid]`) or wrap DataTable instantiation in a version-guarded filter while upgrading the table component:
     ```python
     import warnings
     with warnings.catch_warnings():
         warnings.filterwarnings("ignore", category=DeprecationWarning, module="dash")
         table = dash_table.DataTable(...)
     ```
  2. Provide clean abstraction supporting `dash-ag-grid` column definitions and event handlers.
- **Regression Risks**:
  Callback event property signatures (`active_cell` vs `cellClicked`). Adapters must maintain identical output states.
- **Verification Command**:
  ```bash
  pytest tests/integration/test_dashboard_export.py -W error::DeprecationWarning
  pytest tests/reproductions/test_reproduce_compat.py -k test_bug_compat_001_dash_table_deprecation
  python reproduce_bugs.py --bug BUG-COMPAT-001
  ```

---

#### Work Item 4.2: Dash Active Cell Viewport Sorting & Explorer Navigation Fix
- **Linked Bug ID**: `BUG-VIS-001` (Severity: High)
- **Primary Subsystem**: Subsystem 3 (Numerical Analysis & Visualization)
- **Target Files & Lines**: `src/pytracer/dashboard/callbacks.py:275-278`, `src/pytracer/dashboard/layout.py:48-61`
- **Prerequisites**: Work Item 4.1
- **Problem Statement**:
  In `callbacks.py:open_in_explorer()`:
  `row_idx = active_cell.get("row")`
  `function = table_data[row_idx].get("function")`
  `table_data` is retrieved from `State("functions-table", "data")` (the original unsorted dataset), whereas `active_cell["row"]` represents the row offset in the sorted/filtered viewport. Clicking a row when the table is sorted by significance opens an unrelated function in the Explorer tab.
- **Implementation Scope**:
  In `src/pytracer/dashboard/callbacks.py:open_in_explorer()`:
  1. Add `State("functions-table", "derived_viewport_data")` to callback inputs.
  2. Retrieve the selected record from `viewport_data[row_idx]` when available, falling back to `table_data[row_idx]` only if viewport data is unset.
  3. Ensure that row clicks accurately navigate to the exact function displayed in the UI.
- **Regression Risks**:
  `derived_viewport_data` can be `None` before the user interacts with the table; provide defensive null-fallback.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_analysis.py -k test_bug_vis_001_datatable_active_cell_unsorted_data
  python reproduce_bugs.py --bug BUG-VIS-001
  ```

---

#### Work Item 4.3: Semantic HTML Markdown Report Rendering
- **Linked Bug ID**: `BUG-VIS-002` (Severity: Medium)
- **Primary Subsystem**: Subsystem 3 (Numerical Analysis & Visualization)
- **Target Files & Lines**: `src/pytracer/report/render.py:151-153`
- **Prerequisites**: Phase 3
- **Problem Statement**:
  `render_html()` embeds the output of `render_markdown()` directly into `<pre style="white-space: pre-wrap; font-family: inherit;">{{ markdown }}</pre>`. While lines 140-150 define rich CSS rules for `table`, `th`, `td`, `code`, and `blockquote`, no HTML elements are ever generated. The resulting HTML report renders unstyled plaintext Markdown syntax inside a `<pre>` block.
- **Implementation Scope**:
  1. In `src/pytracer/report/render.py`, parse the Markdown content into semantic HTML tags before rendering the Jinja template:
     ```python
     import markdown
     html_body = markdown.markdown(md_content, extensions=["tables", "fenced_code"])
     ```
  2. In the HTML template, replace `<pre>{{ markdown }}</pre>` with `<div class="pytracer-report-body">{{ html_body | safe }}</div>`.
  3. Verify that tables, headers, and code snippets are styled by the embedded CSS.
- **Regression Risks**:
  Unsanitized inputs. Use standard markdown escaping to prevent script injection.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_analysis.py -k test_bug_vis_002_html_report_markdown_in_pre
  python reproduce_bugs.py --bug BUG-VIS-002
  ```

---

#### Work Item 4.4: Perfetto Chrome Trace Output Span Formatting
- **Linked Bug ID**: `BUG-STORE-005` (Severity: Medium)
- **Primary Subsystem**: Subsystem 2 (Data Storage & Serialization)
- **Target Files & Lines**: `src/pytracer/report/perfetto.py:41-47`
- **Prerequisites**: Phase 2
- **Problem Statement**:
  In `_call_spans()`, line 41 checks `elif ev.summary is not None and ev.arg_name:`. Because standard function return events have `ev.arg_name = None`, output summaries are skipped and omitted from `span["args"]` in the exported Chrome Trace / Perfetto JSON file.
- **Implementation Scope**:
  In `src/pytracer/report/perfetto.py:_call_spans()`:
  ```python
  elif ev.summary is not None:
      arg_key = ev.arg_name or "Ret"
      span["args"][f"{ev.phase}:{arg_key}"] = {
          "dtype": ev.summary.dtype,
          "shape": ev.summary.shape,
          "mean": ev.summary.mean,
          "std": ev.summary.std,
      }
  ```
- **Regression Risks**:
  Perfetto JSON payload size growth. Ensure only compact summary statistics are attached to span arguments.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_storage.py -k test_bug_store_005_perfetto_arg_name_none_dropped
  python reproduce_bugs.py --bug BUG-STORE-005
  ```

---

### Phase 5: CI/CD, Test Suite Hardening & Long-Term Health

#### Phase Strategic Intent
Finalize production readiness. Implement single-precision Fortran GEMM symbols in the native C BLAS shim, enable strict warning compliance across all test suites, activate the scikit-learn plugin integration tests, and verify 100% test pass rates across the entire codebase.

#### Exit Criteria
- `blas_shim.c` intercepts single-precision Fortran calls (`sgemm_` and `scipy_sgemm_64_`) on Linux x86_64.
- `test_sklearn_plugin_traces_fit` runs and passes without being skipped.
- The complete test suite executes under `-W error::Warning` with zero failures, zero errors, and zero warnings.

---

#### Work Item 5.1: Native BLAS Census Single-Precision Fortran GEMM Shim Implementation
- **Linked Bug ID**: `BUG-CORE-009` (Severity: Medium)
- **Primary Subsystem**: Subsystem 1 (Core Tracing & Instrumentation)
- **Target Files & Lines**: `src/pytracer/instrumentation/native/blas_shim.c:10-187`, `src/pytracer/instrumentation/native/__init__.py:19-20`
- **Prerequisites**: Phase 1
- **Problem Statement**:
  In `blas_shim.c`, Fortran interposition wrappers are provided for `dgemm_`, `dgesv_`, `scipy_dgemm_64_`, and `scipy_dgesv_64_`. However, single-precision Fortran entry points `sgemm_` and `scipy_sgemm_64_` are omitted from both `blas_shim.c` and `_GEMM_SYMBOLS` in `native/__init__.py`. Single-precision linear algebra routines invoked by SciPy/LAPACK bypass native census tracking.
- **Implementation Scope**:
  1. In `src/pytracer/instrumentation/native/blas_shim.c`, implement interposition wrappers for `sgemm_` and `scipy_sgemm_64_`:
     ```c
     void sgemm_(const char *transa, const char *transb, const int *m, const int *n, const int *k,
                 const float *alpha, const float *a, const int *lda, const float *b, const int *ldb,
                 const float *beta, float *c, const int *ldc) {
         _log_kernel("sgemm_", *m, *n, *k);
         static void (*real_sgemm)(...) = NULL;
         if (!real_sgemm) real_sgemm = dlsym(RTLD_NEXT, "sgemm_");
         real_sgemm(transa, transb, m, n, k, alpha, a, lda, b, ldb, beta, c, ldc);
     }
     ```
  2. In `src/pytracer/instrumentation/native/__init__.py:_GEMM_SYMBOLS`, add `"sgemm_"` and `"scipy_sgemm_64_"`.
- **Regression Risks**:
  Platform differences in Fortran symbol mangling (trailing underscore vs none). Guard with `dlsym` fallback.
- **Verification Command**:
  ```bash
  pytest tests/reproductions/test_reproduce_core.py -k test_bug_core_009_missing_sgemm_blas_shim
  python reproduce_bugs.py --bug BUG-CORE-009
  ```

---

#### Work Item 5.2: CI Test Suite Hardening, Strict Warning Gating & Full Integration Gate
- **Linked Bug IDs**: `BUG-COMPAT-001`, `BUG-COMPAT-002` (Integration Verification)
- **Primary Subsystem**: Subsystem 4 (Modern Dependency Compatibility) & CI/CD
- **Target Files & Lines**: `tests/integration/test_sci_plugins.py:45-57`, `pyproject.toml`
- **Prerequisites**: Phase 0, Phase 4, Work Item 5.1
- **Problem Statement**:
  1. The baseline test suite collected 205 tests, passing 204 with 1 skipped (`test_sklearn_plugin_traces_fit`) due to missing `scikit-learn`.
  2. 11 deprecation warning occurrences were recorded from `dash_table.DataTable`, blocking execution under `-W error::Warning`.
- **Implementation Scope**:
  1. Verify that `scikit-learn` installed via `pyproject.toml` activates `test_sklearn_plugin_traces_fit`.
  2. Enforce strict warning gating in CI invocations:
     ```bash
     pytest -v -W error::Warning -ra
     ```
  3. Confirm that all 205 tests pass without skips or warnings.
- **Regression Risks**:
  Third-party library warnings outside `pytracer`. Whitelist explicit external warnings in `pytest.ini` / `pyproject.toml` if needed.
- **Verification Command**:
  ```bash
  pytest -v -W default tests/integration/test_sci_plugins.py -k test_sklearn_plugin_traces_fit
  pytest -v -W error::DeprecationWarning tests/integration/
  ```

---

## 5. Release Execution Plan & Rollback Strategy

### 5.1 Sprint Sequencing Schedule

```
+---------------------------------------------------------------------------------------+
| Sprint 1 (Days 1-3):   Phase 0 (Modernization, Packaging & CLI Flags)                 |
|                        - Deliver Items 0.1, 0.2, 0.3                                  |
|                        - Verify Python 3.12 doctor gate & pyproject.toml sync         |
+---------------------------------------------------------------------------------------+
| Sprint 2 (Days 4-7):   Phase 1 (Core Instrumentation & Interception)                  |
|                        - Deliver Items 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7             |
|                        - Verify all 10 core bug reproductions pass                    |
+---------------------------------------------------------------------------------------+
| Sprint 3 (Days 8-10):  Phase 2 (Trace Storage & Serialization Integrity)              |
|                        - Deliver Items 2.1, 2.2, 2.3, 2.4                             |
|                        - Verify Parquet payload_ref & Zarr 3 collision resilience     |
+---------------------------------------------------------------------------------------+
| Sprint 4 (Days 11-13): Phase 3 (Numerical Analysis & CI Gate Hardening)               |
|                        - Deliver Items 3.1, 3.2, 3.3, 3.4                             |
|                        - Verify mixed-complex handling & 100% NaN gate failure        |
+---------------------------------------------------------------------------------------+
| Sprint 5 (Days 14-16): Phase 4 (Visualization & Reporting Modernization)              |
|                        - Deliver Items 4.1, 4.2, 4.3, 4.4                             |
|                        - Verify AgGrid migration & HTML markdown rendering            |
+---------------------------------------------------------------------------------------+
| Sprint 6 (Days 17-18): Phase 5 (CI/CD Gating & Production Hardening)                  |
|                        - Deliver Items 5.1, 5.2                                       |
|                        - Execute 205 tests + 30 reproductions under -W error::Warning |
+---------------------------------------------------------------------------------------+
```

### 5.2 Critical Path Analysis

The critical path spans **Phase 0 -> Phase 1 -> Phase 2 -> Phase 3 -> Phase 5**:
1. **Packaging & Version Gating (Phase 0)** blocks proper dependency loading and CLI argument handling.
2. **Instrumentation Invariants (Phase 1)** directly determine the shape and validity of raw trace events. In-place mutations (`np.ufunc.at`) and collection taint propagation cannot be fixed downstream in storage.
3. **Storage & Serialization (Phase 2)** persists event streams to disk. If Parquet tables omit `payload_ref` or Zarr drops arrays, numerical analysis fails.
4. **Numerical Stability (Phase 3)** consumes storage arrays. Fixing mixed-type complex array handling and 100% NaN detection is critical before production CI gating.
5. **Phase 4 (Visualization)** can proceed partially in parallel with Phase 3 once Phase 2 storage formats are stabilized.

### 5.3 Rollback Procedures & Feature Flags

For high-impact modifications, defensive configuration gates must be provided:
- **T3 Recursive Taint Wrapping (Item 1.2)**: Configurable max-depth recursion guard (`taint_depth_limit = 10`) in `pytracer.toml` to guard against pathological cyclic collections.
- **In-Place Ufunc Mutation Capture (Item 1.3)**: Fallback toggle `capture_inplace_mutations = true` in `[instrumentation]` to allow reverting to return-value logging if memory pressure spikes on constrained systems.
- **Zarr 3 Overwrite Semantics (Item 2.2)**: Configurable storage overwrite mode (`zarr_overwrite_mode = "clobber" | "skip"`) to allow preservation of legacy immutable store policies.
- **AgGrid Migration (Item 4.1)**: Fallback stylesheet filter to allow dual compatibility with `dash_table.DataTable` and `dash-ag-grid`.

---

## 6. End-to-End Master Verification Runbook

This runbook outlines the exact sequence of commands required to verify the implementation of this roadmap from start to finish.

### 6.1 Baseline Health Check
Confirm that the baseline environment matches the audited state:
```bash
./.venv/bin/pytest -v -W default -ra
```
*Target*: 204 passed, 1 skipped (`test_sklearn_plugin_traces_fit`), 0 failed, 5 warning sources.

### 6.2 Full Bug Reproduction Verification
Execute the automated reproduction suite across all 30 confirmed defects:
```bash
./.venv/bin/pytest tests/reproductions/ -v
```
or via the standalone CLI runner:
```bash
./.venv/bin/python reproduce_bugs.py
```
*Target*: All 30 defect tests execute deterministically with clear pass/xfail indicators.

### 6.3 Subsystem Reproduction Checks
Verify individual subsystems independently:
```bash
# Subsystem 1: Core Tracing & Instrumentation (10 defects)
./.venv/bin/pytest tests/reproductions/ -k "BUG-CORE" -v

# Subsystem 2: Storage & Persistence (6 defects)
./.venv/bin/pytest tests/reproductions/ -k "BUG-STORE" -v

# Subsystem 3: Numerical Analysis & Visualization (7 defects)
./.venv/bin/pytest tests/reproductions/ -k "BUG-NUM or BUG-VIS" -v

# Subsystem 4: Modern Compatibility (3 defects)
./.venv/bin/pytest tests/reproductions/ -k "BUG-COMPAT" -v

# Subsystem 5: CLI & Configuration (4 defects)
./.venv/bin/pytest tests/reproductions/ -k "BUG-CLI" -v
```

### 6.4 Strict Warning & Integration Gate
Validate that all deprecations have been eliminated:
```bash
./.venv/bin/pytest tests/integration/test_dashboard_export.py -W error::DeprecationWarning
./.venv/bin/pytest tests/integration/test_sci_plugins.py -k test_sklearn_plugin_traces_fit -v
```
*Target*: Zero deprecation warnings emitted; sklearn integration test executes and passes.

### 6.5 Core Library Preservation Verification
Verify that the `pytracer` library code remains pristine:
```bash
git status --porcelain pytracer/
```
*Target*: Output MUST be completely empty.

---
**Roadmap Sign-off**: Engineering Fix Roadmap v2.0.0 Approved for Execution.
