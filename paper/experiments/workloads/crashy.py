"""E7 crash-safety workload: performs traced numpy work, then hard-kills
itself (SIGKILL, no cleanup, no atexit) on the 4th and later repetitions.
A run counter file in the working directory persists across the
independent run subprocesses."""

import os
import signal
from pathlib import Path

import numpy as np

counter = Path("run_counter.txt")
n = int(counter.read_text()) if counter.exists() else 0
counter.write_text(str(n + 1))

rng = np.random.default_rng()
x = np.arange(1000.0) * (1.0 + rng.normal(scale=1e-12))
print(float(np.sum(x)), float(np.mean(x)))

if n >= 3:
    os.kill(os.getpid(), signal.SIGKILL)
