"""Pytracer CLI. The only place in the codebase allowed to call sys.exit."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from pytracer import __version__
from pytracer._errors import PytracerError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pytracer",
        description="Numerical variability profiler for Python scientific programs",
    )
    parser.add_argument("--version", action="version", version=f"pytracer {__version__}")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="write a default pytracer.toml")
    p_init.add_argument("--force", action="store_true", help="overwrite an existing file")

    p_run = sub.add_parser(
        "run", help="trace a script over repeated runs, analyze, and report"
    )
    p_run.add_argument("script", help="Python script to trace")
    p_run.add_argument("--repeat", type=int, default=1, help="number of independent runs")
    p_run.add_argument(
        "--target", action="append", default=[], metavar="PATH",
        help="extra target (repeatable), e.g. numpy.linalg.solve or numpy.linalg.*",
    )
    p_run.add_argument("--plugins", nargs="*", default=None, help="plugins to enable")
    p_run.add_argument(
        "--instrument", choices=["hybrid", "patch", "monitor", "taint"], default=None,
        help="instrumentation tiers (default: hybrid; taint adds T3 tracer arrays)",
    )
    p_run.add_argument("--alignment", choices=["strict", "callsite", "fuzzy"], default=None)
    p_run.add_argument("--output-dir", default=None)
    p_run.add_argument(
        "--store-arrays", choices=["auto", "always", "never"], default=None,
        help="store array payloads for element-wise significant digits "
        "(default from config: auto)",
    )
    p_run.add_argument(
        "--native", action="store_true",
        help="enable the native BLAS kernel census (T5; Linux + C compiler)",
    )
    p_run.add_argument("--continue-on-error", action="store_true")
    p_run.add_argument("--no-report", action="store_true", help="skip analysis and report")
    # Script arguments are passed after a literal `--`; they are split off
    # before parsing (argparse.REMAINDER would swallow pytracer's own options).

    p_analyze = sub.add_parser("analyze", help="align and aggregate an experiment")
    p_analyze.add_argument("experiment_dir")
    p_analyze.add_argument("--alignment", choices=["strict", "callsite", "fuzzy"],
                           default="callsite")

    p_report = sub.add_parser("report", help="generate reports for an analyzed experiment")
    p_report.add_argument("experiment_dir")
    p_report.add_argument("--formats", nargs="*", default=None,
                          choices=["markdown", "html", "json"])

    p_config = sub.add_parser("config", help="show or validate configuration")
    p_config.add_argument("action", choices=["show", "validate"])

    p_plugins = sub.add_parser("plugins", help="list plugins or their targets")
    p_plugins.add_argument("action", choices=["list", "targets"])
    p_plugins.add_argument("name", nargs="?", help="plugin name (for targets)")

    sub.add_parser("doctor", help="check the environment and configuration")

    p_clean = sub.add_parser("clean", help="delete pytracer experiment directories")
    p_clean.add_argument("--output-dir", default=None)

    p_check = sub.add_parser(
        "check", help="gate on stability thresholds (nonzero exit on violation)"
    )
    p_check.add_argument("experiment_dir")
    p_check.add_argument("--min-sig-bits", type=float, default=None)
    p_check.add_argument("--max-divergence", type=float, default=None)
    p_check.add_argument("--no-nan", action="store_true", help="fail on NaN instability")
    p_check.add_argument("--no-inf", action="store_true", help="fail on Inf instability")
    p_check.add_argument(
        "--thresholds", default=None, metavar="FILE",
        help="thresholds TOML (default: ./pytracer-thresholds.toml when present)",
    )

    p_diff = sub.add_parser("diff", help="compare two experiments (A/B)")
    p_diff.add_argument("experiment_a")
    p_diff.add_argument("experiment_b")
    p_diff.add_argument(
        "--tolerance-bits", type=float, default=1.0,
        help="sig drop considered a regression (default 1.0)",
    )
    p_diff.add_argument(
        "--fail-on-regression", action="store_true",
        help="exit nonzero when regressions are found",
    )

    p_suggest = sub.add_parser(
        "suggest-targets", help="suggest --target entries from the monitor census"
    )
    p_suggest.add_argument("experiment_dir")
    p_suggest.add_argument("--top", type=int, default=15)

    return parser


def _load_config():
    from pytracer.config.loader import load_config

    return load_config()


def cmd_init(args) -> int:
    from pytracer.config.loader import write_default_config

    path = write_default_config(force=args.force)
    print(f"wrote {path}")
    return 0


def cmd_run(args) -> int:
    from pytracer.analysis import analyze_experiment
    from pytracer.experiment import run_experiment
    from pytracer.plugins.registry import targets_for
    from pytracer.report.model import build_report_data
    from pytracer.report.render import terminal_summary, write_reports

    config = _load_config()
    if args.plugins is not None:
        config.trace.plugins = args.plugins
    if args.target:
        config.trace.targets = config.trace.targets + args.target
    if args.instrument:
        config.trace.instrumentation = args.instrument
    if args.alignment:
        config.analysis.alignment = args.alignment
    if args.output_dir:
        config.storage.output_dir = args.output_dir
    if args.store_arrays:
        config.trace.store_arrays = args.store_arrays
    if args.native:
        config.trace.native_census = True
    config.validate()

    script_args = args.script_args

    specs, warnings = targets_for(config.trace.plugins, config.trace.targets)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if not specs and config.trace.instrumentation != "monitor":
        print(
            "warning: no targets resolved (no plugins available and no --target); "
            "only the monitor tier will observe anything",
            file=sys.stderr,
        )

    result = run_experiment(
        config=config,
        script=args.script,
        script_args=script_args,
        target_specs=specs,
        repeat=args.repeat,
        continue_on_error=args.continue_on_error,
    )
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    status = max((r.exit_code for r in result.runs), default=0)

    completed = [r for r in result.runs if r.exit_code == 0]
    if args.no_report or not completed:
        if not completed:
            print("error: no run completed successfully; skipping analysis", file=sys.stderr)
        print(f"Experiment: {result.experiment_dir}")
        return status or (1 if not completed else 0)

    analyze_experiment(
        result.experiment_dir,
        alignment_mode=config.analysis.alignment,
        target_specs=specs,
    )
    data = build_report_data(result.experiment_dir)
    written = write_reports(result.experiment_dir, data, config.report.formats)
    print(terminal_summary(data))
    for path in written:
        print(f"Report: {path}")
    return status


def cmd_analyze(args) -> int:
    from pytracer.analysis import analyze_experiment

    alignment, aggregation, _coverage = analyze_experiment(
        args.experiment_dir, alignment_mode=args.alignment
    )
    summary = alignment.summary_dict()
    print(
        f"aligned {summary['matched_call_groups']}/{summary['total_call_groups']} "
        f"call groups across {summary['runs']} runs "
        f"({summary['divergent_call_groups']} divergent)"
    )
    return 0


def cmd_report(args) -> int:
    from pytracer.report.model import build_report_data
    from pytracer.report.render import terminal_summary, write_reports

    config = _load_config()
    formats = args.formats or config.report.formats
    data = build_report_data(args.experiment_dir)
    written = write_reports(args.experiment_dir, data, formats)
    print(terminal_summary(data))
    for path in written:
        print(f"Report: {path}")
    return 0


def cmd_config(args) -> int:
    config = _load_config()
    if args.action == "show":
        print(json.dumps(config.to_dict(), indent=2))
    else:
        config.validate()
        print("configuration is valid")
    return 0


def cmd_plugins(args) -> int:
    from pytracer.plugins.registry import available_plugins, get_plugin

    if args.action == "list":
        for name in available_plugins():
            plugin = get_plugin(name)
            status = "available" if plugin.available() else f"({plugin.requires} not installed)"
            print(f"{name:<10s} {status}")
        return 0
    if not args.name:
        print("usage: pytracer plugins targets <name>", file=sys.stderr)
        return 2
    plugin = get_plugin(args.name)
    for target in plugin.targets:
        print(f"{target.import_path:<50s} [{target.kind}]")
    return 0


def cmd_doctor(_args) -> int:
    from pytracer.cli.doctor import exit_code, format_checks, run_checks

    checks = run_checks()
    print("Pytracer doctor")
    print(format_checks(checks))
    return exit_code(checks)


def cmd_clean(args) -> int:
    from pytracer.experiment import find_experiments

    config = _load_config()
    output_dir = Path(args.output_dir or config.storage.output_dir)
    experiments = find_experiments(output_dir)
    for experiment in experiments:
        shutil.rmtree(experiment)
        print(f"removed {experiment}")
    latest = output_dir / "latest"
    if latest.is_symlink():
        latest.unlink()
    if not experiments:
        print(f"nothing to clean in {output_dir}")
    return 0


def cmd_check(args) -> int:
    from pytracer.analysis.check import (
        THRESHOLDS_FILENAME,
        Thresholds,
        check_experiment,
        load_thresholds_file,
    )

    thresholds = Thresholds()
    thresholds_path = args.thresholds
    if thresholds_path is None and Path(THRESHOLDS_FILENAME).is_file():
        thresholds_path = THRESHOLDS_FILENAME
    if thresholds_path is not None:
        thresholds = load_thresholds_file(thresholds_path)
    if args.min_sig_bits is not None:
        thresholds.min_sig_bits = args.min_sig_bits
    if args.max_divergence is not None:
        thresholds.max_divergence = args.max_divergence
    if args.no_nan:
        thresholds.allow_nan = False
    if args.no_inf:
        thresholds.allow_inf = False

    if (
        thresholds.min_sig_bits is None
        and thresholds.max_divergence is None
        and thresholds.allow_nan
        and thresholds.allow_inf
        and not thresholds.per_function
    ):
        print(
            "error: no thresholds given (use --min-sig-bits/--max-divergence/"
            f"--no-nan/--no-inf or a {THRESHOLDS_FILENAME})",
            file=sys.stderr,
        )
        return 2

    violations = check_experiment(args.experiment_dir, thresholds)
    if violations:
        print(f"FAIL: {len(violations)} stability violation(s)")
        for violation in violations:
            print(f"  - {violation}")
        return 1
    print("PASS: all stability thresholds satisfied")
    return 0


def cmd_diff(args) -> int:
    from pytracer.analysis.diff import diff_experiments, format_diff

    result = diff_experiments(args.experiment_a, args.experiment_b)
    print(format_diff(result, tolerance_bits=args.tolerance_bits))
    regressions = result.regressions(args.tolerance_bits)
    if regressions:
        print(f"\n{len(regressions)} regression(s) beyond {args.tolerance_bits} bits")
        if args.fail_on_regression:
            return 1
    else:
        print("\nno regressions")
    return 0


def cmd_suggest_targets(args) -> int:
    coverage_path = Path(args.experiment_dir) / "analysis" / "coverage.json"
    if not coverage_path.is_file():
        print(
            f"error: {coverage_path} not found (run `pytracer analyze` first)",
            file=sys.stderr,
        )
        return 1
    coverage = json.loads(coverage_path.read_text())
    untraced = coverage.get("untraced_numerical_callables", [])[: args.top]
    if not coverage.get("monitor_available", False):
        print(
            "monitor (T4) was not available for this experiment; "
            "no census to suggest from",
            file=sys.stderr,
        )
        return 1
    if not untraced:
        print("no untraced numerical callables observed — coverage looks complete")
        return 0
    print("# Untraced numerical callables observed by the monitor.")
    print("# Add to pytracer.toml, or pass as --target flags:")
    print("[trace]")
    targets = ", ".join(f'"{entry["function"]}"' for entry in untraced)
    print(f"targets = [{targets}]")
    print()
    for entry in untraced:
        print(f"# {entry['function']:<44s} {entry['calls']} call(s)")
    return 0


_COMMANDS = {
    "init": cmd_init,
    "run": cmd_run,
    "analyze": cmd_analyze,
    "report": cmd_report,
    "config": cmd_config,
    "plugins": cmd_plugins,
    "doctor": cmd_doctor,
    "clean": cmd_clean,
    "check": cmd_check,
    "diff": cmd_diff,
    "suggest-targets": cmd_suggest_targets,
}


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    script_args: list[str] = []
    if "--" in argv:
        split = argv.index("--")
        argv, script_args = argv[:split], argv[split + 1 :]
    parser = build_parser()
    args = parser.parse_args(argv)
    args.script_args = script_args
    if not args.command:
        parser.print_help()
        return 0
    try:
        return _COMMANDS[args.command](args)
    except PytracerError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
