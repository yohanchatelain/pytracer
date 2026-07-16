"""E5 — sig(mean) summary proxy vs element-wise significant digits.

Every workload is traced twice with identical settings except
--store-arrays: `never` forces the summary basis (sig of the cross-run
mean), `always` enables the element-wise basis. Comparing the two per
function measures how optimistic the proxy is. The permuted-output
workload is the adversarial headline case; the gallery scripts populate
the scatter with realistic points.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from common import (
    EXAMPLES,
    function_summary,
    latest_experiment,
    main_guard,
    run_pytracer,
    scratch_with,
    write_csv,
)

WORKLOADS = Path(__file__).resolve().parent / "workloads"

CASES = [
    ("permuted output", WORKLOADS / "permuted_output.py", ["--plugins"]),
    ("cancellation", EXAMPLES / "cancellation.py", ["--plugins"]),
    ("summation order", EXAMPLES / "summation_order.py", ["--plugins"]),
    ("ill-conditioned solve", EXAMPLES / "ill_conditioned_solve.py", ["--plugins"]),
    ("finite differences", EXAMPLES / "finite_differences.py", ["--plugins"]),
]

REPEAT = 5


def sig_by_basis(script: Path, extra: list[str], store: str) -> dict[str, dict]:
    workdir = scratch_with(script)
    run_pytracer(["run", script.name, "--repeat", str(REPEAT), *extra,
                  "--store-arrays", store, "--no-report"], cwd=workdir)
    exp = latest_experiment(workdir)
    run_pytracer(["analyze", str(exp)], cwd=workdir)
    funcs = function_summary(exp)
    shutil.rmtree(workdir)
    return funcs


def run() -> int:
    rows = []
    for wname, script, extra in CASES:
        summary = sig_by_basis(script, extra, "never")
        element = sig_by_basis(script, extra, "always")
        for fn in sorted(set(summary) & set(element)):
            s, e = summary[fn], element[fn]
            if s["min_output_sig_bits"] is None or e["min_output_sig_bits"] is None:
                continue
            rows.append({
                "workload": wname,
                "function": fn.removeprefix("__main__."),
                "summary_sig_bits": round(s["min_output_sig_bits"], 2),
                "element_sig_bits": round(e["min_output_sig_bits"], 2),
                "proxy_optimism_bits": round(
                    s["min_output_sig_bits"] - e["min_output_sig_bits"], 2),
                "summary_basis": s["sig_basis"],
                "element_basis": e["sig_basis"],
            })
    write_csv("e5_basis.csv", rows)
    worst = max(rows, key=lambda r: r["proxy_optimism_bits"])
    print(f"largest proxy optimism: {worst['function']} "
          f"({worst['workload']}): summary {worst['summary_sig_bits']} bits "
          f"vs element {worst['element_sig_bits']} bits")
    return 0


if __name__ == "__main__":
    main_guard(run)
