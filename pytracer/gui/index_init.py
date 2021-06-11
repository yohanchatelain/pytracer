import os

from pytracer.core.config import constant
import argparse

directory_default = f"{constant.cache.root}{os.sep}"


def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1', 'on'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0', 'off'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')


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
    index_parser.add_argument('--threaded', type=str2bool, nargs='?',
                              const=True, default='True', help='Multithreading yes/no')
