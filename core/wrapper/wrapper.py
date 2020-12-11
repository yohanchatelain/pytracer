import collections.abc
import importlib
import inspect
import os
import re
import sys
from abc import ABCMeta, abstractmethod
from types import FunctionType, LambdaType, ModuleType
from numpy.lib.function_base import vectorize

import pytracer.core.inout as inout
from pytracer.core.config import DictAtKeyError
from pytracer.core.config import config as cfg
from pytracer.core.utils.log import get_logger
from pytracer.core.utils.singleton import Singleton

import functools

logger = get_logger()


def special_case(module, attr_obj):
    """
        Handle special case for module when the object is not
        recognize by the module inspect (ex: numpy.ufunc functions)
    """
    return False


class Filter:

    _wildcard = ".*"

    def __init__(self, filenames):
        self.__modules = dict()
        for filename in filenames:
            self.load_file(filename)

    def debug(self):
        logger.debug(f"{self.__class__.__name__} initialized")
        for module, functions_set in self.__modules.items():
            logger.debug(f"module:{module}")
            for function in functions_set:
                logger.debug(f"\tfunction:{function}")

    def load_file(self, filename):
        if filename:
            logger.debug(f"{self.__class__.__name__} read file: {filename}")
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
        for line in self.fi:
            line = line.strip()
            if line.startswith("#") or line == "":
                continue
            module, function = line.split()
            self._add(module, function)

    def has_module(self, module):
        logger.debug(
            f"{self.__class__.__name__} checking entry for module {module}")
        if not module:
            return False
        if not bool(self.__modules):
            return False
        for _module in self.__modules:
            if _module.fullmatch(module):
                logger.debug(f"{self.__class__.__name__} has module {module}")
                logger.debug(f"Filter {_module}, pattern {module}")
                return True
        return False

    def has_function(self, functions, module=None):
        logger.debug(f"has_function: {functions} {module}", caller=self)
        if isinstance(functions, tuple):
            for function in functions:
                if self._has_function(function, module):
                    return True
            return False
        if isinstance(functions, str):
            return self._has_function(functions, module)
        logger.critical(f"Unknown parameters {functions}", caller=self)
        return

    def has_submodule(self, submodule, module):
        return self.has_function(submodule, module)

    def _has_function(self, function, module=None):
        logger.debug(
            f"{self.__class__.__name__} checking entry for function {function} (in {module})")
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
                            logger.debug(
                                f"{self.__class__.__name__} has function {function} in module {module}")
                            logger.debug(f"Filter {mod}, pattern {module}")
                            logger.debug(
                                f"Filter {_function}, pattern {function}")
                            return True
            return False

        # We search function across all modules
        for function_set in self.__modules.values():
            for _function in function_set:
                if _function.fullmatch(function):
                    logger.debug(
                        f"{self.__class__.__name__} has function {function}")
                    return True
        return False

    def has_entire_module(self, module):
        return self.has_function(self._wildcard, module)


class FilterInclusion(Filter, metaclass=Singleton):

    def __init__(self):
        try:
            super().__init__(cfg.include_file)
        except DictAtKeyError:
            logger.debug("No filename provided")
            super().__init__(None)
        except FileNotFoundError:
            logger.error(f"include-file {cfg.include_file} not found")
        self.debug()


class FilterExclusion(Filter, metaclass=Singleton):

    def __init__(self):
        try:
            super().__init__(cfg.exclude_file)
        except DictAtKeyError:
            logger.debug("No filename provided")
            super().__init__(None)
        except FileNotFoundError:
            logger.error(f"exclude-file {cfg.exclude_file} not found")
        self.default_exclusion()
        self.debug()

    def default_exclusion(self):
        modules_to_load = [module.strip() for module in cfg.modules_to_load]

        for builtin_module in sys.builtin_module_names:
            if builtin_module not in modules_to_load:
                self._add(builtin_module, "*")

        if cfg.python_modules_path:
            python_modules_path = cfg.python_modules_path
        else:
            version = sys.version_info
            major = version.major
            minor = version.minor
            python_modules_path = f"{sys.prefix}/lib/python{major}.{minor}"
            python_modules = os.listdir(python_modules_path)
            for python_module in python_modules:
                if python_module.endswith(".py"):
                    python_module, _ = os.path.splitext(python_module)
                self._add(python_module, "*")


def instance_wrapper(function):
    writer = inout.writer_instance()

    def wrapper(self, *args, **kwargs):
        return writer(function, self, *args, **kwargs)
    return wrapper


def instance_wrapper_ufunc(function):
    writer = inout.writer_ufunc()

    def wrapper(*args, **kwargs):
        return writer(function, *args, **kwargs)
    wrapper.__name__ = function.__name__
    wrapper.types = function.types
    return wrapper


def is_special_attributes(name):
    return name.startswith("__") and name.endswith("__")


def prepare_attributes(attributes):

    new_attributes = dict(attributes)
    new_attributes["__Pytracer_visited__"] = True
    for name, attr in attributes.items():
        if callable(attr) and not is_special_attributes(name):
            new_attributes[name] = instance_wrapper(attr)

    return new_attributes


def wrap_instance(instance):
    from numpy import ufunc, frompyfunc, isnan, vectorize

    x = None

    if cfg.numpy.ufunc and isinstance(instance, ufunc):
        nin = instance.nin
        nout = instance.nout
        wrp_instance = instance_wrapper_ufunc(instance)
        x = frompyfunc(wrp_instance, nin, nout, identity=instance.identity)

    else:
        attributes = {name: getattr(instance, name)
                      for name in dir(instance)}

        new_attributes = prepare_attributes(attributes)
        clss = instance.__class__
        clss_name = clss.__name__
        try:
            wrapped_instance = type(clss_name, (clss,), new_attributes)
            x = wrapped_instance.__new__(wrapped_instance)

            for attr_instance in dir(instance):
                iv = getattr(instance, attr_instance)
                ix = getattr(x, attr_instance)
                if iv != ix:
                    logger.error(
                        f"Attributes {attr_instance} differs {iv} {ix}")

        except TypeError as e:
            if "is not an acceptable base type" in e.args[0]:
                logger.warning(
                    f"Instance {instance} cannot be wrapped", error=e)
            x = None
        except Exception as e:
            logger.warning(
                f"Instance {instance} cannot be wrapped", error=e)
            x = None

    return x


class InstanceWrapper(object):

    included = None
    excluded = None
    writer = None
    __class_attributes_initialized = False

    __attributes = ["instance", "function"]

    def _init_class_attributes(self):
        if not InstanceWrapper.__class_attributes_initialized:
            InstanceWrapper.__class_attributes_initialized = True
            InstanceWrapper.included = FilterInclusion()
            InstanceWrapper.excluded = FilterExclusion()
            InstanceWrapper.writer = inout.writer_instance()

    def __init__(self, instance):
        logger.debug(f"[InstanceWrapper] init {instance}")
        self._init_class_attributes()
        self.instance = instance
        self.__mro__ = instance.__class__.__mro__

    def _get_name(self, function):
        return getattr(function, "__name__")

    def _get_module(self, function):
        module = getattr(function, "__module__", None)
        if not module:
            clss = getattr(function, "__class__")
            module = getattr(clss, "__module__")
        return module

    def __call__(self, *args, **kwds):
        logger.debug(f"[{self.instance.__name__}] __call__({args},{kwds})")
        self.function = self.instance.__call__
        self.function_name = self._get_name(self.instance)
        self.module_name = self._get_module(self.instance)
        return InstanceWrapper.writer(self, *args, **kwds)

    def __handle_included_function(self, method):
        logger.debug(
            f"[{self.instance.__name__}] Included method {str(method)}")
        self.function = method
        self.function_name = self._get_name(method)
        self.module_name = self._get_module(method)

        def wrap(*args, **kwds):
            return InstanceWrapper.writer(self, *args, **kwds)

        return wrap

    def __handle_excluded_function(self, method, msg=""):
        logger.debug(f"Excluded method {method} {msg}")
        return method

    def __getattribute__(self, name):
        to_return = None
        __attributes = ["instance", "function", "function_name",
                        "module_name", "__handle_included_function",
                        "_InstanceWrapper__handle_included_function",
                        "__handle_excluded_function",
                        "_InstanceWrapper__handle_excluded_function",
                        "_get_module", "_get_name",
                        "__class_attributes_initialized",
                        "_init_class_attributes"]
        if name in __attributes:
            to_return = object.__getattribute__(self, name)
        else:
            instance = object.__getattribute__(self, "instance")
            attr = instance.__getattribute__(name)
            if callable(attr) and not (name.startswith("__") and name.endswith("__")):
                if InstanceWrapper.included.has_function(name) or \
                        not InstanceWrapper.excluded.has_function(name):
                    to_return = self.__handle_included_function(attr)
                else:
                    to_return = self.__handle_excluded_function(attr)
            else:
                self.__handle_excluded_function(name, msg="not callable")
                to_return = attr
        return to_return

    def __getstate__(self):
        return self.__dict__

    def __setstate__(self, d):
        _obj = d["instance"]
        self.__dict__ = d
        self.instance = _obj


class Wrapper(metaclass=ABCMeta):

    cache = set()
    wrapped_cache = set()
    wrapper_visited = set()
    m2wm = dict()
    modules_not_initialized = dict()
    visited_functions = dict()
    id_dict = dict()
#    lazy_dict = dict()

    def __init__(self, obj, parent=None):
        self.lazy_dict = dict()
        self.included = FilterInclusion()
        self.excluded = FilterExclusion()
        self.real_obj = obj
        self.parent_obj = parent
        self.obj_name = getattr(self.real_obj, "__name__")
        self.wrapped_obj = self.new_obj()
        self.init_attributes()
        Wrapper.wrapped_cache.add(self.wrapped_obj)
        self.populate(self.real_obj, self.attributes)
        Wrapper.m2wm[self.real_obj] = self.wrapped_obj

    @ abstractmethod
    def new_obj(self):
        pass

    def init_attributes(self):
        self.attributes = dir(self.real_obj)
        logger.debug(f"Initialized attributes for module {self.obj_name}")

    def assert_lazy_modules_loaded(self):
        entry = 0
        no_entry = 0
        total_entry = len(Wrapper.m2wm)
        logger.info(f"Lazy evaluation for module: {self.obj_name}")
        logger.info(
            f"Ensure that all lazy modules ({total_entry}) have been initialized")
        for module, submodule in Wrapper.m2wm.items():
            modname = getattr(module, "__name__")
            if submodule is None:
                logger.debug(f"  module {modname} as no entry")
                no_entry += 1
            else:
                submodname = getattr(submodule, "__name__")
                logger.debug(f"  module {modname} as entry for {submodname}")
                entry += 1

        logger.debug(f"\tTotal_entry: {total_entry}")
        logger.debug(f"\t      entry: {entry}")
        logger.debug(f"\t      empty: {no_entry}")
        assert(entry == total_entry)
        logger.info("All modules have been initialized")

    def assert_lazy_attributes_are_initialized(self):
        logger.info("Ensure that all attributes are initialized")
        for (submodule, attrs) in self.modules_not_initialized.items():
            for attr, wrp_module in attrs:
                if not hasattr(wrp_module, attr):
                    logger.debug(
                        f"Entry {attr} is missing in {wrp_module}, we add it with {Wrapper.m2wm[submodule]}")
                    setattr(wrp_module, attr, Wrapper.m2wm[submodule])
        logger.info("All attributes have been initialized")

    def flush_cache(self):
        self.m2wm.clear()

    def get_name(self):
        return self.obj_name

    def get_module_name(self, obj):
        return getattr(obj, "__module__", getattr(type(obj), "__module__"))

    def get_real_object(self):
        return self.real_obj

    def get_wrapped_object(self):
        return self.wrapped_obj

    def getwrapperfunction(self, info, function, function_wrapper_name):
        """
        Specific Module
        """
        function_module, function_name = info
        function_id = id(function)
        logger.debug(
            f"GET WRAPPER: id {function_id}, name {function_name}, module {function_module}")
        info = (function_id, function_module, function_name)
        wrapper_code = f"""def {function_wrapper_name}(*args, **kwargs):
            return generic_wrapper({info},*args,**kwargs)
        """
#            return generic_wrapper({self.get_name()}.{function_name},*args,**kwargs)
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
            special_case(self.real_obj, attr_obj)

    def islambda(self, function):
        """
        check is the function is a lambda function
        """
        return isinstance(function, LambdaType) and \
            function.__name__ == "<lambda>"

    # Name of the variable that contains the lambda function
    # ex: x = lambda y:y
    def handle_included_lambda(self, name, function):
        """
        Handler for lambda functions
        """
        # code = function.__code__
        # lmbd = LambdaType(code=code, globals=self.wrapped_obj.__dict__)
        setattr(self.wrapped_obj, name, function)

    def handle_excluded_lambda(self, name, function):
        """
        Handler for lambda functions
        """
        setattr(self.wrapped_obj, name, function)

    def handle_excluded_function(self, name, function):
        logger.debug(f"[{self.get_name()}] Excluded function {name}")
        if self.islambda(function):
            self.handle_excluded_lambda(name, function)
            return
        setattr(self.wrapped_obj, name, function)
        Wrapper.visited_functions[function] = function

    def _get_dict(self, function, name):

        new_func_dict = {
            "generic_wrapper": getattr(self.wrapped_obj, "generic_wrapper")}

        for attr in dir(function):
            new_func_dict[attr] = getattr(function, attr)

        if hasattr(function, "__module__"):
            new_func_dict["__module__"] = getattr(function, "__module__")
        else:
            new_func_dict["__module__"] = self.get_name()

        if hasattr(function, "__name__"):
            new_func_dict["__name__"] = getattr(function, "__name__")
        else:
            new_func_dict["__name__"] = name

        return new_func_dict

    def handle_included_function(self, name, function):
        logger.debug(f"[{self.get_name()}] Included function {name}")
        if self.islambda(function):
            self.handle_included_lambda(name, function)
            return

        try:
            function_path = inspect.getfile(function)
        except TypeError:
            function_path = "<string>"

        func_dict = self._get_dict(function, name)
        func_name = getattr(function, "__name__", name)
        func_module = getattr(function, "__module__", self.get_name())
        func_name = func_name if func_name else name
        func_module = func_module if func_module else self.get_name()
        info = (func_module, func_name)
        wrapped_fun = self.getwrapperfunction(info, function, name)
        code = compile(wrapped_fun, function_path, "exec")
        func = FunctionType(code.co_consts[0], func_dict, name)
        setattr(func, "__pytracer__", True)
        setattr(self.wrapped_obj, name, func)
        Wrapper.visited_functions[function] = func
        logger.debug(
            f"Function {name} at {hex(id(function))} -> {hex(id(func))}")

    def handle_function(self, name, function, module=None):
        """
        Handler for functions
        """
        alias_function_name = name
        function_name = getattr(function, "__name__")
        names = (alias_function_name, function_name)
        #        module_name = self.get_module_name(function)
        module_name = self.obj_name

        if hasattr(function, "__pytracer__"):
            logger.debug(f"Function {name} {function} has been visited ")
            setattr(self.wrapped_obj, name, function)
            return

        if function in Wrapper.visited_functions:
            logger.debug(f"Function {name} ({function}) cached")
            cached_function = Wrapper.visited_functions[function]
            setattr(self.wrapped_obj, name, cached_function)
            return

        Wrapper.id_dict[id(function)] = function

        logger.debug(
            f"Handling function {name} from {module_name} ({id(function)})")
        if function_name.startswith("_") or function_name == "generic_wrapper" or\
                function_name == "wrp":
            self.handle_excluded_function(alias_function_name, function)
        elif self.included.has_module(module_name):
            if self.included.has_function(names, module_name):
                self.handle_included_function(alias_function_name, function)
            else:
                self.handle_excluded_function(alias_function_name, function)
        elif self.excluded.has_function(names, module_name):
            self.handle_excluded_function(alias_function_name, function)
        else:
            self.handle_included_function(alias_function_name, function)

        logger.debug(
            f"create function {function_name} in module {self.get_name()}")

    def ismodule(self, attr):
        """
        Check if the attribute is a module
        """
        return inspect.ismodule(attr)

    def handle_excluded_module(self, attr, submodule):
        logger.debug(f"[{self.get_name()}] Excluded module {attr}")
        submodname = submodule.__name__.split(".")[-1]
        setattr(self.wrapped_obj, attr, submodule)
        setattr(self.wrapped_obj, submodname, submodule)
        # The submodule is excluded so we add itself as value
        Wrapper.m2wm[submodule] = submodule
        logger.debug(f"submodule {submodname} excluded")

    def handle_included_module(self, attr, submodule):
        logger.debug(f"[{self.get_name()}] Included module {attr}")
        submodname = submodule.__name__.split(".")[-1]
        parent = self.parent_obj if self.parent_obj else []
        wrp = WrapperModule(submodule, [self.real_obj]+parent)
        submodule_wrp = wrp.get_wrapped_module()
        setattr(submodule_wrp, "__Pytracer_visited__", True)
        setattr(self.wrapped_obj, attr, submodule_wrp)
        setattr(self.wrapped_obj, submodname, submodule_wrp)
        # The submodule is included so we add the wrapped module as value
        Wrapper.m2wm[submodule] = submodule_wrp
        logger.debug(f"submodule {submodname} included")

    def handle_module(self, attr, submodule):
        """
        Handler for submodules
        """
        submodqualname = getattr(submodule, "__name__")
        modulename = ".".join(submodqualname.split(".")[:-1])
        submodname = submodqualname.split(".")[-1]

        if submodule in Wrapper.m2wm:
            # Submodule has been visited
            if Wrapper.m2wm[submodule] is not None:
                # Submodule is already initialized so we can
                # add it in the wrapped module entries
                logger.debug(f"submodule {attr} cached as {submodname}")
                setattr(self.wrapped_obj, attr, Wrapper.m2wm[submodule])
            else:
                if submodule in Wrapper.modules_not_initialized:
                    Wrapper.modules_not_initialized[submodule].add(
                        (attr, self.wrapped_obj))
                else:
                    Wrapper.modules_not_initialized[submodule] = set(
                        [(attr, self.wrapped_obj)])

                logger.debug(f"submodule {attr} cached but not initialized")
            return

        # submodule is visited so add an entry for it
        # we set the value to None since it has not been
        # initialized yet
        Wrapper.m2wm[submodule] = None

        logger.debug(f"submodule detected: {submodqualname}")

        # random       * -> <submodulename>  *
        # numpy.random * -> <submodqualname> *
        # numpy random   -> <module> <attr>

        if submodname == "wrapper.wrapper":
            self.handle_excluded_module(attr, submodname)
        elif self.included.has_submodule(attr, modulename) or \
                self.included.has_module(submodqualname):
            self.handle_included_module(attr, submodule)
        elif self.excluded.has_submodule(attr, modulename) or \
                self.excluded.has_entire_module(submodqualname):
            self.handle_excluded_module(attr, submodule)
        else:
            self.handle_included_module(attr, submodule)

    def isclass(self, attr):
        """
            Check if the attribute is a class
        """
        return inspect.isclass(attr)

    def handle_included_class(self, name, clss):
        logger.debug(f"[{self.get_name()}] Included class {name}", caller=self)
        wrp = WrapperClass(clss)
        class_wrp = wrp.get_wrapped_object()
        # class_wrp = ClassWrapper(clss)
        classname = getattr(clss, "__name__")
        logger.debug(f"Wrapped class {class_wrp}", caller=self)
        setattr(self.wrapped_obj, name, class_wrp)
        setattr(self.wrapped_obj, classname, class_wrp)

#        wrp_clss = new_class(name, inspect.getmro(clss))

    def handle_excluded_class(self, name, clss):
        logger.debug(f"[{self.get_name()}] Excluded class {name}", caller=self)
        classname = getattr(clss, "__name__")
        logger.debug(f"Normal class {clss}", caller=self)
        setattr(self.wrapped_obj, name, clss)
        setattr(self.wrapped_obj, classname, clss)

    def handle_class(self, attr, clss):
        """
            Handler for class
        """

        if clss in WrapperClass.visited_class:
            if WrapperClass.visited_class[clss] is not None:
                setattr(self.wrapped_obj, attr,
                        WrapperClass.visited_class[clss])
            else:
                setattr(self.wrapped_obj, attr, None)
            return

        modname = getattr(clss, "__module__", "")
        clssname = getattr(clss, "__name__")
        logger.debug(
            f"Handling class {clssname} from module {modname}", caller=self)
        self.handle_excluded_class(attr, clss)

        # if inspect.isabstract(clss):
        #     self.handle_excluded_class(attr, clss)
        # elif self.included.has_module(modname):
        #     if self.included.has_function(clssname, modname) or \
        #             self.included.has_function(attr, modname):
        #         self.handle_included_class(attr, clss)
        #     else:
        #         self.handle_excluded_class(attr, clss)
        # elif self.excluded.has_module(modname):
        #     if self.excluded.has_function(clssname, modname) or \
        #             self.excluded.has_function(attr, modname):
        #         self.handle_excluded_class(attr, clss)
        #     else:
        #         self.handle_included_class(attr, clss)
        # else:
        #     self.handle_included_class(attr, clss)

        logger.debug(f"Class {clssname} has been handled", caller=self)

    def handle_included_basic(self, name, obj):
        logger.debug(f"[{self.get_name()}] Included basic {name}", caller=self)
        wrp_obj = obj
        if not hasattr(obj, "__Pytracer_visited__") and callable(obj):
            logger.debug(
                f"Create wrapper instance with {obj} at {name} ({hex(id(obj))})", caller=self)
            wrp_obj = wrap_instance(obj)
            wrp_obj = wrp_obj if wrp_obj else obj
        setattr(self.wrapped_obj, name, wrp_obj)

    def handle_excluded_basic(self, name, obj):
        logger.debug(f"[{self.get_name()}] Excluded basic {name}", caller=self)
        setattr(self.wrapped_obj, name, obj)

    def is_hashable(self, obj):
        try:
            hash(obj)
            return True
        except TypeError:
            return False

    def handle_basic(self, name, obj):
        """
            Handler for basic objects
        """
        obj_name = getattr(obj, "__name__", "")
        names = (name, obj_name)
        module_name = self.get_name()
        logger.debug(f"check object {name} in {module_name}", caller=self)
        if self.is_hashable(obj) and obj in Wrapper.m2wm:
            self.handle_excluded_basic(name, Wrapper.m2wm[obj])
        elif isinstance(obj, functools.partial):
            self.handle_excluded_basic(name, obj)
        elif hasattr(obj, "__Pytracer_visited__"):
            self.handle_excluded_basic(name, obj)
        elif isinstance(obj, Wrapper):
            self.handle_excluded_basic(name, obj)
        elif self.included.has_function(names, module_name):
            self.handle_included_basic(name, obj)
        elif self.excluded.has_function(names, module_name):
            self.handle_excluded_basic(name, obj)
        else:
            self.handle_included_basic(name, obj)

    def isspecialattr(self, attr):
        """
            Check is the attribute is a special attributes
        """
        if attr.startswith("__") and attr.endswith("__"):
            return True
        return False

    def handle_special(self, attr, attr_obj):
        """
            Handler for special attributes
        """

        try:
            setattr(self.wrapped_obj, attr, attr_obj)
        except Exception as e:
            logger.critical(f"{self} {attr} {attr_obj}", error=e, caller=self)

    def populate(self, obj, attributes):
        """
            Create wrapper for each attribute in the module
        """
        for attr in attributes:
            logger.debug(f"[{self.obj_name}] Checking {attr}", caller=self)
            try:
                attr_obj = inspect.getattr_static(obj, attr)
            except AttributeError:
                logger.warning((f"{attr} is not handled by "
                                "inspec.getattr_static"), caller=self)
                # if hasattr(obj, attr):
                #     attr_obj = object.__getattribute__(obj, attr)
                # else:
                try:
                    logger.debug(
                        f"Trying loading module {attr}", caller=self)
                    objname = getattr(obj, "__name__")
                    attr_obj = importlib.import_module(
                        objname + "." + attr)
                except ModuleNotFoundError:
                    logger.warning(
                        f"Attribute {attr} cannot be handled", caller=self)
                    continue
                except ImportError:
                    logger.warning(
                        f"Attribute {attr} cannot be imported", caller=self)
                    continue

            logger.debug(f"Object {attr} at {hex(id(attr_obj))}", caller=self)

            if self.isspecialattr(attr):
                self.handle_special(attr, attr_obj)
            elif self.isfunction(attr_obj):
                self.handle_function(attr, attr_obj)
            elif self.ismodule(attr_obj):
                self.handle_module(attr, attr_obj)
            elif self.isclass(attr_obj):
                self.handle_class(attr, attr_obj)
            else:
                self.handle_basic(attr, attr_obj)


class WrapperModule(Wrapper):

    def new_obj(self):
        return ModuleType(self.get_name())

    def get_wrapped_module(self):
        return self.get_wrapped_object()

    def add_parent(self, parent):
        setattr(self.wrapped_obj, parent.__name__, parent)

    def init_attributes(self):
        super().init_attributes()
        if self.parent_obj:
            for parent in self.parent_obj:
                self.wrapped_obj.__dict__[parent.__name__] = parent
        setattr(self.wrapped_obj, self.obj_name, self.real_obj)
        setattr(self.wrapped_obj, "generic_wrapper", inout.writer())


class WrapperClass(Wrapper):

    visited_class = dict()
    special_attributes = ["__class__", "__dict__", "__base__", "__bases__",
                          "__basicsize__", "__dictoffset__", "__flags__",
                          "__itemsize__", "__mro__", "__text_signature__",
                          "__weakrefoffset__", "__doc__", "__delattr__",
                          "__eq__", "__neq__", "__dir__", "__format__",
                          "__ge__", "__getattribute__", "__getstate__",
                          "__new__", "__reduce__", "__reduce_ex__",
                          "__repr__", "__setattr__", "__setstate__", "__repr__"]

    def generic_wrapper(self, fun):
        def wrp(*args, **kwargs):
            return self.writer(fun, *args, **kwargs)
        return wrp

    def __init__(self, clss):
        super().__init__(clss)
        wrp_class = self.get_wrapped_object()
        self.visited_class[self.real_obj] = wrp_class

    def init_attributes(self):
        super().init_attributes()
        self.writer = inout.writer_class()

    def get_module(self):
        if hasattr(self, "__module_name__"):
            return self.__module_name__
        self.__module_name__ = self.wrapped_obj.__module__

    def new_obj(self):
        if self.real_obj in self.visited_class:
            if self.visited_class is not None:
                return self.visited_class[self.real_obj]
            return self.real_obj
        self.visited_class[self.real_obj] = None
        return self.real_obj

    def handle_function(self, name, function):
        if isinstance(function, (classmethod, staticmethod)):
            self.handle_excluded_function(name, function)
        elif name == "wrp":
            self.handle_excluded_function(name, function)
        else:
            super().handle_function(name, function)

    def handle_included_function(self, name, function):
        try:
            logger.debug(
                f"[{self.get_name()}] Included method {name}", caller=self)
            function_id = id(function)
            setattr(self.wrapped_obj, name,
                    self.generic_wrapper(function_id))
        except TypeError as e:
            logger.warning(f"[{self.wrapped_obj.__name__}] cannot handled method {name}",
                           error=e, caller=self)

    def handle_excluded_function(self, name, function):
        logger.debug(
            f"[{self.real_obj.__name__}] Excluded method {name}")

    def handle_special(self, attr, attr_obj):
        if attr.startswith("__") and attr.endswith("__"):
            return
        if attr in self.special_attributes:
            return
        super().handle_special(attr, attr_obj)

    def handle_basic(self, name, obj):
        try:
            super().handle_included_basic(name, obj)
            # setattr(self.wrapped_obj, name, obj)
            logger.debug(
                f"[{self.get_name()}] Include object {name}", caller=self)
        except TypeError as e:
            logger.warning(
                f"Cannot handled basic object {name}", error=e, caller=self)
        except AttributeError as e:
            logger.warning(
                f"Cannot handled basic object {name}", error=e, caller=self)

    def handle_class(self, attr, clss):
        if clss in self.visited_class:
            if self.visited_class[clss] is not None:
                return self.visited_class[clss]
            return
        super().handle_class(attr, clss)
