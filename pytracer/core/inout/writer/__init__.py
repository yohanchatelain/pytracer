from . import _pickle
from . import _wrapper
from ._wrapper import *

from pytracer.core.info import register

Writer = _pickle.WriterPickle()
register.set_trace(Writer.get_filename(), Writer.get_filename_path())

__all__ = ["Writer"]
__all__.extend(dir(_wrapper))
