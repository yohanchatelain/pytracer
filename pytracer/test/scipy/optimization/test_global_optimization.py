from pytracer.test.utils import trace
import numpy as np
import pytest
from scipy import optimize


def eggholder(x):
    return (-(x[1] + 47) * np.sin(np.sqrt(abs(x[0]/2 + (x[1] + 47))))
            - x[0] * np.sin(np.sqrt(abs(x[0] - (x[1] + 47)))))


def main():
    bounds = [(-512, 512), (-512, 512)]

    x = np.arange(-512, 513)
    y = np.arange(-512, 513)
    xgrid, ygrid = np.meshgrid(x, y)
    xy = np.stack([xgrid, ygrid])

    results = dict()
    results['shgo'] = optimize.shgo(eggholder, bounds)
    print(results['shgo'])

    results['DA'] = optimize.dual_annealing(eggholder, bounds)
    print(results['DA'])

    results['DE'] = optimize.differential_evolution(eggholder, bounds)
    results['BH'] = optimize.basinhopping(eggholder, bounds)
    results['shgo_sobol'] = optimize.shgo(eggholder, bounds, n=200, iters=5,
                                          sampling_method='sobol')


@pytest.mark.usefixtures("cleandir")
def test_trace_only(bash):
    trace(__file__, bash)


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, bash):
    for _ in range(nsamples):
        trace(__file__, bash)


if '__main__' == __name__:
    main()
