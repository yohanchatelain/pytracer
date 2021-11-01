import collections
from pytracer.core.wrapper.wrapper import WrapperInstance, WrapperClass
import pytracer.cache
import builtins
import types
import inspect

_builtins_type = builtins.type
_builtins_isinstance = builtins.isinstance
_builtins_super = builtins.super
_builtins_issubclass = builtins.issubclass
_builtins_object = builtins.object

_types_new_class = types.new_class
_types_prepare_class = types.prepare_class
_types_resolves_bases = types.resolve_bases
_types_MappingProxyType = types.MappingProxyType

_inspect_isclass = inspect.isclass
_inspect_signature = inspect.signature


def _type(_object):

    if _original_type := pytracer.cache.get_type(_object):
        return _original_type
    else:
        return _builtins_type(_object)


def _custom_type(*args):
    if len(args) == 1:
        return _type(*args)
    else:
        return _builtins_type(*args)


def __Type_new__(cls, *args, **kwargs):
    return _custom_type(*args)


_Type_dict = {k: v for k, v in type.__dict__.items() if k != '__qualname__'}
_Type_dict['__new__'] = __Type_new__
_Type = type('_Type', (type,), _Type_dict)

# class _Type(type):

#     def __prepare__(name, bases, **kwargs):
#         return collections.OrderedDict(_builtins_type.__dict__)


#   _Type.__dict__.update(_builtins_type.__dict__)

def original_type(_type):
    if _type == _Type:
        return _builtins_type
    else:
        return _type


def _isInstance(obj, class_or_tuple, /):
    if _builtins_isinstance(class_or_tuple, tuple):
        _tuple = tuple(original_type(_Ty) for _Ty in class_or_tuple)
        _isinstance = _builtins_isinstance(obj, _tuple)
    if class_or_tuple == _Type:
        _isinstance = _builtins_isinstance(obj, _builtins_type)
    else:
        _isinstance = _builtins_isinstance(obj, class_or_tuple)
    # print(f'isinstance {type(obj)} of {class_or_tuple} {_isinstance}')
    return _isinstance


def _issubclass(clss, classinfo):
    t = _builtins_issubclass(clss, classinfo)
    # print(f'issubclass {clss} of {classinfo} {t}')
    return t


# def _isinstance(instance, classinfo):
#     t = _builtins_isinstance(instance, classinfo)
#     print(f'isinstance {instance} of {classinfo} {t}')
#     return t


class _Dict(dict):

    def __getitem__(self, item):
        print(f'get item {item}')
        return super().__getitem__(item)

    def __setitem__(self, key, value):
        print(f'set item {key} to {value}')
        super().__setitem__(key, value)


# _Super_attributes = ('check_stack', '__getattribute__', '__new__',
#                      '__Pytracer_thisclass__', '__Pytracer_self__',
#                      '__Pytracer_self_class__')


# def get_method(_thisclass, _self, _self_class):
#     mro = _self_class.__mro__
#     print("THISCLASS", _thisclass)
#     print("SELF", _self)
#     print("SELF_CLASS", _self_class)
#     print("MRO", mro)
#     for clss in mro:
#         print("CLASS", clss)
#         if clss == _thisclass:
#             return clss
#     return object


def supercheck(b):
    if type(b) == type:
        return b
    else:
        return type(b)


class _Super(super):

    @staticmethod
    def check_stack():
        frame = inspect.currentframe().f_back.f_back

        # print(frame)
        # print(inspect.stack())
        varnames = frame.f_code.co_varnames
        # print('V', varnames, frame.f_code.co_filename,
        #       frame.f_code.co_firstlineno)
        # print('V', frame.f_back.f_code.co_varnames)
        # print(varnames)
        # print(frame.f_code)
        _self = frame.f_locals[varnames[0]]
        _class = frame.f_locals['__class__']
        # print('SELF', hex(id(type(_self))))
        # print('OLD', _class, hex(id(_class)))
        # if (new_class := pytracer.cache.get_global_mapping(_class)) is not None:
        #     _class = new_class
        # print('NEW', _class, hex(id(_class)))
        # for x in _self.__class__.__mro__:
        #     print(x, hex(id(x)))
        return _class, _self

    def __new__(cls, *args, **kwargs):

        _len = 0
        try:
            args[0]
            _len = 1
        except Exception:
            _len = _len

        try:
            args[1]
            _len = 2
        except Exception:
            _len = _len

        if _len == 0:
            _type, _obj = _Super.check_stack()
            # _obj_type = supercheck(_obj)
            # new = _builtins_super(_builtins_type).__new__(cls, *args, **kwargs)
            # new.__Pytracer_thisclass__ = _type
            # new.__Pytracer_self__ = _obj
            # new.__Pytracer_self_class__ = _obj_type

        elif _len == 1:
            _type = args[0]
            new = _builtins_super(_type)

        else:
            _type = args[0]
            _obj = args[1]
            _type, _obj = _Super.check_stack()
            # _obj_type = supercheck(_obj)
            # new = _builtins_super(_builtins_type).__new__(cls, *args, **kwargs)
            # new.__Pytracer_thisclass__ = _type
            # new.__Pytracer_self__ = _obj
            # new.__Pytracer_self_class__ = _obj_type

        # try:
        #     print(_type, _obj, isinstance(_type, _obj))
        # except Exception as e:
        #     print(f'Not an instance {e}')
        # try:
        #     print(_type, _obj, issubclass(_type, _obj))
        # except Exception as e:
        #     print(f'Not a subclass {e}')
        # print("TYPE")
        # print(_type)
        # print("OBJ")
        # print(hex(id(_type)), hex(id(_obj)))
        # try:
        #     print(_obj)
        # except Exception as e:
        #     print(e)
        return _builtins_super(_type, _obj)
        return new


class _MappingProxyType(dict):
    def __getitem__(self, item):
        print(f'mapping get item {item}')
        return super().__getitem__(item)

    def __setitem__(self, key, value):
        print(f'mapping set item {key} to {value}')
        super().__setitem__(key, value)


def _new_class(*args, **kwargs):
    print(f'new class {args} {kwargs}')
    return _types_new_class(*args, **kwargs)


def _prepare_class(*args, **kwargs):
    print(f'prepare class {args} {kwargs}')
    return _types_prepare_class(*args, **kwargs)


def _resolves_bases(*args, **kwargs):
    print(f'resolves bases {args} {kwargs}')
    return _types_resolves_bases(*args, **kwargs)


def _isclass(self, _object):
    if hasattr(_object, '_Pytracer_instance'):
        return False
    return _inspect_isclass(_object)


def _signature(self, _object):
    if signature := pytracer.cache.get_signature(_object):
        return signature
    else:
        return _inspect_signature(_object)


def overload_builtins():
    builtins.type = _Type
    builtins.isinstance = _isInstance
    # builtins.dict = _Dict
    builtins.super = _Super
    builtins.issubclass = _issubclass
    # builtins.isinstance = _isinstance

    types.new_class = _new_class
    types.prepare_class = _prepare_class
    types.resolve_bases = _resolves_bases
    # types.MappingProxyType = _types_MappingProxyType

    inspect.isclass = _inspect_isclass
    # inspect.signature = _inspect_signature
