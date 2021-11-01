import tempfile
import textwrap
import builtins
import collections
import types
import traceback
import functools
import importlib
import inspect
import os
import re
import sys
from abc import ABCMeta, abstractmethod
from types import FunctionType, LambdaType, MappingProxyType, ModuleType

import pytracer.builtins
import pytracer.cache as cache
import pytracer.core.inout.writer as iowriter
from pytracer.core.config import DictAtKeyError
from pytracer.core.config import config as cfg
from pytracer.core.inout.writer import Writer
from pytracer.utils.log import get_logger
from pytracer.utils.singleton import Singleton

visited_attr = "__Pytracer_visited__"

logger = get_logger()


def iX(obj):
    return hex(id(obj))


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

    def print(self):
        for module, function in self.__modules.items():
            logger.debug(f"{module}:{function}", caller=self)


class FilterInclusion(Filter, metaclass=Singleton):

    def __init__(self):
        try:
            super().__init__(cfg.include_file)
            self.print()
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
            self.print()
        except DictAtKeyError:
            logger.debug("No filenames provided", caller=self)
            super().__init__(None)
        except FileNotFoundError as e:
            logger.error(
                f"exclude-file {cfg.exclude_file} not found", caller=self, error=e, raise_error=False)
        self.default_exclusion()

    def default_exclusion(self):
        modules_to_load = [module.strip() for module in cfg.modules_to_load]

        self._add(builtins.__name__, '*')

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


_pytracer_class_attribute = '_Pytracer_class'
_pytracer_instance_attribute = '_Pytracer_instance'


def get_object_name(_object):

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


def get_module_name(_object):
    if inspect.isclass(_object):
        return getattr(_object, "__module__")
    elif inspect.isfunction(_object):
        return getattr(_object, "__module__")
    elif inspect.ismethod(_object) or inspect.ismethoddescriptor(_object):
        module = inspect.getmodule(_object)
        return get_object_name(module)
    elif inspect.ismodule(_object):
        return None
    else:
        return None


def is_arithmetic_operator(name):
    _arithmetic_operator = [
        "__add__", "__floordiv__", "__mul__",
        "__matmul__", "__pow__", "__sub__", "__truediv__",
    ]
    return name in _arithmetic_operator


def is_special_attributes(name):
    return not is_arithmetic_operator(name) and \
        (name.startswith("__") and name.endswith("__"))


def safe_return(_return):
    (outputs, error) = _return
    if error is None:
        return outputs
    else:
        raise error


class WrapperFunction:
    def __init__(self, name, module, function):
        if WrapperFunction.isinstance(function):
            logger.error(
                f'Instance {function} is already wrapped', caller=self)

        # print(f'Wrap {name} {module} instance {function}')
        self._Pytracer_class_ = pytracer.builtins._builtins_type(self)
        self._function = function
        self._pytracer_instance_attribute = _pytracer_instance_attribute
        self._name = name
        self._function_str = getattr(self._function, '__name__', name)
        self._module = module
        try:
            self._function.__doc__ = ''
        except Exception:
            pass

    def __getattribute__(self, name):
        if name == '_name':
            return object.__getattribute__(self, '_name')
        if name == '_function':
            return object.__getattribute__(self, '_function')
        if name == '_function_str':
            return object.__getattribute__(self, '_function_str')
        elif name == '_module':
            return object.__getattribute__(self, '_module')

        # print(
        #     f'[WrapperInstance] getattribute {name} of {self._module}.{self._name} ({self._function_str})')

        if name == '__call__':
            return object.__getattribute__(self, '__call__')
        elif name == '_wrap':
            return object.__getattribute__(self, '_wrap')
        elif name == '__class__':
            return getattr(self._function, '__class__')
        elif name == visited_attr:
            return True
        elif name == _pytracer_instance_attribute:
            return _pytracer_instance_attribute
        else:
            attribute = getattr(self._function, name)
            return attribute
            # print(f'[WrapperInstance] attribute {name} is {attribute}')
            # return attribute
            # return getattr(self._function, name)
            if callable(attribute) and not is_special_attributes(name):
                # print('{name} is callable {attribute}')
                return self._wrap(attribute)
            else:
                # print(f'{name} is not callable {attribute}')
                return attribute

            return getattr(self._function, name)

    def _wrap(self, attribute):
        def wrapper(*args, **kwargs):
            return safe_return(Writer.write(attribute,
                                            self._module,
                                            self._name,
                                            *args, **kwargs))
        return wrapper

    def __call__(self, *args, **kwargs):
        _function = object.__getattribute__(self, '_function')
        _module = object.__getattribute__(self, '_module')
        _name = object.__getattribute__(self, '_name')
        print(f'Call {_function} {_module} {_name}')
        return safe_return(Writer.write(_function,
                                        _module,
                                        _name,
                                        *args, **kwargs))

    def isinstance(_object):
        return hasattr(_object, _pytracer_instance_attribute)


class WrapperInstance:
    def __init__(self, name, module, instance):
        if WrapperInstance.isinstance(instance):
            logger.error(
                f'Instance {instance} is already wrapped', caller=self)

        # print(f'Wrap {name} {module} instance {instance}')
        self._Pytracer_class_ = pytracer.builtins._builtins_type(self)
        self._pytracer_instance_attribute = _pytracer_instance_attribute
        self._instance = instance
        self._name = name
        self._instance_name = getattr(self._instance, '__name__', name)
        self._module = module
        try:
            self._instance.__doc__ = ''
        except Exception:
            pass

    def __getattribute__(self, name):
        if name == '_name':
            return object.__getattribute__(self, '_name')
        if name == '_function':
            return object.__getattribute__(self, '_function')
        if name == '_instance_str':
            return object.__getattribute__(self, '_instance_str')
        elif name == '_module':
            return object.__getattribute__(self, '_module')

        # print(
        #     f'[WrapperInstance] getattribute {name} of {self._module}.{self._name} ({self._function_str})')

        if name == '__call__':
            return object.__getattribute__(self, '__call__')
        elif name == '_wrap':
            return object.__getattribute__(self, '_wrap')
        elif name == '__class__':
            return getattr(self._instance, '__class__')
        elif name == visited_attr:
            return True
        elif name == _pytracer_instance_attribute:
            return _pytracer_instance_attribute
        else:
            attribute = getattr(self._instance, name)
            return attribute
            # print(f'[WrapperInstance] attribute {name} is {attribute}')
            # return attribute
            # return getattr(self._function, name)
            if callable(attribute) and not is_special_attributes(name):
                # print('{name} is callable {attribute}')
                return self._wrap(attribute)
            else:
                # print(f'{name} is not callable {attribute}')
                return attribute

            return getattr(self._function, name)

    def _wrap(self, attribute):
        def wrapper(*args, **kwargs):
            return safe_return(Writer.write(attribute,
                                            self._module,
                                            self._name,
                                            *args, **kwargs))
        return wrapper

    def __call__(self, *args, **kwargs):
        _instance = object.__getattribute__(self, '_instance')
        _module = object.__getattribute__(self, '_module')
        _name = object.__getattribute__(self, '_name')
        return safe_return(Writer.write_instance(_instance,
                                                 _module,
                                                 _name,
                                                 *args, **kwargs))

    def isinstance(_object):
        return hasattr(_object, _pytracer_instance_attribute)


def print_mapping(A, module, name, ori, ori_ty, wrp):
    print(
        f'[{A}] Map {module}.{name} {wrp} to {ori_ty} | Original {iX(ori)} -> Wrapper {iX(wrp)}')


def get_instance_wrapper(name, module, instance):
    wrapper = WrapperInstance(name, module, instance)
    ty = pytracer.builtins._builtins_type(instance)
    cache.add_type(wrapper, ty)
    # print_mapping('InstanceWrapper', module, name, instance, ty, instance)
    assert(type(wrapper) == ty)
    return wrapper


def getattribute(self, name):
    print('getattribute {name}')
    return object.__getattribute__(self.function, name)


def get_function_wrapper(name, module, function):
    wrapper = WrapperFunction(name, module, function)
    ty = pytracer.builtins._builtins_type(function)
    cache.add_type(wrapper, ty)
    # print_mapping('InstanceWrapper', module, name, function, ty, wrapper)
    assert(type(wrapper) == types.FunctionType or type(
        wrapper) == types.BuiltinFunctionType)
    return wrapper


excluded_classes = set({
    collections.OrderedDict,
    collections.Counter,
    Exception
})


def get_arg(parameter):
    if parameter.kind == parameter.POSITIONAL_ONLY:
        return f"{parameter.name}"
    elif parameter.kind == parameter.POSITIONAL_OR_KEYWORD:
        return f"{parameter.name}={parameter.name}"
    elif parameter.kind == parameter.VAR_POSITIONAL:
        return f"*{parameter.name}"
    elif parameter.kind == parameter.KEYWORD_ONLY:
        return f"{parameter.name}={parameter.name}"
    elif parameter.kind == parameter.VAR_KEYWORD:
        return f"**{parameter.name}"


def get_bind(signature, from_object=False):
    new_params = []
    for name, param in signature.parameters.items():
        if not from_object and name != 'self':
            new_params.append(get_arg(param))
    return ",".join(new_params)


def get_init(source):
    with tempfile.NamedTemporaryFile(suffix='.py') as tmp:
        tmp.write(bytes(source, 'utf-8'))
        tmp.flush()
        spec = importlib.util.spec_from_file_location(tmp.name, tmp.name)
        module = importlib.util.module_from_spec(spec)
        module.__loader__.exec_module(module)
        return module.__init__


cg = f"""
def _custom_getattribute(self, name):
    print('getattribute {{name}}')
    if name == '__class__':
        return object.__getattribute__(self, name)
    if name == '__flags__':
        return object.__getattribute__(self, name)
    if name == '_pytracer_wrapper_':
        return object.__getattribute__(self, name)
    if name == '__original_init__':
        return object.__getattribute__(self, name)
    if name == '__str__':
        return object.__getattribute__(self, name)
    if name == '__name__':
        return object.__getattribute__(self, name)
    if name == "prepare":
        return object.__getattribute__(self, name)
    if name == "_custom_attribute":
        return object.__getattribute__(self, name)
    if name == '__init__':
        return __init__
        # return object.__getattribute__(self, name)

    attribute = object.__getattribute__(self, name)

    if callable(attribute) and not is_special_attributes(name):
        if isinstance(attribute, (classmethod, staticmethod)):
            return WrapperClass._wrap_static(attribute, '', name)
        elif isinstance(attribute, types.FunctionType):
            return WrapperClass._wrap_static(attribute, '', name)
        else:
            return WrapperClass._wrap_method(self, attribute, name, '')

    else:
        return attribute
"""


class WrapperClass(type):

    def __getinit__(cls):
        # __init__ method is defined so we can get its is signature
        logger.debug(f'Get init for {cls}', caller=WrapperClass)
        clsname = cls.__name__
        if init := vars(cls).get('__init__', None):
            signature = inspect.signature(init)
            binding = get_bind(signature)
            print('BINDING', cls, binding, init)
            init_source = f"""
{cg}

def __init__{signature}:
    print(f'INIT SIG {cls.__name__}')
    setattr(self, "__getattribute__",_custom_getattribute)
    setattr(self, "{_pytracer_class_attribute}", True)
    self.__original_init__({binding}) # 1
            """
            init_source_dedent = textwrap.dedent(init_source)
            return get_init(init_source_dedent)
        else:
            if cls.__init__ == object.__init__:
                bind = '*args,**kwargs'
            else:
                bind = '*args,**kwargs'
            print('BIND', cls, bind, cls.__init__)
            init_source = f"""
{cg}

def __init__(self, *args, **kwargs):
    print(f'INIT NORMAL {cls.__name__}')
    setattr(self, "__getattribute__",_custom_getattribute)
    setattr(self, "{_pytracer_class_attribute}", True)
    self.__original_init__({bind})
            """
            init_source_dedent = textwrap.dedent(init_source)
            return get_init(init_source_dedent)

    def prepare(cls, namespace, bases):
        namespace['_pytracer_wrapper_'] = WrapperClass._wrap
        namespace['__dict__'] = {k: v for k,
                                 v in vars(cls).items()}
        print(namespace['__dict__'])
        namespace['__init__'] = WrapperClass.__getinit__(cls)
        # namespace['__init__'] = cls.__init__
        namespace['__new__'] = cls.__new__
        namespace['__mro__'] = bases
        namespace['__original_init__'] = cls.__init__
        namespace['__class__'] = cls.__class__
        namespace[_pytracer_class_attribute] = True
        namespace[_pytracer_instance_attribute] = True
        return namespace

    def _custom_getattribute(self, name):
        print(f'get attr {name}')
        if name == '__class__':
            return object.__getattribute__(self, name)
        if name == '__flags__':
            return object.__getattribute__(self, name)
        if name == '_pytracer_wrapper_':
            return object.__getattribute__(self, name)
        if name == '__original_init__':
            return object.__getattribute__(self, name)
        if name == '__str__':
            return object.__getattribute__(self, name)
        if name == '__name__':
            return object.__getattribute__(self, name)
        if name == "prepare":
            return object.__getattribute__(self, name)
        if name == "_custom_attribute":
            return object.__getattribute__(self, name)
        # if name == '__dict__':
        #     return self.__class__.__dict__
        #     return object.__getattribute__(self, name)
        if name == '__init__':
            return object.__getattribute__(self, name)

        # print(f'Custom attribute {self.__dict__} {name}')
        attribute = object.__getattribute__(self, name)

        if callable(attribute) and not is_special_attributes(name):
            if isinstance(attribute, (classmethod, staticmethod)):
                print("IS STATIC", name)
                return WrapperClass._wrap_static(attribute, '', name)
            elif isinstance(attribute, types.FunctionType):
                print("IS FUNCTION", name)
                return WrapperClass._wrap_static(attribute, '', name)
            else:
                print(f"IS METHOD {self.__class__}", name)
                return WrapperClass._wrap_method(self, attribute, name, '')

        else:
            return attribute

    def __new__(*args):

        logger.debug(f'[1] ARGS {args}', caller=WrapperClass)
        cls, _class = args

        name = getattr(_class, '__name__')
        for base in inspect.getmro(_class):
            if base != _class:
                if (b := cache.get_global_mapping(base)) is None:
                    if set.intersection(excluded_classes, set({b})) == set():
                        logger.warning(
                            f"Base {base} is not in cache", caller=WrapperClass)
                        try:
                            new_base = WrapperClass(base)
                        except Exception:
                            new_base = base
                        cache.add_global_mapping(base, new_base)

        bases = tuple(cache.get_global_mapping(base) if cache.get_global_mapping(base) is not None else base for base in inspect.getmro(
            _class) if base != _class)

        if set.intersection(excluded_classes, set(bases)) != set():
            raise Exception('base class excluded')

        namespace = collections.OrderedDict(vars(_class))
        namespace = WrapperClass.prepare(_class, namespace, bases)
        new_clss = type(name, bases, namespace)
        print(new_clss.__mro__)
        return new_clss

    def __instancancecheck__(self, instance):
        print(f'[A] instancecheck {self} {instance}')
        return isinstance(instance, instance.__mro__)

    def __subclasscheck__(self, subclass):
        print(f'[A] issubclass {self} {subclass}')
        return issubclass(subclass, subclass.__mro__)

    @staticmethod
    def _wrap(self, function, function_name, module):
        def wrapper(*args, **kwargs):
            return safe_return(Writer.write_instance(self,
                                                     function,
                                                     function_name,
                                                     module,
                                                     *args,
                                                     **kwargs))
        return wrapper

    @staticmethod
    def _wrap_method(self, method, function, module):
        def wrapper(*args, **kwargs):
            return safe_return(Writer.write_method(self,
                                                   method,
                                                   function,
                                                   module,
                                                   *args,
                                                   **kwargs))
        return wrapper

    @staticmethod
    def _wrap_static(function, module, name):
        def wrapper(*args, **kwargs):
            return safe_return(Writer.write(function,
                                            module,
                                            name,
                                            *args,
                                            **kwargs))
        return wrapper

    @staticmethod
    def isinstance(_object):
        _is_WrapperClass = isinstance(_object, WrapperClass)
        _has_Pytracer_attribute = hasattr(_object, _pytracer_class_attribute)
        if isinstance(_object, type):
            _is_Class_Instance = hasattr(
                _object.__class__, _pytracer_class_attribute)
        else:
            _is_Class_Instance = False
        logger.debug(
            'Is WrapperClass? {_is_WrapperClass}', caller=WrapperClass)
        logger.debug(
            'Has _pytracer_class_attribute? {_has_Pytracer_attribute}', caller=WrapperClass)
        logger.debug(
            'Is class a WrapperClass? {_is_Class_Instance}', caller=WrapperClass)
        return _is_WrapperClass or _has_Pytracer_attribute or _is_Class_Instance


def get_class_wrapper(name, module, clss):
    wrapper_class = WrapperClass(clss)
    # assert(type(wrapper_class) == ty)
    return wrapper_class


cached_error = set()


def pprint(_dict, indent=''):
    for k, v in _dict.items():
        print(f"{indent}{k}")
        if isinstance(v, dict):
            pprint(v, indent+'|')
        else:
            print(f"{indent}{v}")


def get_bfs(_dict):
    t1 = tuple(get_bfs(v) for v in _dict.values())
    t2 = tuple(_dict.keys())
    for t in t1:
        t2 += t
    return t2


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
            # self.parent_obj = parent
            self.obj_name = getattr(self.real_obj, "__name__")
            self.wrapped_obj = self.new_obj()
            self.init_attributes()
            # Wrapper.wrapped_cache.add(self.wrapped_obj)
            self.populate(self.real_obj, self.attributes)
            # self.update_globals()
            # Wrapper.m2wm[self.real_obj] = self.wrapped_obj
            cache.add_global_mapping(self.real_obj, self.wrapped_obj)
            for k, v in self.real_obj.__dict__.items():
                if (wrapped_obj := cache.get_global_mapping(v)) is not None:
                    self.real_obj.__dict__[k] = wrapped_obj
            # self.compute_dependencies(self.real_obj, self.wrapped_obj)
            # self.update_dependencies(self.real_obj, self.wrapped_obj)

    def _sort_vars(self, _vars):
        _classes = []
        _other = []
        _class_to_name = dict()
        for name in _vars:
            obj = vars(self.real_obj)[name]
            if inspect.isclass(obj):
                _class_to_name[obj] = name
                _classes.append(obj)
            else:
                _other.append(name)

        # print(_classes)
        _dict = {}
        for clss in _classes:
            # print(f'walking {clss}')
            mro = list(clss.__mro__)
            mro.reverse()

            if mro[0] in _dict:
                tree = _dict[mro[0]]
            else:
                tree = {}
                _dict[mro[0]] = tree
            for base in mro[1:]:
                # print(f'\tbase {base} of {clss}')
                if base in tree:
                    tree = tree[base]
                else:
                    tree[base] = {}
                    tree = tree[base]
        # pprint(_dict)
        classes = [_class_to_name[clss]
                   for clss in get_bfs(_dict) if clss in _class_to_name]

        return classes + _other

    def init_attributes(self):
        self.attributes = self._sort_vars(list(vars(self.real_obj).keys()))

    def update_globals(self):
        return
        for _, _globals in cache.globals_to_update.items():
            for _name, _value in _globals.items():
                if _value_wrapped := cache.get_global_mapping(_value):
                    _globals[_name] = _value_wrapped

    def mark_function_as_visited(self, func):
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
        return inspect.isfunction(attr_obj)

    def islambda(self, function):
        """
        check is the function is a lambda function
        """
        return isinstance(function, LambdaType) and \
            function.__name__ == "<lambda>"

    def handle_included_lambda(self, name, function):
        """
        Handler for lambda functions
        """
        logger.debug(f"[LambdaHandler] lamdba {name} included", caller=self)
        cache.visited_functions[id(function)] = function
        cache.add_global_mapping(function, function)
        setattr(self.wrapped_obj, name, function)

    def handle_excluded_lambda(self, name, function):
        """
        Handler for lambda functions
        """
        logger.debug(f"[LambdaHandler] lamdba {name} excluded", caller=self)
        cache.visited_functions[id(function)] = function
        cache.add_global_mapping(function, function)
        setattr(self.wrapped_obj, name, function)

    def handle_excluded_function(self, name, function):
        logger.debug(
            f'[FunctionHandler] function {name} excluded', caller=self)

        if self.islambda(function):
            self.handle_excluded_lambda(name, function)
            return

        cache.add_global_mapping(function, function)

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
        return
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
        return
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
            f'[FunctionHandler] function {name} included', caller=self)

        if self.islambda(function):
            self.handle_included_lambda(name, function)
            return

        func_name = getattr(function, "__name__", name)
        func_module = getattr(function, "__module__", self.get_name())
        func_name = func_name if func_name else name
        func_module = func_module if func_module else self.get_name()

        assert(func_module and func_name)

        function_wrapped = get_function_wrapper(
            func_name, func_module, function)

        cache.add_global_mapping(function, function_wrapped)
        setattr(self.wrapped_obj, name, function_wrapped)

    def handle_function(self, name, function, module=None, exclude=False):
        """
        Handler for functions
        """
        logger.debug(f'[FunctionHandler] function {name} handled', caller=self)

        if isinstance(function, functools.partial):
            setattr(self.wrapped_obj, name, function)
            return

        if exclude:
            self.handle_excluded_function(name, function)
        else:
            self.handle_included_function(name, function)
        return

    def ismodule(self, attr):
        """
        Check if the attribute is a module
        """
        return inspect.ismodule(attr)

    def update_module_depedencies(self, module):
        for attribute_name, attribute in vars(module).items():
            if (wrapped_attribute := cache.get_global_mapping(attribute)) is not None:
                setattr(module, attribute_name, wrapped_attribute)

    def handle_module(self, attr, submodule, exclude=False):
        """
        Handler for submodules
        """
        logger.debug(f'[ModuleHandler] module {attr} handled', caller=self)

        if submodule_wrapped := cache.get_global_mapping(submodule):
            logger.debug(
                f'Module {attr} has an entry in global_mapping', caller=self)
            submodule = submodule_wrapped

        # if inspect.ismodule(self.real_obj) and not exclude:
        #     if required_modules := cache.required_modules.get(self.real_obj, None):
        #         required_modules.append(submodule)
        #     else:
        #         cache.required_modules[self.real_obj] = [submodule]
        if submodule.__name__ not in cache.module_to_not_update:
            self.update_module_depedencies(submodule)

        setattr(self.wrapped_obj, attr, submodule)

    def isclass(self, attr):
        """
            Check if the attribute is a class
        """
        return inspect.isclass(attr)

    def handle_included_class(self, name, clss):
        logger.debug(f"[ClassHandler] class {name} included", caller=self)
        name = get_object_name(clss)
        module = get_module_name(clss)
        try:
            class_wrp = get_class_wrapper(name, module, clss)
            cache.add_global_mapping(clss, class_wrp)
            setattr(self.wrapped_obj, name, class_wrp)
            logger.debug(
                f"[ClassHandler] class {name} {iX(clss)} -> {iX(class_wrp)}")
        except Exception as e:

            logger.warning(
                f'Class {name} {getattr(clss,"__name__")} cannot be handled', caller=self, error=e)
            cache.add_global_mapping(clss, clss)
            # class_wrp = clss
        # self.compute_dependencies(clss, class_wrp)
        # self.update_dependencies(clss, class_wrp)
            setattr(self.wrapped_obj, name, clss)
            logger.debug(
                f"[ClassHandler] class {name} {iX(clss)} -> {iX(clss)}")

    def handle_excluded_class(self, name, clss):
        logger.debug(f"[ClassHandler] class {name} excluded", caller=self)
        # classname = getattr(clss, "__name__")
        cache.add_global_mapping(clss, clss)
        # self.compute_dependencies(clss, clss)
        # self.update_dependencies(clss, clss)
        setattr(self.wrapped_obj, name, clss)
        # setattr(self.wrapped_obj, classname, clss)

    def handle_class(self, attr, clss, exclude=False):
        """
            Handler for class
        """
        logger.debug(f"[ClassHandler] class {attr} handled", caller=self)

        if getattr(clss, _pytracer_class_attribute, None):
            logger.error(f"Found ({attr}) {clss} in module {self.real_obj} {iX(self.real_obj)} {self.wrapped_obj} {iX(self.wrapped_obj)}",
                         caller=self, raise_error=True)
            return

        if WrapperClass.isinstance(clss):
            logger.error(f"Found ({attr}) {clss} in module {self.real_obj} {iX(self.real_obj)} {self.wrapped_obj} {iX(self.wrapped_obj)}",
                         caller=self, raise_error=True)

        if exclude:
            self.handle_excluded_class(attr, clss)
        else:
            self.handle_included_class(attr, clss)

    def handle_included_basic(self, name, obj):
        logger.debug(
            f"[InstanceHandler] instance {name} included", caller=self)
        wrp_obj = obj
        if not hasattr(obj, visited_attr) and callable(obj):
            wrp_obj = get_instance_wrapper(name, self.get_name(), obj)
        cache.add_global_mapping(obj, wrp_obj)
        setattr(self.wrapped_obj, name, wrp_obj)

    def handle_excluded_basic(self, name, obj):
        logger.debug(
            f"[InstanceHandler] instance {name} excluded", caller=self)
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
        logger.debug(f"[InstanceHandler] instance {name} handled", caller=self)

        obj_name = getattr(obj, "__name__", "")
        names = (name, obj_name)
        module_name = self.get_name()

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
        # logger.debug(
        #     f"[is_excluded] {obj} {attr} (is module? {is_module})", caller=self)
        if "pytracer.core" in obj:
            return True

        module_included = self.included.has_module(obj)
        module_excluded = self.excluded.has_module(obj)
        function_included = self.included.has_function(attr, obj)
        function_excluded = self.excluded.has_function(attr, obj)

        # logger.debug(
        #     f"[is_excluded] Is module {obj} included: {module_included}", caller=self)
        # logger.debug(
        #     f"[is_excluded] Is module {obj} excluded: {module_excluded}", caller=self)
        # logger.debug(
        #     f"[is_excluded] Has module {obj} function {attr} included: {function_included}", caller=self)
        # logger.debug(
        #     f"[is_excluded] Has module {obj} function {attr} excluded: {function_excluded}", caller=self)

        if is_module:
            if module_included:
                return False
            elif module_excluded:
                return True
            else:
                return True

        if module_included:
            if module_excluded:
                if function_included and not function_excluded:
                    exclude = False
                else:
                    logger.debug(
                        f"1 {module_included} {module_excluded} {function_included} {function_excluded}", caller=self)
                    exclude = True
            else:  # not module excluded
                if function_included:
                    exclude = False
                else:
                    logger.debug(
                        f"2 {module_included} {module_excluded} {function_included} {function_excluded}", caller=self)
                    exclude = True
        else:  # not module included
            if module_excluded:
                if function_excluded:
                    exclude = True
                    logger.debug(
                        f"3 {module_included} {module_excluded} {function_included} {function_excluded}", caller=self)
                elif function_included:
                    logger.debug(
                        f"4 {module_included} {module_excluded} {function_included} {function_excluded}", caller=self)
                    exclude = True
                else:
                    exclude = False
            else:  # not module excluded
                exclude = False

        return exclude

    def is_instrumented(self, _object):
        _is_instrumented = WrapperInstance.isinstance(
            _object) or WrapperClass.isinstance(_object)
        logger.debug(f'is instrumented? {_is_instrumented}', caller=self)
        return _is_instrumented

    def handle_excluded(self, _attribute_name, _attribute):
        logger.debug(f'Handle excluded {_attribute_name}', caller=self)
        cache.add_global_mapping(_attribute, _attribute)
        setattr(self.wrapped_obj, _attribute_name, _attribute)

    def is_cython(self, _object):
        _has_vtable = hasattr(_object, "__pyx_vtable__")
        logger.debug(f"Has vtable? {_has_vtable}", caller=self)
        try:
            file = inspect.getfile(_object)
            return file.endswith(".so")
        except TypeError:
            return True

    def populate(self, _object, _attributes_names):
        """
            Create wrapper for each attribute in the module
        """
        for attribute_name in _attributes_names:
            attribute = vars(self.get_real_object())[attribute_name]
            # attribute = getattr(_object, attribute_name)
            logger.debug(f'Handle {attribute_name} {type(attribute)}',
                         caller=self, show_caller=True)

            # print(
            #     f'checking {attribute_name} {self.get_name()} {iX(attribute)}')
            if self.is_instrumented(attribute) or inspect.isabstract(attribute) or self.is_cython(attribute):
                self.handle_excluded(attribute_name, attribute)
                continue

            module_name = get_module_name(attribute)
            module_name = module_name if module_name else self.get_name()
            object_name = get_object_name(attribute)
            object_name = object_name if object_name else attribute_name

            exclude = self.is_excluded(
                module_name, object_name, is_module=inspect.ismodule(attribute))

            logger.debug(
                f"[{self.obj_name}] Checking {attribute_name} at {hex(id(attribute))} : is excluded? {exclude}", caller=self)

            if self.is_instrumented(attribute):
                self.handle_excluded(attribute_name, attribute)
            elif self.isspecialattr(attribute_name):
                self.handle_special(attribute_name, attribute)
            elif self.isclass(attribute):
                self.handle_class(attribute_name, attribute, exclude=exclude)
            elif inspect.ismethod(attribute):
                self.handle_excluded_basic(attribute_name, attribute)
            elif self.isfunction(attribute):
                self.handle_function(
                    attribute_name, attribute, exclude=exclude)
            elif self.ismodule(attribute):
                self.handle_module(
                    attribute_name, attribute, exclude=exclude)
            else:
                self.handle_basic(attribute_name, attribute, exclude=exclude)


class WrapperModule(Wrapper):

    def new_obj(self):
        new_obj = ModuleType(self.get_name())
        self.mark_function_as_visited(new_obj)
        return new_obj

    def get_wrapped_module(self):
        return self.get_wrapped_object()

    def init_attributes(self):
        super().init_attributes()
        setattr(self.wrapped_obj, self.obj_name, self.real_obj)
        setattr(self.wrapped_obj, "generic_wrapper",
                self.writer.wrapper_function)
