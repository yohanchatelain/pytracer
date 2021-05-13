styles = {
    'json-output': {
        'overflow-y': 'scroll',
        'height': 'calc(50% - 25px)',
        'border': 'thin lightgrey solid'
    },
    'tab': {'height': 'calc(78vh - 50px)'}
}


normal_edge_style = {
    'name': 'edge',
    'style':
    {
        'selector': 'edge',
            'style': {
                'curve-style': 'bezier',
                'target-arrow-shape': 'vee',
            }
    }
}

temporal_edge_style = {
    'name': 'causal',
    'style':  {
        'selector': '.causal',
            'style': {
                'curve-style': 'bezier',
                'target-arrow-shape': 'vee',
                'line-style': 'dotted',
            }
    }
}

normal_node_style = {
    'name': 'node',
    'style':  {
        'selector': 'node',
            'style': {
                'label': 'data(label)',
            }
    }
}

parent_node_style = {
    'name': 'parent',
    'style': {
        'selector': 'parent',
            'style': {
                'border-style': 'double',
                'background-color': 'white',
                'border-width': '1',
                'background-opacity': '0'
                #                'background-opacity': '0.1'
            }
    }
}

factor_edge_style = {
    'name': 'factor',
    'style': {
        'selector': '.factor',
            'style': {
                'line-color': 'blue',
                'label': 'data(cycle)'
            }
    }
}

root_node_style = {
    'name': 'roots',
    'style': {
        'selector': '.roots',
        'style': {
            'background-color': 'green',
            'shape': 'diamond',
            'background-opacity': '1'

        }
    }
}

leaf_node_style = {
    'name': 'leaves',
    'style': {
        'selector': '.leaves',
            'style': {
                'background-color': 'red',
                'shape': 'triangle',
                'background-opacity': '1'
            }
    }
}

isolate_node_style = {
    'name': 'isolate',
    'style':  {
        'selector': '.isolate',
            'style': {
                'background-color': 'orange',
                'shape': 'star',
                'background-opacity': '1'

            }
    }
}

cycle_node_style = {
    'name': 'cycles',
    'style': {
        'selector': '.cycles',
            'style': {
                'line-color': 'red'
            }
    }
}

standard_node_style = {
    'name': 'standard',
    'style': {
        'selector': '.standard',
            'style': {
                'background-color': 'grey',
                'shape': 'circle',
                'background-opacity': '1'

            }
    }
}

hidden_node_style = {
    'name': 'hide',
    'style': {
        'selector': '.hide',
            'style': {
                'visibility': 'hidden'
            }
    }
}
