import builtins
import inspect
import types

import pytracer.cache

_builtins_type = builtins.type
_builtins_isinstance = builtins.isinstance
_builtins_super = builtins.super
_builtins_issubclass = builtins.issubclass
_builtins_object = builtins.object
_builtins_globals = builtins.globals

_types_new_class = types.new_class
_types_prepare_class = types.prepare_class
_types_resolves_bases = types.resolve_bases
_types_MappingProxyType = types.MappingProxyType

_inspect_isclass = inspect.isclass


def _type(_object):

    if _original_type := pytracer.cache.get_type(_object):
        _ty = _original_type
    else:
        _ty = _builtins_type(_object)
    return _ty


def _custom_type(*args, **kwargs):
    if len(args) == 1:
        _ty = _type(*args)
        if _ty == _Type:
            return _builtins_type
        else:
            return _ty
    else:
        return _builtins_type(*args, **kwargs)


class _Type(type):

    def __new__(cls, *args, **kwargs):
        if len(args) == 3 and cls.__name__ != '_Type':
            return _builtins_type.__new__(cls, *args, **kwargs)
        return _custom_type(*args, **kwargs)


def original_type(_type):
    if _type == _Type:
        return _builtins_type
    else:
        return _type


def _isInstance(obj, class_or_tuple, /):
    if _builtins_isinstance(class_or_tuple, tuple):
        _tuple = tuple(original_type(_Ty) for _Ty in class_or_tuple)
        return _builtins_isinstance(obj, _tuple)
    elif class_or_tuple == _Type:
        return _builtins_isinstance(obj, _builtins_type)
    else:
        return _builtins_isinstance(obj, class_or_tuple)


def _issubclass(clss, classinfo):
    t = _builtins_issubclass(clss, classinfo)
    return t


class _Dict(dict):

    def __getitem__(self, item):
        return super().__getitem__(item)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)


class _Super(super):

    def __new__(cls, *args, **kwargs):
        return _builtins_super(_builtins_type).__new__(cls, *args, **kwargs)

    def __call__(self, *args, **kwargs):
        return _builtins_super.__call__(*args, **kwargs)


class _MappingProxyType(dict):
    def __getitem__(self, item):
        return super().__getitem__(item)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)


def _new_class(*args, **kwargs):
    return _types_new_class(*args, **kwargs)


def _prepare_class(*args, **kwargs):
    return _types_prepare_class(*args, **kwargs)


def _resolves_bases(*args, **kwargs):
    return _types_resolves_bases(*args, **kwargs)


def _isclass(self, _object):
    if hasattr(_object, '_Pytracer_instance'):
        return False
    return _inspect_isclass(_object)


def overload_builtins():
    builtins.type = _Type
    builtins.isinstance = _isInstance
