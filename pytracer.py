#!/usr/bin/python3

import importlib
import inspect
import sys
from importlib import invalidate_caches
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec

import utils
from wrapper.wrapper import Wrapper
import utils.log
from config import config as cfg

logger = utils.log.get_log()


class Myloader(Loader):

    def __init__(self, fullname, path=None):
        self.fullname = fullname
        self.path = path

    def is_package(self, fullname):
        return True

    def find_module(self, fullname, path=None):
        spec = self.find_spec(fullname, path)
        if spec is None:
            return None
        return spec

    def create_module(self, spec):
        from importlib.util import find_spec, module_from_spec
        real_spec = importlib.util.find_spec(spec.name)
        real_module = module_from_spec(real_spec)
        real_spec.loader.exec_module(real_module)
        wrp = Wrapper(real_module)
        wrp.assert_lazy_modules_loaded()
        wrapped_module = wrp.get_wrapped_module()
        logger.debug(f"wrapper module for {spec.name} created")
        return wrapped_module

    def exec_module(self, module):
        try:
            _ = sys.modules.pop(module.__name__)
        except KeyError:
            logger.debug(f"module {module.__name__} is not in sys.modules")
        sys.modules[module.__name__] = module
        globals()[module.__name__] = module


class MyImporter(MetaPathFinder):

    modules_to_load = list()

    def __init__(self):
        self._get_modules_to_load()

    def _get_modules_to_load(self):
        if self.modules_to_load == []:
            for module in cfg.modules_to_load:
                module_name = module.strip()
                logger.debug(f"module to load {module_name}")
                try:
                    _ = sys.modules.pop(module_name)
                except KeyError:
                    logger.debug(f"no module {module_name} in sys.modules")
                self.modules_to_load.append(module_name)

    def find_spec(self, fullname, path=None, target=None):
        if fullname not in self.modules_to_load:
            return None

        # if we are in the create_module function,
        # we return the real module (return None)
        for stack in inspect.stack():
            if stack.filename.endswith(__file__) and \
                    stack.function == "create_module":
                return None

        spec = ModuleSpec(fullname, Myloader(fullname))

        logger.debug("{fullname} spec found")
        return spec


def install(loader):
    # insert the path hook ahead of other path hooks
    sys.meta_path.insert(0, loader)
    # clear any loaders that might already be in use by the FileFinder
    sys.path_importer_cache.clear()
    invalidate_caches()


def main():
    finder = MyImporter()
    install(finder)
    for module in finder.modules_to_load:
        logger.debug(f"load module {module}")
        importlib.import_module(module)


main()
