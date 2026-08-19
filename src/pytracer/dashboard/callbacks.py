"""Dash callbacks wiring the explorer, drill-down, gantt, and exports."""

from __future__ import annotations

import io
import math

import numpy as np

from pytracer.dashboard import figures
from pytracer.dashboard.data import ExperimentData


def register_callbacks(app, data: ExperimentData) -> None:
    from dash import Input, Output, State, dcc, html
    from dash.exceptions import PreventUpdate

    # ------------------------------------------------------------- explorer

    @app.callback(
        Output("explorer-graph", "figure"),
        Input("explorer-functions", "value"),
        Input("explorer-metric", "value"),
        Input("explorer-phase", "value"),
        Input("explorer-yscale", "value"),
    )
    def update_timeline(functions, metric, phases, yscale):
        functions = functions or []
        phases = phases or ["input", "output"]
        rows = data.timeline_for(functions, phases)
        if metric == "sig_element":
            rows = [dict(r) for r in rows]
            for r in rows:
                r["sig_element"] = (
                    data.element_sig_min(r["gidx"], r["phase"], r["arg"])
                    if r["has_arrays"] else None
                )
        return figures.timeline_figure(rows, metric, yscale, data.functions)

    @app.callback(
        Output("selected-point", "data"),
        Input("explorer-graph", "clickData"),
        prevent_initial_call=True,
    )
    def select_point(click_data):
        if not click_data:
            raise PreventUpdate
        custom = click_data["points"][0].get("customdata")
        if not custom:
            raise PreventUpdate
        gidx, phase, arg = int(custom[0]), custom[1], custom[2]
        return {"gidx": gidx, "phase": phase, "arg": arg,
                "function": custom[3], "callsite": custom[6]}

    # ---------------------------------------------------------------- theme

    @app.callback(
        Output("theme-store", "data"),
        Output("theme-toggle-btn", "children"),
        Output("pt-root-container", "data-theme"),
        Input("theme-toggle-btn", "n_clicks"),
        State("theme-store", "data"),
        prevent_initial_call=True,
    )
    def toggle_theme(n_clicks, current_theme):
        if not n_clicks:
            raise PreventUpdate
        new_theme = "dark" if current_theme != "dark" else "light"
        btn_text = "☀️ Light" if new_theme == "dark" else "🌙 Dark"
        return new_theme, btn_text, new_theme

    # ------------------------------------------------------------- URL sync

    @app.callback(
        Output("url", "hash"),
        Input("tabs", "value"),
        Input("explorer-functions", "value"),
        prevent_initial_call=True,
    )
    def update_url(tab, functions):
        params = [f"tab={tab.replace('tab-', '')}"]
        if functions and tab == "tab-explorer":
            params.append(f"fn={','.join(functions[:3])}")
        return "&".join(params)

    # ----------------------------------------------------------- drill-down

    @app.callback(
        Output("detail-panel", "style"),
        Output("detail-title", "children"),
        Output("detail-stats", "children"),
        Output("detail-runs-graph", "figure"),
        Output("detail-source", "children"),
        Input("selected-point", "data"),
    )
    def update_detail(selected):
        from dash import dash_table

        from pytracer.dashboard.layout import data_table

        if not selected:
            empty = figures.empty_figure("")
            return {"display": "none"}, "", "", empty, ""

        gidx, phase, arg = selected["gidx"], selected["phase"], selected["arg"]
        group = data.alignment.groups[gidx]
        title_items = [
            html.Span(selected["function"], className="detail-fn"),
            html.Span(f"{arg} ({phase})", className="detail-arg"),
            html.Span(selected.get("callsite", ""), className="detail-site"),
        ]

        cond_summary = data.matrix_condition_summary(gidx, phase, arg)
        if cond_summary:
            cond_val = cond_summary["cond_median"]
            if math.isfinite(cond_val):
                cond_text = f"κ(A) ≈ {cond_val:.2e}"
            else:
                cond_text = "κ(A) = ∞ (singular)"
            tone = "critical" if cond_summary["is_ill_conditioned"] else "good"
            tag = "ill-conditioned" if cond_summary["is_ill_conditioned"] else "well-conditioned"
            title_items.append(
                html.Span(f"{cond_text} ({tag})", className=f"cond-badge cond-badge--{tone}")
            )
        title = html.Div(title_items, className="detail-title")

        detail_rows = data.group_detail(gidx, phase, arg)
        columns = [c for c in
                   ["run", "status", "dtype", "shape", "mean", "std", "min",
                    "max", "l2_norm", "linf_norm", "nan", "inf", "zero",
                    "subnormal", "fingerprint"]
                   if any(c in r for r in detail_rows)]
        stats = data_table(dash_table, detail_rows, columns,
                           "detail-stats-table", page_size=len(data.run_ids),
                           filter_action="none")
        runs_fig = figures.runs_line_figure(detail_rows, arg)

        file, lineno = group.key[3], group.key[4]
        context = data.source_context(file, lineno)
        if context:
            code_lines = []
            for offset, line in enumerate(context["lines"]):
                current = context["start"] + offset
                classname = ("code-line code-line--hit"
                             if current == context["lineno"] else "code-line")
                code_lines.append(html.Div([
                    html.Span(f"{current:>5} ", className="code-lineno"),
                    html.Span(line or " "),
                ], className=classname))
            source = html.Div([
                html.Div(f"{context['file']}:{context['lineno']}",
                         className="code-path"),
                html.Pre(code_lines, className="code-block"),
            ])
        elif file:
            source = html.P(f"{file}:{lineno} (file not readable from here)",
                            className="hint")
        else:
            source = html.P("No source reference captured for this call.",
                            className="hint")

        return {"display": "block"}, title, stats, runs_fig, source

    @app.callback(
        Output("detail-heatmap", "figure"),
        Output("detail-heatmap-note", "children"),
        Output("detail-histogram", "figure"),
        Input("selected-point", "data"),
        Input("heat-mode", "value"),
        Input("heat-colorscale", "value"),
        Input("heat-zscale", "value"),
        Input("hist-bins", "value"),
        Input("hist-norm", "value"),
    )
    def update_element_views(selected, mode, colorscale, zscale, bins, norm):
        if not selected:
            empty = figures.empty_figure("")
            return empty, "", empty

        gidx, phase, arg = selected["gidx"], selected["phase"], selected["arg"]
        loaded = data.element_stack(gidx, phase, arg)
        if loaded is None:
            message = ("No stored arrays for this argument —<br>"
                       "element-wise views need --store-arrays<br>"
                       "(and identical shapes across runs).")
            empty = figures.empty_figure(message)
            return empty, "", figures.empty_figure("")

        sig, stack = loaded
        scale_key = colorscale
        if mode == "sig":
            matrix = sig
            xlabel = "significant bits"
            if colorscale == "auto":
                scale_key = "blues_r"
        elif mode == "value":
            matrix = stack.mean(axis=0)
            xlabel = "mean value across runs"
            if colorscale == "auto":
                scale_key = "blues"
        else:
            matrix = stack.std(axis=0)
            xlabel = "std across runs"
            if colorscale == "auto":
                scale_key = "blues"
        heat = figures.detail_heatmap(matrix, mode, scale_key, zscale, xlabel)
        finite = np.asarray(matrix, dtype=float)
        finite = finite[np.isfinite(finite)]
        note = (f"{len(data.run_ids)} runs · "
                f"shape {'x'.join(map(str, stack.shape[1:])) or 'scalar'} · "
                f"{finite.size:,} finite elements"
                + (f" · min {finite.min():.4g} · max {finite.max():.4g}"
                   if finite.size else ""))
        hist = figures.detail_histogram(matrix, bins or 0, norm, xlabel)
        return heat, note, hist

    # -------------------------------------------------------------- exports

    @app.callback(
        Output("download-timeline", "data"),
        Input("download-timeline-btn", "n_clicks"),
        State("explorer-functions", "value"),
        State("explorer-phase", "value"),
        prevent_initial_call=True,
    )
    def download_timeline(n_clicks, functions, phases):
        if not n_clicks:
            raise PreventUpdate
        import csv

        rows = data.timeline_for(functions or data.functions,
                                 phases or ["input", "output"])
        buffer = io.StringIO()
        fields = ["function", "arg", "phase", "x", "sig_proxy", "mean", "std",
                  "min", "max", "nan_count", "inf_count", "dtype", "shape",
                  "size", "n_runs_present", "divergent", "has_arrays",
                  "file", "lineno"]
        writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        return {"content": buffer.getvalue(), "filename": "pytracer-timeline.csv"}

    # ---------------------------------------------------------------- gantt

    @app.callback(
        Output("gantt-graph", "figure"),
        Input("gantt-run", "value"),
    )
    def update_gantt(run_id):
        if not run_id:
            return figures.empty_figure("No runs found.")
        spans, total = data.run_spans(run_id)
        return figures.gantt_figure(spans, total, run_id)

    # ------------------------------------------------- overview -> explorer

    @app.callback(
        Output("tabs", "value"),
        Output("explorer-functions", "value"),
        Input("amp-chart", "clickData"),
        Input("callgraph-graph", "clickData"),
        Input("functions-table", "active_cell"),
        State("functions-table", "data"),
        State("explorer-functions", "value"),
        prevent_initial_call=True,
    )
    def open_in_explorer(amp_click, graph_click, active_cell, table_data, current):
        from dash import ctx

        if ctx.triggered_id == "amp-chart":
            function = (amp_click or {}).get("points", [{}])[0].get("y")
        elif ctx.triggered_id == "functions-table":
            if not active_cell or not table_data:
                raise PreventUpdate
            row_idx = active_cell.get("row")
            if row_idx is None or row_idx >= len(table_data):
                raise PreventUpdate
            function = table_data[row_idx].get("function")
        else:
            point = (graph_click or {}).get("points", [{}])[0]
            function = point.get("customdata")
        if not function or function not in data.functions:
            raise PreventUpdate
        current = current or []
        if function not in current:
            current = [*current, function]
        return "tab-explorer", current

    # keep dcc import referenced (dash requires component registration)
    _ = dcc

