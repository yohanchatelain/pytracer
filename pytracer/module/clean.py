import os
import shutil

from pytracer.core.config import config as cfg
from pytracer.core.config import constant


def clean():
    dir_to_clean = cfg.io.cache.root
    if not dir_to_clean:
        dir_to_clean = constant.cache.root
    if os.path.isdir(dir_to_clean):
        shutil.rmtree(dir_to_clean, ignore_errors=True)
