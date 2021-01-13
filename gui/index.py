import argparse

import dash_core_components as dcc
import dash_html_components as html

import pytracer.gui.core as pgc
import pytracer.gui.index_init as index_init

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
    index_init.init_module(parser, pytracer_modules=dict())
    args = parser.parse_args()
    main(args)
