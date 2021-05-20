
import os

from pytracer.core.config import constant

directory_default = f"{constant.cache.root}{os.sep}"


def init_module(subparser):
    index_parser = subparser.add_parser("visualize",
                                        help="visualize traces")
    index_parser.add_argument("--directory", default=directory_default,
                              help="directory with traces")
    index_parser.add_argument("--debug", default=False, action="store_true",
                              help="run dash server in debug mode")
    index_parser.add_argument("--filename", required=True,
                              help="file to visualize")
    index_parser.add_argument(
        '--callgraph', required=True, help='Call graph file')
    index_parser.add_argument('--host', default='0.0.0.0', help='IP to run on')
