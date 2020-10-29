#!/usr/bin/python3

import load_hook

import math
import sys
import inspect
from importlib.abc import Loader, MetaPathFinder
from importlib.util import spec_from_file_location
from importlib.machinery import FileFinder, SourceFileLoader, BuiltinImporter, SourcelessFileLoader
from importlib import invalidate_caches
from importlib.machinery import ModuleSpec
import numpy as np

if '__main__' == __name__:

    import hook
    print("list module of hook")
    hook.list_module()

    print(math.pi)
#    print(dir(math))
#    print(sys.modules["math.sin"])
 #   sys.exit(1)

    print("math.sin", math.sin)
    for i in range(10):
        x = math.sin(i)
        print(x)

    print(math.sin(1))
    print(math.cos(1))
    print(math.tan(1))

    import inspect
    print("NUMPY", np.numpy)
    print("NUMPY", np.sin(1))
    print(np.random.uniform(size=10))
