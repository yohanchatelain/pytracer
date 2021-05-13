

from pytracer.callgraph.core import ViewGraph
from dash.dependencies import Input, Output, State

import core
from app import app
import json
import dash


# @app.callback(Output('cytoscape', 'elements'),
#               [Input('radio-expand', 'value')])
# def generate_elements(value):
#     elements = []
#     if value is not None:
#         view_graph = core.view_graphs[value]
#         elements = view_graph.to_cytoscape()
#     return elements


@app.callback(Output('cytoscape', 'layout'),
              [Input('dropdown-layout', 'value')])
def update_cytoscape_layout(layout):
    return {'name': layout, 'fit': True}


@app.callback(Output('tap-node-json-output', 'children'),
              [Input('cytoscape', 'tapNode')])
def displayTapNode(data):
    return json.dumps(data, indent=2)


@app.callback([Output('cytoscape', 'tapNode'),
               Output('cytoscape', 'tapNodeData'),
               Output('reset-view-button', 'n_clicks')],
              Input('cytoscape-toplevel', 'tapNode'))
def select_graph(graph_id):
    return None, None, 0


@app.callback(Output('cytoscape', 'elements'),
              [Input('cytoscape', 'tapNode'),
               Input('reset-view-button', 'n_clicks')],
              [State('cytoscape-toplevel', 'tapNode'),
               State('cytoscape', 'elements')])
def toggleChildren(cyto_node, reset, tap_node_top_level, elements_state):
    ctx = dash.callback_context

    graph_id = None
    if tap_node_top_level is not None:
        graph_id = tap_node_top_level['data']['graph_id']

    if not ctx.triggered or graph_id is None:
        return elements_state

    if len(ctx.triggered) > 1:
        triggering_input_id = "reset-view-button.n_clicks"
    else:
        triggering_input_id = ctx.triggered[0]['prop_id']

    if triggering_input_id == "reset-view-button.n_clicks":
        core_graph = core.core_graphs[graph_id]
        core.view_graphs[graph_id] = core.create_view_graph(core_graph)
        elements = core.view_graphs[graph_id].to_cytoscape()
    elif triggering_input_id == "cytoscape.tapNode":
        if graph_id is not None:
            if cyto_node['data']['isExpanded'] == False:
                elements = expandChildren(cyto_node, graph_id)
            else:
                print("="*20)
                elements = reduceChildren(cyto_node, graph_id)
                print("="*20)
        else:
            elements = elements_state
    return elements


def expandChildren(cyto_node, graph_id):
    view_graph = core.view_graphs[graph_id]
    if cyto_node is not None:
        data = cyto_node['data']
        core_graph = core.core_graphs[graph_id]
        tap_node = core.ViewGraph.node(**data)
        view_graph.expand_successors(core_graph, tap_node)
    elements = view_graph.to_cytoscape()
    return elements


def reduceChildren(cyto_node, graph_id):
    view_graph = core.view_graphs[graph_id]
    if cyto_node is not None:
        data = cyto_node['data']
        core_graph = core.core_graphs[graph_id]
        tap_node = core.ViewGraph.node(**data)
        view_graph.reduce_successors(core_graph, tap_node)
    elements = view_graph.to_cytoscape()
    return elements


@ app.callback(Output('tap-edge-json-output', 'children'),
               [Input('cytoscape', 'tapEdge')])
def displayTapEdge(data):
    return json.dumps(data, indent=2)


@ app.callback(Output('tap-node-data-json-output', 'children'),
               [Input('cytoscape', 'tapNodeData')])
def displayTapNodeData(data):
    return json.dumps(data, indent=2)


@ app.callback(Output('tap-edge-data-json-output', 'children'),
               [Input('cytoscape', 'tapEdgeData')])
def displayTapEdgeData(data):
    return json.dumps(data, indent=2)


@ app.callback(Output('mouseover-node-data-json-output', 'children'),
               [Input('cytoscape', 'mouseoverNodeData')])
def displayMouseoverNodeData(data):
    return json.dumps(data, indent=2)


@ app.callback(Output('mouseover-edge-data-json-output', 'children'),
               [Input('cytoscape', 'mouseoverEdgeData')])
def displayMouseoverEdgeData(data):
    return json.dumps(data, indent=2)


@ app.callback(Output('selected-node-data-json-output', 'children'),
               [Input('cytoscape', 'selectedNodeData')])
def displaySelectedNodeData(data):
    return json.dumps(data, indent=2)


@ app.callback(Output('selected-edge-data-json-output', 'children'),
               [Input('cytoscape', 'selectedEdgeData')])
def displaySelectedEdgeData(data):
    return json.dumps(data, indent=2)
