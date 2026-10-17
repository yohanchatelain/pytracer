# Pytracer Documentation

Welcome to the Pytracer 2 documentation. These guides are designed for both **human engineers** and **AI coding agents**.

## Table of Contents

| Guide | Audience | Contents |
|---|---|---|
| **[CLI & Configuration Reference](cli-and-config.md)** | Humans & Agents | All 13 CLI subcommands, flags, `pytracer.toml` schema, `pytracer-thresholds.toml`, and stochastic arithmetic backend setup (Verificarlo, Verrou). |
| **[Architecture & Metrics](architecture-and-metrics.md)** | Humans & Agents | Subprocess execution pipeline, 5-tier instrumentation stack (`T1`–`T5`), `@pytracer.trace_function` & `pytracer.taint` APIs, call alignment (`strict`, `callsite`, `fuzzy` LCS), significant bits, amplification bits, and coverage blind spots. |
| **[Agent & Data Format Guide](agent-and-data-guide.md)** | AI Agents & CI | Non-interactive diagnostic & remediation workflow, CLI exit codes, `.pytracer/runs/<id>/` directory layout, and JSON/Parquet schemas (`function_summary.json`, `argument_summary.json`, `top_unstable.json`, `events.parquet`). |
| **[Interactive Dashboard](dashboard.md)** | Humans | Dash/Plotly web UI (`pytracer dashboard`), Overview, Explorer, Call Graph, Timeline, Coverage, Runs tabs, and `--compare` A/B mode. |
| **[Examples Gallery](../examples/README.md)** | Humans & Agents | Paired unstable vs. stable implementations of classical numerical pathologies (catastrophic cancellation, quadratic roots, Hilbert solve, summation order, finite differences). |
| **[Verificarlo MCA Workflow](../examples/verificarlo/README.md)** | Humans & Agents | Running Pytracer inside `verificarlo/fuzzy` Monte Carlo Arithmetic containers. |
