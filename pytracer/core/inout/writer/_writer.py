from abc import abstractmethod

from pytracer.utils.singleton import Singleton


class Writer(metaclass=Singleton):

    @abstractmethod
    def __init__(self):
        pass

    @abstractmethod
    def get_filename(self):
        pass

    @abstractmethod
    def get_filename_path(self):
        pass

    @abstractmethod
    def write(self, **kwargs):
        pass

    @abstractmethod
    def inputs(self, **kwargs):
        pass

    @abstractmethod
    def outputs(self, **kwargs):
        pass

    @abstractmethod
    def backtrace(self):
        pass
