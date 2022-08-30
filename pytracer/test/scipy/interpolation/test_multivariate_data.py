import numpy as np
import pytest
from scipy.interpolate import griddata

from pytracer.test.utils import trace


def func(x, y):
    return x*(1-x)*np.cos(4*np.pi*x) * np.sin(4*np.pi*y**2)**2


def main():
    grid_x, grid_y = np.mgrid[0:1:100j, 0:1:200j]

    rng = np.random.default_rng(0)
    points = rng.random((1000, 2))
    values = func(points[:, 0], points[:, 1])

    grid_z0 = griddata(points, values, (grid_x, grid_y), method='nearest')
    grid_z1 = griddata(points, values, (grid_x, grid_y), method='linear')
    grid_z2 = griddata(points, values, (grid_x, grid_y), method='cubic')

    print("Z0", grid_z0)
    print("Z1", grid_z1)
    print("Z2", grid_z2)


@pytest.mark.usefixtures("cleandir")
def test_trace_only(bash):
    trace(__file__, bash)


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, bash):
    for _ in range(nsamples):
        trace(__file__, bash)


if '__main__' == __name__:
    main()
