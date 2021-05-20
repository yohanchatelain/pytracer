from datetime import datetime
from networkx.algorithms.shortest_paths.unweighted import predecessor
from pytracer.core.parser import CallChain, EdgeType
import pytracer.callgraph.layout as layout
import networkx as nx

import pickle

_id_sep = "|"


class ViewGraph:

    _node_attrs = ['position', 'selected',
                   'selectable', 'locked', 'grabbable', 'classes']
    _edge_attrs = ['position', 'selected',
                   'selectable', 'locked', 'grabbable', 'classes']

    _null_index = -1

    def __init__(self, graph_id, graph):
        self.graph_id = graph_id
        self.graph = graph

    def get_id(self):
        return self.graph_id

    def to_cytoscape(self):
        return self.graph

    def __repr__(self):
        str_ = ""
        for elt in self.graph:
            if self.is_node(elt):
                str_ += f"{self.get_label(elt)}\n"
            else:
                src = elt['data']['source'].split('|')[:2]
                trgt = elt['data']['target'].split('|')[:2]
                str_ += f"{src} -> {trgt}\n"
        return str_

    def get_source(self, view_edge):
        assert(ViewGraph.is_edge(view_edge))
        source_id = view_edge['data']['source']
        source_index = self.indexOfId(source_id)
        return self.at(source_index)

    def get_target(self, view_edge):
        assert(ViewGraph.is_edge(view_edge))
        target_id = view_edge['data']['target']
        target_index = self.indexOfId(target_id)
        return self.at(target_index)

    def get_source_id(self, view_edge):
        return view_edge['data']['source']

    def get_target_id(self, view_edge):
        return view_edge['data']['target']

    def get_source_node(self, view_edge):
        view_source_id = self.get_source_id(view_edge)
        if (view_source_index := self.indexOfId(view_source_id)) != self._null_index:
            return self.at(view_source_index)
        return None

    def get_target_node(self, view_edge):
        view_target_id = self.get_target_id(view_edge)
        if (view_target_index := self.indexOfId(view_target_id)) != self._null_index:
            return self.at(view_target_index)
        return None

    def get_label(self, node):
        assert(ViewGraph.is_node(node))
        return node['data']['label']

    def minimal_view_node(self, node):
        return self.get_label(node)

    def minimal_view_edge(self, edge):
        source = self.get_source(edge)
        target = self.get_target(edge)
        source_label = self.get_label(source)
        target_label = self.get_label(target)
        return f"{source_label} -> {target_label}"

    def minimal_view(self):
        str_ = ""
        for elt in self.graph:
            if ViewGraph.is_node(elt):
                str_ += f"{self.get_label(elt)}\n"
            elif ViewGraph.is_edge(elt):
                str_ += f"{self.minimal_view_edge(elt)}\n"
            else:
                raise TypeError(elt)
        return str_

    @ staticmethod
    def node(**kwargs):
        """
        Parameters not in _node_attrs are included in 'data'
        """
        assert('id' in kwargs and 'label' in kwargs)
        node = {'group': 'nodes', 'data': {}}
        for k, v in kwargs.items():
            if k in ViewGraph._node_attrs:
                node[k] = v
            else:
                node['data'][k] = v
        return node

    @ staticmethod
    def edge(**kwargs):
        # print(f'New view edge')
        # for k, v in kwargs.items():
        #     print(f'{k} -> {v}')
        assert('source' in kwargs and 'target' in kwargs)
        edge = {'group': 'edges', 'data': {}}
        for k, v in kwargs.items():
            if k in ViewGraph._edge_attrs:
                edge[k] = v
            else:
                edge['data'][k] = v
        return edge

    @ staticmethod
    def update_data(view_node, **kwargs):
        view_node['data'].update(kwargs)

    @ staticmethod
    def get_node_id(view_node):
        if not ViewGraph.is_node(view_node):
            raise TypeError
        return view_node['data']['id']

    @ staticmethod
    def get_edge_id(view_edge):
        if not ViewGraph.is_edge(view_edge):
            raise TypeError
        return view_edge['data']['id']

    def to_core_graph(self, view_node):
        pass

    @ staticmethod
    def to_core_node(view_node):
        node_id = view_node['data']['id']
        return ViewGraph.to_core_node_from_view_id(node_id)

    @staticmethod
    def to_core_node_from_view_id(view_node_id):
        (core_id, _, _) = view_node_id.rpartition(_id_sep)
        return CallChain.str_to_call(core_id, _id_sep)

    @ staticmethod
    def is_node(view_obj):
        return view_obj['group'] == 'nodes'

    @ staticmethod
    def is_edge(view_obj):
        return view_obj['group'] == 'edges'

    def contains(self, view_obj):
        if self.is_node(view_obj):
            view_id = self.get_node_id(view_obj)
            is_obj = self.is_node
            get_id = self.get_node_id
        elif self.is_edge(view_obj):
            view_id = self.get_edge_id(view_obj)
            is_obj = self.is_edge
            get_id = self.get_edge_id
        else:
            raise TypeError

        for elt in self.graph:
            if is_obj(elt):
                elt_id = get_id(elt)
                if elt_id == view_id:
                    return True
        return False

    def __contains__(self, view_obj):
        return self.contains(view_obj)

    def at(self, view_index):
        if view_index == self._null_index:
            raise IndexError
        return self.graph[view_index]

    def indexOfId(self, view_id):
        for index, elt in enumerate(self.graph):
            if self.is_node(elt):
                elt_id = self.get_node_id(elt)
            elif self.is_edge(elt):
                elt_id = self.get_edge_id(elt)
            else:
                raise TypeError
            if elt_id == view_id:
                return index
        return self._null_index

    def indexOfNode(self, view_node):
        '''
        TODO: Optimize the search with a dict of id
        '''
        view_node_id = self.get_node_id(view_node)
        return self.indexOfId(view_node_id)

    def indexOfEdge(self, view_edge):
        '''
        TODO: Optimize the search with a dict of id
        '''
        view_edge_id = self.get_edge_id(view_edge)
        return self.indexOfId(view_edge_id)

    def indexOf(self, view_obj):
        '''
        TODO: Optimize the search with a dict of id
        '''
        if self.is_node(view_obj):
            return self.indexOfNode(view_obj)
        elif self.is_edge(view_obj):
            return self.indexOfEdge(view_obj)
        else:
            raise TypeError

    def add_node(self, view_node):
        """
        Add node to the graph
        Update it if node already exist
        """
        assert(ViewGraph.is_node(view_node))
        if (index := self.indexOf(view_node)) != self._null_index:
            # print(f"update node at index {index}")
            self.graph[index] = view_node
        else:
            # print(f"append node")
            self.graph.append(view_node)

    def add_edge(self, view_edge):
        """
        Add edge to the graph
        Update it if edge already exist
        """
        assert(ViewGraph.is_edge(view_edge))
        if (source_node := self.get_source_node(view_edge)) is None:
            # print("ADD NODE for source in add_edge")
            source_id = self.get_source_id(view_edge)
            source_core_node = ViewGraph.to_core_node_from_view_id(source_id)
            core_graph = core_graphs[self.get_id()]
            source_view_node = create_view_node(core_graph, source_core_node)
            self.add_node(source_view_node)
        if (target_node := self.get_target_node(view_edge)) is None:
            # print("ADD NODE for target in add_edge")
            source_id = self.get_target_id(view_edge)
            source_core_node = ViewGraph.to_core_node_from_view_id(source_id)
            core_graph = core_graphs[self.get_id()]
            source_view_node = create_view_node(core_graph, source_core_node)
            self.add_node(source_view_node)

        if (index := self.indexOf(view_edge)) != self._null_index:
            # print(f"update edge at index {index}")
            self.graph[index] = view_edge
        else:
            # print(f"append edge")
            self.graph.append(view_edge)

    def remove_node(self, view_node):
        if (index := self.indexOf(view_node)) != self._null_index:
            # print(f"Remove node")
            return self.graph.pop(index)
        raise KeyError

    def remove_edge(self, view_edge):
        if (index := self.indexOf(view_edge)) != self._null_index:
            # print(f"Remove edge")
            return self.graph.pop(index)
        raise KeyError

    def expand_successors(self, core_graph, view_node):
        # print(f'expand node {self.minimal_view_node(view_node)}')
        view_node['data']['isExpanded'] = True
        self.add_node(view_node)
        core_node = self.to_core_node(view_node)
        # print(f'Expand successors of {core_node}')
        core_successors = core_graph.successors(
            core_node, view=EdgeType.HIERARCHICAL)
        for core_succ in core_successors:
            # print(f'Core succ: {core_succ}')
            view_succ = core_graph.to_view_node(core_succ)
            self.add_node(view_succ)
            # print(f'Add node: {self.minimal_view_node(view_succ)}')
        core_edges = core_graph.edges(core_node, where='source')
        for core_edge in core_edges:
            # print(f'Core edge: {core_edge}')
            view_edge = core_graph.to_view_edge(core_edge)
            self.add_edge(view_edge)
        #     print(f'Add edge: {self.minimal_view_edge(view_edge)}')
        # print(f"After expansion:\n {self.minimal_view()}\n")

    def reduce_successors(self, core_graph, view_node, first=True):
        # print(f'reduce node {self.minimal_view_node(view_node)}')
        # print(f"\n BEFORE {self}\n")
        core_node = self.to_core_node(view_node)
        view_node['data']['isExpanded'] = False
        if first:
            self.add_node(view_node)
        core_successors = core_graph.successors(core_node,
                                                view=EdgeType.HIERARCHICAL)

        for core_succ in core_successors:
            view_succ = core_graph.to_view_node(core_succ)
            core_edges = core_graph.edges(
                core_succ, where='all')
            # print(
            # f"Edges of {self.minimal_view_node(view_succ)}: {core_edges}")
            for core_edge in core_edges:
                view_edge = core_graph.to_view_edge(core_edge)
                if view_edge in self:
                    self.remove_edge(view_edge)
            if view_succ in self:
                # print(f'Remove node: {self.minimal_view_node(view_succ)}')
                self.remove_node(view_succ)
                self.reduce_successors(core_graph, view_succ, first=False)
        # print(f"\nAFTER {self}\n")


class NxEdgeView:

    def __init__(self, inView, outView):
        self._in_edges = iter(inView)
        self._out_edges = iter(outView)

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return next(self._in_edges)
        except StopIteration:
            return next(self._out_edges)


class CoreGraph:

    def __init__(self, graph, _id):
        self.id = _id
        self.graph = graph
        self.hierachical_graph = CoreGraph.hierarchical_view(graph)
        self.temporal_graph = CoreGraph.temporal_view(graph)
        # print("init CoreGraph ", _id)
        # print(f"#nodes {self.number_nodes()}")
        # print(f"#edges {self.number_edges()}")

    def get_depth(self, core_node, view=None):
        root = self.unique_root(view)
        return nx.shortest_path_length(self._get_view(view),
                                       source=root,
                                       target=core_node)

    def number_nodes(self):
        counter = 0
        for _ in self.graph.nodes():
            counter += 1
        return counter

    def number_edges(self):
        counter = 0
        for _ in self.graph.edges():
            counter += 1
        return counter

    def _get_view(self, view):
        if view is None:
            return self.graph
        elif view == EdgeType.HIERARCHICAL:
            return self.hierachical_graph
        elif view == EdgeType.CAUSAL:
            return self.temporal_graph
        else:
            raise TypeError

    @ staticmethod
    def hierarchical_view(graph):
        def filter_edge(e): return e[-1]['edgetype'] == EdgeType.HIERARCHICAL
        restricted_node = []
        restricted_edge = [(n1, n2) for (n1, n2, attr) in graph.edges(
            data=True) if not filter_edge((n1, n2, attr))]
        return nx.restricted_view(graph,
                                  restricted_node,
                                  restricted_edge)

    @ staticmethod
    def temporal_view(graph):
        def filter_edge(e): return e[-1]['edgetype'] == EdgeType.CAUSAL
        restricted_node = []
        restricted_edge = [(n1, n2) for (n1, n2, attr) in graph.edges(
            data=True) if not filter_edge((n1, n2, attr))]
        return nx.restricted_view(graph,
                                  restricted_node,
                                  restricted_edge)

    def get_id(self):
        return self.id

    def has_cycle(self):
        return nx.simple_cycles(self.graph) != []

    def roots(self, view=None):
        graph = self._get_view(view)
        root = [v for v, d in graph.in_degree() if d == 0]
        if root == []:
            if self.has_cycle():
                [cycle] = nx.find_cycle(self.graph)
                return [cycle[0]]
        else:
            return root

    def unique_root(self, view=None):
        '''
        Return the unique root if it exist
        Raise ValueError if multiple roots exist
        '''
        try:
            [root] = self.roots(view)
        except:
            root = self.roots(view)[0]
        return root

    def is_root(self, core_node, view=None):
        graph = self._get_view(view)
        return len(graph.in_edges(core_node)) == 0

    def is_leaf(self, core_node, view=None):
        graph = self._get_view(view)
        return len(graph.out_edges(core_node)) == 0

    def leaves(self, view=None):
        graph = self._get_view(view)
        return [v for v, d in graph.out_degree() if d == 0]

    def successors(self, core_node, view=None):
        graph = self._get_view(view)
        return graph.successors(core_node)

    def edges(self, core_node, view=None, where='all'):
        graph = self._get_view(view)
        if where == 'all':
            _in = graph.in_edges(core_node, data=True)
            _out = graph.out_edges(core_node, data=True)
            return NxEdgeView(inView=_in, outView=_out)
        if where == 'source':
            return graph.out_edges(core_node, data=True)
        if where == 'target':
            return graph.in_edges(core_node, data=True)
        raise Exception('Unreachable path')

    def to_view_id(self, core_node):
        return f"{CallChain.call_to_str(core_node,_id_sep)}{_id_sep}{self.id}"

    def to_view_id_successors(self, core_node):
        return f"{CallChain.call_to_str(core_node,_id_sep)}{_id_sep}{self.id}.successors"

    def to_view_id_predecessors(self, core_node):
        return f"{CallChain.call_to_str(core_node,_id_sep)}{_id_sep}{self.id}.predecessors"

    def to_view_label(self, core_node):
        return CallChain.get_name(core_node)

    def to_view_node_attrs(self, core_node):
        view_node_attrs = {'classes': ''}
        if self.is_root(core_node, view=EdgeType.HIERARCHICAL):
            view_node_attrs['classes'] = layout.root_node_style['name']
        elif self.is_leaf(core_node, view=EdgeType.HIERARCHICAL):
            view_node_attrs['classes'] = layout.leaf_node_style['name']
        else:
            view_node_attrs['classes'] = layout.standard_node_style['name']
        return view_node_attrs

    def to_view_node(self, core_node):
        _id_node = self.to_view_id(core_node)
        _label_node = self.to_view_label(core_node)
        _time_node = CallChain.get_time(core_node)
        _name_node = CallChain.get_name(core_node)
        _file_node = CallChain.get_filename(core_node)
        _line_node = CallChain.get_line(core_node)
        _caller_node = CallChain.get_caller(core_node)
        _depth_node = self.get_depth(core_node, view=EdgeType.HIERARCHICAL)
        view_node_attrs = self.to_view_node_attrs(core_node)
        view_node = ViewGraph.node(id=_id_node,
                                   label=_label_node,
                                   time=_time_node,
                                   name=_name_node,
                                   file=_file_node,
                                   caller=_caller_node,
                                   line=_line_node,
                                   depth=_depth_node,
                                   graph_id=self.get_id(),
                                   isExpanded=False,
                                   **view_node_attrs)
        return view_node

    def to_view_class(self, edgetype):
        if edgetype == EdgeType.HIERARCHICAL:
            return layout.normal_edge_style['name']
        elif edgetype == EdgeType.CAUSAL:
            return layout.temporal_edge_style['name']
        else:
            raise ValueError

    def to_view_edge_attrs(self, attrs):
        '''
        Return attributes in ViewGraph format
        '''
        view_attrs = {'classes': ''}
        if 'edgetype' in attrs:
            edge_class = self.to_view_class(attrs['edgetype'])
            view_attrs['edgetype'] = edge_class
            view_attrs['classes'] += edge_class
        return view_attrs

    def to_view_edge(self, core_edge):
        view_edge = None
        if len(core_edge) == 2:
            (source, target) = core_edge
            source_view_id = self.to_view_id(source)
            target_view_id = self.to_view_id(target)
            view_edge_id = source_view_id + target_view_id
            view_edge = ViewGraph.edge(id=view_edge_id,
                                       source=source_view_id,
                                       target=target_view_id)
        elif len(core_edge) == 3:
            (source, target, attrs) = core_edge
            source_view_id = self.to_view_id(source)
            target_view_id = self.to_view_id(target)
            view_edge_id = source_view_id + target_view_id
            view_edge_attrs = self.to_view_edge_attrs(attrs)
            view_edge = ViewGraph.edge(id=view_edge_id,
                                       source=source_view_id,
                                       target=target_view_id,
                                       **view_edge_attrs)
        else:
            raise TypeError

        return view_edge

    def init_view(self):
        roots = self.roots(view=EdgeType.HIERARCHICAL)
        view_roots = [self.to_view_node(root) for root in roots]
        return ViewGraph(graph_id=self.get_id(), graph=view_roots)

    def to_view(self):
        pass


def get_cytonode_id(nx_node, graph_id=0):
    return "".join(map(str, nx_node))+str(graph_id)


def get_cytonode_label(nx_node):
    name = CallChain.get_name(nx_node)
    bt = CallChain.get_bt(nx_node)
    time = CallChain.get_time(nx_node)
    return name
    return f"{name}:{bt}:{time}"


def get_cytonode_children_id(nx_node, graph_id):
    return get_cytonode_id(nx_node, graph_id) + ".children"


def get_cytonode_children_label(nx_node):
    return get_cytonode_label(nx_node)


def is_leaf(graph, node):
    return graph.out_degree()[node] == 0


def is_root(graph, node):
    return graph.in_degree()[node] == 0


def is_isolated(graph, node):
    return is_leaf(graph, node) and is_root(graph, node)


def get_filtered_graph(graph, filter_node=None, filter_edge=None):
    if filter_node:
        return nx.subgraph_view(graph, filter_node=filter_node)
    elif filter_edge:
        return nx.restricted_view(graph, [], [(n1, n2) for (n1, n2, attr) in graph.edges(data=True) if not filter_edge((n1, n2, attr))])
    else:
        return graph


def get_leaves(graph, filter_node=None):
    filter_view = get_filtered_graph(
        graph, filter_node) if filter_node else graph
    return [v for v, d in filter_view.out_degree() if d == 0]


def get_roots(graph, filter_node=None):
    filter_view = get_filtered_graph(
        graph, filter_node) if filter_node else graph
    return [v for v, d in filter_view.in_degree() if d == 0]


def get_group(nx_node):
    name = CallChain.get_name(nx_node)
    (filename, _, _, caller) = CallChain.get_bt(nx_node)
    return (name, filename, caller)


def is_cycle(nx_node1, nx_node2):
    return nx_node1 == nx_node2


def get_children_group(node, graph_id, parent=None):
    _id_node = get_cytonode_id(node, graph_id)
    _id_children = get_cytonode_children_id(node, graph_id)
    _label_children = get_cytonode_children_label(node)
    cyto_node_children = {
        'data': {
            'id': _id_children,
            'label': _label_children,
            'parent': parent
        },
        'classes': ''
    }
    cyto_edge_children = {
        'data': {'source': _id_node, 'target': _id_children},
        'classes': ''
    }
    return (cyto_node_children, cyto_edge_children)


def get_roots_hierarchical(graph):
    hierarchical_view = get_filtered_graph(graph,
                                           filter_edge=lambda e:
                                           e[-1]['edgetype'] == EdgeType.HIERARCHICAL)
    return [node for node in graph.nodes() if is_root(hierarchical_view, node)]


def filter_depth(graph, depth):
    filterd_graph = nx.DiGraph()
    hierarchical_view = get_filtered_graph(graph,
                                           filter_edge=lambda e:
                                           e[-1]['edgetype'] == EdgeType.HIERARCHICAL)
    for node in graph.nodes():
        if is_root(hierarchical_view, node):
            filterd_graph.add_node(node)
    return filterd_graph


def get_depth_nx_node(graph, node):
    roots = get_roots_hierarchical(graph)
    assert(len(roots) == 1)
    [root] = roots
    return nx.shortest_path_length(graph, source=root, target=node)


def create_view_node(core_graph, core_node, **kwargs):
    _id_node = core_graph.to_view_id(core_node)
    _label_node = core_graph.to_view_label(core_node)
    _time_node = CallChain.get_time(core_node)
    _name_node = CallChain.get_name(core_node)
    _file_node = CallChain.get_filename(core_node)
    _line_node = CallChain.get_line(core_node)
    _caller_node = CallChain.get_caller(core_node)
    _depth_node = core_graph.get_depth(core_node, view=EdgeType.HIERARCHICAL)
    view_node = ViewGraph.node(id=_id_node,
                               label=_label_node,
                               time=_time_node,
                               name=_name_node,
                               file=_file_node,
                               caller=_caller_node,
                               line=_line_node,
                               depth=_depth_node,
                               isExpanded=False,
                               **kwargs)
    return view_node


def create_view_edge(core_graph_source, core_source,
                     core_graph_target, core_target,
                     **kwargs):
    _id_source_node = core_graph_source.to_view_id(core_source)
    _id_target_node = core_graph_target.to_view_id(core_target)
    _id_edge = _id_source_node + _id_target_node
    view_edge = ViewGraph.edge(id=_id_edge,
                               source=_id_source_node,
                               target=_id_target_node,
                               **kwargs)
    return view_edge


def create_view_successors_node(core_graph, core_node):
    _id_node = core_graph.to_view_id(core_node)
    _label_successors = core_graph.to_view_label(core_node)
    _id_successors = core_graph.to_view_id_successors(core_node)
    successors_node = ViewGraph.node(id=_id_successors,
                                     label=_label_successors,
                                     graph_id=core_graph.get_id(),
                                     isgroup=True,
                                     isExpanded=False,
                                     parent=_id_node)
    return successors_node


def create_view_successors_edge(core_graph, core_node):
    _id_node = core_graph.to_view_id(core_node)
    _id_successors = core_graph.to_view_id_successors(core_node)
    _id_edge = _id_node + _id_successors
    successors_edge = ViewGraph.edge(id=_id_edge,
                                     source=_id_node,
                                     target=_id_successors,
                                     classes='')
    return successors_edge


def create_view_predecessors_node(core_graph, core_node):
    _label_predecessors = core_graph.id
    _id_predecessors = core_graph.to_view_id_predecessors(core_node)
    predecessor_node = ViewGraph.node(id=_id_predecessors,
                                      label=_label_predecessors,
                                      graph_id=core_graph.get_id(),
                                      isExpanded=False,
                                      isgroup=True)
    return predecessor_node


def create_view_graph(core_graph):
    root = core_graph.unique_root()
    view_root_group = create_view_predecessors_node(core_graph, root)
    view_root = create_view_node(core_graph,
                                 root,
                                 graph_id=core_graph.get_id(),
                                 parent=ViewGraph.get_node_id(view_root_group),
                                 classes='roots')
    view_graph = ViewGraph(graph_id=core_graph.get_id(),
                           graph=[view_root_group, view_root])
    return view_graph


def create_top_level_view_graph(core_graphs):
    # item : (id,core_graph)
    core_graphs_sorted = sorted(core_graphs.items(),
                                key=lambda i: i[0])

    to_push = core_graphs.pop(0)
    current_core_graph = to_push

    current_core_root = current_core_graph.unique_root()
    current_view_root = create_view_node(current_core_graph,
                                         current_core_root,
                                         graph_id=current_core_graph.get_id(),
                                         classes=layout.standard_node_style['name'])
    view_graph_elements = [current_view_root]

    for next_graph_id, next_core_graph in core_graphs.items():
        next_core_root = next_core_graph.unique_root()
        if next_core_graph.is_leaf(next_core_root):
            node_class = layout.standard_node_style['name']
        else:
            node_class = layout.parent_node_style['name']
        next_view_root = create_view_node(next_core_graph,
                                          next_core_root,
                                          graph_id=next_graph_id,
                                          classes=node_class)
        view_graph_elements.append(next_view_root)
        view_edge = create_view_edge(current_core_graph, current_core_root,
                                     next_core_graph, next_core_root,
                                     classes=layout.temporal_edge_style['name'])
        view_graph_elements.append(view_edge)
        current_core_graph = next_core_graph
        current_core_root = next_core_root

    core_graphs[0] = to_push

    return ViewGraph(graph_id=-1, graph=view_graph_elements)


def nx_to_cyto(graph, graph_id=0, depth=None):
    """
    Convert networkx graph into Dash cytoscape
    """
    elements = []
    hierarchical_view = get_filtered_graph(graph,
                                           filter_edge=lambda e:
                                           e[-1]['edgetype'] == EdgeType.HIERARCHICAL)

    cyto_graph_group = {
        'data': {'id': graph_id, 'label': graph_id, 'depth': 0}}
    elements.append(cyto_graph_group)

    nx_to_cyto = dict()
    nx_to_children = dict()

    for node in graph.nodes():
        _id_node = get_cytonode_id(node, graph_id)
        _label_node = get_cytonode_label(node)
        _time_node = CallChain.get_time(node)
        _depth_node = get_depth_nx_node(hierarchical_view, node)
        cyto_node = {
            'data': {'id': _id_node,
                     'label': _label_node,
                     'time': _time_node,
                     'name': CallChain.get_name(node),
                     'file': CallChain.get_filename(node),
                     'caller': CallChain.get_caller(node),
                     'line': CallChain.get_line(node),
                     'lineno': CallChain.get_lineno(node),
                     'depth': _depth_node
                     },
            'classes': ''
        }

        if depth and _depth_node >= depth:
            cyto_node['classes'] += ' hide'

        if is_isolated(hierarchical_view, node):
            cyto_node['classes'] += ' isolate'
            cyto_node['data']['parent'] = graph_id
        elif is_root(hierarchical_view, node):
            cyto_node['classes'] += ' roots'
            cyto_node['data']['parent'] = graph_id
            # Create group for children
            cyto_node_children, cyto_edge_children = get_children_group(
                node, graph_id, parent=graph_id)
            if _depth_node + 1 >= depth:
                cyto_node_children['classes'] += ' hide'
                cyto_edge_children['classes'] += ' hide'
            cyto_node_children['data']['depth'] = _depth_node + 1
            nx_to_children[node] = cyto_node_children
            elements.append(cyto_node_children)
            elements.append(cyto_edge_children)

        elif is_leaf(hierarchical_view, node):
            cyto_node['classes'] += ' leaves'
        else:
            cyto_node['classes'] += ' standard'

        nx_to_cyto[node] = cyto_node

    for (source, target, attr) in graph.edges(data=True):
        _id_node_source = get_cytonode_id(source, graph_id)
        _id_node_target = get_cytonode_id(target, graph_id)

        _depth_source = get_depth_nx_node(hierarchical_view, source)
        _depth_target = get_depth_nx_node(hierarchical_view, target)

        clss = ""
        if _depth_source >= depth or _depth_target >= depth:
            clss += ' hide'

        edgetype = attr['edgetype']

        if edgetype == EdgeType.HIERARCHICAL:

            if not is_leaf(hierarchical_view, target):
                # Get id of children group of source node
                source_children_id = get_cytonode_children_id(source, graph_id)
                if target in nx_to_children:
                    # Target node have a children group
                    # so we update the parent with the chilren source
                    nx_to_children[target]['data']['parent'] = source_children_id
                else:
                    # Create the children group for target
                    cyto_node_children, cyto_edge_children = get_children_group(
                        target, graph_id, parent=source_children_id)

                    if _depth_target + 1 >= depth:
                        cyto_node_children['classes'] += ' hide'
                        cyto_edge_children['classes'] += ' hide'
                    cyto_node_children['data']['depth'] = _depth_target + 1
                    nx_to_children[target] = cyto_node_children
                    elements.append(cyto_node_children)
                    elements.append(cyto_edge_children)

            if source not in nx_to_children:
                # Create the children group
                cyto_node_children, cyto_edge_children = get_children_group(
                    source, graph_id, parent=None)  # We don't know the parent yet

                if _depth_source + 1 >= depth:
                    cyto_node_children['classes'] += ' hide'
                    cyto_edge_children['classes'] += ' hide'
                cyto_node_children['data']['depth'] = _depth_source + 1

                nx_to_children[source] = cyto_node_children
                elements.append(cyto_edge_children)

            source_children_id = get_cytonode_children_id(source, graph_id)
            # print(f'target: {target}')
            # print(f'has parent: {source_children_id}')
            nx_to_cyto[target]['data']['parent'] = source_children_id

        elif edgetype == EdgeType.CAUSAL:
            clss += ' causal'
            parent = None

            if 'cycle' in attr:
                clss += ' factor'
                cycle = attr['cycle']
                cyto_edge = {
                    'data': {
                        'source': _id_node_source,
                        'target': _id_node_target,
                        'cycle': cycle},
                    'classes': clss
                }
            else:
                if is_cycle(source, target):
                    clss += ' cycles'
                cyto_edge = {
                    'data': {
                        'source': _id_node_source,
                        'target': _id_node_target},
                    'classes': clss
                }
            elements.append(cyto_edge)
        else:
            raise Exception('Unknown edgetype')

    elements.extend(nx_to_cyto.values())

    for elt in elements:
        if 'source' in elt['data']:
            continue
        else:
            if 'depth' not in elt['data']:
                print(elt)

    return elements


def find_cytonode(elements, key):
    return filter(elements, key=key)


def load(filename):
    fi = open(filename, "rb")
    unpickler = pickle.Unpickler(fi)
    graphs = dict()
    graph_id = 0
    while True:
        try:
            graphs[graph_id] = unpickler.load()
            graph_id += 1
        except EOFError:
            break
    return graphs


def get_time(node):
    return int(CallChain.get_time(node))


def get_name(node):
    return CallChain.get_name(node)


def convert_time_to_date(time):
    s = datetime.fromtimestamp(time+18000)
    return datetime.isoformat(s)


def convert_date_to_time(date):
    s = datetime.fromisoformat(date)
    return datetime.timestamp(s)-18000


def get_gantt_child(graph, gantt, node):
    if graph.is_leaf(node, view=EdgeType.HIERARCHICAL):
        function = get_name(node)
        time = get_time(node)
        gantt.append(dict(Task=function,
                          Start=convert_time_to_date(time),
                          Finish=convert_time_to_date(time+1))
                     )
        return time
    else:
        function = get_name(node)
        start_time = get_time(node)
        end_time = 0
        for child in graph.successors(node, view=EdgeType.HIERARCHICAL):
            end_time = max(end_time, get_gantt_child(graph, gantt, child))
        gantt.append({'Task': function,
                      'Start': convert_time_to_date(start_time),
                      'Finish': convert_time_to_date(end_time)})
        assert start_time < end_time, f"Error {node}"
        return end_time


def get_gantt(graph):
    core_graph = CoreGraph(graph, 0)
    root = core_graph.unique_root()
    function = get_name(root)
    start_time = get_time(root)
    end_time = 0
    gantt = list()
    if core_graph.is_leaf(root, view=EdgeType.HIERARCHICAL):
        end_time = start_time + 1
    else:
        for child in core_graph.successors(root, view=EdgeType.HIERARCHICAL):
            end_time = max(end_time, get_gantt_child(core_graph, gantt, child))
    gantt.append({'Task': function,
                  'Start': convert_time_to_date(start_time),
                  'Finish': convert_time_to_date(end_time)})
    assert start_time < end_time, f"Error {root}"
    return gantt


raw_graphs = None
core_graphs = dict()
view_graphs = dict()
