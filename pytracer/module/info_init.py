import os
from pytracer.core.config import constant

directory_default = f"{constant.cache.root}{os.sep}{constant.cache.info}"


def init_module(subparser):
    parser_parser = subparser.add_parser(
        "info", help="get info about current traces")
    parser_parser.add_argument('--directory', default=directory_default,
                               help="Directory to get information from")
    parser_parser.add_argument('--trace', action='store_true',
                               help="Print traces information")
    parser_parser.add_argument('--aggregation', action='store_true',
                               help="Print aggregations information")
