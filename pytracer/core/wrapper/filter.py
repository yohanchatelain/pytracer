import os
import re
import sys

from pytracer.core.config import DictAtKeyError
from pytracer.core.config import config as cfg
from pytracer.utils.log import get_logger
from pytracer.utils.singleton import Singleton

logger = get_logger()


class Filter:

    _wildcard = ".*"
    _rewildcard = re.compile(".*")

    _debug_enabled = True

    def __init__(self, filenames):
        self.__modules = {}
        for filename in filenames:
            self.load_file(filename)

    def debug(self, *args, **kwargs):
        if self._debug_enabled:
            logger.debug(*args, **kwargs)

    def load_file(self, filename):
        if filename:
            logger.debug(f"read file: {filename}", caller=self)
            self.fi = open(filename)
            self.read_file()

    def _add(self, module, function):
        module_re = re.compile(module.replace("*", self._wildcard))
        function_re = re.compile(function.replace("*", self._wildcard))
        if module_re in self.__modules:
            self.__modules[module_re].add(function_re)
        else:
            self.__modules[module_re] = set([function_re])

    def read_file(self):
        for i, line in enumerate(self.fi, start=1):
            line = line.strip()
            if line.startswith("#") or line == "":
                continue
            try:
                module, function = line.split()
            except ValueError as e:
                logger.error(
                    f"Syntaxic error in {self.fi.name} at line {i}: '{line}'",
                    caller=self, error=e, raise_error=False)
            self._add(module, function)
            if function[0].isupper():
                self._add(module, f"{function}.*")

    def has_module(self, module):
        if not module:
            return False
        if not bool(self.__modules):
            return False
        for _module in self.__modules:
            if _module.fullmatch(module):
                return True
        return False

    def has_function(self, functions, module=None):
        if isinstance(functions, tuple):
            for function in functions:
                if self._has_function(function, module):
                    return True
            return False
        if isinstance(functions, str):
            return self._has_function(functions, module)
        logger.critical(f"Unknown parameters {functions}", caller=self)

    def has_submodule(self, submodule, module):
        return self.has_function(submodule, module)

    def _has_function(self, function, module=None):
        if not function:
            return False
        if not bool(self.__modules):
            return False
        # We search function in module
        if module:
            for mod in self.__modules:
                if mod.fullmatch(module):
                    functions = self.__modules[mod]
                    for _function in functions:
                        if _function.fullmatch(function):
                            return True
            return False

        # We search function across all modules
        for function_set in self.__modules.values():
            for _function in function_set:
                if _function.fullmatch(function):
                    return True
        return False

    def has_entire_module(self, module):
        self.debug(f"has entier module {module}", caller=self)
        return self.has_function(self._wildcard, module)


class FilterInclusion(Filter, metaclass=Singleton):

    def __init__(self):
        try:
            super().__init__(cfg.include_file)
        except DictAtKeyError:
            logger.debug("No filenames provided", caller=self)
            super().__init__(None)
        except FileNotFoundError as e:
            logger.error(f"include-file {cfg.include_file} not found",
                         caller=self, error=e, raise_error=False)


class FilterExclusion(Filter, metaclass=Singleton):

    def __init__(self):
        try:
            super().__init__(cfg.exclude_file)
        except DictAtKeyError:
            logger.debug("No filenames provided", caller=self)
            super().__init__(None)
        except FileNotFoundError as e:
            logger.error(f"exclude-file {cfg.exclude_file} not found",
                         caller=self, error=e, raise_error=False)
        self.default_exclusion()

    def default_exclusion(self):
        modules_to_load = [module.strip() for module in cfg.modules_to_load]

        for builtin_module in sys.builtin_module_names:
            if builtin_module not in modules_to_load:
                self._add(builtin_module, "*")

        for module_to_exclude in cfg.modules_to_exclude:
            self._add(module_to_exclude, "*")
            self._add(f"{module_to_exclude}.*", "*")

        if cfg.python_modules_path:
            python_modules_path = cfg.python_modules_path
        else:
            version = sys.version_info
            major = version.major
            minor = version.minor
            root = sys.base_prefix
            python_modules_path = f"{root}/lib/python{major}.{minor}"
            python_modules = os.listdir(python_modules_path)
            for python_module in python_modules:
                if python_module.endswith(".py"):
                    python_module, _ = os.path.splitext(python_module)
                self._add(python_module, "*")
