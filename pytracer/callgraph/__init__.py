from datetime import datetime
from itertools import cycle
# from pytracer.gui.callbacks import get_name
import networkx as nx
import sys
import plotly.express as px
import dash
from pytracer.core.parser import CallChain, EdgeType

# from app import app
# import callbacks
import pytracer.callgraph.core as core
import pytracer.callgraph.layout as layout


def root(g):
    root = [n for n, d in g.in_degree() if d == 0]
    if root == []:
        assert has_cycle(g)
        [cycle] = nx.find_cycle(g)
        return cycle[0]
    assert len(root) == 1, f"root {root} {g}"
    return root.pop()


def compare_root(r1, r2):
    print(f"r1 {r1}")
    print(f"r2 {r2}")
    (hfunc1, func1, label1, bt1, _) = r1
    (hfunc2, func2, label2, bt2, _) = r2
    return hfunc1 == hfunc2 and func1 == func2 and label1 == label2 and bt1 == bt2


def same_node(g1, g2):
    print(f"Same node {root(g1)} {root(g2)}")
    r1 = root(g1)
    r2 = root(g2)
    return compare_root(r1, r2)
    return root(g1) == root(g2)


def has_cycle(g1):
    c = list(nx.simple_cycles(g1))
    return c != []


def merge(g1, g2):
    if has_cycle(g1):
        [cycle] = nx.find_cycle(g1)
        src, dst = cycle
        g1.get_edge_data(src, dst)['loop'] += 1
    else:
        g1.add_edge(root(g1), root(g1), loop=1, edgetype=EdgeType.CAUSAL)
    return g1


if __name__ == "__main__":
    filename = sys.argv[1]
    core.raw_graphs = core.load(filename)

    gantt = list()

    for graph_id, graph in core.raw_graphs.items():
        gantt += get_gantt(graph)

    new_graph_id = 0
    current_graph = core.raw_graphs.pop(0)
    for graph_id, graph in core.raw_graphs.items():
        if same_node(current_graph, graph):
            current_graph = merge(current_graph, graph)
        else:
            core.core_graphs[new_graph_id] = core.CoreGraph(
                current_graph, new_graph_id)
            current_graph = graph
            new_graph_id += 1

    # for graph_id, graph in core.raw_graphs.items():
    #     core.core_graphs[graph_id] = core.CoreGraph(graph, graph_id)

    for graph_id, core_graph in core.core_graphs.items():
        core.view_graphs[graph_id] = core.create_view_graph(core_graph)

    # roots_dict = dict()
    # for graph_id, graph in core.graphs.items():
    #     if roots := core.get_roots_hierarchical(graph):
    #         for root in roots:
    #             name = CallChain.get_name(root)
    #             lineno = CallChain.get_lineno(root)
    #             v = f"{name}:{lineno}"
    #             if graph_id in roots_dict:
    #                 roots_dict[graph_id].append(v)
    #             else:
    #                 roots_dict[graph_id] = [v]

    # roots_dict = dict({("\n".join(v), k) for (k, v) in roots_dict.items()})

    core.view_graph_toplevel = core.create_top_level_view_graph(
        core.core_graphs)

    app.layout = layout.init(roots=core.view_graph_toplevel.to_cytoscape(),
                             gantt=gantt)

    # roots_dict = dict()
    # for graph_id, core_graph in core.core_graphs.items():
    #     root = core_graph.unique_root()
    #     root_label = core_graph.to_view_label(root)
    #     roots_dict[graph_id] = root_label

    # app.layout = layout.init(roots=roots_dict)

    elements = []
    # for graph_id, graph in core.graphs.items():
    #     elements.extend(core.nx_to_cyto(graph, graph_id))

    layout.g1.elements = elements

    app.run_server(debug=True)
