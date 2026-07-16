"""Generate paper/tables/*.tex (booktabs) from paper/results/*.csv.

Tables are generated, never hand-typed: the paper's numbers cannot drift
from the measured results.
"""

from __future__ import annotations

import json
from pathlib import Path

from common import PAPER, read_csv

TABLES = PAPER / "tables"


def esc(text: str) -> str:
    return (str(text).replace("_", r"\_").replace("%", r"\%")
            .replace("&", r"\&").replace("#", r"\#"))


def write_table(name: str, lines: list[str]) -> None:
    TABLES.mkdir(exist_ok=True)
    out = TABLES / f"{name}.tex"
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out.relative_to(PAPER.parent)}")


def t_gallery() -> None:
    rows = read_csv("e1_gallery.csv")
    lines = [
        r"\begin{tabular}{llrrrrl}",
        r"\toprule",
        r"Pathology & Formulation & \multicolumn{2}{c}{$\sig_{\min}$ (bits)} "
        r"& Gap & Amp.\ & Rank \\",
        r"\cmidrule(lr){3-4}",
        r" & & unstable & stable & (bits) & (bits) & \\",
        r"\midrule",
    ]
    for r in rows:
        patho = esc(r["script"].removesuffix(".py").replace("_", " "))
        pair = esc(r["unstable"])
        rank = f"{r['rank_unstable']}\\,/\\,{r['rank_stable'] or '--'}"
        lines.append(
            f"{patho} & \\texttt{{{pair}}} & {r['sig_unstable_bits']} & "
            f"{r['sig_stable_bits']} & {r['gap_bits']} & "
            f"{r['amp_unstable_bits']} & {rank} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}"]
    write_table("gallery", lines)


def t_overhead() -> None:
    rows = read_csv("e2_overhead.csv")
    lines = [
        r"\begin{tabular}{llrrrr}",
        r"\toprule",
        r"Workload & Tier & Overhead & Events & Events/s & B/event \\",
        r"\midrule",
    ]
    for r in rows:
        ev = f"{int(r['events']):,}" if r["events"] else "--"
        evs = f"{int(r['events_per_s']):,}" if r["events_per_s"] else "--"
        bpe = r["bytes_per_event"] or "--"
        lines.append(
            f"{esc(r['workload'])} & {r['tier']} & "
            f"{r['overhead_x']}$\\times$ & {ev} & {evs} & {bpe} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}"]
    write_table("overhead", lines)


def t_coverage() -> None:
    rows = read_csv("e3_coverage.csv")
    lines = [
        r"\begin{tabular}{llrrrr}",
        r"\toprule",
        r"Workload & Configuration & Traced & \multicolumn{2}{c}{Untraced seen} "
        r"& Native \\",
        r"\cmidrule(lr){4-5}",
        r" & & fns & callables & calls & kernels \\",
        r"\midrule",
    ]
    last = None
    for r in rows:
        w = esc(r["workload"]) if r["workload"] != last else ""
        last = r["workload"]
        lines.append(
            f"{w} & {esc(r['config'])} & {r['traced_functions']} & "
            f"{r['untraced_callables']} & {r['untraced_calls']} & "
            f"{r['native_kernels']} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}"]
    write_table("coverage", lines)


def t_alignment() -> None:
    rows = read_csv("e4_alignment.csv")
    lines = [
        r"\begin{tabular}{llrrrl}",
        r"\toprule",
        r"Workload & Strategy & Call groups & Matched & Divergent & Outcome \\",
        r"\midrule",
    ]
    last = None
    for r in rows:
        w = esc(r["workload"]) if r["workload"] != last else ""
        last = r["workload"]
        if r["outcome"] == "aborts":
            lines.append(f"{w} & {r['strategy']} & -- & -- & -- & aborts \\\\")
        else:
            lines.append(
                f"{w} & {r['strategy']} & {r['total_call_groups']} & "
                f"{r['matched_call_groups']} & {r['divergent_call_groups']} & "
                f"ok \\\\"
            )
    lines += [r"\bottomrule", r"\end{tabular}"]
    write_table("alignment", lines)


def t_basis() -> None:
    rows = read_csv("e5_basis.csv")
    lines = [
        r"\begin{tabular}{llrrr}",
        r"\toprule",
        r"Workload & Function & $\sig$(summary) & $\sig$(element) & "
        r"Proxy optimism \\",
        r" & & (bits) & (bits) & (bits) \\",
        r"\midrule",
    ]
    last = None
    for r in rows:
        w = esc(r["workload"]) if r["workload"] != last else ""
        last = r["workload"]
        lines.append(
            f"{w} & \\texttt{{{esc(r['function'])}}} & {r['summary_sig_bits']} & "
            f"{r['element_sig_bits']} & {r['proxy_optimism_bits']} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}"]
    write_table("basis", lines)


def t_case() -> None:
    rows = read_csv("e6_case.csv")
    lines = [
        r"\begin{tabular}{lrrrrr}",
        r"\toprule",
        r"Traced call & \multicolumn{2}{c}{float64 (bits)} & "
        r"\multicolumn{2}{c}{float32 (bits)} & Amp.\ \\",
        r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}",
        r" & min & median & min & median & (bits) \\",
        r"\midrule",
    ]
    for r in rows:
        def v(x):
            return x if x != "" else "--"
        lines.append(
            f"\\texttt{{{esc(r['function'])}}} & {v(r['min_sig_f64'])} & "
            f"{v(r['median_sig_f64'])} & {v(r['min_sig_f32'])} & "
            f"{v(r['median_sig_f32'])} & {v(r['amp_bits_f64'])} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}"]
    write_table("case", lines)


def t_v1_matrix() -> None:
    rows = read_csv("e0_v1_matrix.csv")
    lines = [
        r"\begin{tabular}{lccccl}",
        r"\toprule",
        r"Python & Install & Import & CLI & Trace & First failure \\",
        r"\midrule",
    ]
    mark = {"True": r"\checkmark", "False": r"$\times$"}
    for r in rows:
        err = r["trace_error"].split(":")[0] if r["trace_error"] else ""
        lines.append(
            f"{r['python']} & {mark[r['install_ok']]} & {mark[r['import_ok']]} & "
            f"{mark[r['cli_ok']]} & {mark[r['trace_ok']]} & "
            f"\\texttt{{{esc(err)}}} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}"]
    write_table("v1matrix", lines)


def t_storage() -> None:
    rows = read_csv("e7_storage.csv")
    by_workload: dict[str, list[dict]] = {}
    for r in rows:
        by_workload.setdefault(r["workload"], []).append(r)
    lines = [
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        r"Workload & JSONL & Parquet & Arrays & Parquet/JSONL \\",
        r"\midrule",
    ]

    def kb(n: float) -> str:
        return f"{n / 1024:,.0f}\\,KiB" if n < 1024 ** 2 \
            else f"{n / 1024 ** 2:,.1f}\\,MiB"

    for w, group in by_workload.items():
        j = sum(int(r["jsonl_bytes"]) for r in group) / len(group)
        p = sum(int(r["parquet_bytes"]) for r in group) / len(group)
        a = sum(int(r["arrays_bytes"]) for r in group) / len(group)
        lines.append(
            f"{esc(w)} & {kb(j)} & {kb(p)} & {kb(a)} & "
            f"{p / j:.2f}$\\times$ \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}"]
    write_table("storage", lines)


def macros() -> None:
    """Headline numbers referenced from prose, as LaTeX macros."""
    e1 = read_csv("e1_gallery.csv")
    e2 = {(r["workload"], r["tier"]): r for r in read_csv("e2_overhead.csv")}
    e5 = read_csv("e5_basis.csv")
    ci = json.loads((PAPER / "results" / "e6_ci.json").read_text())
    crash = json.loads((PAPER / "results" / "e7_crash.json").read_text())
    e7 = read_csv("e7_storage.csv")
    heavy = [r for r in e7 if "loop" in r["workload"]]
    jsonl = sum(int(r["jsonl_bytes"]) for r in heavy) / len(heavy)
    parquet = sum(int(r["parquet_bytes"]) for r in heavy) / len(heavy)

    perm = next(r for r in e5 if r["function"] == "permuted_pipeline")
    n_detected = sum(r["detected"] == "True" for r in e1)

    def m(name: str, value) -> str:
        return f"\\newcommand{{\\{name}}}{{{value}}}"

    lines = [
        m("nPathologies", len(e1)),
        m("nDetected", n_detected),
        m("ovTinyT1", e2[("20k tiny numpy.sum calls", "T1")]["overhead_x"]),
        m("ovLargeT1", e2[("2M-element numpy.sum calls", "T1")]["overhead_x"]),
        m("ovTinyT2", e2[("20k tiny numpy.sum calls", "T2")]["overhead_x"]),
        m("ovTaint", e2[("operator loop (x*a+b)", "T3")]["overhead_x"]),
        m("ovMonitor", e2[("end-to-end simple_numpy.py", "T4")]["overhead_x"]),
        m("permSummaryBits", perm["summary_sig_bits"]),
        m("permElementBits", perm["element_sig_bits"]),
        m("permOptimismBits", perm["proxy_optimism_bits"]),
        m("checkExit", ci["check_exit_code"]),
        m("diffExit", ci["diff_exit_code"]),
        m("crashKilled", len(crash["runs_killed"])),
        m("crashRunsRecovered", crash["alignment_runs"]),
        m("parquetRatio", f"{jsonl / parquet:.0f}"),
    ]
    write_table("macros", lines)


def main() -> int:
    t_gallery()
    t_overhead()
    t_coverage()
    t_alignment()
    t_basis()
    t_case()
    t_v1_matrix()
    t_storage()
    macros()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
