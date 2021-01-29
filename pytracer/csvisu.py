import argparse
import sys

import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go

from pytracer.utils import get_human_size

sort_keys = ["module", "function", "calls", "memory"]


def parse_args():
    parser = argparse.ArgumentParser("csvisu")
    parser.add_argument("--csvfile", required=True, help="CSV file to print")
    parser.add_argument("--sort-by", default="module",
                        choices=sort_keys, help="Key to sort rows")
    args = parser.parse_args()
    return args


def read(args):
    return pd.read_csv(args.csvfile)


def sort(args, data):
    data.sort_values(by=[args.sort_by], inplace=True)


def clean(args, data):
    data["memory"] = data["memory"].apply(get_human_size)


def plot(args, data):
    fig = go.Figure(data=[go.Table(
        header=dict(values=list(data.columns),
                    align='left'),
        cells=dict(values=[data.module, data.function, data.call, data.memory],
                   align='left'))
    ])
    return fig


if __name__ == "__main__":

    args = parse_args()

    data = read(args)
    sort(args, data)
    clean(args, data)
    fig = plot(args, data)

    fig.show()
