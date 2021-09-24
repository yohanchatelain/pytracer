import numpy as np
from scipy.fft import ifftn

N = 30
xf = np.zeros((N, N))
xf[0, 5] = 1
xf[0, N-5] = 1
Z = ifftn(xf)
print(Z)

xf = np.zeros((N, N))
xf[5, 0] = 1
xf[N-5, 0] = 1
Z = ifftn(xf)
print(Z)

xf = np.zeros((N, N))
xf[5, 10] = 1
xf[N-5, N-10] = 1
Z = ifftn(xf)
print(Z)
