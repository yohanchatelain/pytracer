
import math
import inspect


def list_module():
    print('begin list_module')
    assert(not inspect.isbuiltin(math))
    print("HOOK:", math.sin)
    print("HOOK:", math.sin(1))
    print('end list_module')


list_module()
