import argparse
import os

import dash_core_components as dcc
import dash_html_components as html
from pytracer.core.config import constant

import pytracer.gui.core as pgc

directory_default = f"{constant.cache.root}{os.sep}{constant.cache.stats}"

data = pgc.Data()


def init_layout(app, args):
    from pytracer.gui.layout import header, modal, rootpanel, sidebar
    app.layout = html.Div([
        dcc.Store(id="memory-args", data=dict(args._get_kwargs())),
        dcc.Store(id="memory-path"),
        dcc.Store(id="memory-header"),
        dcc.Store(id="memory-data", storage_type="local"),
        html.Div(id="output-clientsid"),
        header,
        html.Div(
            [
                sidebar,
                rootpanel
            ],
            style={"display": "flex", "flex-direction": "row"}
        ),
        modal
    ])  # , style={"display": "flex", "flex-direction": "column"})


def init_module(subparser, pytracer_modules):
    index_parser = subparser.add_parser("visualize",
                                        help="visualize traces")
    index_parser.add_argument("--directory", default=directory_default,
                              help="directory with traces")
    index_parser.add_argument("--debug", default=False, action="store_true",
                              help="rue dash server in debug mode")

    pytracer_modules["visualize"] = main


def main(args):
    global data
    import pytracer.gui.callbacks
    from pytracer.gui.app import app

    init_layout(app, args)
    pgc.init_data(args)
    app.run_server(debug=args.debug)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Pytracer visualization module")
    init_module(parser, pytracer_modules=dict())
    args = parser.parse_args()
    main(args)
