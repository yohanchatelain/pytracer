"""Per-run child process: install instrumentation, execute the target script.

Invoked by the experiment orchestrator as
``python -m pytracer._bootstrap <spec.json>``. One subprocess per repetition:
repeats must be statistically independent (module caches, RNG state,
perturbation-backend seeds are all per-process).

Instrumentation is installed BEFORE the target script is imported, so the
script's own ``import numpy`` sees the patched attributes.
"""

from __future__ import annotations

import json
import runpy
import sys
import traceback
from pathlib import Path

from pytracer.instrumentation.monitor import Monitor
from pytracer.instrumentation.patcher import Patcher, resolve_targets
from pytracer.instrumentation.recorder import Recorder, set_active_recorder
from pytracer.storage.parquet import finalize_run
from pytracer.trace.metadata import collect_run_metadata, write_metadata
from pytracer.trace.writer import TraceWriter


def run_from_spec(spec: dict) -> int:
    run_dir = Path(spec["run_dir"])
    run_dir.mkdir(parents=True, exist_ok=True)
    script = spec["script"]
    script_args = spec.get("script_args", [])
    instrumentation = spec.get("instrumentation", "hybrid")

    meta = collect_run_metadata(
        experiment_id=spec["experiment_id"],
        run_id=spec["run_id"],
        command=[script, *script_args],
    )

    writer = TraceWriter(run_dir)
    recorder = Recorder(
        writer,
        spec["run_id"],
        capture_backtrace=spec.get("capture_backtrace", True),
        mode=spec.get("mode", "summary"),
    )
    set_active_recorder(recorder)

    patcher = Patcher(recorder)
    if instrumentation in ("hybrid", "patch"):
        report = resolve_targets(spec.get("targets", []))
        meta.unresolved_targets = report.errors
        patcher.patch(report.resolved)

    monitor = Monitor(scope_dir=Path(script).resolve().parent, run_dir=run_dir)
    if instrumentation in ("hybrid", "monitor"):
        monitor.start()
        if not monitor.available:
            meta.notes.append("sys.monitoring unavailable; T4 monitor disabled")
    else:
        meta.notes.append("monitor tier disabled by configuration")

    status = 0
    old_argv = sys.argv
    try:
        sys.argv = [script, *script_args]
        runpy.run_path(script, run_name="__main__")
    except SystemExit as e:
        if isinstance(e.code, int):
            status = e.code
        elif e.code is not None:
            status = 1
    except BaseException:
        status = 1
        meta.error = traceback.format_exc()
    finally:
        sys.argv = old_argv
        set_active_recorder(None)
        patcher.unpatch()
        monitor.stop()
        writer.close()
        meta.exit_code = status
        write_metadata(run_dir / "metadata.json", meta)
        try:
            finalize_run(run_dir)
        except Exception as e:  # parquet is an artifact, not the capture
            note = f"parquet finalize failed: {type(e).__name__}: {e}"
            meta.notes.append(note)
            write_metadata(run_dir / "metadata.json", meta)
    return status


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m pytracer._bootstrap <spec.json>", file=sys.stderr)
        return 2
    spec = json.loads(Path(argv[0]).read_text())
    return run_from_spec(spec)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
