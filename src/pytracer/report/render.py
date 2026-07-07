"""Render report data to Markdown, HTML, JSON, and the terminal summary.

All significance values are `sig(mean)` in bits — the cross-run stability of
summary statistics, an optimistic proxy for element-wise significant digits
(see the plan, §3.1). Reports say so explicitly.
"""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment

_SIG_NOTE_SUMMARY = (
    "Significance values are `sig(mean)` in bits: the cross-run stability of each "
    "argument's mean, capped at 53. This is an optimistic proxy for element-wise "
    "significant digits, which require stored arrays (not enabled in this run)."
)
_SIG_NOTE_ELEMENT = (
    "Significance values are element-wise significant digits in bits (relative-std "
    "estimator, capped at 53), computed from arrays stored during capture. Rows "
    "with basis `summary` fall back to the `sig(mean)` proxy for that argument."
)


def _fmt(value, digits=1) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_markdown(data: dict) -> str:
    a = data.get("alignment", {})
    cov = data.get("coverage", {})
    exp = data.get("experiment", {})
    lines: list[str] = []
    add = lines.append

    add("# Pytracer report")
    add("")
    add("## Summary")
    add("")
    add(f"- Script: `{exp.get('script', '?')}`")
    add(f"- Runs: {a.get('runs', '?')}")
    add(f"- Instrumentation: {exp.get('instrumentation', '?')}")
    add(f"- Call groups: {a.get('total_call_groups', 0)} "
        f"(matched: {a.get('matched_call_groups', 0)}, "
        f"divergent: {a.get('divergent_call_groups', 0)})")
    if a.get("truncated_runs"):
        add(f"- **Truncated runs**: {', '.join(a['truncated_runs'])}")
    add("")
    any_element = any(f.get("sig_basis") == "element" for f in data.get("functions", []))
    add(f"> {_SIG_NOTE_ELEMENT if any_element else _SIG_NOTE_SUMMARY}")
    add("")

    add("## Coverage: what was observed")
    add("")
    tiers = cov.get("calls_per_tier", {})
    add(f"- Traced calls per tier: {tiers if tiers else 'none'}")
    add(f"- Monitor (T4) available: {cov.get('monitor_available', False)}")
    untraced = cov.get("untraced_numerical_callables", [])
    if untraced:
        add("")
        add("Untraced numerical callables observed by the monitor "
            "(candidates for `--target`):")
        add("")
        add("| Function | Calls |")
        add("|---|---|")
        for entry in untraced[:15]:
            add(f"| `{entry['function']}` | {entry['calls']} |")
    for note in cov.get("notes", []):
        add(f"- {note}")
    add("")

    add("## Top unstable functions")
    add("")
    top = data.get("top_unstable", [])
    if top:
        add("| Function | min sig (bits) | basis | max amplification (bits) "
            "| divergence | NaN | Inf |")
        add("|---|---|---|---|---|---|---|")
        for row in top:
            add(
                f"| `{row['function']}` | {_fmt(row['min_output_sig_bits'])} "
                f"| {row.get('sig_basis', 'summary')} "
                f"| {_fmt(row['max_amplification_bits'])} "
                f"| {_fmt(row['divergence_score'], 3)} "
                f"| {'yes' if row['nan_instability'] else '-'} "
                f"| {'yes' if row['inf_instability'] else '-'} |"
            )
    else:
        add("No traced calls were aggregated.")
    add("")

    div = a.get("divergent_calls", [])
    add("## Control-flow divergence")
    add("")
    if div:
        add("| Function | Divergence score | Missing in runs |")
        add("|---|---|---|")
        for entry in div:
            add(
                f"| `{entry['function']}` | {_fmt(entry['divergence_score'], 3)} "
                f"| {', '.join(entry['missing_in_runs'])} |"
            )
    else:
        add("None: all runs executed the same traced calls.")
    add("")

    add("## Reproducibility")
    add("")
    runs = data.get("runs", [])
    if runs:
        first = runs[0]
        add(f"- Python: {first.get('python_version', '?')}")
        add(f"- Platform: {first.get('platform', '?')}")
        add(f"- Packages: {first.get('packages', {})}")
        add(f"- Environment (allowlisted): {first.get('environment', {})}")
    add("")
    return "\n".join(lines)


_HTML_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Pytracer report</title>
<style>
body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 60rem;
       line-height: 1.5; color: #1a1a1a; }
table { border-collapse: collapse; width: 100%; margin: 0.5rem 0 1.5rem; }
th, td { border: 1px solid #ccc; padding: 0.3rem 0.6rem; text-align: left; }
th { background: #f0f0f0; }
code { background: #f5f5f5; padding: 0.1rem 0.3rem; border-radius: 3px; }
blockquote { border-left: 3px solid #999; margin: 1rem 0; padding: 0.2rem 1rem;
             color: #555; background: #fafafa; }
@media (prefers-color-scheme: dark) {
  body { background: #16181d; color: #dcdfe4; }
  th { background: #23262d; } th, td { border-color: #3a3f4a; }
  code, blockquote { background: #1e2128; color: #c8ccd4; }
}
</style></head><body>
<pre style="white-space: pre-wrap; font-family: inherit;">{{ markdown }}</pre>
</body></html>
"""


def render_html(data: dict) -> str:
    env = Environment(autoescape=True)
    template = env.from_string(_HTML_TEMPLATE)
    return template.render(markdown=render_markdown(data))


def render_json(data: dict) -> str:
    return json.dumps(data, indent=2)


def write_reports(experiment_dir: str | Path, data: dict, formats: list[str]) -> list[Path]:
    report_dir = Path(experiment_dir) / "report"
    report_dir.mkdir(exist_ok=True)
    written = []
    if "markdown" in formats:
        path = report_dir / "report.md"
        path.write_text(render_markdown(data))
        written.append(path)
    if "html" in formats:
        path = report_dir / "report.html"
        path.write_text(render_html(data))
        written.append(path)
    if "json" in formats:
        path = report_dir / "report.json"
        path.write_text(render_json(data))
        written.append(path)
    return written


def terminal_summary(data: dict) -> str:
    a = data.get("alignment", {})
    lines = [
        "Pytracer run complete",
        f"Runs: {a.get('runs', '?')}",
        f"Call groups: {a.get('total_call_groups', 0)} "
        f"(matched: {a.get('matched_call_groups', 0)}, "
        f"divergent: {a.get('divergent_call_groups', 0)})",
    ]
    top = data.get("top_unstable", [])
    if top:
        lines.append("Top functions (sig(mean) bits | amplification bits | divergence):")
        for i, row in enumerate(top[:5], start=1):
            lines.append(
                f"{i}. {row['function']:<40s} "
                f"sig: {_fmt(row['min_output_sig_bits']):>5s}  "
                f"amp: {_fmt(row['max_amplification_bits']):>5s}  "
                f"div: {_fmt(row['divergence_score'], 3)}"
            )
    return "\n".join(lines)
