from abc import abstractmethod

from pytracer.utils.singleton import Singleton


class Exporter(metaclass=Singleton):

    @abstractmethod
    def export(self, obj, expectedrows):
        pass
