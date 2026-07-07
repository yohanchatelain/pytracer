"""Operator-heavy code: invisible to T1/T2, fully visible under
--instrument taint (T3 tracer arrays)."""

import numpy as np

import pytracer

x = pytracer.taint(np.arange(4.0))
y = x * 2.0 + 1.0  # multiply + add via operator dispatch
print(float(y.sum()))  # add.reduce via method dispatch
