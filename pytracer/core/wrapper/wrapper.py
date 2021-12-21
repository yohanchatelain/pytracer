import functools
import inspect
import types
from abc import ABCMeta, abstractmethod
from types import FunctionType, LambdaType, MappingProxyType, ModuleType

import pytracer
import pytracer.builtins
import pytracer.cache as cache
import pytracer.core.inout.writer as iowriter
from pytracer.core.inout.writer import Writer
from pytracer.core.wrapper.filter import FilterExclusion, FilterInclusion
from pytracer.utils.log import get_logger

visited_attr = "__Pytracer_visited__"

logger = get_logger()


def special_case(module, attr_obj):
    """
        Handle special case for module when the object is not
        recognize by the module inspect (ex: numpy.ufunc functions)
    """
    return False


def is_arithmetic_operator(name):
    _arithmetic_operator = [
        "__add__", "__floordiv__", "__mul__",
        "__matmul__", "__pow__", "__sub__", "__truediv__",
    ]
    return name in _arithmetic_operator


def is_special_attributes(name):
    return not is_arithmetic_operator(name) and \
        (name.startswith("__") and name.endswith("__"))


cached_error = set()

_pytracer_instance_attribute = '_Pytracer_instance'


class WrapperInstance:
    def __init__(self, name, module, function):
        if WrapperInstance.isinstance(function):
            logger.error(
                f'Instance {function} is already wrapped', caller=self)

        self._Pytracer_instance = True
        self._Pytracer_class_ = pytracer.builtins._builtins_type(self)
        self._function = function
        self._function_str = getattr(self._function, '__name__', name)
        self._name = name
        self._module = module

    def __getattribute__(self, name):
        if name == _pytracer_instance_attribute:
            return _pytracer_instance_attribute
        if name == '_name':
            return object.__getattribute__(self, '_name')
        if name == '_function':
            return object.__getattribute__(self, '_function')
        if name == '_function_str':
            return object.__getattribute__(self, '_function_str')
        if name == '_module':
            return object.__getattribute__(self, '_module')
        if name == '__module__':
            return object.__getattribute__(self, '_module')
        if name == '__call__':
            return object.__getattribute__(self, '__call__')
        if name == '_wrap':
            return object.__getattribute__(self, '_wrap')
        if name == '__getstate__':
            return object.__getattribute__(self, '__getstate__')
        if name == '__setstate__':
            return object.__getattribute__(self, '__setstate__')
        if name == '__reduce_ex__':
            return object.__getattribute__(self, '__reduce_ex__')
        if name == '__class__':
            return getattr(self._function, '__class__')
        if name == visited_attr:
            return True

        attribute = getattr(self._function, name)
        if callable(attribute) and not is_special_attributes(name):
            return self._wrap(attribute)
        else:
            return attribute

    def _wrap(self, attribute):
        def wrapper(*args, **kwargs):
            return Writer.write(attribute,
                                self._module,
                                self._name,
                                *args, **kwargs)
        return wrapper

    def __setstate__(self, state):
        print('setstate')
        self._function = state

    def __getstate__(self):
        print('getstate')
        return self._function

    def __reduce_ex__(self, protocol):
        print('reduce')
        return (self._function, ())

    def __call__(self, *args, **kwargs):
        _function = object.__getattribute__(self, '_function')
        _module = object.__getattribute__(self, '_module')
        _name = object.__getattribute__(self, '_name')
        # print(f'{_function} {_module} {_name}')
        return Writer.write(_function,
                            _module,
                            _name,
                            *args, **kwargs)

    def isinstance(_object):
        return hasattr(_object, _pytracer_instance_attribute)


def get_instance_wrapper(name, module, instance):
    wrapper = WrapperInstance(name, module, instance)
    ty = pytracer.builtins._builtins_type(instance)
    cache.add_type(wrapper, ty)

    if type(wrapper) != ty or not isinstance(wrapper, ty):
        logger.error(f'InstanceWrapper ({wrapper}) is not recognized as {ty}')

    return wrapper


def get_function_wrapper(name, module, function):
    wrapper = WrapperInstance(name, module, function)
    ty = pytracer.builtins._builtins_type(function)
    cache.add_type(wrapper, ty)

    if type(wrapper) != types.FunctionType:
        logger.error(f'FunctionWrapper ({wrapper}) is not recognized as {ty}')
    if type(wrapper) != types.BuiltinFunctionType:
        logger.error(f'FunctionWrapper ({wrapper}) is not recognized as {ty}')
    if not isinstance(wrapper, ty):
        logger.error(f'FunctionWrapper ({wrapper}) is not recognized as {ty}')

    return wrapper


class Wrapper(metaclass=ABCMeta):

    cache = set()
    wrapper_visited = set()
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
            self.obj_name = getattr(self.real_obj, "__name__")
            self.wrapped_obj = self.new_obj()
            self.init_attributes()
            self.populate(self.real_obj, self.attributes)
            self.update_globals()
            cache.add_global_mapping(self.real_obj, self.wrapped_obj)
            self.compute_dependencies(self.real_obj, self.wrapped_obj)
            self.update_dependencies(self.real_obj, self.wrapped_obj)

    @abstractmethod
    def new_obj(self):
        pass

    def init_attributes(self):
        self.attributes = list(vars(self.real_obj))

    def update_globals(self):
        for _, _globals in cache.globals_to_update.items():
            for _name, _value in _globals.items():
                if _value_wrapped := cache.get_global_mapping(_value):
                    _globals[_name] = _value_wrapped

    def mark_function_as_visited(self, func):
        logger.debug(f"Function {func} marked as visited", caller=self)
        setattr(func, visited_attr, True)

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

    def _get_dict(self, function, name):

        _dict = getattr(function, '__global__', {})
        _dict["generic_wrapper"] = getattr(self.wrapped_obj, "generic_wrapper")
        return _dict

    def _compute_dependencies_generic(self,
                                      original_object,
                                      wrapped_object,
                                      map_name,
                                      dependency_map):

        try:
            _map_original = getattr(original_object, map_name, {})
            if isinstance(_map_original, MappingProxyType):
                return
            _map_wrapper = getattr(wrapped_object, map_name, {})
            for _name, _referenced_object in _map_original.items():
                if not callable(_referenced_object) and \
                        not inspect.ismodule(_referenced_object):
                    continue
                if _name.startswith('__') and _name.endswith('__'):
                    continue
                # if _name == "_preprocess_data":
                #     continue
                is_same_object = id(_referenced_object) == id(original_object)
                _wrapped_referenced_object = cache.get_global_mapping(
                    _referenced_object)

                if not is_same_object and\
                        _wrapped_referenced_object is not None:
                    _map_wrapper[_name] = _wrapped_referenced_object

                else:
                    _id = id(_referenced_object)
                    if not (s := dependency_map.get(_id, set())):
                        dependency_map[id(_referenced_object)] = s
                    s.add((_name, original_object))
                    _map_wrapper[_name] = _referenced_object

        except Exception as e:
            msg = f"Error while computing dependencies of {original_object}"
            logger.critical(msg, caller=self, error=e)

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

    def handle_excluded_function(self, name, function):
        cache.increment_exclude(self.real_obj, 'function')
        logger.debug(f"[{self.get_name()}] Excluded function {name}")
        if self.islambda(function):
            self.handle_excluded_lambda(name, function)
            return

        cache.add_global_mapping(function, function)
        # self.compute_dependencies(function, function)

        setattr(self.wrapped_obj, name, function)
        cache.id_dict[id(function)] = function
        cache.visited_functions[id(function)] = function

    def handle_included_function(self, name, function):
        cache.increment_include(self.real_obj, 'function')
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

        if func_module is None and func_name is None:
            logger.error(f'Included function {function} has no name')

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

        if exclude:
            self.handle_excluded_function(name, function)
        else:
            self.handle_included_function(name, function)

    def ismodule(self, attr):
        """
        Check if the attribute is a module
        """
        return inspect.ismodule(attr)

    def update_module_depedencies(self, module):
        for attribute_name, attribute in vars(module).items():
            wrapped_attribute = cache.get_global_mapping(attribute)
            if wrapped_attribute is not None:
                setattr(module, attribute_name, wrapped_attribute)

    def handle_module(self, attr, submodule, exclude=False):
        """
        Handler for submodules
        """
        logger.debug(f"[ModuleHandler] {attr} -> {submodule}", caller=self)

        if submodule_wrapped := cache.get_global_mapping(submodule):
            submodule = submodule_wrapped

        if submodule.__name__ not in cache.module_to_not_update:
            self.update_module_depedencies(submodule)

        setattr(self.wrapped_obj, attr, submodule)

    def isclass(self, attr):
        """
            Check if the attribute is a class
        """
        return inspect.isclass(attr)

    def handle_included_class(self, name, clss):
        cache.increment_include(self.real_obj, 'classe')
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

        debug_msg = (f"[ClassHandler] {clss} ({hex(id(clss))})"
                     f" -> "
                     f"{class_wrp} ({hex(id(class_wrp))})")
        logger.debug(debug_msg, caller=self)

    def handle_excluded_class(self, name, clss):
        cache.increment_exclude(self.real_obj, 'classe')
        logger.debug(f"[{self.get_name()}] Excluded class {name}", caller=self)
        classname = getattr(clss, "__name__")
        logger.debug(f"Normal class {clss}", caller=self)
        cache.add_global_mapping(clss, clss)
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
        cache.increment_include(self.real_obj, 'basic')
        logger.debug(f"[{self.get_name()}] Included basic {name}", caller=self)
        wrp_obj = obj
        if not hasattr(obj, visited_attr) and callable(obj):
            wrp_obj = get_instance_wrapper(name, self.get_name(), obj)
            cache.add_global_mapping(obj, wrp_obj)
        setattr(self.wrapped_obj, name, wrp_obj)

    def handle_excluded_basic(self, name, obj):
        cache.increment_exclude(self.real_obj, 'basic')
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

        if name == "__spec__":
            obj.origin = "Pytracer"
            setattr(self.wrapped_obj, name, obj)
            return

        if name == ("__cached__", "__file__"):
            return

        if exclude:
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
            difference = /
            complement = ^
                    Object              |     Included    | Excluded
            -----------------------------------------------------------
                Include and     Exclude | I / (I ∩ E)     | I ∩ E
                Include and not Exclude | I               | I^
            not Include and     Exclude | E^              | E
            not Include and not Exclude | A               | o

                Attributes
            ---------------------------------------------------
            | Include     Exclude |    Included     | Excluded
            |  *            *     |       o         |    A
            |  I            *     |       o         |    A
            |  *            E     |       E^        |    E
            |  I            E     |   I / (I ∩ E)   |  I' ∪ (I ∩ E)
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

        io = self.included.has_module(obj)
        eo = self.excluded.has_module(obj)
        ia = self.included.has_function(attr, obj)
        ea = self.excluded.has_function(attr, obj)

        logger.debug(f"Is module {obj} included: {io}",
                     caller=self)
        logger.debug(f"Is module {obj} excluded: {eo}",
                     caller=self)
        logger.debug(f"Has module {obj} function {attr} included: {ia}",
                     caller=self)
        logger.debug(f"Has module {obj} function {attr} excluded: {ea}",
                     caller=self)

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
        if (module := inspect.getmodule(_object)) is not None:
            return module.__name__
        if inspect.isclass(_object):
            return getattr(_object, "__module__")
        elif inspect.isfunction(_object):
            return getattr(_object, "__module__")
        elif inspect.ismethod(_object) or inspect.ismethoddescriptor(_object):
            module = inspect.getmodule(_object)
            return self.get_object_name(module, '')
        elif inspect.ismodule(_object):
            return None
        else:
            return None

    def get_object_name(self, _object, name):

        if inspect.isclass(_object):
            return getattr(_object, "__name__")
        elif inspect.isfunction(_object):
            name = getattr(_object, "__name__")
            return getattr(_object, "__qualname__", name)
        elif inspect.ismethod(_object) or inspect.ismethoddescriptor(_object):
            if inspect.isbuiltin(_object):
                return getattr(_object, "__name__")
            if qualname := getattr(_object, "__qualname__", None):
                return qualname.split('.')[0]
            return getattr(_object, "__name__", name)
        elif inspect.ismodule(_object):
            return getattr(_object, "__name__")
        else:
            return None

    def is_instrumented(self, _object):
        return hasattr(_object, visited_attr) or\
            WrapperInstance.isinstance(_object)

    def handle_excluded(self, _attribute_name, _attribute):
        setattr(self.wrapped_obj, _attribute_name, _attribute)

    def populate(self, _object, _attributes_names):
        """
            Create wrapper for each attribute in the module
        """
        for attribute_name in _attributes_names:
            cache.increment_visit(_object)
            attribute = vars(_object)[attribute_name]

            if is_special_attributes(attribute_name):
                continue

            if isinstance(attribute, functools.partial):
                setattr(self.wrapped_obj, attribute_name, attribute)
                continue

            if self.is_instrumented(attribute):
                self.handle_excluded(attribute_name, attribute)
                continue

            logger.debug(f'attribute {attribute_name}', caller=self)
            module_name = self.get_module_name(attribute)
            logger.debug(f'module_name {module_name}', caller=self)
            module_name = module_name if module_name else self.get_name()
            object_name = self.get_object_name(attribute, attribute_name)
            logger.debug(f'object_name {object_name}', caller=self)
            object_name = object_name if object_name else attribute_name

            exclude = self.is_excluded(module_name,
                                       object_name,
                                       is_module=inspect.ismodule(attribute))

            if self.isspecialattr(attribute_name):
                self.handle_special(attribute_name, attribute)
            elif self.isclass(attribute):
                if issubclass(attribute, dict):
                    self.handle_basic(
                        attribute_name, attribute, exclude=exclude)
                else:
                    self.handle_class(
                        attribute_name, attribute, exclude=exclude)
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
        setattr(self.wrapped_obj, "generic_wrapper",
                Writer.write_function)


class WrapperClass(Wrapper):

    visited_class = {}
    special_attributes = ["__class__", "__dict__", "__base__", "__bases__",
                          "__basicsize__", "__dictoffset__", "__flags__",
                          "__itemsize__", "__mro__", "__text_signature__",
                          "__weakrefoffset__", "__doc__", "__delattr__",
                          "__eq__", "__neq__", "__dir__", "__format__",
                          "__ge__", "__getattribute__", "__getstate__",
                          "__new__", "__reduce__", "__reduce_ex__",
                          "__repr__", "__setattr__", "__setstate__"]

    def generic_wrapper(self, info):
        _wrapper = self.writer.write_function

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
                error = (f"Function registered={registered} "
                         f"and not visited={visited}")
                logger.error(error)
        elif exclude:
            self.handle_excluded_function(name, function)
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
            error_msg = (f"Function {function} (id:{hex(function_id)}) "
                         f"has been registered twice")
            logger.error(error_msg, caller=self)

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
        if not hasattr(wrapped_function, visited_attr):
            logger.error(f'Included method has no {visited_attr} set')
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
            error_msg = (f"Unkown error while wrapping "
                         f"method {function} named {name}")
            logger.critical(error_msg, error=e, caller=self)
        else:
            debug_msg = f"[{self.get_name()}] Include methoddescriptor {name}"
            logger.debug(debug_msg, caller=self)

    def handle_included_function(self, name, function):
        function_id = id(function)
        function_module = function.__module__
        function_name = function.__qualname__

        if function_module is None:
            logger.error(f'Included function {function} has no module name')

        info = (function_id, function_module, function_name)
        wrapped_function = self.generic_wrapper(info)
        self.mark_function_as_visited(wrapped_function)
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
            error_msg = (f"Unkown error while "
                         f"wrapping method {function} named {name}")
            logger.critical(error_msg, error=e, caller=self)
        else:

            debug_msg = (f"[{self.get_name()}] "
                         f"Include function {function_name} ({function_id})")
            logger.debug(debug_msg, caller=self)

    def handle_visited_function(self, name, function):
        debug_msg = (f"[{self.real_obj.__name__}] (Visited) "
                     f"Include method {name} ({id(function)})")
        logger.debug(debug_msg)
        wrapped_function = cache.visited_functions[id(function)]
        try:
            setattr(self.wrapped_obj, name, wrapped_function)
        except TypeError:
            pass

    def handle_excluded_function(self, name, function):
        cache.visited_functions[id(function)] = function
        cache.add_global_mapping(function, function)

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
