import pytracer.core.tracer as pt
import sys

module = sys.argv[1]
pt.run()
pt.exec_module(module)
