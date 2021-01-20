from enum import IntEnum, auto
import os


class IOType(IntEnum):
    TEXT = auto()
    JSON = auto()
    PICKLE = auto()

    def from_string(string):
        if string == "text":
            return IOType.TEXT
        if string == "json":
            return IOType.JSON
        if string == "pickle":
            return IOType.PICKLE
        return None


def split_filename(filename):
    _, name = os.path.split(filename)
    head, count, ext = name.split(os.extsep)
    return (head, count, ext)
