import os

from pytracer.core.config import constant

cache_default = f"{constant.cache.root}"
directory_default = f"{constant.cache.root}{os.sep}{constant.cache.traces}"


def init_module(subparser):
    parser_parser = subparser.add_parser("parse", help="parse traces")
    mutual_exclusion = parser_parser.add_mutually_exclusive_group()
    mutual_exclusion.add_argument("--filename", help="only parse <filename>")
    mutual_exclusion.add_argument("--directory", default=directory_default,
                                  help=("parse all files in <directory>"
                                        "and merge them"))
    parser_parser.add_argument("--format", choices=constant.iotypes,
                               help="format of traces (auto-detected by default)")
    parser_parser.add_argument("--batch-size", default=50,
                               help=(f"Number of elements to process per batch. "
                                     f"Increasing this number requires more memory RAM"))
