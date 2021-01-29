from enum import Enum, auto


class UnknownVerificarloBackend(Exception):
    """Raised when backend is unknown"""
    pass


class BackendType(Enum):
    IEEE = auto()
    MCA = auto()
    MCA_MPFR = auto()
    VPREC = auto()


class Backend:

    def __init__(self, backend_type, **kwargs):
        self._type = backend_type
        self._libname = f"libinterflop_{self._type.name.lower()}.so"
        self._options = kwargs

    def __options_str(self):
        options_str = map(lambda item: f"--{item[0]}={item[1]}",
                          self._options.items())
        return " ".join(options_str)

    def getenv(self):
        pass


class BackendIEEE(Backend):

    def __init__(self, **kwargs):
        super().__init__(BackendType.IEEE, **kwargs)


class BackendMCA(Backend):

    def __init__(self, **kwargs):
        super().__init__(BackendType.MCA, **kwargs)


class BackendMCAMPFR(Backend):

    def __init__(self, **kwargs):
        super().__init__(BackendType.MCA_MPFR, **kwargs)


class BackendVPREC(Backend):

    def __init__(self, **kwargs):
        super().__init__(BackendType.VPREC, **kwargs)


_smart_constructor = {
    BackendType.IEEE: BackendIEEE,
    BackendType.MCA: BackendMCA,
    BackendType.MCA_MPFR: BackendMCAMPFR,
    BackendType.VPREC: BackendVPREC,
}


def get_env(backend, options=None):
    try:
        return _smart_constructor[backend](options).getenv()
    except KeyError:
        raise UnknownVerificarloBackend(backend)
