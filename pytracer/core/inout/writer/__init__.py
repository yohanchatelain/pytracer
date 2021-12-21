from . import _pickle

from pytracer.module.info import register

Writer = _pickle.WriterPickle()
register.set_trace(Writer.get_filename(), Writer.get_filename_path())
