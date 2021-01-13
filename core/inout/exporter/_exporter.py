from abc import abstractmethod

from pytracer.core.utils.singleton import Singleton


class Exporter(metaclass=Singleton):

    @abstractmethod
    def export(self, obj):
        pass
