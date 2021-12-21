#!/usr/bin/python3

import json
import sys

def pprint(_dict):
    for x in sorted(_dict.items()):
        print(x)

def load(filename):
    with open(filename, "r") as fi:
        return json.load(fi)

if '__main__' == __name__:
    filename = sys.argv[1]
    d = load(filename)
    pprint(d)
