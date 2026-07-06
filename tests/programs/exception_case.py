"""Traced call raising: the exception event must be recorded and the
script's failure mirrored in the run exit code."""

import numpy as np

np.linalg.solve(np.zeros((2, 2)), np.ones(2))  # singular: raises LinAlgError
