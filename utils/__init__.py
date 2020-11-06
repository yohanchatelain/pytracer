import sys
import os


def getenv(env_name, exit_on_failure=True):
    env = os.getenv(env_name)
    if exit_on_failure and not env:
        sys.exit(f"{env_name} does not exist")
    return env


def check_extension(filename, extension):
    from . import log
    logger = log.get_log()

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
