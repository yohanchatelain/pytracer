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
