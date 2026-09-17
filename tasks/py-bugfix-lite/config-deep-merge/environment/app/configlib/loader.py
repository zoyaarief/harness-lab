import json
from functools import reduce

from .merge import merge


def load_layers(*paths):
    """Load JSON config files and merge them in order (later files win)."""
    layers = []
    for path in paths:
        with open(path) as f:
            layers.append(json.load(f))
    return reduce(merge, layers, {})
