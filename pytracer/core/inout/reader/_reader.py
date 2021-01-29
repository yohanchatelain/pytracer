from abc import abstractmethod
from pytracer.utils.singleton import Singleton


class Reader(metaclass=Singleton):

    @abstractmethod
    def read(self, filename):
        pass
