# Technical Review — pytracer

*Review of `yohanchatelain/pytracer` at commit `ed755c7` (master), July 2026.*

Pytracer instruments Python modules at import time to record the inputs and
outputs of targeted functions, aggregates traces from multiple stochastic-
arithmetic runs into per-call statistics (mean, std, significant digits via
`significantdigits`), and visualizes them in a Dash dashboard. The three-stage
pipeline (trace → parse → visualize) is a sound architecture for the problem,
and the import-hook approach (a `MetaPathFinder`/`Loader` pair that swaps in
wrapped modules) is the right general mechanism for tracing third-party code
without modifying it.

The main findings are: (1) a number of confirmed correctness bugs, several of
which silently corrupt or drop trace data; (2) an error-handling design in
which *any* call to `logger.error` terminates the traced process, even when
callers pass `raise_error=False`; (3) heavy import-time side effects and
global monkey-patching (`builtins.type`/`isinstance`) that make the package
hard to test, embed, or reason about; and (4) a packaging/dependency setup
that no longer installs on current Python/NumPy and has no `install_requires`
at all.

---

## 1. Confirmed correctness bugs

### 1.1 Logging: `raise_error=False` still kills the process
`pytracer/utils/log.py:198-212` (`LogPrint.error`/`critical`) and
`log.py:264-284` (`LogLogger`): after optionally raising, both methods fall
through to an **unconditional** `sys.exit(1)`/`sys.exit(2)`. Consequences:

- `logger.error(..., raise_error=False)` — used in e.g.
  `core/wrapper/filter.py:51-53` and `writer/_pickle.py:123` precisely to
  *continue* after a recoverable problem — still terminates the process.
- Any code path that reaches `logger.error` during tracing kills the traced
  application with no traceback of the real failure.

The `raise_error` flag should gate the `raise`, and `sys.exit` should not be
in a logging method at all (a library logger must never own process exit).

### 1.2 HDF5 exporter: list-valued stats exported twice
`core/inout/exporter/_hdf5.py:309-341` (`export`): the chain is

```python
if isinstance(stats, list): ...
if isinstance(stats, dict): ...   # should be elif
else: ...
```

A list hits the first branch (exported per element as `name_TIDi`) and then,
not being a dict, hits the `else` and is exported **again** whole. Double rows
per argument for tuple-returning functions bias every downstream statistic.

### 1.3 HDF5 exporter: missing f-string collapses sanitized names
`_hdf5.py:291`: `function = 'safename_{function}'` (no `f` prefix). Every
function whose name fails `check_attribute_name` is renamed to the *same*
literal string, so their tables collide in one HDF5 group and their
statistics are merged together.

### 1.4 Config: `_Config.__bool__` raises, `sys.exit` misused
- `core/config.py:209`: `len(_Config._data())` — `_data` is a `DictAt`, not
  callable; any truthiness test of the config raises `TypeError`.
- `core/config.py:163-164`: `sys.exit(f"...", f"...")` — `sys.exit` accepts
  one argument; the intended error path raises `TypeError: exit expected at
  most 1 argument` instead of the message.

### 1.5 Wrapper: dead comparisons and attribute typos
- `core/wrapper/wrapper.py:548`: `if name == ("__cached__", "__file__"):` —
  a string is compared to a tuple, always `False`; should be `in`. The
  `__cached__`/`__file__` skip never happens.
- `wrapper.py:374`: `if id(obj) != new_obj:` compares an integer id to an
  object — effectively always true; should be `id(new_obj)`.
- `wrapper.py:251,379,939`: `getattr(function, '__global__', ...)` — the real
  attribute is `__globals__`. Because of the typo, `cache.globals_to_update`
  is never populated and `Wrapper.update_globals` (wrapper.py:184-188) is a
  no-op. If the empty-dict fallback in `_get_dict` is intentional (wrapper
  functions only need `generic_wrapper` in scope), that deserves a comment;
  the other two occurrences look like genuine dead code caused by the typo.
- `wrapper.py:161`: `logger.error("Object {obj} already visited")` — missing
  `f` prefix.
- `wrapper.py:138-150` (`get_function_wrapper`): the two checks
  `type(wrapper) != types.FunctionType` and `type(wrapper) !=
  types.BuiltinFunctionType` are mutually exclusive — at least one always
  fires, so this function unconditionally logs an error (which, per §1.1,
  exits the process). It appears to be unused; it should be fixed or removed.

### 1.6 Cache: `has_global_mapping` always returns False
`pytracer/cache.py:41-50`: `add_global_mapping` has the line populating
`_reverse_global_mapping` commented out, so `has_global_mapping` can never
return `True`. The duplicate-module guard at `module/tracer.py:111` is
therefore dead, and double-wrapping a module would go undetected.

Related: `cache.add_type`/`get_type` (cache.py:61-71) key entries on
`(id(obj), obj.__sizeof__)`. `id()` values are recycled after garbage
collection and `__sizeof__` is just a bound-method object; this map can
silently return the wrong type for a recycled id. Since `builtins.type` is
redirected through this map during tracing (see §3.2), a stale entry would
make `type(x)` lie about an unrelated object.

### 1.7 Stats: broken enum caching and dead branches
`core/stats/stats.py`:
- Lines 21-46: `hasattr(self, "__scalar")` checks the literal name while
  `self.__scalar = ...` stores the name-mangled `_TypeValue__scalar`, so the
  cache test never passes. Worse, `is_vector`/`is_matrix` reference
  `self.VECTOR`/`self.MATRIX`, which don't exist in the enum —
  `AttributeError` if ever called.
- Line 87: error message missing `f` prefix.
- Line 128: `TypeValue.STRING` is never produced by `get_type`, so the STRING
  branch of `get_stats` is unreachable.
- `tohex` (lines 136-145): `hex(float)` always raises `TypeError` (floats use
  `float.hex()`), so the first branch can never succeed.

### 1.8 Parser: silent truncation and `eval` on trace data
- `module/parser.py:39` (`Group`): traces are combined with `zip(*readers)`,
  which stops at the shortest trace. If one run recorded fewer calls (e.g. a
  pickle failure truncated it, see §1.9), the surplus records of every other
  run are silently discarded. `itertools.zip_longest` + an explicit error
  would surface the divergence instead of quietly biasing results.
- `parser.py:305-311` (`str_to_call`, used from `callgraph/core.py:152`):
  `eval(bt)` reconstructs a backtrace tuple from a string. Besides being
  fragile, evaluating strings derived from trace files is an arbitrary-code-
  execution hole (trace files are already pickles, but this adds a second,
  avoidable one — use `ast.literal_eval`).
- `parser.py:157-183` (`get_traces`): globs *every* file in the traces
  directory regardless of extension, and the leftover `ls` variable is unused.

### 1.9 Writer: exceptions swallowed, data silently dropped
`core/inout/writer/_pickle.py`:
- `_dump` (lines 160-169) catches `Exception` and does nothing — a failed
  dump silently truncates the trace, which later trips §1.8's zip behavior.
- `safe_dump` (lines 65-75) is a context manager that `return`s before
  `yield` when `is_dumping` is set — using it in that state raises
  `RuntimeError: generator didn't yield`. It appears unused; remove or fix.
- `is_writable` (lines 145-158) pickles every argument to a throwaway
  `BytesIO` before the real dump — every traced value is serialized twice
  (once per `clean_args` argument plus once whole), a substantial constant-
  factor cost on the hot path; it also `print(e)`s raw exceptions to stdout.
- Two divergent `format_output` implementations exist: `binding.format_output`
  (deep-copies dict values, filters callables) and the module-level one in
  `_pickle.py:385-394` (no copy, no callable filter). `write` uses the
  binding version, `write_function` the local one — outputs are recorded
  under different rules depending on which wrapper path invoked the call.
- A module-level `lock = threading.Lock()` (line 27) is never acquired, and
  the `is_dumping` flag plus `utils/singleton.Counter` ("Atomic counter",
  `self._internal += 1`) are not thread-safe. The visualizer runs Flask
  threaded; the tracer may trace threaded code. Either make the writer
  thread-safe or document single-threaded scope.

### 1.10 Tracer: variable shadowing in lazy-module fixup
`module/tracer.py:294-306` (`initialize_lazy_modules`): the inner loop
`for name, module in sys.modules.items():` rebinds both `name` and `module`
of the enclosing loop, and re-scans *all* of `sys.modules` once per lazy
module (quadratic). The shadowing is a latent bug the next time anyone edits
this function; rename the inner variables and hoist the scan.

### 1.11 Filter: error recovery uses stale variables, leaked handles
`core/wrapper/filter.py:43-56` (`read_file`): on a malformed line the code
logs with `raise_error=False` (intending to continue — currently exits, §1.1)
and then falls through to `self._add(module, function)` using values from the
*previous* iteration — or `UnboundLocalError` if the first line is bad. Add a
`continue`. Also `load_file` opens `self.fi` and never closes it.

## 2. Compatibility: the code no longer runs on current toolchains

- `np.object` (`stats/stats.py:118,131`) was removed in NumPy 1.24 (2022).
- `collections.Hashable` (`utils/__init__.py`, `ishashable`) was removed in
  Python 3.10; must be `collections.abc.Hashable`.
- `dash_html_components`/`dash_core_components` standalone imports
  (`gui/index.py`) are the Dash 1.x layout; Dash ≥2 moved them into `dash`.
- `requirements.txt` pins Flask 1.1.2 / Jinja2 2.11.2 / Werkzeug 1.0.1 /
  MarkupSafe 1.1.1 — this constellation no longer installs cleanly and the
  pinned Pillow 8.1.0, ipython 7.20, etc. carry known CVEs.
- CI runs only Python 3.8 on ubuntu-20.04 with `actions/checkout@v2` /
  `setup-python@v2` — all EOL/deprecated; the workflow cannot be exercising
  the code on any currently supported interpreter.

In short, the project is pinned to a ~2021 environment. A user following the
README on a 2026 machine cannot install or run it without an archaeology
exercise (the Docker images are the only reproducible path).

## 3. Design and robustness concerns

### 3.1 Import-time side effects everywhere
- `core/config.py:249`: `config = _Config()` executes at import and calls
  `sys.exit` if `PYTRACER_CONFIG` is unset or invalid — importing *any*
  pytracer submodule (including in a test runner or REPL) can terminate the
  interpreter.
- `core/inout/writer/__init__.py` instantiates `WriterPickle()` at import:
  merely importing the package creates `.__pytracercache__/` directories,
  opens a trace file, and registers `atexit` handlers.
- `utils/log.py:get_logger()` opens log files at import time of nearly every
  module, and `LogLogger` calls `logging.basicConfig(level=DEBUG)` on the
  **root** logger — hijacking the traced application's logging
  configuration.

Recommendation: make configuration lazy and explicit (`load_config(path)`),
construct writers/loggers in `main()`, and use a namespaced
`logging.getLogger("pytracer")` instead of the root logger.

### 3.2 Global monkey-patching of builtins
`pytracer/builtins.py:overload_builtins` permanently replaces
`builtins.type` and `builtins.isinstance` for the traced process so wrapped
callables masquerade as their originals (in tandem with
`WrapperInstance.__class__` spoofing and the `cache._map_type` lookup). This
is the highest-risk part of the design: it changes semantics for *all* code
in the process (including stdlib and unrelated libraries), `_isinstance`
handles only some `_Type` cases, `builtins.issubclass` is saved but never
replaced (asymmetric), and nothing ever restores the originals. At minimum
document the blast radius; ideally, invest in making the wrappers
transparent enough (e.g. via `functools.wraps`-style identity plus
`__class__` property) that the builtins patch becomes unnecessary.

### 3.3 Identity-keyed global caches
The wrapping machinery keys everything on `id()`
(`cache.id_dict`, `visited_functions`, `_global_mapping`,
`WrapperClass.visited_class`). This works only while every original object
stays alive; nothing pins them except incidental references. If an original
is collected, a recycled id silently aliases two different functions. Use a
dict keyed on weak references (`weakref.WeakValueDictionary` /
`WeakKeyDictionary`) or keep explicit strong references alongside.

### 3.4 Error containment inverted
Because of §1.1, benign conditions (a class already wrapped, a filter-file
syntax error, an unpicklable argument that reaches an `error` path)
terminate the user's application, while genuinely serious conditions
(`_dump` failures, §1.9) are silently ignored. The policy should be exactly
the opposite: tracing problems must degrade to "this call not recorded, warn
once", and data-integrity problems in parse/export must be loud.

### 3.5 Miscellaneous
- `WrapperClass.isstatic` (wrapper.py:830-847) falls back to *source-text
  scanning* (`'@staticmethod' in src`) and "first parameter isn't named
  `self`" heuristics — both misfire (decorated code in comments/strings,
  methods named `cls`/`this`). `inspect.getattr_static` gives an exact
  answer.
- `PytracerLoader.exec_module` (tracer.py:141-156) writes modules into the
  *tracer's* `globals()` and `sys.modules` and never runs the real module's
  code through the loader protocol as documented; `create_module` doing the
  full wrap and `exec_module` being a stub inverts the intended contract.
- `debug` printing in `CallChain.to_tree` gated on `len(self._stack) < 4`
  with a hand-rolled `printd` — leftover debugging scaffolding in a hot loop.
- `WrapperInstance.__setstate__/__getstate__/__reduce_ex__` contain bare
  `print('setstate')` etc. (wrapper.py:101-111) — stray debug output.
- Dead/vestigial code: commented-out blocks in `parser.py` and
  `wrapper.py`, unused `Group.iotype`, unused `special_case()` that always
  returns `False`, `pycfg`, `pyre-check`, `fb-sapp` in requirements.

## 4. Security notes

Appropriate to flag even for a research tool:

- Traces are pickles read back with `dill` (`reader/_pickle.py`); loading a
  trace executes arbitrary code by construction. Fine for personal use, but
  the README should say "only parse traces you produced", and the parse
  stage ingests *every* file in the directory (§1.8), widening exposure.
- `eval()` on call-graph strings (§1.8) — replace with `ast.literal_eval`.
- The Dash server binds with a user-supplied `--host` and no auth; anyone
  who can reach the port can browse traces. Default to `127.0.0.1`
  (documented) and say so explicitly.

## 5. Packaging, docs, project hygiene

- `setup.py` declares **no `install_requires`** — `pip install pytracer`
  yields a package that cannot import. The 100-line fully-pinned
  `requirements.txt` mixes runtime deps with dev tooling (pytest, ipython,
  pyre-check, matplotlib…). Split into `install_requires` (loose lower
  bounds) + `dev` extras, and move to `pyproject.toml`.
- `significantdigits` is vendored as a git submodule *and* expected on the
  path via `included_packages` — it's on PyPI now; depend on it normally.
- The classifier claims MIT but there is **no LICENSE file** in the repo.
- README: several typos ("hfd5", "exlude_file", "wihtout"), the
  `module_to_load`/`modules_to_load` key naming is inconsistent between
  README and code, and the config schema is only prose — a JSON-schema or a
  validated dataclass would catch user mistakes (currently unknown keys are
  silently absorbed by `DictAt`/`NoneDict`, which also makes typos in the
  config file invisible).
- Version is `0.0.1` with no changelog/tags; no `python_requires` upper
  bound despite hard 3.8/3.9-era incompatibilities (§2).

## 6. Testing

- The internal tests (`test_basic.py`, `test_class.py`, `test_hook.py`) are
  end-to-end via `pytest-shell`; the sklearn/scipy suites are full example
  scripts. There are **no unit tests** for the components where the review
  found bugs (parser merging, stats typing, HDF5 export, filters, config).
  Most of §1 would have been caught by small direct tests.
- CI runs a single Python version (3.8) and only the "not slow" marker; the
  export path (`_hdf5.py`) is only exercised through `parse --online` in a
  fixture teardown, which is why the double-export bug (§1.2) survives.
- Suggestion: add pure-unit tests for `Binding`, `format_output` (unify the
  two first), `Parser.merge`, `get_stats`, `Filter`, and a tiny golden-file
  test that traces a 10-line script twice and asserts the exact set of
  HDF5 rows.

## 7. Prioritized recommendations

1. **Fix the logger exit semantics** (§1.1) — it changes the observable
   behavior of half the error handling in the codebase; nothing else can be
   reasoned about until `raise_error=False` actually means "don't die".
2. **Fix the data-integrity bugs**: HDF5 double export (§1.2), sanitized-name
   collision (§1.3), `zip` truncation (§1.8), silent `_dump` failures (§1.9).
   These corrupt the numerical results the tool exists to produce.
3. **Restore installability**: `install_requires`, drop dead pins, replace
   `np.object`/`collections.Hashable`, migrate to Dash 2, refresh CI to
   supported Python versions. Until then the Docker images are the only
   supported entry point and the README should say so.
4. **Remove import-time side effects** (§3.1) so the package can be imported,
   tested, and embedded safely.
5. Replace `eval` with `ast.literal_eval`; add a LICENSE file; add unit
   tests around parser/stats/export.
6. Longer term: reconsider the `builtins.type`/`isinstance` patch (§3.2) and
   the `id()`-keyed caches (§3.3) — they are the two structural sources of
   "impossible" bugs this design will keep producing.

---

*Files read in full during this review: `core/wrapper/wrapper.py`,
`core/wrapper/filter.py`, `core/inout/writer/_pickle.py` (+ `_writer`,
`binding`, `_init`), `core/inout/reader/_pickle.py`,
`core/inout/exporter/_hdf5.py`, `core/config.py`, `core/stats/stats.py`,
`module/tracer.py`, `module/parser.py`, `module/info.py`, `cache.py`,
`builtins.py`, `utils/log.py`, `utils/__init__.py`, `utils/singleton.py`,
`__main__.py`, `gui/index.py` (skim), test suite layout, CI workflows,
`setup.py`, `requirements.txt`.*
