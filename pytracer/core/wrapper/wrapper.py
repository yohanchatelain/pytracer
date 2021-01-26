import functools
import importlib
import inspect
import os
import re
import sys
from abc import ABCMeta, abstractmethod
import traceback
from types import FunctionType, LambdaType, ModuleType

import pytracer.core.inout.writer as iowriter
import pytracer.core.wrapper.cache as cache
from pytracer.core.config import DictAtKeyError
from pytracer.core.config import config as cfg
from pytracer.core.utils.log import get_logger
from pytracer.core.utils.singleton import Singleton

visited_attr = "__Pytracer_visited__"

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
    writer = iowriter.Writer()
    _wrapper = iowriter.wrapper_instance

    def wrapper(self, *args, **kwargs):
        return _wrapper(writer, self, *args, **kwargs)
    return wrapper


def instance_wrapper_ufunc(function):
    writer = iowriter.Writer()
    _wrapper = iowriter.wrapper_ufunc

    def wrapper(*args, **kwargs):
        return _wrapper(writer, function, *args, **kwargs)
    wrapper.__name__ = function.__name__
    wrapper.types = function.types
    return wrapper


def is_arithmetic_operator(name):
    _arithmetic_operator = [
        "__add__", "__floordiv__", "__mul__",
        "__matmul__", "__pow__", "__sub__", "__truediv__",
    ]
    return name in _arithmetic_operator


def is_special_attributes(name):
    return not is_arithmetic_operator(name) and \
        (name.startswith("__") and name.endswith("__"))


def prepare_attributes(attributes):

    new_attributes = dict(attributes)
    new_attributes["visited_attr"] = True
    for name, attr in attributes.items():
        if callable(attr) and not is_special_attributes(name):
            new_attributes[name] = instance_wrapper(attr)

    return new_attributes


def wrap_instance(instance):
    from numpy import frompyfunc, isnan, ufunc

    x = None

    if isinstance(instance, ufunc):
        if cfg.numpy.ufunc:
            nin = instance.nin
            nout = instance.nout
            wrp_instance = instance_wrapper_ufunc(instance)
            x = frompyfunc(wrp_instance, nin, nout, identity=instance.identity)
        else:
            x = None
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
                    if not isnan(iv):
                        logger.error(
                            f"Attributes {attr_instance} differs {iv} {ix} {type(iv)} {type(ix)}")

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


class Wrapper(metaclass=ABCMeta):

    cache = set()
    wrapped_cache = set()
    wrapper_visited = set()
    m2wm = dict()
    modules_not_initialized = dict()
#    visited_functions = dict()
    # id_dict = dict()
#    lazy_dict = dict()

    def __init__(self, obj, parent=None):
        if hasattr(obj, visited_attr):
            logger.error("Object {obj} already visited", caller=self)
            # self.wrapped_obj = obj
            # self.real_obj = obj
        else:
            self.writer = iowriter.Writer()
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
        cache.visited_functions[id(function)] = function
        setattr(self.wrapped_obj, name, function)

    def handle_excluded_lambda(self, name, function):
        """
        Handler for lambda functions
        """
        cache.visited_functions[id(function)] = function
        setattr(self.wrapped_obj, name, function)

    def handle_excluded_function(self, name, function):
        logger.debug(f"[{self.get_name()}] Excluded function {name}")
        if self.islambda(function):
            self.handle_excluded_lambda(name, function)
            return
        setattr(self.wrapped_obj, name, function)
        cache.visited_functions[id(function)] = function

    def _get_dict(self, function, name):

        new_func_dict = {
            "generic_wrapper": getattr(self.wrapped_obj, "generic_wrapper")}

        for attr in dir(function):
            # Cause segfault with dipy
            if attr == "__kwdefaults__":
                continue
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
        assert(func_module and func_name)
        info = (func_module, func_name)
        wrapped_fun = self.getwrapperfunction(info, function, name)
        code = compile(wrapped_fun, function_path, "exec")
        func = FunctionType(code.co_consts[0], func_dict, name)
        setattr(func, visited_attr, True)
        setattr(self.wrapped_obj, name, func)
        cache.visited_functions[id(function)] = func
        logger.debug(
            f"Function {name} at {hex(id(function))} -> {hex(id(func))}")

    def handle_function(self, name, function, module=None):
        """
        Handler for functions
        """
        alias_function_name = name
        function_name = getattr(function, "__name__")
        names = (alias_function_name, function_name)
        module_name = self.obj_name

        if hasattr(function, visited_attr):
            logger.debug(f"Function {name} {function} has been visited ")
            setattr(self.wrapped_obj, name, function)
            return

        fid = id(function)

        if fid in cache.id_dict:
            # if function in cache.visited_functions:
            logger.debug(f"Function {name} ({function}) cached")
            cached_function = cache.visited_functions[fid]
            try:
                setattr(self.wrapped_obj, name, cached_function)
            except TypeError as e:
                pass
                # logger.warning(f"Cannot set attribute", caller=self, error=e)
            return

        if fid in cache.id_dict:
            logger.error(
                f"Function {function} in cache (id:{fid} -> {cache.id_dict[fid]}) but not visited",
                caller=self)
        else:
            logger.info(
                f"Adding function {function} in cache (fid:{fid})", caller=self)
            assert fid not in cache.id_dict
            cache.id_dict[fid] = function

        logger.debug(
            f"Handling function {name} from {module_name} ({id(function)})")
        if not is_arithmetic_operator(name) and \
            (function_name.startswith("_") or
                function_name == "generic_wrapper" or
             function_name == "_generic_wrapper"):
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
        setattr(submodule_wrp, visited_attr, True)
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
        elif hasattr(submodule, visited_attr):
            self.handle_excluded_module(attr, submodule)
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

        if inspect.isabstract(clss):
            self.handle_excluded_class(attr, clss)
        # Exclude class inhereting from BaseException
        elif issubclass(clss, BaseException):
            self.handle_excluded_class(attr, clss)
        elif self.included.has_module(modname):
            if self.included.has_function(clssname, modname) or \
                    self.included.has_function(attr, modname):
                self.handle_included_class(attr, clss)
            else:
                self.handle_excluded_class(attr, clss)
        elif self.excluded.has_module(modname):
            if self.excluded.has_function(clssname, modname) or \
                    self.excluded.has_function(attr, modname):
                self.handle_excluded_class(attr, clss)
            else:
                self.handle_included_class(attr, clss)
        else:
            self.handle_included_class(attr, clss)

        logger.debug(f"Class {clssname} has been handled", caller=self)

    def handle_included_basic(self, name, obj):
        logger.debug(f"[{self.get_name()}] Included basic {name}", caller=self)
        wrp_obj = obj
        if not hasattr(obj, visited_attr) and callable(obj):
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

        # self.handle_excluded_basic(name, obj)

        if self.is_hashable(obj) and obj in Wrapper.m2wm:
            self.handle_excluded_basic(name, Wrapper.m2wm[obj])
        elif isinstance(obj, functools.partial):
            self.handle_excluded_basic(name, obj)
        elif hasattr(obj, "visited_attr"):
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
        return is_special_attributes(attr)

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
        setattr(self.wrapped_obj, "generic_wrapper",
                self.writer.wrapper_function)


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

    def generic_wrapper(self, info):
        _wrapper = self.writer.wrapper_class

        def _generic_wrapper(*args, **kwargs):
            return _wrapper(info, *args, **kwargs)
        # _generic_wrapper.__module__ = info[1]
        # _generic_wrapper.__name__ = info[2]
        # _generic_wrapper.__qualname__ = f"{info[1]}.{info[2]}"
        setattr(_generic_wrapper, visited_attr, True)
        return _generic_wrapper

    def __init__(self, clss):
        super().__init__(clss)
        wrp_class = self.get_wrapped_object()
        self.visited_class[self.real_obj] = wrp_class

    def init_attributes(self):
        super().init_attributes()
        self.writer = iowriter.Writer()

    def get_module(self):
        if hasattr(self, "__module_name__"):
            return self.__module_name__
        self.__module_name__ = self.wrapped_obj.__module__
        return self.__module_name__

    def new_obj(self):
        if self.real_obj in self.visited_class:
            if self.visited_class is not None:
                return self.visited_class[self.real_obj]
            return self.real_obj
        self.visited_class[self.real_obj] = None
        return self.real_obj

    def is_cython_function(self, function):
        _ty = type(function)
        cython_types = ("cython_function_or_method",
                        "fused_cython_function")
        return _ty.__name__ in cython_types

    def handle_function(self, name, function):
        registered = id(function) in cache.id_dict
        visited = id(function) in cache.visited_functions
        if registered and visited:
            self.handle_visited_function(name, function)
        elif registered:
            if not visited:
                logger.error(
                    f"Function registered={registered} and visited={visited}")
        elif isinstance(function, (classmethod, staticmethod)):
            self.handle_excluded_function(name, function)
        elif name == "__new__":
            self.handle_excluded_function(name, function)
        elif name == "generic_wrapper":
            self.handle_excluded_function(name, function)
        elif name == "_generic_wrapper":
            self.handle_excluded_function(name, function)
        elif hasattr(function, visited_attr):
            self.handle_excluded_function(name, function)
        elif not callable(function):
            self.handle_excluded_function(name, function)
        elif inspect.ismethod(function):
            self.handle_included_method(name, function)
        elif self.is_cython_function(function):
            self.handle_excluded_function(name, function)
        elif inspect.ismethoddescriptor(function):
            self.handle_included_methoddescriptor(name, function)
        elif inspect.isfunction(function):
            self.handle_included_function(name, function)
        elif inspect.isbuiltin(function):
            self.handle_excluded_function(name, function)
        else:
            super().handle_function(name, function)

    def check_not_visited(self, function, function_id):
        if function_id in cache.id_dict:
            logger.error(f"Function {function} (id:{hex(function_id)}) has been registered",
                         caller=self)

    def handle_included_methoddescriptor(self, name, function):
        function_id = id(function)
        function_class = function.__objclass__.__name__
        function_name = function.__name__
        info = (function_id, function_class, function_name)
        wrapped_function = self.generic_wrapper(info)
        self.check_not_visited(function, function_id)
        cache.id_dict[function_id] = function
        cache.visited_functions[function_id] = wrapped_function
        assert hasattr(wrapped_function, visited_attr)
        try:
            setattr(self.wrapped_obj, name, wrapped_function)
        except TypeError as e:
            logger.warning((
                f"cannot handle methoddescriptor {name}"),
                error=e, caller=self)
            if function_id in cache.id_dict:
                cache.id_dict.pop(function_id)
            if function_id in cache.visited_functions:
                cache.visited_functions.pop(function_id)
        except Exception as e:
            logger.critical(f"Unkown error while wrapping method {function} named {name}",
                            error=e, caller=self)
        else:
            logger.debug(f"[{self.get_name()}] Include methoddescriptor {name}",
                         caller=self)

    def handle_included_method(self, name, function):
        function_id = id(function)
        function_class = function.__self__.__name__
        function_name = function.__name__
        info = (function_id, function_class, function_name)
        wrapped_function = self.generic_wrapper(info)
        self.check_not_visited(function, function_id)
        cache.id_dict[function_id] = function
        cache.visited_functions[function_id] = wrapped_function
        try:
            setattr(self.wrapped_obj, name, wrapped_function)
        except TypeError as e:
            logger.warning((
                f"cannot handle method {name}"),
                error=e, caller=self)
            if function_id in cache.id_dict:
                cache.id_dict.pop(function_id)
            if function_id in cache.visited_functions:
                cache.visited_functions.pop(function_id)
        except Exception as e:
            logger.critical(f"Unkown error while wrapping method {function} named {name}",
                            error=e, caller=self)
        else:
            logger.debug(
                f"[{self.get_name()}] Include method {name}", caller=self)

    def handle_included_function(self, name, function):
        function_id = id(function)
        function_module = function.__module__
        function_name = function.__name__
        assert function_module
        function_name = getattr(function, "__name__")
        info = (function_id, function_module, function_name)
        wrapped_function = self.generic_wrapper(info)
        self.check_not_visited(function, function_id)
        cache.id_dict[function_id] = function
        cache.visited_functions[function_id] = wrapped_function
        try:
            setattr(self.wrapped_obj, name, wrapped_function)
        except TypeError as e:
            logger.warning((f"[{self.wrapped_obj.__name__}]"
                            f"cannot handle method {name}"),
                           error=e, caller=self)
            if function_id in cache.id_dict:
                cache.id_dict.pop(function_id)
            if function_id in cache.visited_functions:
                cache.visited_functions.pop(function_id)
        except Exception as e:
            logger.critical(f"Unkown error while wrapping method {function} named {name}",
                            error=e, caller=self)
        else:
            logger.debug(
                f"[{self.get_name()}] Include function {name}", caller=self)

    def handle_visited_function(self, name, function):
        logger.debug(
            f"[{self.real_obj.__name__}] (Visited) Include method {name}")
        wrapped_function = cache.visited_functions[id(function)]
        setattr(self.wrapped_obj, name, wrapped_function)

    def handle_excluded_function(self, name, function):
        cache.visited_functions[id(function)] = function
        logger.debug(
            f"[{self.real_obj.__name__}] Exclude method {name}")

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
                f"Cannot handle basic object {name}", error=e, caller=self)
        except AttributeError as e:
            logger.warning(
                f"Cannot handle basic object {name}", error=e, caller=self)

    def handle_class(self, attr, clss):
        if clss in self.visited_class:
            if self.visited_class[clss] is not None:
                return self.visited_class[clss]
            return
        super().handle_class(attr, clss)
