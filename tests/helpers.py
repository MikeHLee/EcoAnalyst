"""Small builders shared by the tests."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def kg(value):
    return {"value": value, "unit": "kg/day"}


def add(network, node_id, kind="handler", rate=None, capacity=1000, node_class=None, **extra):
    """Add a node with an explicit ID and an optional loss rate."""
    props = {"capacity": kg(capacity)}
    if rate is not None:
        props["waste_rate"] = rate
    return network.add_node(
        kind, node_class or node_id.title(), node_id, properties=props, node_id=node_id, **extra
    )


def link(network, src, tgt, rate=None, kind="inventory", max_rate=1000, **extra):
    """Add an edge with an optional loss rate."""
    flow = {"max_rate": kg(max_rate)}
    if rate is not None:
        flow["waste_rate"] = rate
    return network.add_edge(src, tgt, kind, flow, **extra)
