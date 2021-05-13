import argparse
from pytracer.gui.layout import get_rootpanel

import dash_core_components as dcc
import dash_html_components as html

import pytracer.gui.core as pgc
import pytracer.gui.index_init as index_init


def init_layout(app, args):
    from pytracer.gui.layout import header, modal, get_rootpanel, sidebar
    app.layout = html.Div([
        html.Div(id="output-clientsid"),
        header,
        modal,
        html.Div(
            [
                sidebar,
                get_rootpanel(args)
            ],
            style={"display": "flex", "flex-direction": "row", 'width': '100vh'}
        ),
    ], style={"display": "flex", "flex-direction": "column", 'width': '100%'},
        className='container')


def main(args):
    import pytracer.gui.callbacks
    from pytracer.gui.app import app

    init_layout(app, args)
    pgc.init_data(args)
    app.run_server(debug=args.debug, threaded=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Pytracer visualization module")
    subparser = parser.add_subparsers()
    index_init.init_module(subparser)
    args = parser.parse_args()
    main(args)
