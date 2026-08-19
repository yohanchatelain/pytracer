"""Plotly figure builders. All figures share the pytracer template."""

from __future__ import annotations

import numpy as np

from pytracer.dashboard import theme
from pytracer.dashboard.data import MAX_TIMELINE_POINTS_WEBGL, as_matrix

METRICS = {
    "sig_proxy": "Significant bits — sig(mean) proxy",
    "sig_element": "Significant bits — element-wise min",
    "mean": "Mean (cross-run mean of means)",
    "std": "Std of per-run means",
    "min": "Min across runs",
    "max": "Max across runs",
    "nan_count": "NaN count (all runs)",
    "inf_count": "Inf count (all runs)",
}

_TEMPLATE = None


def template():
    global _TEMPLATE
    if _TEMPLATE is None:
        _TEMPLATE = theme.make_template()
    return _TEMPLATE


def empty_figure(message: str):
    import plotly.graph_objects as go

    fig = go.Figure()
    fig.update_layout(
        template=template(),
        xaxis={"visible": False},
        yaxis={"visible": False},
        annotations=[{
            "text": message, "showarrow": False,
            "font": {"color": theme.MUTED, "size": 13},
        }],
        height=260,
    )
    return fig


# ------------------------------------------------------------------ overview

def amplification_figure(top_rows: list[dict]):
    """Horizontal ranking of digit-loss amplification per function."""
    import plotly.graph_objects as go

    rows = [r for r in top_rows if r.get("max_amplification_bits") is not None]
    if not rows:
        return empty_figure("No amplification measured "
                            "(needs matched input and output significance).")
    rows = sorted(rows, key=lambda r: r["max_amplification_bits"], reverse=True)
    fig = go.Figure(go.Bar(
        x=[r["max_amplification_bits"] for r in rows],
        y=[r["function"] for r in rows],
        orientation="h",
        marker={"color": theme.ACCENT, "cornerradius": 4},
        width=0.55,
        hovertemplate=("<b>%{x:.2f} bits destroyed</b><br>%{y}"
                       "<br>min output sig: %{customdata[0]:.2f} bits"
                       "<extra></extra>"),
        customdata=[[r.get("min_output_sig_bits") or 0] for r in rows],
        text=[f"{r['max_amplification_bits']:.1f}" for r in rows],
        textposition="outside",
        textfont={"color": theme.INK_SECONDARY, "size": 11},
        cliponaxis=False,
    ))
    fig.update_layout(
        template=template(),
        title="Digit-loss amplification — bits of precision destroyed per call (max)",
        xaxis_title="bits",
        height=max(220, 92 + 44 * len(rows)),
        yaxis={"autorange": "reversed"},
        showlegend=False,
    )
    return fig


def sig_overview_figure(functions: list[dict]):
    """Min output significance per function against float32/float64 landmarks."""
    import plotly.graph_objects as go

    rows = [r for r in functions if r.get("min_output_sig_bits") is not None]
    if not rows:
        return empty_figure("No cross-run significance measured "
                            "(needs at least 2 runs).")
    rows = sorted(rows, key=lambda r: r["min_output_sig_bits"])
    colors = [
        theme.STATUS["critical"] if r["min_output_sig_bits"] < 10
        else theme.STATUS["serious"] if r["min_output_sig_bits"] < theme.FLOAT32_BITS
        else theme.ACCENT
        for r in rows
    ]
    fig = go.Figure(go.Bar(
        x=[r["min_output_sig_bits"] for r in rows],
        y=[r["function"] for r in rows],
        orientation="h",
        marker={"color": colors, "cornerradius": 4},
        width=0.55,
        hovertemplate="<b>%{x:.2f} significant bits</b><br>%{y}<extra></extra>",
    ))
    fig.add_vline(x=theme.FLOAT32_BITS, line_color=theme.BASELINE, line_width=1,
                  annotation_text="float32 (24)", annotation_position="top left",
                  annotation_font={"color": theme.MUTED, "size": 10})
    fig.add_vline(x=theme.SIG_CAP_BITS, line_color=theme.BASELINE, line_width=1,
                  annotation_text="exact (53)", annotation_position="top left",
                  annotation_font={"color": theme.MUTED, "size": 10})
    fig.update_layout(
        template=template(),
        title="Worst-case output significance per function",
        xaxis={"title": "significant bits", "range": [0, 57]},
        height=max(220, 92 + 44 * len(rows)),
        yaxis={"autorange": "reversed"},
        showlegend=False,
    )
    return fig


# ------------------------------------------------------------------ explorer

def timeline_figure(rows: list[dict], metric: str, yscale: str,
                    all_functions: list[str]):
    """Per-invocation scatter: the pytracer-1 timeline on aligned call groups.

    Inputs are triangles-up, outputs triangles-down, one categorical slot per
    function; exceptions and divergent groups get status marks.
    """
    import plotly.graph_objects as go

    if not rows:
        return empty_figure("Select one or more functions to plot their calls.")
    if all(r.get(metric) is None for r in rows):
        if metric in ("sig_proxy", "sig_element"):
            return empty_figure(
                "Significance is undefined here — cross-run metrics need at "
                "least 2 runs<br>(and element-wise ones need stored arrays). "
                "Try the mean/std metrics instead.")
        return empty_figure("No values for this metric on the current selection.")

    total = len(rows)
    scatter_cls = go.Scattergl if total > MAX_TIMELINE_POINTS_WEBGL else go.Scatter
    fig = go.Figure()

    by_trace: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        by_trace.setdefault((r["function"], r["phase"]), []).append(r)

    for (function, phase), trace_rows in sorted(by_trace.items()):
        color = theme.function_color(function, all_functions)
        symbol = "triangle-up" if phase == "input" else "triangle-down"
        xs, ys, custom, symbols, sizes, mcolors = [], [], [], [], [], []
        for r in trace_rows:
            y = r.get(metric)
            xs.append(r["x"])
            ys.append(y)
            custom.append([
                r["gidx"], r["phase"], r["arg"], r["function"],
                r["dtype"], r["shape"],
                f"{r['file']}:{r['lineno']}" if r["file"] else "",
                "arrays stored" if r["has_arrays"] else "summary only",
            ])
            if r["exception"]:
                symbols.append("x")
                mcolors.append(theme.STATUS["critical"])
                sizes.append(11)
            elif r["divergent"]:
                symbols.append("star")
                mcolors.append(theme.STATUS["serious"])
                sizes.append(11)
            else:
                symbols.append(symbol)
                mcolors.append(color)
                sizes.append(9)
        fig.add_trace(scatter_cls(
            name=f"{function} · {phase}s",
            x=xs, y=ys,
            mode="markers",
            marker={
                "symbol": symbols, "color": mcolors, "size": sizes,
                "opacity": 0.85,
                "line": {"color": theme.SURFACE, "width": 1},
            },
            customdata=custom,
            hovertemplate=(
                "<b>%{y:.6g}</b> · " + METRICS.get(metric, metric)
                + "<br>%{customdata[3]} — %{customdata[2]} (%{customdata[1]})"
                + "<br>call #%{x} · %{customdata[4]} %{customdata[5]}"
                + "<br>%{customdata[6]} · %{customdata[7]}"
                + "<extra></extra>"
            ),
        ))

    fig.update_layout(
        template=template(),
        height=460,
        xaxis={"title": "Invocation (aligned call index, program order)"},
        yaxis={"title": METRICS.get(metric, metric), "type": yscale},
        hovermode="closest",
        clickmode="event",
    )
    if metric in ("sig_proxy", "sig_element"):
        fig.add_hline(y=theme.FLOAT32_BITS, line_color=theme.BASELINE,
                      line_width=1, line_dash="dot",
                      annotation_text="float32 precision",
                      annotation_font={"color": theme.MUTED, "size": 10})
        fig.update_yaxes(range=[-2, 57] if yscale == "linear" else None)
    return fig


# ---------------------------------------------------------------- drill-down

def detail_heatmap(matrix: np.ndarray, mode: str, colorscale_key: str,
                   zscale: str, title: str):
    import plotly.graph_objects as go

    z = as_matrix(matrix).astype(float)
    zmin = zmax = None
    colorbar_title = title
    if mode == "sig":
        zmin, zmax = 0.0, theme.SIG_CAP_BITS
        colorscale = theme.HEATMAP_SCALES.get(colorscale_key, theme.SIG_COLORSCALE)
    else:
        colorscale = theme.HEATMAP_SCALES.get(colorscale_key,
                                              theme.MAGNITUDE_COLORSCALE)
    if zscale in ("log2", "log10") and mode != "sig":
        with np.errstate(all="ignore"):
            z = np.log2(np.abs(z)) if zscale == "log2" else np.log10(np.abs(z))
        colorbar_title = f"{zscale}|{title}|"

    fig = go.Figure(go.Heatmap(
        z=z,
        zmin=zmin, zmax=zmax,
        colorscale=colorscale,
        colorbar={"title": {"text": colorbar_title, "side": "right"},
                  "thickness": 12, "outlinewidth": 0},
        hovertemplate="row %{y} · col %{x}<br><b>%{z:.6g}</b><extra></extra>",
    ))
    height = min(520, max(240, 28 * z.shape[0] + 120))
    fig.update_layout(
        template=template(),
        height=height,
        xaxis={"side": "top", "showgrid": False, "constrain": "domain"},
        yaxis={"autorange": "reversed", "showgrid": False,
               "scaleanchor": "x" if max(z.shape) <= 64 else None},
        margin={"l": 40, "r": 8, "t": 40, "b": 12},
    )
    return fig


def detail_histogram(values: np.ndarray, nbins: int, norm: str, xlabel: str):
    import plotly.graph_objects as go

    flat = np.asarray(values, dtype=float).ravel()
    flat = flat[np.isfinite(flat)]
    if flat.size == 0:
        return empty_figure("No finite values to bin.")
    fig = go.Figure(go.Histogram(
        x=flat,
        nbinsx=max(1, int(nbins or 0)) or None,
        histnorm=norm or "",
        marker={"color": theme.ACCENT, "cornerradius": 2,
                "line": {"color": theme.SURFACE, "width": 1}},
        hovertemplate="%{x}<br><b>%{y}</b><extra></extra>",
    ))
    fig.update_layout(
        template=template(),
        height=260,
        xaxis_title=xlabel,
        yaxis_title=norm or "count",
        bargap=0.02,
        showlegend=False,
        margin={"l": 48, "r": 8, "t": 16, "b": 40},
    )
    return fig


def runs_line_figure(detail_rows: list[dict], arg: str):
    """Per-run mean with std whiskers for one argument of one aligned call."""
    import plotly.graph_objects as go

    rows = [r for r in detail_rows if r.get("mean") is not None]
    if not rows:
        return empty_figure("No numeric summary for this argument.")
    fig = go.Figure(go.Scatter(
        x=[r["run"] for r in rows],
        y=[r["mean"] for r in rows],
        error_y={
            "type": "data",
            "array": [r.get("std") or 0 for r in rows],
            "color": theme.BASELINE, "thickness": 1.5, "width": 4,
        },
        mode="markers+lines",
        line={"color": theme.GRID, "width": 1},
        marker={"color": theme.ACCENT, "size": 9,
                "line": {"color": theme.SURFACE, "width": 2}},
        hovertemplate="<b>%{y:.9g}</b> ± %{error_y.array:.3g}<br>%{x}<extra></extra>",
    ))
    fig.update_layout(
        template=template(),
        height=240,
        title=f"Per-run mean of {arg} (whiskers: within-run std)",
        yaxis={"tickformat": ".6g"},
        showlegend=False,
        margin={"l": 64, "r": 8, "t": 40, "b": 32},
    )
    return fig


# --------------------------------------------------------------- call graph

def _graph_layout(root: str, nodes: list[str],
                  edges: list[tuple[str, str]]) -> dict[str, tuple[float, float]]:
    """Layered left-to-right DAG layout (longest path + barycenter ordering)."""
    children: dict[str, list[str]] = {}
    parents: dict[str, list[str]] = {}
    for a, b in edges:
        children.setdefault(a, []).append(b)
        parents.setdefault(b, []).append(a)

    level: dict[str, int] = {root: 0}

    def assign(name: str, stack: frozenset) -> int:
        if name in level:
            return level[name]
        if name in stack:  # cycle guard
            return 0
        ps = parents.get(name, [])
        depth = 1 + max(
            (assign(p, stack | {name}) for p in ps), default=0
        ) if ps else 1
        level[name] = depth
        return depth

    for name in nodes:
        assign(name, frozenset())

    by_level: dict[int, list[str]] = {}
    for name in nodes:
        by_level.setdefault(level[name], []).append(name)
    for names in by_level.values():
        names.sort()

    pos: dict[str, tuple[float, float]] = {}
    for _ in range(2):  # barycenter sweeps
        for depth in sorted(by_level):
            names = by_level[depth]
            if pos:
                names.sort(key=lambda n: (
                    sum(pos[p][1] for p in parents.get(n, []) if p in pos)
                    / max(1, len([p for p in parents.get(n, []) if p in pos]))
                    if any(p in pos for p in parents.get(n, [])) else 0.0,
                    n,
                ))
            n = len(names)
            for i, name in enumerate(names):
                pos[name] = (float(depth), i - (n - 1) / 2.0)
    return pos


def callgraph_figure(graph: dict):
    """Nodes are functions, arrows are outputs flowing to the caller's frame;
    color is worst output significance (red = bad, yellow = float32,
    green = exact). The value is printed on every node, so color never
    carries meaning alone."""
    import plotly.graph_objects as go

    nodes, edges = graph["nodes"], graph["edges"]
    if not nodes:
        return empty_figure("No traced calls to draw.")
    root = graph["root"]
    names = [root, *nodes.keys()]
    pos = _graph_layout(root, names, list(edges))

    max_count = max((e["count"] for e in edges.values()), default=1)
    annotations = []
    edge_hover_x, edge_hover_y, edge_hover_text = [], [], []
    for (a, b), edge in edges.items():
        x0, y0 = pos[a]
        x1, y1 = pos[b]
        color = theme.sig_to_color(edge["min_sig"])
        width = 1.2 + 2.4 * (edge["count"] / max_count)
        annotations.append({
            "x": x1, "y": y1, "ax": x0, "ay": y0,
            "xref": "x", "yref": "y", "axref": "x", "ayref": "y",
            "showarrow": True, "arrowhead": 3, "arrowsize": 1.1,
            "arrowwidth": width, "arrowcolor": color,
            "standoff": 26, "startstandoff": 26,
            "text": "",
        })
        edge_hover_x.append((x0 + x1) / 2)
        edge_hover_y.append((y0 + y1) / 2)
        sig_txt = (f"{edge['min_sig']:.1f} significant bits (worst output)"
                   if edge["min_sig"] is not None else "no cross-run measure")
        edge_hover_text.append(
            f"<b>{a} → {b}</b><br>{edge['count']} call site(s) · {sig_txt}")

    node_x, node_y, node_text, node_color, node_size = [], [], [], [], []
    node_custom, node_hover = [], []
    for name in names:
        x, y = pos[name]
        node_x.append(x)
        node_y.append(y)
        if name == root:
            info = None
            label = graph.get("root_label", root)
            node_text.append(f"<b>{label}</b>")
            node_color.append(theme.UNKNOWN_GRAY)
            node_size.append(30)
            node_custom.append("")
            node_hover.append(f"<b>{label}</b><br>traced script (root)")
            continue
        info = nodes[name]
        short = name.split(".", 1)[1] if "." in name else name
        sig = info["min_sig"]
        sig_label = f"{sig:.1f} b" if sig is not None else "–"
        node_text.append(f"<b>{short}</b><br>{sig_label}")
        node_color.append(theme.sig_to_color(sig))
        node_size.append(24 + 10 * (info["calls"] / max(
            n["calls"] for n in nodes.values())))
        node_custom.append(name)
        median = info["median_sig"]
        node_hover.append(
            f"<b>{name}</b><br>"
            f"{info['calls']} aligned call group(s) · tier {','.join(info['tiers'])}"
            f"<br>min output sig: "
            + (f"{sig:.2f} bits" if sig is not None else "n/a")
            + (f" · median: {median:.2f} bits" if median is not None else "")
            + (f"<br>⚠ {info['exceptions']} call(s) raised"
               if info["exceptions"] else ""))

    fig = go.Figure()
    fig.add_trace(go.Scatter(  # invisible edge-midpoint hover targets
        x=edge_hover_x, y=edge_hover_y, mode="markers",
        marker={"size": 22, "color": "rgba(0,0,0,0)"},
        hovertemplate="%{text}<extra></extra>", text=edge_hover_text,
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y, mode="markers+text",
        text=node_text, textposition="middle center",
        textfont={"size": 10.5, "color": theme.INK},
        marker={
            "size": node_size,
            "color": node_color,
            "opacity": 0.28,
            "line": {"color": node_color, "width": 2},
            "symbol": "circle",
        },
        customdata=node_custom,
        hovertemplate="%{hovertext}<extra></extra>", hovertext=node_hover,
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(  # colorbar carrier
        x=[None], y=[None], mode="markers",
        marker={
            "colorscale": theme.SEVERITY_COLORSCALE,
            "cmin": 0, "cmax": theme.SIG_CAP_BITS, "color": [0],
            "showscale": True,
            "colorbar": {
                "title": {"text": "significant bits", "side": "right"},
                "thickness": 12, "outlinewidth": 0, "len": 0.7,
                "tickvals": [0, 10, theme.FLOAT32_BITS, 40, theme.SIG_CAP_BITS],
                "ticktext": ["0", "10", "24 (float32)", "40", "53 (exact)"],
            },
        },
        hoverinfo="skip", showlegend=False,
    ))

    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    fig.update_layout(
        template=template(),
        annotations=annotations,
        height=max(420, 130 + 90 * (max(ys) - min(ys) + 1)),
        xaxis={"visible": False,
               "range": [min(xs) - 0.5, max(xs) + 0.55]},
        yaxis={"visible": False,
               "range": [min(ys) - 0.6, max(ys) + 0.6]},
        hovermode="closest",
        clickmode="event",
        margin={"l": 16, "r": 16, "t": 24, "b": 16},
    )
    return fig


# -------------------------------------------------------------------- gantt

def gantt_figure(spans: list[dict], total: int, run_id: str):
    """Horizontal call-span timeline for one run, colored by tier."""
    import plotly.graph_objects as go

    if not spans:
        return empty_figure("No timestamped calls in this run "
                            "(events carry no ts_ns).")
    fig = go.Figure()
    lanes = list(range(len(spans)))
    # sub-pixel spans stay clickable: enforce a minimum rendered duration
    t_max = max(s["start_us"] + s["dur_us"] for s in spans)
    min_dur = max(t_max, 1.0) * 0.004
    for tier in sorted({s["tier"] for s in spans}):
        idx = [i for i, s in enumerate(spans) if s["tier"] == tier]
        fig.add_trace(go.Bar(
            name=f"tier {tier}",
            base=[spans[i]["start_us"] for i in idx],
            x=[max(spans[i]["dur_us"], min_dur) for i in idx],
            y=[lanes[i] for i in idx],
            orientation="h",
            width=0.72,
            marker={
                "color": theme.TIER_COLORS.get(tier, theme.MUTED),
                "cornerradius": 3,
                "line": {"color": theme.SURFACE, "width": 1},
            },
            customdata=[[spans[i]["name"], spans[i]["dur_us"],
                         spans[i]["depth"],
                         spans[i]["exception"] or ""] for i in idx],
            hovertemplate=("<b>%{customdata[0]}</b>"
                           "<br>%{customdata[1]:.1f} µs · depth %{customdata[2]}"
                           "<br>start %{base:.1f} µs"
                           "<br>%{customdata[3]}<extra></extra>"),
        ))
    fig.update_layout(
        template=template(),
        barmode="overlay",
        height=max(280, 60 + 18 * len(spans)),
        xaxis={"title": "µs since first traced call"},
        yaxis={
            "autorange": "reversed",
            "tickmode": "array",
            "tickvals": lanes,
            "ticktext": [
                (" " * min(s["depth"], 8) * 2) + s["name"] for s in spans
            ],
            "tickfont": {"size": 10, "family": "ui-monospace, monospace"},
            "showgrid": False,
        },
        title=(f"Call spans — {run_id}"
               + (f" (showing {len(spans)} longest of {total})"
                  if total > len(spans) else "")),
        legend={"orientation": "h"},
    )
    return fig


# ------------------------------------------------------------------ coverage

def tier_coverage_figure(calls_per_tier: dict):
    import plotly.graph_objects as go

    tier_help = {
        "t1": "t1 — decorated / explicit targets",
        "t2": "t2 — intercepted ufuncs",
        "t3": "t3 — tracer arrays (taint)",
        "t4": "t4 — monitor census",
    }
    if not calls_per_tier:
        return empty_figure("No traced calls.")
    tiers = sorted(calls_per_tier)
    fig = go.Figure(go.Bar(
        x=[tier_help.get(t, t) for t in tiers],
        y=[calls_per_tier[t] for t in tiers],
        marker={"color": [theme.TIER_COLORS.get(t, theme.MUTED) for t in tiers],
                "cornerradius": 4},
        width=0.25,
        text=[f"{calls_per_tier[t]:,}" for t in tiers],
        textposition="outside",
        textfont={"color": theme.INK_SECONDARY, "size": 11},
        cliponaxis=False,
        hovertemplate="<b>%{y:,} traced calls</b><br>%{x}<extra></extra>",
    ))
    fig.update_layout(
        template=template(),
        title="Traced calls per instrumentation tier",
        height=300,
        yaxis_title="calls",
        showlegend=False,
    )
    return fig
