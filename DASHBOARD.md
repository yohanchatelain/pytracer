# Pytracer Dashboard

```
pip install 'pytracer[gui]'
pytracer dashboard EXPERIMENT_DIR [--host 127.0.0.1] [--port 8050]
```

The dashboard reads a **completed, analyzed experiment**. Aggregates come
from `analysis/*.json` and are never recomputed; per-call records are
re-assembled in memory at startup for interactive drill-down; array payloads
and event timelines load lazily, on demand.

It is the interactive successor of the pytracer 1 visualizer: every
capability of the old GUI has an equivalent here, rebuilt on pytracer 2's
aligned-runs data model (see the mapping table at the end).

## Functionality

### Header & KPI row (always visible)

- Traced script, experiment id, run count, alignment mode, instrumentation.
- KPI cards: runs, call groups, matched, divergent, **min output
  significance (bits)**, **max amplification (bits)**, NaN/Inf-unstable
  function counts. Cards are status-colored (green/orange/red) by severity
  thresholds (10 bits critical, 24 bits = float32 precision).

### Overview tab

- **Digit-loss amplification ranking** — bits of precision destroyed per
  call, per function (the "who is a *source* of instability" chart).
  Clicking a bar jumps to the Explorer with that function selected.
- **Worst-case output significance per function**, with float32 (24-bit)
  and exact (53-bit) landmarks; bars below the landmarks are
  status-colored.
- **Functions table** — sortable/filterable: sig basis (element vs summary
  proxy), min/median output sig, max amplification, divergence score,
  matched groups, NaN/Inf instability.
- **Arguments & outputs table** — per (function, argument, phase): min/p05/
  median element-wise sig, sig(mean) proxy, mean/std of per-run means.
- **Control-flow divergence** — which functions were missing in which runs.
- Truncated-run banner when a run crashed mid-capture.

### Explorer tab (the pytracer 1 core view)

- **Per-invocation timeline**: one point per aligned call group × argument
  × phase, x = invocation index in program order.
  - Metrics: significant bits (sig(mean) proxy), element-wise min
    significant bits (when arrays were stored), mean, std of per-run
    means, min/max across runs, NaN/Inf counts — the pytracer 1
    mean/std/sig modes, extended.
  - Inputs are ▲, outputs are ▼; one stable color per function;
    exceptions marked ✕ (red), divergent groups ★ (orange).
  - Phase filter (inputs/outputs), linear/log y-scale, float32 reference
    line on significance metrics.
  - WebGL rendering kicks in automatically above 5 000 points.
  - **Download CSV** of the current selection.
- **Click-to-drill-down** on any point:
  - **Per-run summaries table**: dtype, shape, mean, std, min, max, L2/L∞
    norms, NaN/Inf/zero/subnormal counts, value fingerprint — per run.
  - **Per-run mean chart** with within-run std whiskers (run-to-run drift
    at a glance).
  - **Element-wise view** (needs `--store-arrays`): heatmap of per-element
    significant bits across runs (fixed 0–53 scale, darker = fewer bits),
    or mean value, or cross-run spread (std); colormap choice
    (blue ramp / diverging / viridis) and linear/log2/log10 z-scale.
  - **Histogram** of the element-wise view with bin count and
    count/percent/density normalization.
  - **Source context**: the calling file with ±7 lines and the callsite
    highlighted (successor of the pytracer 1 Ace-editor modal).

### Call timeline tab

- Per-run Gantt of traced call spans from monotonic capture timestamps
  (`ts_ns`), colored by instrumentation tier, hover shows duration, call
  depth, and exception text. Capped at the 400 longest spans with a note;
  the full multi-run flame view remains
  `pytracer export --format perfetto` → https://ui.perfetto.dev.

### Coverage tab

- Traced calls per tier (t1 decorated, t2 ufunc interception, t3 tracer
  arrays, t4 monitor).
- Native BLAS kernel census (T5) when available.
- **Untraced numerical callables** observed by the monitor — coverage gaps,
  with a pointer to `pytracer suggest-targets`.
- Coverage caveat notes (what tiers *cannot* see).

### Runs tab

- Per-run metadata table: exit code, creation time, python/numpy versions,
  platform, error text.
- Captured environment (allowlist-only, as stored).
- Reproduce block: interpreter, platform, packages, command.

## How it integrates

```
capture (events.jsonl, arrays/, metadata.json)
        │ pytracer analyze         ── writes analysis/*.json
        ▼
report.model.build_report_data     ── aggregates (never recomputed here)
        │
dashboard.data.ExperimentData      ── + in-memory re-alignment for
        │                             call-level rows, lazy array loads,
        │                             lazy span parsing, source lookup
        ▼
dashboard.layout (tabs) ⇄ dashboard.callbacks ⇄ dashboard.figures/theme
```

- `dashboard/data.py` — the only module that touches disk. Builds one
  timeline row per (aligned group, argument, phase); caches element-wise
  stacks, source snippets, and per-run spans.
- `dashboard/figures.py` — pure figure builders; `dashboard/theme.py`
  holds the palette and shared Plotly template (categorical hue per
  function is stable across filters; sequential single-hue ramps for
  magnitude; reserved status colors for NaN/exception/divergence marks).
- `dashboard/layout.py` + `assets/pytracer.css` — page chrome.
- `dashboard/app.py` — `build_app()` / `run_dashboard()`, the only public
  entry points (used by `pytracer dashboard` and the tests).

Nothing else in pytracer imports the dashboard; the `[gui]` extra stays
optional and a missing `dash` raises a clean `PytracerError`.

## Pytracer 1 → 2 feature mapping

| pytracer 1 GUI | pytracer 2 dashboard |
|---|---|
| module/function selection table | Explorer function multi-select (+ Overview click-through) |
| timeline modes mean / std / sig | Explorer metrics (sig proxy, element sig, mean, std, min, max, NaN/Inf) |
| inputs ▲ / outputs ▼ markers, color per callsite | same marker grammar, color per function (stable slots) |
| x/y linear/log + tick format | y linear/log (x is an invocation index) |
| hover → ndarray heatmap (real/imag tabs) | click → element-wise heatmap (complex handled as magnitude) |
| heatmap colormap/z-scale/min-max controls | colormap + z-scale controls, fixed 0–53 sig scale |
| histogram of heatmap + bins + normalization | same |
| hover stats (shape, norms, cond, min/max) | per-run summaries table (norms, counts, fingerprint) + per-run mean chart |
| source line + Ace editor modal | inline source context with highlighted callsite |
| callgraph Gantt | per-run call-span timeline (+ Perfetto export) |
| dump timeline/heatmap JSON | timeline CSV download |
| object values as ★ | exceptions ✕ / divergent groups ★ |

Not carried over: separate real/imaginary tabs (complex arrays are stacked
as magnitudes by the element-wise pipeline) and figure-JSON dumps (Plotly's
modebar PNG export plus the CSV export cover it).

## Potential improvements

- **A/B mode**: load two experiments and overlay their timelines /
  diff their function tables (the `pytracer diff` data is already there).
- **Complex dtypes**: store real/imag parts separately so the element-wise
  view can offer real/imaginary tabs like pytracer 1 (today complex is
  reduced to magnitude at stack time).
- **Dark mode**: the CSS is variable-based; a `prefers-color-scheme`
  variant needs a second set of validated ramp steps.
- **Cross-run heatmap animation**: step the element-value heatmap through
  runs (pytracer 1 had a stub for this).
- **Virtualized tables** and server-side pagination for experiments with
  10⁵+ call groups; the timeline already switches to WebGL.
- **Condition-number estimates** in the drill-down (pytracer 1 computed
  `np.linalg.cond` on hover; here it would need the stored array —
  cheap to add behind a button).
- **Deep links**: encode tab + selection in the URL hash so views are
  shareable.
- **Live mode**: watch an experiment directory and refresh while runs are
  still executing.
