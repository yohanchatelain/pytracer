import inspect
import os
import re
import sys
from types import FunctionType, LambdaType, ModuleType

import inout
import utils.log
from utils.singleton import Singleton
from config import DictAtKeyError, config as cfg

logger = utils.log.get_log()


def special_case(module, attr_obj):
    """
        Handle special case for module when the object is not
        recognize by the module inspect (ex: numpy.ufunc functions)
    """
    if module.__name__ == "numpy":
        if type(attr_obj).__name__ == "ufunc":
            return True
        return False
    return False


class Filter:

    def __init__(self, filename):
        self.modules = dict()
        self.load_file(filename)

    def load_file(self, filename):
        if filename:
            self.fi = open(cfg.include_file)
            self.read_file()

    def _add(self, module, function):
        module_re = re.compile(module.replace("*", ".*"))
        function_re = re.compile(function.replace("*", ".*"))
        if module_re in self.modules:
            self.modules[module_re].add(function_re)
        else:
            self.modules[module_re] = set([function_re])

    def read_file(self):
        for line in self.fi:
            line = line.strip()
            if line.startswith("#") or line == "":
                continue
            module, function = line.split()
            self._add(module, function)

    def has_module(self, value):
        if not bool(self.modules):
            return False
        for module in self.modules:
            if module.findall(value) != []:
                return True
        return False

    def has_function(self, value):
        if not bool(self.modules):
            return False
        for function in self.modules.values():
            if function.findall(value):
                return True
        return False


class FilterInclusion(Filter, metaclass=Singleton):

    def __init__(self):
        try:
            super().__init__(cfg.include_file)
        except DictAtKeyError:
            super().__init__(None)
        logger.debug("Inclusion filter initialized")


class FilterExclusion(Filter, metaclass=Singleton):

    def __init__(self):
        try:
            super().__init__(cfg.exclude_file)
        except DictAtKeyError:
            super().__init__(None)
        logger.debug("Exclusion filter initialized")
        self.default_exclusion()

    def default_exclusion(self):
        modules_to_load = [module.strip() for module in cfg.modules_to_load]
        for builtin_module in sys.builtin_module_names:
            if builtin_module not in modules_to_load:
                self._add(builtin_module, "*")


class Wrapper:

    special_attributes = ["__spec__", "__all__", "__dir__",
                          "__dict__", "__getattr__", "__setattr__",
                          "__hasattr__"]

    cache = set()
    wrapped_cache = set()
    wrapper_visited = set()
    m2wm = dict()
#    lazy_dict = dict()

    def __init__(self, module, parent=None):
        self.lazy_dict = dict()
        self.included = FilterInclusion()
        self.excluded = FilterExclusion()
        self.real_module = module
        self.parent_module = parent
        self.module_name = self.real_module.__name__
        self.wrapped_module = ModuleType(self.module_name)
        self.attributes = dir(self.real_module)
        self.init_attributes(parent)
        Wrapper.wrapped_cache.add(self.wrapped_module)
        self.create()
        logger.debug(f"module {self.module_name} created")
        # Initalized the module in m2wm dict
        Wrapper.m2wm[self.real_module] = self.wrapped_module

    def init_attributes(self, parent):
        if parent:
            self.wrapped_module.__dict__[
                self.parent_module.__name__] = self.parent_module
        self.wrapped_module.__dict__[self.module_name] = self.real_module
        self.wrapped_module.__dict__[
            "generic_wrapper"] = inout.writer()

    def assert_lazy_modules_loaded(self):
        entry = 0
        no_entry = 0
        total_entry = len(Wrapper.m2wm)
        logger.info(f"Lazy evaluation for module: {self.module_name}")
        logger.info(
            f"Ensure that all lazy modules ({total_entry}) have been initialized")
        for module, submodule in Wrapper.m2wm.items():
            if submodule is None:
                logger.debug(f"  module {module.__name__} as no entry")
                no_entry += 1
            else:
                logger.debug(
                    f"  module {module.__name__} as entry for {submodule.__name__}")
                entry += 1

        logger.debug(f"\tTotal_entry: {total_entry}")
        logger.debug(f"\t      entry: {entry}")
        logger.debug(f"\t      empty: {no_entry}")
        assert(entry == total_entry)
        logger.info("All modules have been initialized")

    def get_real_module(self):
        return self.real_module

    def get_wrapped_module(self):
        return self.wrapped_module

    def getwrapperfunction(self, function, function_wrapper_name):
        function_name = function.__name__
        wrapper_code = f"""def {function_wrapper_name}(*args, **kwargs):
            return generic_wrapper({self.module_name}.{function_name},*args,**kwargs)
        """
        return wrapper_code

    def getwrapperbasic(self, basic):
        """
        Return wrapper for basic python objects
        """
        wrapper_code = f"{basic} = {self.module_name}.{basic}{os.linesep}"
        return wrapper_code

    def isfunction(self, attr_obj):
        """
        check if the object is a function
        """
        return inspect.isbuiltin(attr_obj) or \
            inspect.isfunction(attr_obj) or \
            inspect.isroutine(attr_obj) or \
            special_case(self.real_module, attr_obj)

    def islambda(self, function):
        """
        check is the function is a lambda function
        """
        return isinstance(function, LambdaType) and \
            function.__name__ == "<lambda>"

    # Name of the variable that contains the lambda function
    # ex: x = lambda y:y
    def handle_lambda(self, name, function):
        """
        Handler for lambda functions
        """
        code = function.__code__
        func = LambdaType(code, self.wrapped_module.__dict__)
        self.wrapped_module.__dict__[name] = func

    def handle_function(self, name, function):
        """
        Handler for functions
        """
        function_name = name

        if self.islambda(function):
            self.handle_lambda(name, function)
            return

        logger.debug(
            f"create function {function_name} in module {self.module_name}")

        wrapped_fun = self.getwrapperfunction(function, function_name)
        code = compile(wrapped_fun, "<string>", "exec")
        func = FunctionType(
            code.co_consts[0], self.wrapped_module.__dict__, function_name)

        self.wrapped_module.__dict__[function_name] = func

    def ismodule(self, attr):
        """
        Check if the attribute is a module
        """
        return inspect.ismodule(attr)

    def handle_excluded_module(self, submodule):
        submodule_name = submodule.__name__.split(".")[-1]
        logger.debug(f"submodule {submodule_name} excluded")
        self.wrapped_module.__dict__[submodule_name] = submodule
        # The submodule is excluded so we add itself as value
        Wrapper.m2wm[submodule] = submodule

    def handle_included_module(self, submodule):
        submodule_name = submodule.__name__.split(".")[-1]
        logger.debug(f"submodule {submodule_name} included")
        submodule_wrapper = Wrapper(submodule, self.real_module)
        submodule_wrp = submodule_wrapper.get_wrapped_module()
        self.wrapped_module.__dict__[submodule_name] = submodule_wrp
        # The submodule is included so we add the wrapped module as value
        Wrapper.m2wm[submodule] = submodule_wrp

    def handle_module(self, submodule):
        """
        Handler for submodules
        """
        submodule_qualname = submodule.__name__
        submodule_name = submodule.__name__.split(".")[-1]

        if submodule in Wrapper.m2wm:
            # Submodule has been visited
            if Wrapper.m2wm[submodule] is not None:
                # Submodule is already initialized so we can
                # add it in the wrapped module entries
                self.wrapped_module.__dict__[
                    submodule_name] = Wrapper.m2wm[submodule]
            return

        # submodule is visited so add an entry for it
        # we set the value to None since it has not been
        # initialized yet
        Wrapper.m2wm[submodule] = None

        logger.debug(f"submodule detected: {submodule_name}")

        if self.included.has_module(submodule_qualname):
            self.handle_included_module(submodule)
        elif self.excluded.has_module(submodule_qualname):
            self.handle_excluded_module(submodule)
        else:
            self.handle_included_module(submodule)

    def isclass(self, attr):
        """
            Check if the attribute is a class
        """
        return inspect.isclass(attr)

    def handle_class(self, clss):
        """
            Handler for class
        """
        class_name = clss.__name__
        logger.debug(f"create class {class_name}")
        self.wrapped_module.__dict__[class_name] = clss

    def handle_basic(self, name, obj):
        """
            Handler for basic objects
        """
        logger.debug(f"create object {name}")
        self.wrapped_module.__dict__[name] = obj

    def isspecialattr(self, attr):
        """
            Check is the attribute is a special attributes
        """
        if attr in self.special_attributes:
            return True
        return False

    def handle_special(self, attr, attr_obj):
        """
            Handler for special attributes
        """
        if attr == "__spec__":
            self.wrapped_module.__spec__ = attr_obj
        elif attr == "__all__":
            self.wrapped_module.__all__ = attr_obj
        elif attr == "__dir__":
            self.wrapped_module.__dir__ = attr_obj
        elif attr == "__dict__":
            self.wrapped_module.__dict__ = attr_obj
        elif attr == "__setattr__":
            self.wrapped_module.__setattr__ = attr_obj
        elif attr == "__getattr__":
            self.wrapped_module.__getattr__ = attr_obj
        elif attr == "__hasattr__":
            self.wrapped_module.__hasattr__ = attr_obj

    def create(self):
        """
            Create wrapper for each attribute in the module
        """
        for attr in self.attributes:
            try:
                attr_obj = inspect.getattr_static(self.real_module, attr)
            except AttributeError:
                logger.warning(f"{attr} is not handled")
                attr_obj = getattr(self.real_module, attr)

            if self.isspecialattr(attr):
                self.handle_special(attr, attr_obj)
            elif self.isfunction(attr_obj):
                self.handle_function(attr, attr_obj)
            elif self.ismodule(attr_obj):
                self.handle_module(attr_obj)
            elif self.isclass(attr_obj):
                self.handle_class(attr_obj)
            else:
                self.handle_basic(attr, attr_obj)
