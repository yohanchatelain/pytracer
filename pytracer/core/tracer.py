#!/usr/bin/python3

import json
from pytracer.utils import ishashable

from numpy.core.fromnumeric import trace
import pytracer.core.wrapper.cache as cache
import argparse
import importlib.util
import inspect
import os
import sys
from importlib import invalidate_caches
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
import ast

from pytracer.core.config import config as cfg
from pytracer.utils.log import get_logger
from pytracer.core.wrapper.wrapper import WrapperClass, WrapperModule, visited_attr, Wrapper
from pytracer.core.wrapper.cache import add_global_mapping, get_global_mapping, visited_files
import pytracer.core.tracer_init as tracer_init
import pytracer.utils.report as report

logger = get_logger()


class Myloader(Loader):

    def __init__(self, fullname, path=None):
        self.to_initialize = list()
        self.fullname = fullname
        self.path = path
        self.visited_modules = set()
        self.spec_to_aliases = {}

    def is_package(self, fullname):
        return True

    def find_spec(self, fullname, path=None):
        logger.debug(f"find spec {fullname} {path}", caller=self)
        return super().find_spec(fullname, path)

    def find_module(self, fullname, path=None):
        logger.debug(f"find spec {fullname} {path}", caller=self)
        spec = self.find_spec(fullname, path)
        if spec is None:
            return None
        return spec

    def compare_module(self, mod1, mod2):
        logger.debug(f"Comparing {mod1} and {mod2}")
        dir1 = dir(mod1)

        for attr in dir1:
            a1 = getattr(mod1, attr, None)
            a2 = getattr(mod2, attr, None)
            if a1 != a2:
                logger.debug(f"{a1} and {a2} differ", caller=self)
                if inspect.ismodule(a1):
                    self.compare_module(a1, a2)

    def sanitize_check(self, real_module, wrapped_module, indent=""):
        if wrapped_module.__name__ in self.visited_modules:
            return

        self.visited_modules.add(wrapped_module.__name__)

        symbols = dir(real_module)

        if hasattr(real_module, visited_attr):
            return

        for sym in symbols:
            # Doing this instead of hasattr to not call __getattr__ of
            # the module since it makes an infinite loop for numpy.testing
            try:
                obj = object.__getattribute__(real_module, sym)
                has_attr = True
            except AttributeError:
                has_attr = False
            except ModuleNotFoundError:
                has_attr = False
            except ImportError:
                has_attr = False
            if not has_attr:
                continue
            if not hasattr(wrapped_module, sym):
                try:
                    setattr(wrapped_module, sym, obj)
                except:
                    logger.error(warn, caller=self)
                if sym == "__warningregistry__":
                    continue
            sym_obj_wrp = getattr(wrapped_module, sym)
            sym_obj_rl = getattr(real_module, sym)
            if inspect.ismodule(sym_obj_wrp):
                self.sanitize_check(sym_obj_rl, sym_obj_wrp, indent+" ")

    def get_globals(self, spec, module):
        for alias, value in globals().items():
            if value == module:
                aliases = self.spec_to_aliases.get(cache.hash_spec(spec), [])
                aliases.append(alias)

    def create_module(self, spec):
        try:
            logger.debug(f"create module for spec {spec}")
            cache.visited_spec[spec.name] = True
            real_module = importlib.import_module(spec.name)
            self.get_globals(spec, real_module)
            Wrapper.m2wm[real_module] = None
            logger.debug(
                f"real module {real_module} imported ({hex(id(real_module))})")
            wrp = WrapperModule(real_module)
            wrapped_module = wrp.wrapped_obj
            cache.orispec_to_wrappedmodule[cache.hash_spec(
                spec)] = wrapped_module
            wrp.assert_lazy_modules_loaded()
            wrp.assert_lazy_attributes_are_initialized()
            Wrapper.m2wm[real_module] = wrapped_module
            add_global_mapping(real_module, wrapped_module)
            logger.debug(f"create Wrapped module {wrapped_module.__spec__}")
            logger.debug(f"Wrapped module {hex(id(wrapped_module))}")
            self.sanitize_check(real_module, wrapped_module)
            logger.debug(
                f"wrapper module for {spec.name} created", caller=self)
            return wrapped_module
        except ImportError as e:
            logger.warning("ImportError", caller=self, error=e)
            self.to_initialize.append(spec)
            return None
        except Exception as e:
            logger.critical("Unknown exception", error=e, caller=self)

    def exec_module(self, module):
        logger.debug(f"exec module {module}", caller=self)

        try:
            _ = sys.modules.pop(module.__name__)
        except KeyError:
            logger.debug(
                f"module {module.__name__} is not in sys.modules", caller=self)

        sys.modules[module.__name__] = module
        globals()[module.__name__] = module

        for alias in self.spec_to_aliases.get(cache.hash_spec(module.__spec__), []):
            globals()[alias] = module


class MyImporter(MetaPathFinder):

    modules_to_load = []

    def __init__(self):
        self.find_true_spec = False
        self._get_modules_to_load()

    def _get_modules_to_load(self):
        if self.modules_to_load == []:
            for module in cfg.modules_to_load:
                module_name = module.strip()
                logger.debug(f"Module to load: {module_name}", caller=self)
                try:
                    _ = sys.modules.pop(module_name)
                except KeyError:
                    pass
                self.modules_to_load.append(module_name)

    def is_internal_import(self, stack):
        if stack.code_context is None:
            return False
        try:
            m = ast.parse(inspect.cleandoc(stack.code_context[0]))
        except SyntaxError:
            # We don't have an import stmt so we can discard it
            return False
        return isinstance(m.body[0], (ast.Import, ast.ImportFrom))

    def need_real_module(self):
        for stack in inspect.stack():
            if self.is_internal_import(stack):
                return False
            if "/pytracer/core" in stack.filename:
                if stack.filename.endswith(__file__):
                    if stack.function == "create_module":
                        return True
                if stack.filename.endswith("_wrapper.py"):
                    return True
        return False

    def find_original_spec(self, fullname):
        self.find_true_spec = True
        return importlib.util.find_spec(fullname)

    def find_spec(self, fullname, path=None, target=None):

        if self.find_true_spec:
            return None

        if self.find_original_spec(fullname) is None:
            self.find_true_spec = False
            return None
        self.find_true_spec = False

        if fullname in cache.visited_spec:
            return None

        to_load = False

        for to_exclude in cfg.modules_to_exclude:
            if fullname.startswith(to_exclude):
                return None

        for module in self.modules_to_load:
            if fullname.startswith(module):
                to_load = True
                break
        if not to_load:
            return None

        logger.debug(f"find spec for {fullname} {path} {target}", caller=self)

        spec = ModuleSpec(fullname, Myloader(fullname), origin="Pytracer")

        cache.visited_spec[fullname] = None

        # if we are in the create_module function,
        # we return the real module (return None)
        # if self.need_real_module():
        if cache.visited_spec.get(fullname):
            logger.debug("need the original module {fullname}", caller=self)
            return None

        logger.debug(f"{fullname} spec found", caller=self)
        return spec


def install(loader):
    # insert the path hook ahead of other path hooks
    sys.meta_path.insert(0, loader)
    # clear any loaders that might already be in use by the FileFinder
    sys.path_importer_cache.clear()
    invalidate_caches()


def fill_required_function(modules_state, global_state):

    current_modules_state = list(sys.modules.keys())
    current_globals_state = list(globals().keys())

    for key in current_modules_state:
        if key not in modules_state:
            del sys.modules[key]
    for key in current_globals_state:
        if key not in global_state:
            del globals()[key]

    keys = list(sys.modules.keys())
    for module in cfg.modules_to_load:
        for key in keys:
            if key.startswith(f"{module}") and key in sys.modules:
                del sys.modules[key]

    keys = list(sys.modules.keys())
    for module in cfg.modules_to_exclude:
        for key in keys:
            if key.startswith(f"{module}") and key in sys.modules:
                del sys.modules[key]


def run():
    if sys.platform != "linux":
        logger.error("Others platforms than linux are not supported")

    fill_required_function(list(sys.modules.keys()), list(globals().keys()))
    finder = MyImporter()
    install(finder)
    for module in finder.modules_to_load:
        if module in sys.modules:
            logger.debug(
                f"original module {module} was removed from sys.module")
            sys.modules.pop(module)
        logger.debug(f"load module {module}")
        importlib.import_module(module)


def exec_module(module_name):
    visited_files.add(module_name)
    spec = importlib.util.spec_from_file_location("__main__", module_name)
    module = importlib.util.module_from_spec(spec)
    logger.debug(f"Exec target module {spec} {module} {module.__dict__} ")
    # Pass arguments to program
    argindex = sys.argv.index(module_name)
    sys.argv = sys.argv[argindex:]
    spec.loader.exec_module(module)


def initialize_lazy_modules():
    logger.debug('Initialized lazy modules')
    for module, submodule in cache.modules_not_initialized.items():
        name = getattr(submodule, '__name__')
        value = get_global_mapping(submodule)
        setattr(module, name, value)

        for name, module in sys.modules.items():
            keys = list(module.__dict__)
            for k in keys:
                v = module.__dict__[k]
                if new_v := get_global_mapping(v):
                    module.__dict__[k] = new_v


def dump_visited():
    with open('visited_function.json', 'w') as fo:
        json.dump(cache.dumped_functions, fo)


def main(args):

    if os.path.isfile(args.module):
        report.set_report(args.report)
        if not args.dry_run:
            run()
        initialize_lazy_modules()
        exec_module(args.module)
        if report.report_enable():
            report.dump_report()
        dump_visited()
    else:
        logger.error(f"File {args.module} not found")


if __name__ == "__main__":
    parser_args = argparse.ArgumentParser(
        description="Pytracer tracing module")
    tracer_init.init_arguments(parser_args)
    args = parser_args.parse_args()
    main(args)
