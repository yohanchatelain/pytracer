#!/usr/bin/python3

from pytracer.core.inout import _init
import argparse
import ast
import importlib.util
import inspect
import json
import os
import sys
from importlib import invalidate_caches
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
import pytracer.cache as cache
import pytracer.module.tracer_init as tracer_init
import pytracer.utils.report as report
from pytracer.core.config import config as cfg
from pytracer.cache import (add_global_mapping,
                            get_global_mapping, visited_files)
from pytracer.core.wrapper.wrapper import (WrapperModule, visited_attr)
from pytracer.module.info import register
from pytracer.utils.log import get_logger

logger = get_logger()


class PytracerLoader(Loader):

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
                except Exception:
                    pass
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
            real_module = importlib.import_module(spec.name)
            self.get_globals(spec, real_module)

            if cache.has_global_mapping(real_module):
                logger.error(f"Module {real_module} has been created already",
                             caller=self)
            else:
                cache.add_global_mapping(real_module, None)
            cache.required_modules[real_module] = []

            logger.debug(
                f"real module {real_module} imported ({hex(id(real_module))})")
            wrp = WrapperModule(real_module)
            wrapped_module = wrp.wrapped_obj

            cache.add_global_mapping(real_module, wrapped_module)

            cache.orispec_to_wrappedmodule[cache.hash_spec(
                spec)] = wrapped_module
            add_global_mapping(real_module, wrapped_module)
            logger.debug(f"create Wrapped module {wrapped_module.__spec__}")
            logger.debug(f"Wrapped module {hex(id(wrapped_module))}")
            self.sanitize_check(real_module, wrapped_module)
            logger.debug(
                f"wrapper module for {spec.name} created", caller=self)
            return wrapped_module
        except ImportError as e:
            logger.warning(f"ImportError encountered for {spec}", caller=self,
                           error=e)
        except Exception as e:
            logger.critical("Unknown exception", error=e,
                            caller=self)

    def exec_module(self, module):
        logger.debug(f"exec module {module}", caller=self)

        try:
            _ = sys.modules.pop(module.__name__)
        except KeyError:
            logger.debug(
                f"module {module.__name__} is not in sys.modules", caller=self)

        sys.modules[module.__name__] = module
        globals()[module.__name__] = module

        aliases = self.spec_to_aliases.get(
            cache.hash_spec(module.__spec__), [])
        for alias in aliases:
            globals()[alias] = module


class PytracerImporter(MetaPathFinder):

    modules_to_load = []

    def __init__(self):
        self.importing_module = set()
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

    def return_original_spec(self, fullname):
        logger.debug(f"Need the original module {fullname}", caller=self)
        self.importing_module.remove(fullname)
        return None

    def is_valid_spec(self, fullname, path):
        meta_path = [meta_path for meta_path in sys.meta_path
                     if not isinstance(meta_path, PytracerImporter)]
        return any([finder.find_spec(fullname, path) for finder in meta_path
                    if hasattr(finder, "find_spec")])

    def find_spec(self, fullname, path=None, target=None):
        logger.debug(f"find spec for {fullname} {path} {target}", caller=self)

        if not self.is_valid_spec(fullname, path):
            return None

        if fullname in self.importing_module:
            logger.debug(f"{fullname} in importing_module", caller=self)
            return self.return_original_spec(fullname)
        else:
            self.importing_module.add(fullname)

        for to_exclude in cfg.modules_to_exclude:
            if fullname.startswith(to_exclude):
                logger.debug(f"{fullname} in to_exclude modules", caller=self)
                return self.return_original_spec(fullname)

        to_load = any([fullname.startswith(module)
                       for module in self.modules_to_load])
        if not to_load:
            logger.debug(
                f"{fullname} is not in to_include modules", caller=self)
            return self.return_original_spec(fullname)

        spec = ModuleSpec(name=fullname, loader=PytracerLoader(fullname))

        logger.debug(f"{fullname} spec found", caller=self)
        return spec


class TracerRun:

    def __init__(self, args):
        self.parameters = _init.IOInitializer()
        self.args = args
        self.module = self.args.command[0]
        logger.info(f"Trace {self.module}", caller=self)

    def install(self, loader):
        # insert the path hook ahead of other path hooks
        sys.meta_path.insert(0, loader)
        # clear any loaders that might already be in use by the FileFinder
        sys.path_importer_cache.clear()
        invalidate_caches()

    def fill_required_function(self, modules_state, global_state):

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

    def run(self):
        if sys.platform != "linux":
            logger.error("Others platforms than linux are not supported")

        self.fill_required_function(list(sys.modules.keys()),
                                    list(globals().keys()))
        finder = PytracerImporter()
        self.install(finder)
        for module in finder.modules_to_load:
            if module in sys.modules:
                logger.debug(
                    f"original module {module} was removed from sys.module")
                sys.modules.pop(module)
            logger.debug(f"Load module {module}", caller=self)
            importlib.import_module(module)

    def exec_module(self):
        visited_files.add(self.module)
        spec = importlib.util.spec_from_file_location("__main__", self.module)
        module = importlib.util.module_from_spec(spec)
        # Pass arguments to program
        sys.argv = self.args.command
        logger.info(f"Exec traced command: {self.args.command}", caller=self)
        spec.loader.exec_module(module)

    def initialize_lazy_modules(self):
        logger.debug('Initialized lazy modules', caller=self)
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

    def dump_visited(self):
        with open('visited_function.json', 'w') as fo:
            json.dump(cache.dumped_functions, fo)

    def main(self):
        if os.path.isfile(self.module):
            report.report = report.Report(
                self.args.report, self.args.report_file)
            register.set_report(report.report.get_filename(),
                                report.report.get_filename_path())
            if not self.args.dry_run:
                self.run()
            self.initialize_lazy_modules()
            try:
                self.exec_module()
            except Exception as e:
                if (error := cache.cached_error) is not None:
                    msg, err = error
                    logger.error(f"{msg}Unexpected error while writing",
                                 error=err, caller=self, raise_error=True)
                else:
                    logger.error(
                        f"Unexpected error {e}", error=e, caller=self,
                        raise_error=True)
            if report.report.report_enable():
                report.report.dump_report()
            self.dump_visited()
        else:
            logger.error(f"File {self.args.command} not found", caller=self)


if __name__ == "__main__":
    parser_args = argparse.ArgumentParser(
        description="Pytracer tracing module")
    tracer_init.init_arguments(parser_args)
    args = parser_args.parse_args()

    report.report = report.Report(args.report, args.report_file)
    register.set_report(report.report.get_filename(),
                        report.report.get_filename_path())

    runner = TracerRun(args)
    runner.main()
    register.register_trace()
