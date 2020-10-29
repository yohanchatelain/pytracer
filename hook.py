
import math
import sys
import inspect
print("IMPORT HOOK:", sys.modules['math'])


def list_module():
    print('begin list_module')
#    print('HOOK', sys.meta_path)
#    print("HOOK:", globals())
    print("HOOK:", sys.modules['math'])
    print("HOOK:", dir(sys.modules['math']))
    assert(not inspect.isbuiltin(math))
#    print("HOOK:", sys.path_importer_cache)
    print("HOOK:", math.sin)
    print("HOOK:", math.sin(1))
    print('end list_module')


print("internal")
print(sys.meta_path)
list_module()
