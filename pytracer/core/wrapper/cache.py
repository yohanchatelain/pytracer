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


def get_global_mapping(_object):
    _id = id(_object)
    return _global_mapping.get(_id, None)


def add_global_mapping(_original_object, _wrapped_object):
    _id = id(_original_object)
    _id_wrapped = _wrapped_object
    _reverse_global_mapping.add(_id_wrapped)
    _global_mapping[_id] = _wrapped_object


def has_global_mapping(_object):
    _id = id(_object)
    return _id in _reverse_global_mapping


def hash_spec(spec):
    t = (spec.name, spec.loader, spec.origin)
    return hash(t)
