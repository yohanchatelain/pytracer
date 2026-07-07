"""Aggregate aligned calls into per-function/per-argument stability metrics.

Two metric bases, never conflated (plan §3.1):

- ``sig_basis = "summary"``: `sig(mean)` — cross-run stability of each
  argument's mean summary statistic, in bits. Cheap, always available, and
  an *optimistic proxy*: element permutations across runs are invisible to
  it.
- ``sig_basis = "element"``: element-wise significant digits computed from
  arrays stored during capture (``store_arrays``). The real measurement;
  used whenever every run stored the argument's payload.

Amplification (plan §3.2): per aligned call,
    amplification = min sig(inputs) − min sig(outputs)
i.e. how many bits of precision this call destroyed. Functions are ranked
by amplification first — separating *sources* of instability from victims
of already-noisy inputs.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pytracer.analysis.align import Alignment
from pytracer.analysis.elementwise import elementwise_sig, stack_arrays
from pytracer.storage.arrays import load_array

SIG_CAP_BITS = 53.0  # float64 mantissa; "std == 0" means indistinguishable-from-exact


def sig_bits(values: list[float]) -> float | None:
    """Cross-run significance of a statistic, in bits: -log2(std/|mean|)."""
    clean = [v for v in values if v is not None and math.isfinite(v)]
    if len(clean) < 2:
        return None
    n = len(clean)
    mean = sum(clean) / n
    var = sum((v - mean) ** 2 for v in clean) / n
    std = math.sqrt(var)
    if std == 0.0:
        return SIG_CAP_BITS
    if mean == 0.0:
        return 0.0
    return max(0.0, min(SIG_CAP_BITS, -math.log2(std / abs(mean))))


@dataclass(slots=True)
class ArgumentRow:
    function: str
    arg_name: str
    phase: str  # "input" | "output"
    n_runs: int
    n_call_groups: int
    sig_basis: str  # "element" | "summary"
    sig_mean_bits: float | None  # summary-basis proxy (always computed)
    sig_min_bits: float | None = None  # element basis only
    sig_p05_bits: float | None = None
    sig_median_bits: float | None = None
    mean_of_means: float | None = None
    std_of_means: float | None = None
    nan_instability: bool = False
    inf_instability: bool = False


@dataclass(slots=True)
class FunctionRow:
    function: str
    n_call_groups: int
    n_matched: int
    divergence_score: float
    min_output_sig_bits: float | None
    median_output_sig_bits: float | None
    max_amplification_bits: float | None
    mean_amplification_bits: float | None
    nan_instability: bool
    inf_instability: bool
    sig_basis: str = "summary"
    tiers: list[str] = field(default_factory=list)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


@dataclass(slots=True)
class AggregationResult:
    functions: list[FunctionRow]
    arguments: list[ArgumentRow]

    def top_unstable(self, k: int = 10) -> list[FunctionRow]:
        def sort_key(row: FunctionRow):
            amp = row.max_amplification_bits
            sig = row.min_output_sig_bits
            return (
                -(amp if amp is not None else -math.inf),
                sig if sig is not None else math.inf,
                -row.divergence_score,
            )

        interesting = [
            r
            for r in self.functions
            if r.divergence_score > 0
            or (r.max_amplification_bits or 0) > 0
            or (r.min_output_sig_bits is not None and r.min_output_sig_bits < SIG_CAP_BITS)
            or r.nan_instability
            or r.inf_instability
        ]
        pool = interesting if interesting else self.functions
        return sorted(pool, key=sort_key)[:k]


def _element_sig_for_arg(
    calls: list, phase: str, arg_name: str, run_dirs: list[Path] | None
) -> dict | None:
    """Element-wise sig distribution when every run stored this argument."""
    if run_dirs is None:
        return None
    refs = [
        (c.input_refs if phase == "input" else c.output_refs).get(arg_name) for c in calls
    ]
    if any(r is None for r in refs):
        return None
    arrays = [load_array(d, r) for d, r in zip(run_dirs, refs, strict=True)]
    stack = stack_arrays(arrays)
    if stack is None:
        return None
    return elementwise_sig(stack)


def aggregate(alignment: Alignment, run_dirs: list[Path] | None = None) -> AggregationResult:
    n_runs = len(alignment.run_ids)
    per_function: dict[str, dict] = {}
    per_argument: dict[tuple[str, str, str], dict] = {}

    for group in alignment.groups:
        function = group.function
        f = per_function.setdefault(
            function,
            {
                "groups": 0,
                "matched": 0,
                "output_sigs": [],
                "amplifications": [],
                "nan": False,
                "inf": False,
                "tiers": set(),
                "element_based": False,
            },
        )
        f["groups"] += 1
        if not group.complete:
            continue
        f["matched"] += 1
        calls = [c for c in group.calls if c is not None]
        f["tiers"].update(c.tier for c in calls)

        input_sigs: list[float] = []
        output_sigs: list[float] = []
        for phase, get_args in (("input", lambda c: c.inputs), ("output", lambda c: c.outputs)):
            arg_names = set()
            for c in calls:
                arg_names.update(get_args(c))
            for arg_name in arg_names:
                summaries = [get_args(c).get(arg_name) for c in calls]
                if any(s is None for s in summaries):
                    continue
                means = [s.mean for s in summaries]
                proxy_sig = sig_bits(means)
                element = _element_sig_for_arg(calls, phase, arg_name, run_dirs)
                sig = element["min"] if element is not None else proxy_sig
                if element is not None:
                    f["element_based"] = True

                nan_var = len({s.nan_count for s in summaries}) > 1
                inf_var = len({s.inf_count for s in summaries}) > 1
                f["nan"] |= nan_var
                f["inf"] |= inf_var
                if sig is not None:
                    (input_sigs if phase == "input" else output_sigs).append(sig)

                a = per_argument.setdefault(
                    (function, arg_name, phase),
                    {
                        "groups": 0,
                        "sigs": [],
                        "proxy_sigs": [],
                        "p05s": [],
                        "medians": [],
                        "means": [],
                        "basis": "summary",
                        "nan": False,
                        "inf": False,
                    },
                )
                a["groups"] += 1
                if sig is not None:
                    a["sigs"].append(sig)
                if proxy_sig is not None:
                    a["proxy_sigs"].append(proxy_sig)
                if element is not None:
                    a["basis"] = "element"
                    a["p05s"].append(element["p05"])
                    a["medians"].append(element["median"])
                clean = [m for m in means if m is not None and math.isfinite(m)]
                if clean:
                    a["means"].append(sum(clean) / len(clean))
                a["nan"] |= nan_var
                a["inf"] |= inf_var

        if output_sigs:
            f["output_sigs"].append(min(output_sigs))
            if input_sigs:
                f["amplifications"].append(min(input_sigs) - min(output_sigs))

    function_rows = []
    for function, f in sorted(per_function.items()):
        amps = f["amplifications"]
        function_rows.append(
            FunctionRow(
                function=function,
                n_call_groups=f["groups"],
                n_matched=f["matched"],
                divergence_score=(f["groups"] - f["matched"]) / f["groups"],
                min_output_sig_bits=min(f["output_sigs"]) if f["output_sigs"] else None,
                median_output_sig_bits=_median(f["output_sigs"]),
                max_amplification_bits=max(amps) if amps else None,
                mean_amplification_bits=(sum(amps) / len(amps)) if amps else None,
                nan_instability=f["nan"],
                inf_instability=f["inf"],
                sig_basis="element" if f["element_based"] else "summary",
                tiers=sorted(f["tiers"]),
            )
        )

    argument_rows = []
    for (function, arg_name, phase), a in sorted(per_argument.items()):
        mom = sum(a["means"]) / len(a["means"]) if a["means"] else None
        if a["means"] and len(a["means"]) > 1:
            mu = mom
            som = math.sqrt(sum((m - mu) ** 2 for m in a["means"]) / len(a["means"]))
        else:
            som = None
        is_element = a["basis"] == "element"
        argument_rows.append(
            ArgumentRow(
                function=function,
                arg_name=arg_name,
                phase=phase,
                n_runs=n_runs,
                n_call_groups=a["groups"],
                sig_basis=a["basis"],
                sig_mean_bits=min(a["proxy_sigs"]) if a["proxy_sigs"] else None,
                sig_min_bits=min(a["sigs"]) if is_element and a["sigs"] else None,
                sig_p05_bits=min(a["p05s"]) if is_element and a["p05s"] else None,
                sig_median_bits=_median(a["medians"]) if is_element else None,
                mean_of_means=mom,
                std_of_means=som,
                nan_instability=a["nan"],
                inf_instability=a["inf"],
            )
        )

    return AggregationResult(functions=function_rows, arguments=argument_rows)


def write_aggregation(experiment_dir: str | Path, result: AggregationResult) -> None:
    analysis_dir = Path(experiment_dir) / "analysis"
    analysis_dir.mkdir(exist_ok=True)
    (analysis_dir / "function_summary.json").write_text(
        json.dumps([asdict(r) for r in result.functions], indent=2)
    )
    (analysis_dir / "argument_summary.json").write_text(
        json.dumps([asdict(r) for r in result.arguments], indent=2)
    )
    (analysis_dir / "top_unstable.json").write_text(
        json.dumps([asdict(r) for r in result.top_unstable()], indent=2)
    )
