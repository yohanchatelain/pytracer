from abc import abstractmethod
from pytracer.utils.singleton import Singleton


class Reader():

    @abstractmethod
    def read(self, filename):
        pass
