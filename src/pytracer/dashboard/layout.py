"""Dash layout: header, KPI row, and the dashboard tabs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pytracer.dashboard import figures, theme

if TYPE_CHECKING:
    from pytracer.dashboard.data import ExperimentData

TABLE_STYLE = {
    "style_table": {"overflowX": "auto"},
    "style_header": {
        "backgroundColor": theme.PAGE,
        "color": theme.INK_SECONDARY,
        "fontWeight": "600",
        "fontSize": "0.72rem",
        "textTransform": "uppercase",
        "letterSpacing": "0.04em",
        "border": "none",
        "borderBottom": f"1px solid {theme.GRID}",
    },
    "style_cell": {
        "fontFamily": "ui-monospace, SFMono-Regular, Menlo, monospace",
        "fontSize": "0.8rem",
        "padding": "0.45rem 0.7rem",
        "backgroundColor": theme.SURFACE,
        "color": theme.INK,
        "border": "none",
        "borderBottom": f"1px solid {theme.GRID}",
        "textAlign": "left",
        "maxWidth": "26rem",
        "overflow": "hidden",
        "textOverflow": "ellipsis",
    },
    "css": [{"selector": ".dash-filter input",
             "rule": f"color: {theme.INK} !important;"}],
}


def _round(value, digits=2):
    if isinstance(value, float):
        return round(value, digits)
    return value


def data_table(dash_table, rows, columns, table_id, page_size=12, **overrides):
    kwargs = {
        "sort_action": "native",
        "filter_action": "native" if len(rows) > page_size else "none",
        "page_size": page_size,
        **TABLE_STYLE,
        **overrides,
    }
    return dash_table.DataTable(
        id=table_id,
        data=[{c: _round(r.get(c)) for c in columns} for r in rows],
        columns=[{"name": c.replace("_", " "), "id": c} for c in columns],
        **kwargs,
    )


def kpi(label, value, tone=None):
    from dash import html

    classname = "kpi" + (f" kpi--{tone}" if tone else "")
    return html.Div([
        html.Div(str(value), className="kpi-value"),
        html.Div(label, className="kpi-label"),
    ], className=classname)


def header_bar(data: ExperimentData, data_compare: ExperimentData | None = None):
    from dash import html

    experiment = data.report.get("experiment", {})
    alignment = data.report.get("alignment", {})
    script = experiment.get("script", "")

    meta_parts = [
        f"exp {experiment.get('experiment_id', '?')}",
        f"{alignment.get('runs', '?')} runs",
        f"mode: {alignment.get('alignment_mode', '?')}",
        f"tier: {experiment.get('instrumentation', '?')}",
    ]
    if data_compare:
        cmp_id = data_compare.report.get("experiment", {}).get("experiment_id", "B")
        meta_parts.append(f"vs {cmp_id}")

    return html.Div([
        html.Div([
            html.Img(src="/assets/logo.png", className="brand-logo", alt="Pytracer"),
            html.Div([
                html.Div([
                    html.Span("Pytracer", className="brand"),
                    html.Span("v2.0.0", className="brand-version"),
                ], className="brand-title-row"),
                html.Span("numerical variability profiler", className="brand-sub"),
            ], className="brand-text"),
        ], className="brand-box"),
        html.Div([
            html.Code(script, className="script-chip") if script else None,
            html.Span(" · ".join(meta_parts), className="header-meta"),
            html.Button("🌙 Dark", id="theme-toggle-btn", className="theme-toggle-btn"),
        ], className="header-right"),
    ], className="pt-header")


def kpi_row(data: ExperimentData):
    from dash import html

    alignment = data.report.get("alignment", {})
    functions = data.report.get("functions", [])
    sigs = [f["min_output_sig_bits"] for f in functions
            if f.get("min_output_sig_bits") is not None]
    amps = [f["max_amplification_bits"] for f in functions
            if f.get("max_amplification_bits") is not None]
    divergent = alignment.get("divergent_call_groups", 0)
    nan_fns = sum(1 for f in functions if f.get("nan_instability"))
    inf_fns = sum(1 for f in functions if f.get("inf_instability"))
    min_sig = min(sigs) if sigs else None
    max_amp = max(amps) if amps else None
    return html.Div([
        kpi("runs", alignment.get("runs", "?")),
        kpi("call groups", alignment.get("total_call_groups", 0)),
        kpi("matched", alignment.get("matched_call_groups", 0)),
        kpi("divergent", divergent, tone="serious" if divergent else "good"),
        kpi("min output sig (bits)",
            f"{min_sig:.1f}" if min_sig is not None else "–",
            tone=("critical" if min_sig is not None and min_sig < 10
                  else "serious" if min_sig is not None
                  and min_sig < theme.FLOAT32_BITS else None)),
        kpi("max amplification (bits)",
            f"{max_amp:.1f}" if max_amp is not None else "–",
            tone="serious" if max_amp is not None and max_amp > 10 else None),
        kpi("NaN-unstable functions", nan_fns,
            tone="critical" if nan_fns else "good"),
        kpi("Inf-unstable functions", inf_fns,
            tone="critical" if inf_fns else "good"),
    ], className="kpi-row")


# -------------------------------------------------------------------- tabs

def overview_tab(data: ExperimentData, dash_table):
    from dash import dcc, html

    report = data.report
    functions = report.get("functions", [])
    arguments = report.get("arguments", [])
    divergent = report.get("alignment", {}).get("divergent_calls", [])
    truncated = report.get("alignment", {}).get("truncated_runs", [])

    children = [
        html.Div([
            html.Div(dcc.Graph(
                id="amp-chart",
                figure=figures.amplification_figure(report.get("top_unstable", [])),
                config={"displayModeBar": False},
            ), className="card half"),
            html.Div(dcc.Graph(
                id="sig-overview-chart",
                figure=figures.sig_overview_figure(functions),
                config={"displayModeBar": False},
            ), className="card half"),
        ], className="row"),
        html.P("Click a bar or table row to open that function in the Explorer.",
               className="hint"),
    ]
    if truncated:
        children.insert(0, html.Div(
            f"⚠ truncated runs (crashed mid-capture): {', '.join(truncated)}",
            className="banner banner--serious"))

    if functions:
        columns = ["function", "sig_basis", "min_output_sig_bits",
                   "median_output_sig_bits", "max_amplification_bits",
                   "divergence_score", "n_call_groups", "n_matched",
                   "nan_instability", "inf_instability"]
        children += [
            html.H3("Functions"),
            html.Div(data_table(dash_table, functions, columns, "functions-table"),
                     className="card"),
        ]
    if arguments:
        columns = ["function", "arg_name", "phase", "sig_basis", "sig_min_bits",
                   "sig_p05_bits", "sig_median_bits", "sig_mean_bits",
                   "mean_of_means", "std_of_means", "n_call_groups"]
        children += [
            html.H3("Arguments & outputs"),
            html.Div(data_table(dash_table, arguments, columns, "arguments-table"),
                     className="card"),
        ]

    children.append(html.H3("Control-flow divergence"))
    if divergent:
        rows = [{"function": d["function"],
                 "divergence_score": round(d["divergence_score"], 3),
                 "missing_in_runs": ", ".join(d["missing_in_runs"])}
                for d in divergent]
        children.append(html.Div(
            data_table(dash_table, rows,
                       ["function", "divergence_score", "missing_in_runs"],
                       "divergence-table"),
            className="card"))
    else:
        children.append(html.P(
            "None — every run executed the same traced calls.",
            className="hint"))
    return html.Div(children, className="tab-body")


def explorer_tab(data: ExperimentData):
    from dash import dcc, html

    function_options = [{"label": f, "value": f} for f in data.functions]
    top = [r["function"] for r in data.report.get("top_unstable", [])]
    default = top[:3] if top else data.functions[:3]
    any_arrays = any(r["has_arrays"] for r in data.timeline_rows)

    controls = html.Div([
        html.Div([
            html.Label("Functions"),
            dcc.Dropdown(id="explorer-functions", options=function_options,
                         value=default, multi=True,
                         placeholder="Pick functions to plot…"),
        ], className="control control--wide"),
        html.Div([
            html.Label("Metric"),
            dcc.Dropdown(
                id="explorer-metric",
                options=[{"label": label, "value": key}
                         for key, label in figures.METRICS.items()
                         if key != "sig_element" or any_arrays],
                value="sig_proxy", clearable=False),
        ], className="control"),
        html.Div([
            html.Label("Phase"),
            dcc.Checklist(id="explorer-phase",
                          options=[{"label": " inputs", "value": "input"},
                                   {"label": " outputs", "value": "output"}],
                          value=["input", "output"], inline=True),
        ], className="control"),
        html.Div([
            html.Label("Y scale"),
            dcc.RadioItems(id="explorer-yscale",
                           options=[{"label": " linear", "value": "linear"},
                                    {"label": " log", "value": "log"}],
                           value="linear", inline=True),
        ], className="control"),
        html.Div([
            html.Label("Export"),
            html.Button("Download CSV", id="download-timeline-btn",
                        className="btn"),
            dcc.Download(id="download-timeline"),
        ], className="control"),
    ], className="controls-row")

    detail = html.Div([
        html.Div(id="detail-title", className="detail-title"),
        html.Div([
            html.Div([
                html.H4("Per-run summaries"),
                html.Div(id="detail-stats"),
                dcc.Graph(id="detail-runs-graph",
                          config={"displayModeBar": False}),
            ], className="card half"),
            html.Div([
                html.Div([
                    html.H4("Element-wise view"),
                    html.Div([
                        dcc.RadioItems(
                            id="heat-mode",
                            options=[
                                {"label": " significant bits", "value": "sig"},
                                {"label": " mean value", "value": "value"},
                                {"label": " spread (std/run)", "value": "spread"},
                            ],
                            value="sig", inline=True),
                        dcc.Dropdown(
                            id="heat-colorscale",
                            options=[
                                {"label": "blue ramp", "value": "auto"},
                                {"label": "diverging", "value": "diverging"},
                                {"label": "viridis", "value": "viridis"},
                            ],
                            value="auto", clearable=False,
                            className="mini-dropdown"),
                        dcc.RadioItems(
                            id="heat-zscale",
                            options=[{"label": " linear", "value": "linear"},
                                     {"label": " log2", "value": "log2"},
                                     {"label": " log10", "value": "log10"}],
                            value="linear", inline=True),
                    ], className="controls-row controls-row--tight"),
                ]),
                dcc.Graph(id="detail-heatmap", config={"displayModeBar": False}),
                html.Div(id="detail-heatmap-note", className="hint"),
                html.Div([
                    html.Label("Histogram bins"),
                    dcc.Input(id="hist-bins", type="number", min=0, max=1000,
                              value=0, debounce=True,
                              placeholder="auto"),
                    dcc.RadioItems(
                        id="hist-norm",
                        options=[{"label": " count", "value": ""},
                                 {"label": " percent", "value": "percent"},
                                 {"label": " density",
                                  "value": "probability density"}],
                        value="", inline=True),
                ], className="controls-row controls-row--tight"),
                dcc.Graph(id="detail-histogram",
                          config={"displayModeBar": False}),
            ], className="card half"),
        ], className="row"),
        html.Div([
            html.H4("Source context"),
            html.Div(id="detail-source"),
        ], className="card"),
    ], id="detail-panel", style={"display": "none"})

    note = None
    if not any_arrays:
        note = html.P(
            "No array payloads were stored for this experiment — element-wise "
            "views are unavailable. Re-run with --store-arrays auto|always to "
            "enable per-element heatmaps and histograms.",
            className="hint")

    return html.Div([
        controls,
        html.Div(dcc.Graph(id="explorer-graph"), className="card"),
        html.P("Click any point to drill into that call: per-run statistics, "
               "matrix condition number, element-wise significance, and source context.",
               className="hint"),
        note,
        dcc.Store(id="selected-point"),
        detail,
    ], className="tab-body")


def diff_tab(data_a: ExperimentData, data_b: ExperimentData, dash_table):
    from dash import dcc, html

    diff_rows = data_a.diff_with(data_b)
    n_regress = sum(1 for r in diff_rows if r["status"] == "regression")
    n_improve = sum(1 for r in diff_rows if r["status"] == "improvement")
    n_stable = sum(1 for r in diff_rows if r["status"] == "stable")

    columns = ["function", "status", "sig_a", "sig_b", "delta_sig", "amp_a", "amp_b"]

    return html.Div([
        html.Div([
            kpi("regressions", n_regress, tone="critical" if n_regress else "good"),
            kpi("improvements", n_improve, tone="good" if n_improve else None),
            kpi("stable functions", n_stable, tone="good"),
            kpi("total functions", len(diff_rows)),
        ], className="kpi-row"),
        html.Div([
            html.Div(dcc.Graph(
                id="diff-waterfall-graph",
                figure=figures.diff_waterfall_figure(diff_rows),
                config={"displayModeBar": False},
            ), className="card"),
        ]),
        html.H3("Function-by-function comparison"),
        html.Div(
            data_table(dash_table, diff_rows, columns, "diff-table", page_size=15),
            className="card",
        ),
    ], className="tab-body")


def graph_tab(data: ExperimentData):
    from dash import dcc, html

    return html.Div([
        html.Div(dcc.Graph(
            id="callgraph-graph",
            figure=figures.callgraph_figure(data.call_graph()),
            config={"displayModeBar": False},
        ), className="card"),
        html.P("Nodes are traced functions; arrows point the way outputs "
               "flow (callee → shown under its caller). Color and the "
               "printed value are the worst cross-run output significance "
               "(sig(mean) proxy): red = digits lost, yellow ≈ float32, "
               "green = exact. Gray = nothing measurable (inputs only, or "
               "a single run). Arrow thickness scales with call count. "
               "Click a node to open it in the Explorer.",
               className="hint"),
    ], className="tab-body")


def gantt_tab(data: ExperimentData):
    from dash import dcc, html

    return html.Div([
        html.Div([
            html.Div([
                html.Label("Run"),
                dcc.Dropdown(id="gantt-run",
                             options=[{"label": r, "value": r}
                                      for r in data.run_ids],
                             value=data.run_ids[0] if data.run_ids else None,
                             clearable=False),
            ], className="control"),
        ], className="controls-row"),
        html.Div(dcc.Graph(id="gantt-graph"), className="card"),
        html.P("Spans use monotonic capture timestamps (ts_ns). For the full "
               "multi-run flame view, use `pytracer export --format perfetto` "
               "and open it at ui.perfetto.dev.", className="hint"),
    ], className="tab-body")


def coverage_tab(data: ExperimentData, dash_table):
    from dash import dcc, html

    coverage = data.report.get("coverage", {})
    children = [
        html.Div(dcc.Graph(
            id="tier-coverage-graph",
            figure=figures.tier_coverage_figure(coverage.get("calls_per_tier", {})),
            config={"displayModeBar": False},
        ), className="card half"),
    ]
    native = coverage.get("native_kernels", {})
    if native:
        rows = [{"kernel": k, "calls": v["calls"], "volume": v["volume"]}
                for k, v in sorted(native.items(), key=lambda kv: -kv[1]["volume"])]
        children.append(html.Div([
            html.H4("Native BLAS kernels (T5 census)"),
            data_table(dash_table, rows, ["kernel", "calls", "volume"],
                       "native-table", page_size=10),
        ], className="card half"))
    untraced = coverage.get("untraced_numerical_callables", [])
    if untraced:
        children.append(html.Div([
            html.H4("Untraced numerical callables"),
            html.P("Observed by the monitor but not traced — coverage gaps. "
                   "Add them with --target, or run "
                   "`pytracer suggest-targets <experiment>`.", className="hint"),
            data_table(dash_table, untraced[:50], ["function", "calls"],
                       "untraced-table", page_size=10),
        ], className="card"))
    else:
        children.append(html.Div([
            html.H4("Untraced numerical callables"),
            html.P("None observed — coverage looks complete.", className="hint"),
        ], className="card"))
    notes = coverage.get("notes", [])
    if notes:
        children.append(html.Div(
            [html.P(n, className="hint") for n in notes], className="card"))
    return html.Div(children, className="tab-body")


def runs_tab(data: ExperimentData, dash_table):
    from dash import html

    runs = data.report.get("runs", [])
    if not runs:
        return html.Div(html.P("No run metadata found.", className="hint"),
                        className="tab-body")
    rows = []
    for meta in runs:
        rows.append({
            "run": meta.get("run_id"),
            "exit_code": meta.get("exit_code"),
            "created_at": meta.get("created_at", "")[:19],
            "python": meta.get("python_version"),
            "numpy": meta.get("packages", {}).get("numpy"),
            "platform": meta.get("platform"),
            "error": meta.get("error") or "",
        })
    first = runs[0]
    env = first.get("environment", {})
    env_rows = [{"variable": k, "value": v} for k, v in sorted(env.items())]
    return html.Div([
        html.H3("Runs"),
        html.Div(data_table(dash_table, rows,
                            ["run", "exit_code", "created_at", "python",
                              "numpy", "platform", "error"],
                            "runs-table"), className="card"),
        html.H3("Captured environment (allowlist only)"),
        html.Div(data_table(dash_table, env_rows, ["variable", "value"],
                            "env-table", page_size=15), className="card"),
        html.H3("Reproduce"),
        html.Div(html.Pre(
            f"python   {first.get('python_version')}\n"
            f"platform {first.get('platform')}\n"
            f"packages {first.get('packages')}\n"
            f"command  {' '.join(first.get('command', []))}",
            className="code-block"), className="card"),
    ], className="tab-body")


def build_layout(data: ExperimentData, data_compare: ExperimentData | None = None):
    from dash import dash_table, dcc, html

    tabs_children = [
        dcc.Tab(label="Overview", value="tab-overview",
                className="pt-tab", selected_className="pt-tab--active",
                children=overview_tab(data, dash_table)),
    ]

    if data_compare is not None:
        tabs_children.append(
            dcc.Tab(label="Diff (A/B)", value="tab-diff",
                    className="pt-tab", selected_className="pt-tab--active",
                    children=diff_tab(data, data_compare, dash_table))
        )

    tabs_children.extend([
        dcc.Tab(label="Explorer", value="tab-explorer",
                className="pt-tab", selected_className="pt-tab--active",
                children=explorer_tab(data)),
        dcc.Tab(label="Call graph", value="tab-graph",
                className="pt-tab", selected_className="pt-tab--active",
                children=graph_tab(data)),
        dcc.Tab(label="Call timeline", value="tab-gantt",
                className="pt-tab", selected_className="pt-tab--active",
                children=gantt_tab(data)),
        dcc.Tab(label="Coverage", value="tab-coverage",
                className="pt-tab", selected_className="pt-tab--active",
                children=coverage_tab(data, dash_table)),
        dcc.Tab(label="Runs", value="tab-runs",
                className="pt-tab", selected_className="pt-tab--active",
                children=runs_tab(data, dash_table)),
    ])

    return html.Div([
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="theme-store", data="light"),
        header_bar(data, data_compare),
        html.Div([
            kpi_row(data),
            dcc.Tabs(id="tabs", value="tab-overview", className="pt-tabs",
                     parent_className="pt-tabs-parent", children=tabs_children),
        ], className="page-body"),
    ], id="pt-root-container", className="pt-root")
