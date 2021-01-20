
import os

from pytracer.core.config import constant

directory_default = f"{constant.cache.root}{os.sep}{constant.cache.stats}"


def init_module(subparser):
    index_parser = subparser.add_parser("visualize",
                                        help="visualize traces")
    index_parser.add_argument("--directory", default=directory_default,
                              help="directory with traces")
    index_parser.add_argument("--debug", default=False, action="store_true",
                              help="rue dash server in debug mode")
