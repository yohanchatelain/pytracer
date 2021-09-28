import numpy as np
from scipy.fft import dct, idct

N = 100
t = np.linspace(0, 20, N, endpoint=False)
x = np.exp(-t/3)*np.cos(2*t)
y = dct(x, norm='ortho')
window = np.zeros(N)
window[:20] = 1
yr = idct(y*window, norm='ortho')
s = np.sum(np.abs(x-yr)**2) / np.sum(np.abs(x)**2)
print(s)

window = np.zeros(N)
window[:15] = 1
yr = idct(y*window, norm='ortho')
s = np.sum(np.abs(x-yr)**2) / np.sum(np.abs(x)**2)
print(s)
