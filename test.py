#!/usr/bin/python3

import pytracer
import math
import numpy as np

if '__main__' == __name__:

    import hook
    print("list module of hook")
    hook.list_module()

    print(math.pi)

    print("math.sin", math.sin)
    for i in range(10):
        x = math.sin(i)
        print(x)

    print(math.sin(1))
    print(math.cos(1))
    print(math.tan(1))

    print(np.float16(1))
    print("NUMPY", np.sin(1))
    # for attr in dir(np):
    #     try:
    #         print(attr, np.__dict__[attr])
    #     except Exception:
    #         continue
    print(np.linalg)
    print(np.random)
    print(np.random.uniform(size=10))
    