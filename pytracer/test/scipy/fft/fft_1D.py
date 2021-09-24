from scipy.signal import blackman
import numpy as np
from scipy.fft import fft, ifft, fftfreq, fftshift, rfft, irfft

x = np.array([1.0, 2.0, 1.0, -1.0, 1.5])
y = fft(x)
print(y)
yinv = ifft(y)
print(yinv)

# Number of sample points
N = 600
# sample spacing
T = 1.0 / 800.0
x = np.linspace(0.0, N*T, N, endpoint=False)
y = np.sin(50.0 * 2.0*np.pi*x) + 0.5*np.sin(80.0 * 2.0*np.pi*x)
yf = fft(y)
w = blackman(N)
ywf = fft(y*w)
xf = fftfreq(N, T)[:N//2]
print(xf)

freq = fftfreq(8, 0.125)
print(freq)

x = np.arange(8)
y = fftshift(x)
print(y)

# number of signal points
N = 400
# sample spacing
T = 1.0 / 800.0
x = np.linspace(0.0, N*T, N, endpoint=False)
y = np.exp(50.0 * 1.j * 2.0*np.pi*x) + 0.5*np.exp(-80.0 * 1.j * 2.0*np.pi*x)
yf = fft(y)
xf = fftfreq(N, T)
xf = fftshift(xf)
yplot = fftshift(yf)
print(yplot)

x = np.array([1.0, 2.0, 1.0, -1.0, 1.5, 1.0])
fft(x)
yr = rfft(x)
print(yr)
irfft(yr)
x = np.array([1.0, 2.0, 1.0, -1.0, 1.5])
print(fft(x))
yr = rfft(x)
print(yr)

y = irfft(yr)
print(y)
y = irfft(yr, n=len(x))
print(y)
