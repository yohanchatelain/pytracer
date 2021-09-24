import functools
import importlib
import inspect
import os
import re
import sys
from abc import ABCMeta, abstractmethod
from types import FunctionType, LambdaType, ModuleType, MappingProxyType

import pytracer.core.inout.writer as iowriter
import pytracer.core.wrapper.cache as cache
from pytracer.core.config import DictAtKeyError
from pytracer.core.config import config as cfg
from pytracer.utils.log import get_logger
from pytracer.utils.singleton import Singleton
from pytracer.utils import ishashable

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
            logger.error(
                f"exclude-file {cfg.exclude_file} not found", caller=self, error=e, raise_error=False)
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
            python_modules_path = f"{sys.base_prefix}/lib/python{major}.{minor}"
            python_modules = os.listdir(python_modules_path)
            for python_module in python_modules:
                if python_module.endswith(".py"):
                    python_module, _ = os.path.splitext(python_module)
                self._add(python_module, "*")


def instance_wrapper(function):
    writer = iowriter.Writer
    _wrapper = iowriter.wrapper_instance

    def wrapper(self, *args, **kwargs):
        return _wrapper(writer, self, *args, **kwargs)

    # for attr in dir(function):
    #     try:
    #         obj = getattr(function, attr, None)
    #         setattr(function, attr, obj)
    #     except Exception:
    #         continue

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
    new_attributes[visited_attr] = True
    for name, attr in attributes.items():
        if callable(attr) and not is_special_attributes(name):
            new_attributes[name] = instance_wrapper(attr)

    return new_attributes


cached_error = set()


# TODO: Fix wrap_instance by loading numpy at the end of the instrumentation
def wrap_instance(name, instance):

    x = None

    if False:  # isinstance(instance, cache.hidden.ufunc):
        if cfg.numpy.ufunc:
            nin = instance.nin
            nout = instance.nout
            wrp_instance = instance_wrapper_ufunc(instance)
            x = cache.hidden.frompyfunc(
                wrp_instance, nin, nout, identity=instance.identity)
        else:
            x = None
    else:

        try:
            instance.__call__ = instance_wrapper(instance.__call__)
            x = instance
        except AttributeError:
            pass

        # attributes = {name: getattr(instance, name)
        #               for name in dir(instance)}

        # new_attributes = prepare_attributes(attributes)
        # clss = instance.__class__
        # clss_name = clss.__name__
        # try:
        #     wrapped_instance = type(clss_name, (clss,), new_attributes)
        #     x = wrapped_instance.__new__(wrapped_instance)

        #     for attr_instance in dir(instance):
        #         iv = getattr(instance, attr_instance)
        #         ix = getattr(x, attr_instance)
        #         if iv != ix:
        #             # if not cache.hidden.isnan(iv):
        #             if not str(float(iv)) == 'nan':
        #                 logger.error(
        #                     f"Attributes {attr_instance} differs {iv} {ix} {type(iv)} {type(ix)}")

        # except Exception as e:
        #     logger.warning(
        #         f"Instance {name} of {repr(instance)} cannot be wrapped", error=e)
        #     x = None

    return x


class Wrapper(metaclass=ABCMeta):

    cache = set()
    wrapped_cache = set()
    wrapper_visited = set()
    m2wm = {}
    modules_not_initialized = {}

    def __init__(self, obj, parent=None):
        if hasattr(obj, visited_attr):
            logger.error("Object {obj} already visited", caller=self)
        else:
            self.writer = iowriter.Writer
            self.lazy_dict = {}
            self.included = FilterInclusion()
            self.excluded = FilterExclusion()
            self.real_obj = obj
            self.parent_obj = parent
            self.obj_name = getattr(self.real_obj, "__name__")
            self.wrapped_obj = self.new_obj()
            self.init_attributes()
            Wrapper.wrapped_cache.add(self.wrapped_obj)
            self.populate(self.real_obj, self.attributes)
            self.update_globals()
            Wrapper.m2wm[self.real_obj] = self.wrapped_obj
            cache.add_global_mapping(self.real_obj, self.wrapped_obj)
            self.compute_dependencies(self.real_obj, self.wrapped_obj)
            self.update_dependencies(self.real_obj, self.wrapped_obj)

    @ abstractmethod
    def new_obj(self):
        pass

    def init_attributes(self):
        self.attributes = dir(self.real_obj)

    def update_globals(self):

        for _, _globals in cache.globals_to_update.items():
            for _name, _value in _globals.items():
                if _value_wrapped := cache.get_global_mapping(_value):
                    _globals[_name] = _value_wrapped

    def mark_function_as_visited(self, func):
        logger.debug(f"Function {func} marked as visited", caller=self)
        setattr(func, visited_attr, True)

    def assert_lazy_modules_loaded(self):
        entry = 0
        no_entry = 0
        total_entry = len(Wrapper.m2wm)

        required_modules = cache.required_modules[self.real_obj]
        total_entry = len(required_modules)

        logger.info(
            f"Lazy evaluation for module: {self.obj_name}", caller=self)
        logger.info(
            f"Ensure that all lazy modules ({total_entry}) have been initialized", caller=self)
        modules_not_init = []

        for required_module in required_modules:
            if cache.get_global_mapping(required_module) is None:
                no_entry += 1
                modules_not_init.append(str(required_module))
            else:
                entry += 1

        logger.debug(f"\tTotal_entry: {total_entry}", caller=self)
        logger.debug(f"\t      entry: {entry}", caller=self)
        logger.debug(f"\t      empty: {no_entry}", caller=self)

        if (entry == total_entry):
            logger.info("All modules have been initialized", caller=self)
        else:
            msg = "\n".join(modules_not_init)
            logger.error(
                f"{no_entry} modules have not been initialized{os.linesep}{msg}", caller=self)

        # cache.modules_not_initialized[self.wrapped_obj] = module

    def assert_lazy_attributes_are_initialized(self):
        for (submodule, attrs) in self.modules_not_initialized.items():
            for attr, wrp_module in attrs:
                setattr(wrp_module, attr, Wrapper.m2wm[submodule])

    def flush_cache(self):
        self.m2wm.clear()

    def get_name(self):
        return self.obj_name

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
        info = (function_id, function_module, function_name)
        wrapper_code = f"""def {function_wrapper_name}(*args, **kwargs):
            return generic_wrapper({info},*args,**kwargs)
        """
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
        cache.add_global_mapping(function, function)
        setattr(self.wrapped_obj, name, function)

    def handle_excluded_lambda(self, name, function):
        """
        Handler for lambda functions
        """
        cache.visited_functions[id(function)] = function
        cache.add_global_mapping(function, function)
        setattr(self.wrapped_obj, name, function)

    def handle_excluded_function(self, name, function):
        logger.debug(f"[{self.get_name()}] Excluded function {name}")
        if self.islambda(function):
            self.handle_excluded_lambda(name, function)
            return

        cache.add_global_mapping(function, function)
        # self.compute_dependencies(function, function)

        setattr(self.wrapped_obj, name, function)
        cache.id_dict[id(function)] = function
        cache.visited_functions[id(function)] = function

    def _get_dict(self, function, name):

        _dict = getattr(function, '__global__', {})
        _dict["generic_wrapper"] = getattr(self.wrapped_obj, "generic_wrapper")
        return _dict

        new_func_dict = {
            "generic_wrapper": getattr(self.wrapped_obj, "generic_wrapper")}

        for attr in dir(function):
            # Cause segfault with dipy
            if attr in ("__kwdefaults__"):
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

    def _compute_dependencies_generic(self, original_object,
                                      wrapped_object, map_name, dependency_map):

        try:
            _map_original = getattr(original_object, map_name, {})
            if isinstance(_map_original, MappingProxyType):
                return
            _map_wrapper = getattr(wrapped_object, map_name, {})
            for _name, _referenced_object in _map_original.items():
                if not callable(_referenced_object) and not inspect.ismodule(_referenced_object):
                    continue
                if _name.startswith('__') and _name.endswith('__'):
                    continue
                if _name == "_preprocess_data":
                    continue
                is_same_object = id(_referenced_object) == id(original_object)
                _wrapped_referenced_object = cache.get_global_mapping(
                    _referenced_object)

                if not is_same_object and _wrapped_referenced_object is not None:
                    _map_wrapper[_name] = _wrapped_referenced_object

                else:
                    if not (s := dependency_map.get(id(_referenced_object), set())):
                        dependency_map[id(_referenced_object)] = s
                    s.add((_name, original_object))
                    _map_wrapper[_name] = _referenced_object

        except Exception as e:
            logger.critical(
                f"Error while computing dependencies of {original_object}", caller=self, error=e)

    def compute_dependencies(self, original_object, wrapped_object):
        self._compute_dependencies_generic(
            original_object,
            wrapped_object,
            "__globals__",
            cache.function_to_dependencies_globals)
        self._compute_dependencies_generic(
            original_object,
            wrapped_object,
            "__dict__",
            cache.function_to_dependencies_dict)

    def _update_dependencies_generic(self, original_object,
                                     wrapped_object,
                                     map_name,
                                     dependency_map):
        if (to_modify := dependency_map.get(id(original_object), None)):
            for _name, _object in to_modify:
                getattr(_object, map_name)[_name] = wrapped_object

    def update_dependencies(self, original_object, wrapped_object):
        self._update_dependencies_generic(
            original_object,
            wrapped_object,
            "__globals__",
            cache.function_to_dependencies_globals)
        self._update_dependencies_generic(
            original_object,
            wrapped_object,
            "__dict__",
            cache.function_to_dependencies_dict)

    def get_function_path(self, function):
        try:
            return inspect.getfile(function)
        except TypeError:
            return "<string>"

    def handle_included_function(self, name, function):
        logger.debug(
            f"[{self.get_name()}] Included function {name}", caller=self)
        if self.islambda(function):
            self.handle_included_lambda(name, function)
            return

        func_dict = self._get_dict(function, name)

        func_name = getattr(function, "__name__", name)
        func_module = getattr(function, "__module__", self.get_name())
        func_name = func_name if func_name else name
        func_module = func_module if func_module else self.get_name()

        assert(func_module and func_name)
        info = (func_module, func_name)
        wrapped_fun = self.getwrapperfunction(info, function, name)
        code = compile(wrapped_fun, "", "exec")
        function_wrapped = FunctionType(code.co_consts[0], func_dict, name)

        for attr in dir(function):
            if attr in ("__globals__", "__code__"):
                continue
            try:
                obj = getattr(function, attr)
                new_obj = getattr(function_wrapped, attr)
                if id(obj) != new_obj:
                    setattr(function_wrapped, attr, obj)
            except Exception:
                continue

        if _globals := getattr(function, '__global__', None):
            cache.globals_to_update[id(_globals)] = _globals

        cache.add_global_mapping(function, function_wrapped)
        self.mark_function_as_visited(function_wrapped)
        setattr(self.wrapped_obj, name, function_wrapped)
        cache.id_dict[id(function)] = function
        cache.visited_functions[id(function)] = function_wrapped
        cache.add_global_mapping(function, function_wrapped)
        self.compute_dependencies(function, function_wrapped)
        self.update_dependencies(function, function_wrapped)

    def handle_function(self, name, function, module=None, exclude=False):
        """
        Handler for functions
        """

        logger.debug(f"[FunctionHandler] {name} -> {function}", caller=self)

        if isinstance(function, functools.partial):
            setattr(self.wrapped_obj, name, function)
            return

        alias_function_name = name
        function_name = getattr(function, "__name__", name)
        names = (alias_function_name, function_name)
        module_name = module if module else getattr(
            function, "__module__", self.obj_name)

        fid = id(function)

        if fid in cache.id_dict:
            logger.debug(f"Function {name} ({function}) cached")
            cached_function = cache.visited_functions[fid]
            try:
                setattr(self.wrapped_obj, name, cached_function)
            except TypeError as e:
                logger.warning(
                    f"Cannot set attribute {name}", caller=self, error=e)
            return

        if hasattr(function, visited_attr):
            logger.debug(f"Function {name} {function} has been visited ")
            setattr(self.wrapped_obj, name, function)
            return

        if fid in cache.id_dict:
            logger.error(
                f"Function {function} in cache (id:{fid} -> {cache.id_dict[fid]}) but not visited",
                caller=self)

        logger.debug(
            f"Handling function {name} from {module_name} ({id(function)})", caller=self)

        if exclude:
            self.handle_excluded_function(alias_function_name, function)
        elif is_arithmetic_operator(name):
            self.handle_included_function(alias_function_name, function)
        elif function_name == ("generic_wrapper", "_generic_wrapper"):
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

    def ismodule(self, attr):
        """
        Check if the attribute is a module
        """
        return inspect.ismodule(attr)

    def handle_module(self, attr, submodule, exclude=False):
        """
        Handler for submodules
        """
        logger.debug(f"[ModuleHandler] {attr} -> {submodule}", caller=self)

        if submodule_wrapped := cache.get_global_mapping(submodule):
            submodule = submodule_wrapped

        if inspect.ismodule(self.real_obj) and not exclude:
            if required_modules := cache.required_modules.get(self.real_obj, None):
                required_modules.append(submodule)
            else:
                cache.required_modules[self.real_obj] = [submodule]

        setattr(self.wrapped_obj, attr, submodule)

    def isclass(self, attr):
        """
            Check if the attribute is a class
        """
        return inspect.isclass(attr)

    def handle_included_class(self, name, clss):
        logger.debug(f"[{self.get_name()}] Included class {name}", caller=self)
        wrp = WrapperClass(clss)
        class_wrp = wrp.get_wrapped_object()
        cache.add_global_mapping(clss, class_wrp)
        self.compute_dependencies(clss, class_wrp)
        self.update_dependencies(clss, class_wrp)
        classname = getattr(clss, "__name__")
        logger.debug(f"Wrapped class {class_wrp}", caller=self)
        setattr(self.wrapped_obj, name, class_wrp)
        setattr(self.wrapped_obj, classname, class_wrp)

        logger.debug(
            f"[ClassHandler] {clss} ({hex(id(clss))}) -> {class_wrp} ({hex(id(class_wrp))})", caller=self)

    def handle_excluded_class(self, name, clss):
        logger.debug(f"[{self.get_name()}] Excluded class {name}", caller=self)
        classname = getattr(clss, "__name__")
        logger.debug(f"Normal class {clss}", caller=self)
        cache.add_global_mapping(clss, clss)
        # self.compute_dependencies(clss, clss)
        # self.update_dependencies(clss, clss)
        setattr(self.wrapped_obj, name, clss)
        setattr(self.wrapped_obj, classname, clss)

    def handle_class(self, attr, clss, exclude=False):
        """
            Handler for class
        """
        logger.debug(f"[ClassHandler] {attr} -> {clss}", caller=self)

        if id(clss) in WrapperClass.visited_class:
            logger.debug(f"{clss} has been visited", caller=self)
            if WrapperClass.visited_class[id(clss)] is not None:
                setattr(self.wrapped_obj, attr,
                        WrapperClass.visited_class[id(clss)])
            else:
                setattr(self.wrapped_obj, attr, None)
            return

        modname = getattr(clss, "__module__", "")
        clssname = getattr(clss, "__name__")
        logger.debug(
            f"Handling class {clssname} from module {modname}", caller=self)

        if exclude:
            self.handle_excluded_class(attr, clss)
        elif inspect.isabstract(clss):
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
            wrp_obj = wrap_instance(name, obj)
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

    def handle_basic(self, name, obj, exclude=False):
        """
            Handler for basic objects
        """

        obj_name = getattr(obj, "__name__", "")
        names = (name, obj_name)
        module_name = self.get_name()

        if name == "__spec__":
            obj.origin = "Pytracer"
            setattr(self.wrapped_obj, name, obj)
            return

        if name == ("__cached__", "__file__"):
            return

        if self.is_hashable(obj) and obj in Wrapper.m2wm:
            self.handle_excluded_basic(name, Wrapper.m2wm[obj])
        elif exclude:
            self.handle_excluded_basic(name, obj)
        # Dirty hack to check if the object
        # is a fortran object. We cannot check
        # the type because it exists several
        # class fortran implementation (not the same id)
        # If it's a fortran function, we exclude it
        # elif str(obj) == cache.hidden.daxpy_str:
        #     self.handle_excluded_basic(name, obj)
        elif isinstance(obj, functools.partial):
            self.handle_excluded_basic(name, obj)
        elif hasattr(obj, visited_attr):
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
        logger.debug(f"[SpecialHandler] {attr}", caller=self)
        try:
            setattr(self.wrapped_obj, attr, attr_obj)
        except Exception as e:
            logger.critical(f"{self} {attr} {attr_obj}", error=e, caller=self)

    def is_excluded(self, obj, attr, is_module=False):
        """
            A = {set of all attributes for a object}
            o = {empty set}
            I = {set of included attributes}
            E = {set of excluded attributes}
            intersection = ∩
            union = ∪
            difference = \
            complement = ^
                    Object              |     Included    | Excluded
            -----------------------------------------------------------
                Include and     Exclude | I \ (I ∩ E)     | I ∩ E
                Include and not Exclude | I               | I^
            not Include and     Exclude | E^              | E
            not Include and not Exclude | A               | o

                Attributes
            ---------------------------------------------------
            | Include     Exclude |    Included     | Excluded
            |  *            *     |       o         |    A
            |  I            *     |       o         |    A
            |  *            E     |       E^        |    E
            |  I            E     |   I \ (I ∩ E)   |  I' ∪ (I ∩ E)
            ---------------------------------------------------
            |  *            -     |       A         |    o
            |  I            -     |       I         |    I^
            ----------------------------------------------------
            |  -            *     |       o         |    A
            |  -            E     |       E^        |    E
            ----------------------------------------------------
            |  -            -     |       A         |    o

            if io:
                if eo:
                    if ia and not ea:
                        include = True
                    else:
                        exclude = True
                else:  # not eo
                    if ia:
                        include = True
                    else:
                        exclude = True
            else:  # not io
                if eo:
                    if ea:
                        exclude = True
                    else:
                        include = True
                else: # not eo
                    include = True
        """
        if "pytracer.core" in obj:
            return True

        io = self.included.has_module(obj)
        eo = self.excluded.has_module(obj)
        ia = self.included.has_function(attr, obj)
        ea = self.excluded.has_function(attr, obj)

        # logger.debug(f"Is module {obj} included: {io}", caller=self)
        # logger.debug(f"Is module {obj} excluded: {eo}", caller=self)
        # logger.debug(
        #     f"Has module {obj} function {attr} included: {ia}", caller=self)
        # logger.debug(
        #     f"Has module {obj} function {attr} excluded: {ea}", caller=self)

        if is_module:
            if io:
                return False
            elif eo:
                return True
            else:
                return True

        if io:
            if eo:
                if ia and not ea:
                    exclude = False
                else:
                    exclude = True
            else:  # not eo
                if ia:
                    exclude = False
                else:
                    exclude = True
        else:  # not io
            if eo:
                if ea:
                    exclude = True
                else:
                    exclude = False
            else:  # not eo
                exclude = False

        return exclude

    def get_module_name(self, _object):
        if inspect.isclass(_object):
            return getattr(_object, "__module__")
        elif inspect.isfunction(_object):
            return getattr(_object, "__module__")
        elif inspect.ismethod(_object) or inspect.ismethoddescriptor(_object):
            module = inspect.getmodule(_object)
            return self.get_object_name(module)
        elif inspect.ismodule(_object):
            return None
        else:
            return None

    def get_object_name(self, _object):

        if inspect.isclass(_object):
            return getattr(_object, "__name__")
        elif inspect.isfunction(_object):
            return getattr(_object, "__qualname__", getattr(_object, "__name__"))
        elif inspect.ismethod(_object) or inspect.ismethoddescriptor(_object):
            if inspect.isbuiltin(_object):
                return getattr(_object, "__name__")
            if qualname := getattr(_object, "__qualname__", None):
                return qualname.split('.')[0]
            return getattr(_object, "__name__")
        elif inspect.ismodule(_object):
            return getattr(_object, "__name__")
        else:
            return None

    def populate(self, _object, _attributes_names):
        """
            Create wrapper for each attribute in the module
        """
        for attribute_name in _attributes_names:
            if isinstance(self, WrapperClass):
                attribute = _object.__dict__[attribute_name]
                attribute_obj = getattr(_object, attribute_name)
                module_name = self.get_module_name(attribute_obj)
                module_name = module_name if module_name else '*'
                object_name = attribute_name
            else:
                attribute = getattr(_object, attribute_name)
                if inspect.ismodule(attribute):
                    module_name = getattr(attribute, '__name__')
                    object_name = module_name
                else:
                    if hasattr(_object, "__module__") and hasattr(_object, "__qualname__"):
                        modulename = getattr(_object, "__module__")
                        qualname = getattr(_object, "__qualname__")
                        qualname = ".".join(qualname.split(".")[:-1])
                        obj_name = f"{modulename}.{qualname}"
                    else:
                        obj_name = getattr(_object, "__name__")

                    module_name = self.get_module_name(attribute)
                    module_name = module_name if module_name else obj_name
                    object_name = self.get_object_name(attribute)
                    object_name = object_name if object_name else attribute_name

            exclude = self.is_excluded(
                module_name, object_name, is_module=inspect.ismodule(attribute))

            logger.debug(
                f"[{self.obj_name}] Checking {attribute_name} at {hex(id(attribute))} : is excluded? {exclude}", caller=self)

            if self.isspecialattr(attribute_name):
                self.handle_special(attribute_name, attribute)
            elif self.isclass(attribute):
                self.handle_class(attribute_name, attribute, exclude=exclude)
            elif self.isfunction(attribute):
                self.handle_function(
                    attribute_name, attribute, exclude=exclude)
            elif self.ismodule(attribute):
                self.handle_module(attribute_name, attribute, exclude=exclude)
            else:
                self.handle_basic(attribute_name, attribute, exclude=exclude)


class WrapperModule(Wrapper):

    def new_obj(self):
        new_obj = ModuleType(self.get_name())
        logger.debug(
            f"New object created {new_obj} {hex(id(new_obj))}", caller=self)
        return new_obj

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

    visited_class = {}
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
        self.mark_function_as_visited(_generic_wrapper)
        return _generic_wrapper

    def __init__(self, clss):
        super().__init__(clss)
        self.module_class = getattr(self.real_obj, "__module__")
        wrp_class = self.get_wrapped_object()
        self.visited_class[id(self.real_obj)] = wrp_class
        cache.add_global_mapping(self.real_obj, wrp_class)

    def init_attributes(self):
        self.attributes = list(self.real_obj.__dict__.keys())
        self.writer = iowriter.Writer

    def get_module(self):
        if hasattr(self, "__module_name__"):
            return self.__module_name__
        self.__module_name__ = self.wrapped_obj.__module__
        return self.__module_name__

    def new_obj(self):
        if id(self.real_obj) in self.visited_class:
            if self.visited_class[id(self.real_obj)] is not None:
                return self.visited_class[id(self.real_obj)]
            return self.real_obj
        self.visited_class[id(self.real_obj)] = None
        return self.real_obj

    def is_cython_function(self, function):
        _ty = type(function)
        cython_types = ("cython_function_or_method",
                        "fused_cython_function")
        return _ty.__name__ in cython_types

    def isstatic(self, function):
        if isinstance(function, (classmethod, staticmethod)):
            return True
        try:
            src = inspect.getsource(function)
            if ('@staticmethod' in src) or ('@classmethod' in src):
                return True
        except (TypeError, OSError):
            pass

        try:
            sig = inspect.signature(function)
            if list(sig.parameters)[0] != 'self':
                return True
        except Exception:
            pass

        return False

    def handle_function(self, name, function, exclude=False):
        registered = id(function) in cache.id_dict
        visited = id(function) in cache.visited_functions
        if registered and visited:
            self.handle_visited_function(name, function)
        elif registered:
            if not visited:
                logger.error(
                    f"Function registered={registered} and not visited={visited}")
        elif exclude:
            self.handle_excluded_function(name, function)
        # elif str(function) == cache.hidden.daxpy_str:
        #     self.handle_excluded_function(name, function)
        elif self.isstatic(function):
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
            module_name = f"{self.get_module()}.{self.obj_name}"
            super().handle_function(name, function, module=module_name)

    def check_not_visited(self, function, function_id):
        if function_id in cache.id_dict:
            logger.error(f"Function {function} (id:{hex(function_id)}) has been registered twice",
                         caller=self)

    def handle_included_methoddescriptor(self, name, function):
        function_id = id(function)
        function_class = function.__objclass__.__name__
        function_name = function.__qualname__
        info = (function_id, function_class, function_name)
        wrapped_function = self.generic_wrapper(info)
        self.check_not_visited(function, function_id)
        cache.id_dict[function_id] = function
        cache.visited_functions[function_id] = wrapped_function
        cache.add_global_mapping(function, wrapped_function)
        # self.compute_dependencies(function, wrapped_function)
        # self.update_dependencies(function, wrapped_function)
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

    # TODO: This function should be safely removed
    #       since Class object contains function
    #       method are for instances class
    def handle_included_method(self, name, function):
        function_id = id(function)
        function_class = function.__self__.__name__
        function_name = function.__qualname__
        # function_name = function.__name__
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
                f"[{self.get_name()}] Include method {function_name}", caller=self)

    def handle_included_function(self, name, function):
        function_id = id(function)
        function_module = function.__module__
        function_name = function.__qualname__
        assert function_module
        info = (function_id, function_module, function_name)
        wrapped_function = self.generic_wrapper(info)
        self.check_not_visited(function, function_id)
        cache.id_dict[function_id] = function
        cache.visited_functions[function_id] = wrapped_function
        cache.add_global_mapping(function, wrapped_function)

        if _globals := getattr(function, '__global__', None):
            cache.globals_to_update[id(_globals)] = _globals

        self.compute_dependencies(function, wrapped_function)
        self.update_dependencies(function, wrapped_function)

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
                f"[{self.get_name()}] Include function {function_name} ({function_id})", caller=self)

    def handle_visited_function(self, name, function):
        logger.debug(
            f"[{self.real_obj.__name__}] (Visited) Include method {name} ({id(function)})")
        wrapped_function = cache.visited_functions[id(function)]
        try:
            setattr(self.wrapped_obj, name, wrapped_function)
        except TypeError as e:
            pass

    def handle_excluded_function(self, name, function):
        cache.visited_functions[id(function)] = function
        cache.add_global_mapping(function, function)
        # self.compute_dependencies(function, function)
        # self.update_dependencies(function, function)

        logger.debug(
            f"[{self.real_obj.__name__}] Exclude method {name}")

    def handle_special(self, attr, attr_obj):
        logger.debug(f"[SpecialHandler] {attr}", caller=self)
        if attr.startswith("__") and attr.endswith("__"):
            return
        if attr in self.special_attributes:
            return
        super().handle_special(attr, attr_obj)

    def handle_basic(self, name, obj, exclude=False):
        try:
            if exclude:
                super().handle_excluded_basic(name, obj)
            else:
                super().handle_basic(name, obj)
            logger.debug(
                f"[{self.get_name()}] Include object {name}", caller=self)
        except TypeError as e:
            logger.warning(
                f"Cannot handle basic object {name}", error=e, caller=self)
        except AttributeError as e:
            logger.warning(
                f"Cannot handle basic object {name}", error=e, caller=self)

    def handle_class(self, attr, clss, exclude=False):
        if id(clss) in self.visited_class:
            if self.visited_class[id(clss)] is not None:
                return self.visited_class[id(clss)]
            return
        super().handle_class(attr, clss, exclude=exclude)
