"""Dashboard visual theme: palette, plotly template, colorscales.

Palette follows a validated categorical/sequential scheme: fixed-order
categorical hues (never cycled per-chart), a single-hue blue ramp for
magnitude, and reserved status colors that never impersonate a series.
"""

from __future__ import annotations

SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
BORDER = "rgba(11,11,11,0.10)"

# Fixed-order categorical slots; assignment is by stable entity index.
CATEGORICAL = [
    "#2a78d6",  # blue
    "#1baf7a",  # aqua
    "#eda100",  # yellow
    "#008300",  # green
    "#4a3aa7",  # violet
    "#e34948",  # red
    "#e87ba4",  # magenta
    "#eb6834",  # orange
]

STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

TIER_COLORS = {
    "t1": "#2a78d6",  # decorator / explicit targets
    "t2": "#1baf7a",  # ufunc interception
    "t3": "#4a3aa7",  # tracer arrays (taint)
    "t4": "#eda100",  # monitor census
    "native": "#eb6834",
}

# Single-hue blue ramp, light -> dark.
SEQ_BLUE = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
    "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b",
]

ACCENT = "#2a78d6"
DEEMPHASIS = "#c3c2b7"

SIG_CAP_BITS = 53.0
FLOAT32_BITS = 24.0


def _scale(colors: list[str]) -> list[list]:
    n = len(colors) - 1
    return [[i / n, c] for i, c in enumerate(colors)]


#: For significant-bits heatmaps: darker = fewer bits = more worrying,
#: so instability carries the visual weight (light = stable, recedes).
SIG_COLORSCALE = _scale(list(reversed(SEQ_BLUE)))

#: For plain magnitude (values, spread): more is darker.
MAGNITUDE_COLORSCALE = _scale(SEQ_BLUE)

#: Diverging blue <-> red with a neutral gray midpoint, for signed values.
DIVERGING_COLORSCALE = [
    [0.0, "#0d366b"], [0.25, "#5598e7"], [0.5, "#f0efec"],
    [0.75, "#e88a89"], [1.0, "#7a1f1f"],
]

HEATMAP_SCALES = {
    "blues": MAGNITUDE_COLORSCALE,
    "blues_r": SIG_COLORSCALE,
    "diverging": DIVERGING_COLORSCALE,
    "viridis": "Viridis",
}

FONT_FAMILY = 'system-ui, -apple-system, "Segoe UI", sans-serif'

# Traffic-light severity for significant bits: red (0) -> yellow (float32
# precision, 24) -> green (exact, 53). Color is always redundant with a
# printed value, so the red/green axis never carries meaning alone.
_SEVERITY_STOPS = [
    (0.0, (208, 59, 59)),     # critical red
    (FLOAT32_BITS, (250, 178, 25)),   # warning yellow
    (SIG_CAP_BITS, (12, 163, 12)),    # good green
]

UNKNOWN_GRAY = "#c3c2b7"


def sig_to_color(sig: float | None) -> str:
    """Map significant bits to the red-yellow-green severity ramp."""
    if sig is None:
        return UNKNOWN_GRAY
    s = max(0.0, min(SIG_CAP_BITS, float(sig)))
    for (x0, c0), (x1, c1) in zip(_SEVERITY_STOPS, _SEVERITY_STOPS[1:], strict=False):
        if s <= x1:
            t = 0.0 if x1 == x0 else (s - x0) / (x1 - x0)
            r, g, b = (round(a + (b_ - a) * t)
                       for a, b_ in zip(c0, c1, strict=True))
            return f"rgb({r},{g},{b})"
    return f"rgb{_SEVERITY_STOPS[-1][1]}"


#: Same ramp as a plotly colorscale (for the colorbar).
SEVERITY_COLORSCALE = [
    [x / SIG_CAP_BITS, f"rgb({r},{g},{b})"] for x, (r, g, b) in _SEVERITY_STOPS
]


DARK_SURFACE = "#1e293b"
DARK_PAGE = "#0f172a"
DARK_INK = "#f8fafc"
DARK_INK_SECONDARY = "#cbd5e1"
DARK_MUTED = "#94a3b8"
DARK_GRID = "#334155"
DARK_BASELINE = "#475569"
DARK_BORDER = "rgba(255,255,255,0.12)"


def make_template(dark: bool = False):
    """Plotly template shared by every dashboard figure (light or dark)."""
    import plotly.graph_objects as go

    surface = DARK_SURFACE if dark else SURFACE
    ink = DARK_INK if dark else INK
    ink_secondary = DARK_INK_SECONDARY if dark else INK_SECONDARY
    muted = DARK_MUTED if dark else MUTED
    grid = DARK_GRID if dark else GRID
    baseline = DARK_BASELINE if dark else BASELINE

    axis = {
        "gridcolor": grid,
        "gridwidth": 1,
        "linecolor": baseline,
        "zerolinecolor": baseline,
        "ticks": "outside",
        "tickcolor": baseline,
        "tickfont": {"color": muted, "size": 11},
        "title": {"font": {"color": ink_secondary, "size": 12}},
        "automargin": True,
    }
    return go.layout.Template(
        layout=go.Layout(
            paper_bgcolor=surface,
            plot_bgcolor=surface,
            font={"family": FONT_FAMILY, "color": ink, "size": 12},
            colorway=CATEGORICAL,
            xaxis=axis,
            yaxis=axis,
            margin={"l": 56, "r": 24, "t": 48, "b": 44},
            title={"font": {"size": 14, "color": ink}, "x": 0, "xanchor": "left"},
            legend={
                "orientation": "h",
                "yanchor": "bottom",
                "y": 1.02,
                "xanchor": "left",
                "x": 0,
                "font": {"color": ink_secondary, "size": 11},
            },
            hoverlabel={
                "bgcolor": surface,
                "bordercolor": grid,
                "font": {"family": FONT_FAMILY, "color": ink, "size": 12},
            },
        )
    )


def function_color(function: str, all_functions: list[str]) -> str:
    """Stable categorical slot for a function (color follows the entity)."""
    try:
        index = all_functions.index(function)
    except ValueError:
        index = 0
    return CATEGORICAL[index % len(CATEGORICAL)]
