"""E7 — Storage footprint and crash-safety.

Footprint: per-run bytes of the append-only JSON-lines capture vs the
finalized Parquet, and the compressed array-payload store, measured on a
gallery workload with full array storage.

Crash-safety: a workload that SIGKILLs itself (no cleanup) on runs 4-6 of
--repeat 6. With --continue-on-error the experiment completes, and
analysis runs on the surviving runs; the killed runs still leave their
append-only JSONL behind.
"""

from __future__ import annotations

from pathlib import Path

from common import (
    EXAMPLES,
    latest_experiment,
    load_analysis,
    main_guard,
    run_pytracer,
    scratch_with,
    write_csv,
)

WORKLOADS = Path(__file__).resolve().parent / "workloads"


def du(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    if path.is_dir():
        return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    return 0


def run() -> int:
    rows = []

    # -- footprint --------------------------------------------------------
    for wname, script in [
        ("linear solve (few calls)", EXAMPLES / "ill_conditioned_solve.py"),
        ("2k-call loop", WORKLOADS / "storage_heavy.py"),
    ]:
        workdir = scratch_with(script)
        run_pytracer(["run", script.name, "--repeat", "5", "--plugins", "numpy",
                      "--store-arrays", "always", "--no-report"], cwd=workdir)
        exp = latest_experiment(workdir)
        for run_dir in sorted((exp / "runs").iterdir()):
            rows.append({
                "workload": wname,
                "run": run_dir.name,
                "jsonl_bytes": du(run_dir / "events.jsonl"),
                "parquet_bytes": du(run_dir / "events.parquet"),
                "arrays_bytes": du(run_dir / "arrays"),
            })
    write_csv("e7_storage.csv", rows)

    # -- crash-safety -------------------------------------------------------
    crashdir = scratch_with(WORKLOADS / "crashy.py")
    proc = run_pytracer(["run", "crashy.py", "--repeat", "6",
                         "--plugins", "numpy",
                         "--continue-on-error", "--no-report"],
                        cwd=crashdir, check=False)
    exp = latest_experiment(crashdir)
    analyze = run_pytracer(["analyze", str(exp)], cwd=crashdir, check=False)

    survivors, killed = [], []
    for run_dir in sorted((exp / "runs").iterdir()):
        (killed, survivors)[(run_dir / "events.parquet").exists()].append(
            run_dir.name)
    crash_report = {
        "run_exit_code": proc.returncode,
        "analyze_exit_code": analyze.returncode,
        "runs_completed": survivors,
        "runs_killed": killed,
        "killed_runs_have_jsonl": all(
            du(exp / "runs" / r / "events.jsonl") > 0 for r in killed),
        "alignment_runs": load_analysis(exp, "alignment")["runs"]
        if analyze.returncode == 0 else None,
    }
    import json
    out = Path(__file__).resolve().parent.parent / "results" / "e7_crash.json"
    out.write_text(json.dumps(crash_report, indent=1))
    print(f"crash-safety: completed={survivors} killed={killed} "
          f"analyze_exit={analyze.returncode} "
          f"jsonl_preserved={crash_report['killed_runs_have_jsonl']}")
    return 0


if __name__ == "__main__":
    main_guard(run)
