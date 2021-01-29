import sys
import os
import argparse


def getenv(env_name, exit_on_failure=True):
    env = os.getenv(env_name)
    if exit_on_failure and not env:
        sys.exit(f"{env_name} does not exist")
    return env


def check_extension(filename, extension):
    from pytracer.core.utils.log import get_logger
    logger = get_logger()

    def warn():
        logger.warning(f"{filename} does not have {extension} extension")

    _, ext = os.path.splitext(filename)

    if isinstance(extension, (tuple, list)):
        if ext not in extension:
            warn()
            return False
        return True

    if isinstance(extension, str):
        if ext != extension:
            warn()
            return False
        return True

    raise TypeError


KB = 2**10
MB = 2**20
GB = 2**30
TB = 2**40


def get_human_size(size):
    sizeh = ""
    if size < KB:
        sizeh = f"{size}B"
    elif KB <= size < MB:
        sizeh = f"{int(size/KB)}KB"
    elif MB <= size < GB:
        sizeh = f"{int(size/MB)}MB"
    elif GB <= size < TB:
        sizeh = f"{int(size/GB)}GB"
    else:
        sizeh = f"{int(size/TB)}TB"
    return sizeh

# https://stackoverflow.com/questions/15008758/parsing-boolean-values-with-argparse


def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')