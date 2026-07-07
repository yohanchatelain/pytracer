"""pytracer diff — compare two experiments function-by-function.

The A/B use case: same script traced before and after a library upgrade,
compiler-flag change, or refactor. Reports significance and divergence
deltas, plus functions that appeared or disappeared.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pytracer.analysis.check import load_function_summary


@dataclass(slots=True)
class DiffRow:
    function: str
    sig_a: float | None
    sig_b: float | None
    sig_delta: float | None  # positive = B more stable
    divergence_a: float
    divergence_b: float

    def regressed(self, tolerance_bits: float) -> bool:
        if self.sig_a is not None and self.sig_b is not None:
            if self.sig_b < self.sig_a - tolerance_bits:
                return True
        return self.divergence_b > self.divergence_a + 1e-12


@dataclass(slots=True)
class DiffResult:
    rows: list[DiffRow]
    only_in_a: list[str]
    only_in_b: list[str]

    def regressions(self, tolerance_bits: float = 1.0) -> list[DiffRow]:
        return [r for r in self.rows if r.regressed(tolerance_bits)]


def diff_experiments(dir_a: str | Path, dir_b: str | Path) -> DiffResult:
    a = {r["function"]: r for r in load_function_summary(dir_a)}
    b = {r["function"]: r for r in load_function_summary(dir_b)}
    rows = []
    for function in sorted(set(a) & set(b)):
        ra, rb = a[function], b[function]
        sig_a = ra.get("min_output_sig_bits")
        sig_b = rb.get("min_output_sig_bits")
        delta = sig_b - sig_a if sig_a is not None and sig_b is not None else None
        rows.append(
            DiffRow(
                function=function,
                sig_a=sig_a,
                sig_b=sig_b,
                sig_delta=delta,
                divergence_a=ra.get("divergence_score", 0.0),
                divergence_b=rb.get("divergence_score", 0.0),
            )
        )
    return DiffResult(
        rows=rows,
        only_in_a=sorted(set(a) - set(b)),
        only_in_b=sorted(set(b) - set(a)),
    )


def format_diff(result: DiffResult, tolerance_bits: float = 1.0) -> str:
    lines = []
    header = f"{'function':<44s} {'sig A':>7s} {'sig B':>7s} {'delta':>7s}  note"
    lines.append(header)
    lines.append("-" * len(header))

    def fmt(v):
        return f"{v:7.1f}" if v is not None else "      -"

    for row in result.rows:
        note = ""
        if row.regressed(tolerance_bits):
            note = "REGRESSION"
        elif row.sig_delta is not None and row.sig_delta > tolerance_bits:
            note = "improved"
        if row.divergence_b != row.divergence_a:
            note = (note + " divergence-change").strip()
        lines.append(
            f"{row.function:<44s} {fmt(row.sig_a)} {fmt(row.sig_b)} "
            f"{fmt(row.sig_delta)}  {note}"
        )
    for name in result.only_in_a:
        lines.append(f"{name:<44s} only in A (call disappeared in B)")
    for name in result.only_in_b:
        lines.append(f"{name:<44s} only in B (new call)")
    return "\n".join(lines)
