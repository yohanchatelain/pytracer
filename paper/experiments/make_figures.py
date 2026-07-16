"""Generate paper/figures/*.pdf from paper/results/*.csv with matplotlib.

Palette: blue #2a78d6 as the primary series hue; blue/red as the
stable/unstable polarity pair; grays for chrome. Thin marks, direct
labels, recessive axes.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from common import PAPER, read_csv
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

FIGURES = PAPER / "figures"

BLUE = "#2a78d6"
RED = "#e34948"
GREEN = "#008300"
ORANGE = "#eb6834"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 9,
    "axes.edgecolor": AXIS,
    "axes.labelcolor": INK,
    "axes.linewidth": 0.6,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.labelcolor": INK2,
    "ytick.labelcolor": INK2,
    "grid.color": GRID,
    "grid.linewidth": 0.5,
    "text.color": INK,
    "figure.dpi": 150,
    "savefig.bbox": "tight",
})


def save(fig, name: str) -> None:
    FIGURES.mkdir(exist_ok=True)
    out = FIGURES / f"{name}.pdf"
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out.relative_to(PAPER.parent)}")


def despine(ax, keep=("left", "bottom")) -> None:
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(side in keep)


# -- F1: architecture / pipeline diagram -----------------------------------

def fig_architecture() -> None:
    fig, ax = plt.subplots(figsize=(6.4, 3.1))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 48)
    ax.axis("off")

    def box(x, y, w, h, label, sub="", fc="#eef4fc", ec=BLUE, lw=0.9):
        ax.add_patch(FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.6,rounding_size=1.2",
            facecolor=fc, edgecolor=ec, linewidth=lw))
        cy = y + h / 2 + (1.6 if sub else 0)
        ax.text(x + w / 2, cy, label, ha="center", va="center",
                fontsize=7.5, color=INK)
        if sub:
            ax.text(x + w / 2, y + h / 2 - 2.6, sub, ha="center", va="center",
                    fontsize=6, color=INK2)

    def arrow(x0, y0, x1, y1):
        ax.add_patch(FancyArrowPatch(
            (x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=9,
            color=INK2, linewidth=0.8, shrinkA=2, shrinkB=2))

    tiers = [
        ("T1 boundary\npatching", "wrapt proxies"),
        ("T2 ufunc\nproxy", "call/reduce/…"),
        ("T3 tracer\narrays", "taint, opt-in"),
        ("T4 runtime\nmonitor", "sys.monitoring"),
        ("T5 native\ncensus", "LD_PRELOAD"),
    ]
    for i, (label, sub) in enumerate(tiers):
        box(1, 38 - i * 9.4, 15.5, 7.4, label, sub,
            fc="#eef4fc" if i < 2 or i == 3 else "#f6f6f4",
            ec=BLUE if i < 2 or i == 3 else MUTED)

    box(23.5, 18, 14, 10, "event\nstream", "versioned")
    for i in range(5):
        arrow(17.5, 41.7 - i * 9.4, 23.5, 23 + (2 - i) * 1.4)

    box(42.5, 18, 15, 10, "append-only\ncapture", "JSONL, crash-safe")
    arrow(38.5, 23, 42.5, 23)
    box(62.5, 24.5, 14.5, 8, "Parquet", "per-run finalize")
    box(62.5, 11.5, 14.5, 8, "Zarr / npy", "array payloads")
    arrow(58.5, 25, 62.5, 28)
    arrow(58.5, 21, 62.5, 15.5)

    box(82.5, 18, 16.5, 10, "alignment +\nattribution",
        "sig bits, amplif.")
    arrow(78, 28, 82.5, 24.5)
    arrow(78, 15.5, 82.5, 21.5)

    for i, out in enumerate(["report / dashboard", "check / diff (CI)",
                             "Perfetto export"]):
        ax.text(90.8, 12.5 - i * 3.6, out, ha="center", va="center",
                fontsize=6.8, color=INK2)
    arrow(90.8, 17.4, 90.8, 14.2)

    ax.text(8.7, 47.2, "instrumentation tiers", fontsize=7.5, color=MUTED,
            ha="center")
    ax.text(61, 47.2,
            "one independent subprocess per repetition;\n"
            "runs aligned call-by-call across repetitions",
            fontsize=7, color=MUTED, ha="center", va="center")
    save(fig, "architecture")


# -- F2: gallery dumbbell ----------------------------------------------------

def fig_gallery() -> None:
    rows = read_csv("e1_gallery.csv")
    rows = sorted(rows, key=lambda r: float(r["gap_bits"]))
    labels = [r["script"].removesuffix(".py").replace("_", " ")
              + (f"\n({r['unstable']})" if r["script"] == "expm1_log1p.py" else "")
              for r in rows]
    y = range(len(rows))
    unstable = [float(r["sig_unstable_bits"]) for r in rows]
    stable = [float(r["sig_stable_bits"]) for r in rows]

    fig, ax = plt.subplots(figsize=(5.6, 3.2))
    ax.hlines(y, unstable, stable, color=AXIS, linewidth=1.2, zorder=1)
    ax.scatter(unstable, y, s=34, color=RED, zorder=2, label="unstable variant")
    ax.scatter(stable, y, s=34, color=BLUE, zorder=2, label="stable variant")
    ax.set_yticks(y, labels, fontsize=7.5)
    ax.set_xlabel("minimum significant bits of the output (5 runs)")
    ax.set_xlim(-2, 56)
    ax.axvline(52, color=GRID, linewidth=0.8, zorder=0)
    ax.text(52, len(rows) - 0.4, "float64\nresolution", fontsize=6.5,
            color=MUTED, ha="center")
    ax.grid(axis="x")
    ax.set_axisbelow(True)
    despine(ax)
    ax.legend(frameon=False, fontsize=7.5, loc="upper left",
              bbox_to_anchor=(0.02, 1.14), ncols=2)
    save(fig, "gallery")


# -- F3: overhead bars -------------------------------------------------------

SHORT_WORKLOAD = {
    "20k tiny numpy.sum calls": "tiny sums",
    "2M-element numpy.sum calls": "2M-elem sums",
    "operator loop (x*a+b)": "operator loop",
    "end-to-end simple_numpy.py": "end-to-end script",
}


def fig_overhead() -> None:
    rows = read_csv("e2_overhead.csv")
    labels = [f"{r['tier']}\n{SHORT_WORKLOAD[r['workload']]}" for r in rows]
    values = [float(r["overhead_x"]) for r in rows]

    fig, ax = plt.subplots(figsize=(5.4, 2.7))
    bars = ax.bar(range(len(rows)), values, width=0.55, color=BLUE, zorder=2)
    for bar, v in zip(bars, values, strict=True):
        ax.text(bar.get_x() + bar.get_width() / 2, v * 1.12,
                f"{v:.0f}×", ha="center", fontsize=8, color=INK)
    ax.set_yscale("log")
    ax.set_ylim(1, 900)
    ax.set_ylabel("wall-time overhead (×, log)")
    ax.set_xticks(range(len(rows)), labels, fontsize=7)
    ax.grid(axis="y")
    ax.set_axisbelow(True)
    despine(ax)
    save(fig, "overhead")


# -- F4: coverage ------------------------------------------------------------

def fig_coverage() -> None:
    rows = [r for r in read_csv("e3_coverage.csv")
            if r["workload"] == "sklearn pipeline"]
    labels = [r["config"].replace("hybrid+", "hybrid\n+") for r in rows]
    traced = [int(r["traced_functions"]) for r in rows]
    untraced = [int(r["untraced_callables"]) for r in rows]
    x = range(len(rows))
    w = 0.36

    fig, ax = plt.subplots(figsize=(5.2, 2.8))
    b1 = ax.bar([i - w / 2 for i in x], traced, width=w - 0.03, color=BLUE,
                zorder=2, label="traced functions")
    b2 = ax.bar([i + w / 2 for i in x], untraced, width=w - 0.03, color=ORANGE,
                zorder=2, label="seen but untraced")
    for bars in (b1, b2):
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.12,
                    f"{bar.get_height():.0f}", ha="center", fontsize=8,
                    color=INK)
    ax.set_xticks(x, labels, fontsize=7.5)
    ax.set_ylabel("numerical callables")
    ax.set_ylim(0, max(traced + untraced) + 1.6)
    ax.grid(axis="y")
    ax.set_axisbelow(True)
    despine(ax)
    ax.legend(frameon=False, fontsize=7.5, loc="upper left")
    ax.set_title("scikit-learn pipeline: observed vs. admitted-unobserved",
                 fontsize=8, color=INK2)
    save(fig, "coverage")


# -- F5: basis scatter -------------------------------------------------------

def fig_basis() -> None:
    rows = read_csv("e5_basis.csv")

    fig, ax = plt.subplots(figsize=(3.8, 3.5))
    ax.plot([0, 54], [0, 54], color=AXIS, linewidth=0.8, linestyle="--",
            zorder=1)
    ax.text(28, 31.5, "y = x", fontsize=7, color=MUTED, rotation=45)

    for r in rows:
        x = float(r["summary_sig_bits"])
        y = float(r["element_sig_bits"])
        if r["function"] == "permuted_pipeline":
            ax.scatter(x, y, s=48, color=RED, zorder=3)
            ax.annotate(
                "permuted output:\nproxy says stable,\nelements disagree",
                (x, y), xytext=(20, 12), textcoords=None, fontsize=7,
                color=INK,
                arrowprops=dict(arrowstyle="-|>", color=INK2, linewidth=0.8,
                                shrinkB=4))
        else:
            ax.scatter(x, y, s=26, color=BLUE, zorder=2)

    ax.set_xlabel("sig(mean) summary proxy (bits)")
    ax.set_ylabel("element-wise significant bits")
    ax.set_xlim(-2, 56)
    ax.set_ylim(-2, 56)
    ax.set_aspect("equal")
    ax.grid(True)
    ax.set_axisbelow(True)
    despine(ax)
    save(fig, "basis")


def main() -> int:
    fig_architecture()
    fig_gallery()
    fig_overhead()
    fig_coverage()
    fig_basis()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
