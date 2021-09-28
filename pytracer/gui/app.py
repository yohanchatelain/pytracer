#!/usr/bin/python3

import dash
import os

__root__ = os.path.dirname(__spec__.origin)
assets_folder = os.path.join(__root__, 'assets')


external_stylesheets = [
    "https://github.com/plotly/dash-app-stylesheets/blob/master/dash-oil-and-gas.css"]
app = dash.Dash(__name__,
                external_stylesheets=[external_stylesheets],
                meta_tags=[{"name": "viewport",
                            "content": "width=device-width"}],
                assets_folder=assets_folder)
mathjax = 'https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.5/MathJax.js?config=TeX-MML-AM_CHTML'
app.scripts.append_script({'external_url': mathjax})
server = app.server
