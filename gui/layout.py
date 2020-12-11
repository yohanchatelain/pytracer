
import dash_core_components as dcc
import dash_html_components as html
import dash_table as dt
import dash_daq as daq

import pytracer.gui.core as pgc

info_table = html.Div(
    [
        dt.DataTable(
            id="info-table",
            columns=[{"id": "module", "name": "module"},
                     {"id": "function", "name": "function"}],
            data=None,
            selected_rows=[0],
            sort_action="native",
            cell_selectable=False,
            row_selectable="single",
            fixed_columns={"headers": True, "data": 0},
            style_table={
                "overflowY": "auto"
            }, css=[{"selector": ".row", "rule": "margin: 0"}]),
        html.Div(id="data-choosen", className="mini_container",
                 children=dcc.Markdown(id="data-choosen-txt"))
    ],
    # style={"display": "flex", "flex-direction": "column",
    #        "justify-content": "start", "align-items": "flex-start"},
    className="pretty_container three columns"
)

mode_selector = html.Div([
    html.P(
        "Selects mode:",
        className="control_label",
    ),
    dcc.RadioItems(
        id="timeline-mode",
        options=[
            {"label": "Mean", "value": "mean"},
            {"label": "Standard deviation", "value": "std"},
            {"label": "Significant bits", "value": "sig"}
        ],
        value="sig",

        className="dcc_control",
    )], className="mini_container")

xscale_selector = html.Div([
    html.P("X-scale:",
           className="control_label"),
    dcc.RadioItems(
        id="x-scale",
        options=[
            {"label": "linear", "value": "linear"},
            {"label": "log", "value": "log"}
        ],
        value="linear",
        labelStyle={"display": "inline-block"},
        className="dcc_control",
    )], className="mini_container")

yscale_selector = html.Div([
    html.P("Y-scale:",
           className="control_label"),
    dcc.RadioItems(
        id="y-scale",
        options=[
            {"label": "linear", "value": "linear"},
            {"label": "log", "value": "log"},
        ],
        value="linear",
        labelStyle={"display": "inline-block"},
        className="dcc_control",
    )], className="mini_container")


timeline_hover_info = html.Div(
    dcc.Markdown(id="info-data-timeline-summary"),
    className="mini_container"
)

timeline_hover_heatmap = html.Div(
    dcc.Graph(id="info-data-timeline-heatmap"),
    className="pretty_container"
)

timeline_hover = html.Div(
    [
        timeline_hover_info,
        timeline_hover_heatmap
    ],
    id="info-timeline",
    className="pretty_container",
    style={"display": "flex", "display-direction": "row"}
)

modal = html.Div(
    [
        # dcc.Markdown(id="source-modal-body-md",
        #              style={"marginBottom": 10,
        #                     "width": "100%",
        #                     "height": "100%",
        #                     "overflowY": "scroll"})
    ],
    id="source-file",
    className="pretty_container ten columns",
    style={"display": "flex", "height": 400})

timeline_graph = html.Div([
    dcc.Graph(id="timeline"),
    html.Div(
        [
            html.Div(
                [
                    dcc.Link(id="source-link", href=""),
                    dcc.Markdown(id="source",
                                 style={"overflowY": "auto",
                                        "height": "200"}),
                ], className="mini_container"
            ),
            daq.BooleanSwitch(label="Show source",
                              id="source-button", on=False),
        ], className="mini_container",
        style={"display": "flex", "flex-direction": "row"},
    ),
    timeline_hover,
])

info_ctx_debug = html.Div(
    [
        dcc.Textarea(id="debug-ctx",
                     style={"witdth": "100%", "height": 200}
                     )],
    className="mini_container")

header_title = html.Div(
    [
        html.Div(
            [
                html.H3(
                    "Pytracer Visualizer",
                    style={"margin-bottom": "0px"},
                ),
                html.H5(
                    "", style={"margin-top": "0px"}
                ),
            ]
        )
    ],
    className="eight column",
    id="title",
)

header_link = html.Div(
    [
        html.A(
            html.Button("Learn More", id="learn-more-button"),
            href="https://github.com/yohanchatelain",
        )
    ],
    className="one-third column",
    id="button",
)


header = html.Div(
    [
        header_title,
        header_link
    ],
    id="header",
    className="row flex-display",
    style={"margin-bottom": "25px"}
)

sidebar = info_table

rootpanel = html.Div(
    [
        html.Div(
            [
                mode_selector,
                xscale_selector,
                yscale_selector
            ],
            className="pretty_container",
            style={"display": "flex", "flex-direction": "row"},
            id="cross-filter-options"
        ),
        html.Div(
            [
                timeline_graph,
            ],
            className="pretty_container",
            style={"display": "flex", "flex-direction": "column"}
        )
    ],
    id="mainContainer",
    style={"display": "flex", "flex-direction": "column",
           "justify-direction": "stretch",
           "width": "100%"}
)
