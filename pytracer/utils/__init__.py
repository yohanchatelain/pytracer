from enum import Enum
import sys
import os
import argparse


def getenv(env_name, exit_on_failure=True):
    env = os.getenv(env_name)
    if exit_on_failure and not env:
        sys.exit(f"{env_name} does not exist")
    return env


def check_extension(filename, extension):
    from pytracer.utils.log import get_logger
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


class SIPrefix(Enum):
    B = 1
    KB = 2**10
    MB = 2**20
    GB = 2**30
    TB = 2**40
    PB = 2**50


def __to_si_prefix(size, si_prefix):
    return f"{float(size/si_prefix.value):.1f}{si_prefix.name}"


__si_prefixes = SIPrefix.__members__.values()


def get_human_size(size):
    _si = SIPrefix.B
    for si in __si_prefixes:
        if size < si.value:
            return __to_si_prefix(size, _si)
        _si = si
    raise Exception(f"Unknown error get_humane_size: {size}")


def str2bool(v):
    # Taken from:
    # https://stackoverflow.com/questions/15008758/parsing-boolean-values-with-argparse
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')


def get_filename(name):
    i = 0
    while os.path.isfile(name):
        name = f"{name}.{i}"
        i += 1
    return name
