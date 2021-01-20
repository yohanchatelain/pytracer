class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(
                Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class Counter(metaclass=Singleton):
    """
    Atomic counter
    """

    def __init__(self):
        self._internal = 0

    def increment(self):
        self._internal += 1

    def __call__(self):
        return self._internal
