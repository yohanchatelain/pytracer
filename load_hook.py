#!/usr/bin/python3

from importlib.machinery import ModuleSpec
from importlib import invalidate_caches
from importlib.machinery import SourceFileLoader
from importlib.abc import MetaPathFinder, Loader
import os.path
import inspect
import sys
import copy
from types import ModuleType
import wrapper


class MyLoader(SourceFileLoader):
    def __init__(self, fullname, path):
        self.fullname = fullname
        self.path = path

    def find_module(self, fullname, path=None):
        spec = self.find_spec(fullname, path)
        if spec is None:
            return None
        return spec

    def get_filename(self, fullname):
        return self.path

    def get_data(self, filename):
        """exec_module is already defined for us, we just have to provide a way
        of getting the source code of the module"""
        with open(filename, 'rb') as f:
            data = f.read()
        # do something with data ...
        # eg. ignore it... return "print('hello world')"
        return data


class Myloader(Loader):

    def __init__(self, fullname, path=None):
        self.fullname = fullname
        self.path = path

    def _fill_attribute(self, fake, real, attr):
        if hasattr(real, attr):
            setattr(fake, getattr(real, attr))

    def fill_attributes(self, fake, real):
        self._fill_attribute(fake, real, "__package__")
        self._fill_attribute(fake, real, "__path__")
        self._fill_attribute(fake, real, "__file__")

    def is_package(self, fullname):
        return True

    def find_module(self, fullname, path=None):
        print("Find module", fullname)
        assert(0)
        spec = self.find_spec(fullname, path)
        if spec is None:
            return None
        print("Module found")
        return spec

    def create_module(self, spec):
        from importlib.util import module_from_spec, find_spec
        print("Create fake module from spec", spec)
        real_spec = find_spec(spec.name)
        real_module = module_from_spec(real_spec)
        real_spec.loader.exec_module(real_module)
        wrp = wrapper.Wrapper(real_module)
        fake_module = wrp.get_wrapped_module()
        print("Fake module created:", fake_module)
        return fake_module

    def exec_module(self, module):
        real_module = sys.modules.pop(module.__name__)
        sys.modules[module.__name__] = module
        globals()[module.__name__] = module
        print("CREATED MODULE", module)
        print("CREATED MODULE", dir(module))


class MyImporter(MetaPathFinder):

    pytracer_modules_env = "PYTRACER_MODULES"
    modules_to_load = list()
    modules_to_load_path = list()
    modules = dict()

    # def __init__(self):
    #     self._get_modules_to_load()

    def _get_modules_to_load(self):
        if self.modules_to_load == []:
            modules_to_load = os.getenv(self.pytracer_modules_env)
            if not modules_to_load:
                sys.exit("{env} is empty".format(
                    env=self.pytracer_modules_env))
            modules_to_load = modules_to_load.split(",")
            for module in modules_to_load:
                module_name = module.strip()
                print("Module to load", module_name)
                self.modules_to_load.append(module_name)

    def find_spec(self, fullname, path=None, target=None):
        #print("Find spec for", fullname)
        self._get_modules_to_load()
        #print("Finding spec for", fullname)
        if fullname not in self.modules_to_load:
            return None

        for stack in inspect.stack():
            if stack.filename.endswith("load_hook.py") and stack.function == "create_module":
                return None

        spec = ModuleSpec(fullname, Myloader(fullname))
        print("Spec found", spec)
        return spec


def install(loader):
    # insert the path hook ahead of other path hooks
    sys.meta_path.insert(0, loader)
    # clear any loaders that might already be in use by the FileFinder
    sys.path_importer_cache.clear()
    invalidate_caches()


def main():

    # numpy = importlib.import_module("numpy")
    # sys.modules["real_numpy"] = numpy
    # globals()["real_numpy"] = numpy
    # del sys.modules["numpy"]

    # math = importlib.import_module("math")
    # del sys.modules["math"]
    # sys.modules["real_math"] = math
    # globals()["real_math"] = math
    # print("LOAD HOOK", sys.modules["real_math"])

    finder = MyImporter()
    install(finder)

    # math = importlib.import_module("math")
    # sys.modules["math"] = math
    # numpy = importlib.import_module("numpy")
    # sys.modules["numpy"] = numpy

    # importlib.reload(math)
    # importlib.reload(numpy)


main()
