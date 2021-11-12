from abc import abstractmethod


class Reader():

    @abstractmethod
    def read(self, filename):
        pass
