import math
from datetime import datetime

import pytest

from ecoanalyst import EcosystemNetwork, RelationshipType, compound_loss
from helpers import add, link


def test_add_and_remove_nodes_and_edges():
    n = EcosystemNetwork()
    add(n, "a")
    add(n, "b")
    add(n, "c")
    e1 = link(n, "a", "b")
    e2 = link(n, "b", "c")
    e3 = link(n, "a", "b", kind="currency")
    assert len(n.nodes) == 3 and len(n.edges) == 3
    assert n.graph.number_of_edges("a", "b") == 2

    assert n.remove_edge(e3)
    assert not n.remove_edge(e3)
    assert n.graph.number_of_edges("a", "b") == 1

    assert n.remove_node("b")
    assert not n.remove_node("b")
    assert set(n.nodes) == {"a", "c"}
    assert e1 not in n.edges and e2 not in n.edges
    assert n.graph.number_of_edges() == 0


def test_edge_needs_existing_nodes():
    n = EcosystemNetwork()
    add(n, "a")
    with pytest.raises(ValueError, match="Target node not found"):
        link(n, "a", "missing")
    with pytest.raises(ValueError, match="Source node not found"):
        link(n, "missing", "a")


def test_duplicate_ids_rejected():
    n = EcosystemNetwork()
    add(n, "a")
    with pytest.raises(ValueError, match="Duplicate node id"):
        add(n, "a")


def test_timestamps_are_utc_aware():
    n = EcosystemNetwork()
    stamp = datetime.fromisoformat(n.created_at)
    assert stamp.utcoffset() is not None
    assert stamp.utcoffset().total_seconds() == 0


def test_compound_loss_helper():
    assert compound_loss([0.1, 0.2]) == pytest.approx(0.28)
    assert compound_loss([]) == 0.0
    assert compound_loss([None, 0.5]) == pytest.approx(0.5)
    assert compound_loss([1.0, 0.1]) == pytest.approx(1.0)


def test_path_loss_compounds():
    n = EcosystemNetwork()
    add(n, "a", rate=0.1)
    add(n, "b", rate=0.2)
    link(n, "a", "b")
    total, breakdown = n.calculate_path_waste(["a", "b"])
    assert total == pytest.approx(0.28)
    assert breakdown == {"node:a": 0.1, "node:b": 0.2}


def test_path_loss_stays_below_one():
    # Additive summation would report 0.6 + 0.5 + 0.6 = 1.7.
    n = EcosystemNetwork()
    add(n, "a", rate=0.6)
    add(n, "b", rate=0.6)
    link(n, "a", "b", 0.5)
    total, _ = n.calculate_path_waste(["a", "b"])
    assert total == pytest.approx(1 - 0.4 * 0.5 * 0.4)
    assert total < 1.0


def test_path_loss_node_and_edge_switches():
    n = EcosystemNetwork()
    add(n, "a", rate=0.1)
    add(n, "b", rate=0.2)
    link(n, "a", "b", 0.5)
    assert n.calculate_path_waste(["a", "b"], include_edges=False)[0] == pytest.approx(0.28)
    assert n.calculate_path_waste(["a", "b"], include_nodes=False)[0] == pytest.approx(0.5)


def routing_network():
    """Path A (s -> m -> t) loses 0.5 then 0.5; path B (s -> t) loses 0.9."""
    n = EcosystemNetwork()
    add(n, "s", "producer")
    add(n, "m", "handler")
    add(n, "t", "consumer")
    link(n, "s", "m", 0.5)
    link(n, "m", "t", 0.5)
    link(n, "s", "t", 0.9)
    return n


def test_min_loss_route_uses_compounded_loss():
    n = routing_network()
    # Additive scores would be A = 1.0 and B = 0.9, picking B.
    # Compounded, A loses 0.75 and B loses 0.9, so A is correct.
    path, loss, breakdown = n.find_minimum_waste_path("s", "t")
    assert path == ["s", "m", "t"]
    assert loss == pytest.approx(0.75)
    assert breakdown == {"edge:s->m": 0.5, "edge:m->t": 0.5}


def test_min_loss_route_counts_source_node_losses():
    n = EcosystemNetwork()
    add(n, "s", "producer")
    add(n, "hub", "handler", rate=0.5)
    add(n, "t", "consumer")
    link(n, "s", "hub", 0.0)
    link(n, "hub", "t", 0.0)
    link(n, "s", "t", 0.4)
    path, loss, _ = n.find_minimum_waste_path("s", "t")
    assert path == ["s", "t"]
    assert loss == pytest.approx(0.4)


def test_edges_with_total_loss_are_skipped():
    n = EcosystemNetwork()
    add(n, "s")
    add(n, "t")
    link(n, "s", "t", 1.0)
    path, loss, breakdown = n.find_minimum_waste_path("s", "t")
    assert path is None and math.isinf(loss) and breakdown == {}

    link(n, "s", "t", 0.99)
    path, loss, _ = n.find_minimum_waste_path("s", "t")
    assert path == ["s", "t"]
    assert loss == pytest.approx(0.99)


def test_unknown_endpoint_raises():
    n = routing_network()
    with pytest.raises(ValueError, match="Node not found"):
        n.find_minimum_waste_path("s", "nowhere")


def parallel_network():
    n = EcosystemNetwork()
    add(n, "a", "producer")
    add(n, "b", "consumer")
    link(n, "a", "b", 0.3, kind="currency")  # added first on purpose
    link(n, "a", "b", 0.05, kind="inventory")
    link(n, "a", "b", 0.2, kind="inventory")
    return n


def test_parallel_edges_pick_lowest_loss():
    n = parallel_network()
    total, breakdown = n.calculate_path_waste(["a", "b"])
    assert total == pytest.approx(0.05)
    assert breakdown == {"edge:a->b": 0.05}


def test_parallel_edges_respect_edge_kinds():
    n = parallel_network()
    assert n.calculate_path_waste(["a", "b"], edge_kinds=["currency"])[0] == pytest.approx(0.3)
    assert n.calculate_path_waste(["a", "b"], edge_kinds=["inventory_flow"])[0] == pytest.approx(0.05)
    chosen = n.select_path_edges(["a", "b"], edge_kinds=[RelationshipType.CURRENCY])
    assert [e.relationship_type for e in chosen] == ["currency"]
    with pytest.raises(ValueError, match="No edge"):
        n.calculate_path_waste(["a", "b"], edge_kinds=["energy"])


def test_routing_respects_edge_kinds(chain):
    # A zero-loss payment edge must not become a route for goods.
    n = chain
    link(n, "farm", "shop", 0.0, kind="currency")
    path, loss, _ = n.find_minimum_waste_path("farm", "shop")
    assert path == ["farm", "shop"]
    assert loss == pytest.approx(1 - 0.9 * 0.8)

    path, loss, _ = n.find_minimum_waste_path("farm", "shop", edge_kinds=["inventory"])
    assert path == ["farm", "store", "shop"]
    assert loss == pytest.approx(1 - 0.9 * 0.95 * 0.98 * 0.99 * 0.8)

    path, _, _ = n.find_minimum_waste_path(
        "farm", "shop", relationship_type=RelationshipType.INVENTORY_FLOW
    )
    assert path == ["farm", "store", "shop"]


def test_find_all_paths_sorted_by_compounded_loss(chain):
    paths = chain.find_all_paths("farm", "shop", edge_kinds=["inventory"])
    assert [p for p, _ in paths] == [["farm", "store", "shop"], ["farm", "shop"]]
    losses = [loss for _, loss in paths]
    assert losses == sorted(losses)
    assert losses[1] == pytest.approx(1 - 0.9 * 0.7 * 0.8)
    assert len(chain.find_all_paths("farm", "shop", max_paths=1, edge_kinds=["inventory"])) == 1


def test_summary_counts_kinds(chain):
    s = chain.summary()
    assert s["node_count"] == 3 and s["edge_count"] == 4
    assert s["node_types"] == {"producer": 1, "handler": 1, "consumer": 1}
    assert s["edge_types"] == {"inventory": 3, "currency": 1}
