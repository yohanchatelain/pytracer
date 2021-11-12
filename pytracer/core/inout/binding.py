import inspect
import copy


class Binding:

    def __init__(self, function, *args, **kwargs):
        try:
            sig = inspect.signature(function)
            self._bind_initializer(sig, *args, **kwargs)
        except (ValueError, TypeError):
            self._default_initializer(*args, **kwargs)

    def _bind_initializer(self, sig, *args, **kwargs):
        bind = sig.bind(*args, **kwargs)
        self.arguments = bind.arguments
        self.args = bind.args
        self.kwargs = bind.kwargs

    def _default_initializer(self, *args, **kwargs):
        self.arguments = {
            **{f"Arg{i}": x for i, x in enumerate(args)}, **kwargs}
        self.args = args
        self.kwargs = kwargs


def format_output(outputs):
    if isinstance(outputs, dict):
        _dict = {k: copy.deepcopy(v) for k, v in outputs.items()
                 if not k.startswith('__')
                 and not k.endswith('__')
                 and not callable(v)}
        _outputs = _dict
    elif isinstance(outputs, tuple):
        _outputs = {f"Ret{i}": o for i, o in enumerate(outputs)}
    else:
        _outputs = {"Ret": outputs}
    return _outputs
