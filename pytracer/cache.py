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
    # _id_wrapped = _wrapped_object
    # _reverse_global_mapping.add(_id_wrapped)
    _global_mapping[_id] = _wrapped_object


def has_global_mapping(_object):
    _id = id(_object)
    return _id in _reverse_global_mapping


def hash_spec(spec):
    t = (spec.name, spec.loader, spec.origin)
    return hash(t)


_map_type = {}


def add_type(_object, _object_type):
    _id = id(_object)
    _hash = _object.__sizeof__
    _map_type[(_id, _hash)] = _object_type


def get_type(_object):
    _id = id(_object)
    _hash = _object.__sizeof__
    key = (_id, _hash)
    return _map_type.get(key, None)


module_to_not_update = set(['builtins'])

module_args = {}


def set_module_args(args):
    module_args.update(vars(args))


cached_error = None


_attribute_counter = dict()


def increment_visit(module):
    if module in _attribute_counter:
        _attribute_counter[module]['visited'] += 1
    else:
        _attribute_counter[module] = dict(visited=1,
                                          included=dict(function=0,
                                                        classe=0,
                                                        basic=0),
                                          excluded=dict(function=0,
                                                        classe=0,
                                                        basic=0)
                                          )


def increment_include(module, _type):
    _attribute_counter[module]['included'][_type] += 1


def increment_exclude(module, _type):
    _attribute_counter[module]['excluded'][_type] += 1


def print_stats():
    visited = 0
    included = dict(function=0, classe=0, basic=0)
    excluded = dict(function=0, classe=0, basic=0)
    modes = dict(visited=visited, included=included, excluded=excluded)
    for module, stats in _attribute_counter.items():
        print(f'{module.__name__}')
        for mode, values in stats.items():
            if isinstance(values, dict):
                for _type, stat in values.items():
                    modes[mode][_type] += stat
                    print(f'{mode} {_type}:{stat}')
            else:
                modes[mode] += values
                print(f'{mode}:{values}')

    modes['included']['all'] = sum(modes['included'].values())
    modes['excluded']['all'] = sum(modes['excluded'].values())
    print(f'Total {modes}')
