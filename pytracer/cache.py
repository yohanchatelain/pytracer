import inspect
import types

# Map that associates function to their id
id_dict = {}
visited_functions = {}
visited_files = set()

modules_not_initialized = {}
submodules = {}
orispec_to_wrappedmodule = {}

required_modules = {}

visited_spec = {}

hidden = types.ModuleType('cache.hidden')
hidden.required_functions = {"numpy":
                             ["ufunc", "nan", "frompyfunc",
                              "isscalar", "dtype", "isnan",
                              "ndarray", "issubdtype", "can_cast"],
                             "scipy.linalg._fblas": ["daxpy"]
                             }


function_to_dependencies_dict = {}
function_to_dependencies_globals = {}

dumped_functions = {}

_global_mapping = {}
_reverse_global_mapping = set()

globals_to_update = {}

_map_type = {}


def add_type(_object, _object_type):
    _id = id(_object)
    _map_type[_id] = _object_type


def get_type(_object):
    return _map_type.get(id(_object), None)


def get_global_mapping(_object):
    _id = id(_object)
    return _global_mapping.get(_id, None)


def add_global_mapping(_original_object, _wrapped_object):
    _id = id(_original_object)
    _id_wrapped = id(_wrapped_object)
    # print(
    #     f"Add global maping {_original_object} ({hex(id(_original_object))})-> {_wrapped_object} ({hex(id(_wrapped_object))})")
    _reverse_global_mapping.add(_id_wrapped)
    _global_mapping[_id] = _wrapped_object


def has_global_mapping(_object):
    _id = id(_object)
    return _id in _reverse_global_mapping


def hash_spec(spec):
    t = (spec.name, spec.loader, spec.origin)
    return hash(t)


# _signatures = {}


# def get_signature(_object):
#     return _signatures.get(id(_object))


# def add_signature(signature, _object):
#     _signatures[id(_object)] = signature


module_to_not_update = set(['builtins'])
# _map_instance_type = {}


# def add_instance_type(wrapper, function_type):
#     _map_instance_type[id(wrapper)] = function_type


# def get_instance_type(wrapper):
#     return _map_instance_type[id(wrapper)]
