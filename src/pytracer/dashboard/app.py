"""Optional interactive dashboard (`pip install pytracer[gui]`).

Reads a completed experiment's analysis directory — it never recomputes
analysis. One page: summary, coverage, amplification chart, sortable
function/argument tables, divergence, metadata.
"""

from __future__ import annotations

from pathlib import Path

from pytracer._errors import PytracerError
from pytracer.report.model import build_report_data


def _require_dash():
    try:
        import dash  # noqa: F401
    except ImportError as e:
        raise PytracerError(
            "the dashboard requires the gui extra: pip install 'pytracer[gui]'"
        ) from e


def build_app(experiment_dir: str | Path):
    _require_dash()
    from dash import Dash, dash_table, dcc, html

    data = build_report_data(experiment_dir)
    alignment = data.get("alignment", {})
    coverage = data.get("coverage", {})
    functions = data.get("functions", [])
    arguments = data.get("arguments", [])
    top = data.get("top_unstable", [])

    app = Dash(__name__, title="Pytracer")

    def stat(label, value):
        return html.Div(
            [html.Div(str(value), style={"fontSize": "1.6rem", "fontWeight": "600"}),
             html.Div(label, style={"color": "#666", "fontSize": "0.85rem"})],
            style={"padding": "0.8rem 1.4rem", "border": "1px solid #ddd",
                   "borderRadius": "8px", "textAlign": "center"},
        )

    header = html.Div(
        [
            stat("runs", alignment.get("runs", "?")),
            stat("call groups", alignment.get("total_call_groups", 0)),
            stat("matched", alignment.get("matched_call_groups", 0)),
            stat("divergent", alignment.get("divergent_call_groups", 0)),
            stat("alignment", alignment.get("alignment_mode", "?")),
        ],
        style={"display": "flex", "gap": "1rem", "flexWrap": "wrap",
               "margin": "1rem 0"},
    )

    children = [
        html.H1("Pytracer"),
        html.P(data.get("experiment", {}).get("script", ""),
               style={"fontFamily": "monospace", "color": "#555"}),
        header,
    ]

    amp_rows = [r for r in top if r.get("max_amplification_bits") is not None]
    if amp_rows:
        import plotly.graph_objects as go

        figure = go.Figure(
            go.Bar(
                x=[r["max_amplification_bits"] for r in amp_rows],
                y=[r["function"] for r in amp_rows],
                orientation="h",
                marker_color="#c0504d",
            )
        )
        figure.update_layout(
            title="Digit-loss amplification (bits destroyed per call, max)",
            xaxis_title="bits",
            height=max(240, 60 * len(amp_rows)),
            margin={"l": 10, "r": 10, "t": 40, "b": 30},
            yaxis={"autorange": "reversed"},
        )
        children.append(dcc.Graph(figure=figure))

    def table(rows, columns, page_size=15):
        return dash_table.DataTable(
            data=rows,
            columns=[{"name": c, "id": c} for c in columns],
            sort_action="native",
            filter_action="native",
            page_size=page_size,
            style_table={"overflowX": "auto"},
            style_cell={"fontFamily": "monospace", "fontSize": "0.85rem",
                        "padding": "0.3rem 0.6rem"},
        )

    if functions:
        function_columns = [
            "function", "sig_basis", "min_output_sig_bits",
            "max_amplification_bits", "divergence_score", "n_matched",
            "nan_instability", "inf_instability",
        ]
        rows = [
            {c: (round(r[c], 2) if isinstance(r.get(c), float) else r.get(c))
             for c in function_columns}
            for r in functions
        ]
        children += [html.H2("Functions"), table(rows, function_columns)]

    if arguments:
        argument_columns = [
            "function", "arg_name", "phase", "sig_basis", "sig_min_bits",
            "sig_median_bits", "sig_mean_bits", "n_call_groups",
        ]
        rows = [
            {c: (round(r[c], 2) if isinstance(r.get(c), float) else r.get(c))
             for c in argument_columns}
            for r in arguments
        ]
        children += [html.H2("Arguments / outputs"), table(rows, argument_columns)]

    divergent = alignment.get("divergent_calls", [])
    children.append(html.H2("Control-flow divergence"))
    if divergent:
        rows = [
            {"function": d["function"],
             "divergence_score": round(d["divergence_score"], 3),
             "missing_in_runs": ", ".join(d["missing_in_runs"])}
            for d in divergent
        ]
        children.append(table(rows, ["function", "divergence_score", "missing_in_runs"]))
    else:
        children.append(html.P("None: all runs executed the same traced calls."))

    children.append(html.H2("Coverage"))
    tiers = coverage.get("calls_per_tier", {})
    children.append(html.P(f"Traced calls per tier: {tiers or 'none'}"))
    native = coverage.get("native_kernels", {})
    if native:
        rows = [
            {"kernel": k, "calls": v["calls"], "volume": v["volume"]}
            for k, v in sorted(native.items(), key=lambda kv: -kv[1]["volume"])
        ]
        children.append(table(rows, ["kernel", "calls", "volume"], page_size=10))
    untraced = coverage.get("untraced_numerical_callables", [])
    if untraced:
        children.append(html.P("Untraced numerical callables (candidates for --target):"))
        children.append(
            table(untraced[:20], ["function", "calls"], page_size=10)
        )
    for note in coverage.get("notes", []):
        children.append(html.P(note, style={"color": "#777", "fontSize": "0.85rem"}))

    runs = data.get("runs", [])
    if runs:
        children.append(html.H2("Reproducibility"))
        first = runs[0]
        children.append(html.Pre(
            f"python  {first.get('python_version')}\n"
            f"platform {first.get('platform')}\n"
            f"packages {first.get('packages')}\n"
            f"env      {first.get('environment')}",
            style={"background": "#f6f6f6", "padding": "0.8rem",
                   "borderRadius": "6px", "overflowX": "auto"},
        ))

    app.layout = html.Div(
        children,
        style={"maxWidth": "72rem", "margin": "0 auto", "padding": "1rem",
               "fontFamily": "system-ui, sans-serif"},
    )
    return app


def run_dashboard(experiment_dir: str | Path, host: str = "127.0.0.1",
                  port: int = 8050, debug: bool = False) -> None:
    app = build_app(experiment_dir)
    app.run(host=host, port=port, debug=debug)
