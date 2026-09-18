import pytest
from pydantic import ValidationError

from ecoanalyst import (
    CANONICAL_EDGE_KINDS,
    CANONICAL_NODE_KINDS,
    EDGE_KIND_ALIASES,
    EcosystemNetwork,
    NodeType,
    RelationshipType,
    normalize_edge_kind,
    normalize_node_kind,
)
from helpers import add, link


def test_canonical_sets():
    assert CANONICAL_NODE_KINDS == ("producer", "processor", "handler", "consumer")
    assert CANONICAL_EDGE_KINDS == ("inventory", "energy", "currency", "information")


@pytest.mark.parametrize("alias,canonical", sorted(EDGE_KIND_ALIASES.items()))
def test_legacy_edge_aliases_normalize(alias, canonical):
    assert normalize_edge_kind(alias) == canonical


def test_all_seven_legacy_aliases_present():
    assert EDGE_KIND_ALIASES == {
        "inventory_flow": "inventory",
        "energy_flow": "energy",
        "currency_flow": "currency",
        "information_flow": "information",
        "service_flow": "service",
        "waste_flow": "waste",
        "control_signal": "control",
    }


def test_enum_values_are_canonical_kinds():
    assert RelationshipType.INVENTORY_FLOW.value == "inventory"
    assert RelationshipType.CONTROL_SIGNAL.value == "control"
    assert RelationshipType.INVENTORY is RelationshipType.INVENTORY_FLOW
    assert RelationshipType("inventory_flow") is RelationshipType.INVENTORY
    assert [m.value for m in RelationshipType] == [
        "inventory", "energy", "currency", "information", "service", "waste", "control",
    ]
    assert NodeType.PRODUCER.value == "producer"


def test_enum_members_normalize_to_plain_strings():
    assert normalize_node_kind(NodeType.GRID) == "grid"
    assert type(normalize_node_kind(NodeType.GRID)) is str
    assert normalize_edge_kind(RelationshipType.ENERGY_FLOW) == "energy"
    assert type(normalize_edge_kind(RelationshipType.ENERGY_FLOW)) is str


@pytest.mark.parametrize("kind", ["cold_store", "reservoir", "a", "x9", "heat_pump_2"])
def test_custom_kinds_are_accepted(kind):
    assert normalize_node_kind(kind) == kind
    assert normalize_edge_kind(kind) == kind


@pytest.mark.parametrize(
    "kind", ["", "Producer", "cold store", "9lives", "_hidden", "heat-pump", "inventory!", None, 3]
)
def test_malformed_kinds_are_rejected(kind):
    with pytest.raises(ValueError):
        normalize_node_kind(kind)
    with pytest.raises(ValueError):
        normalize_edge_kind(kind)


def test_models_store_normalized_strings():
    n = EcosystemNetwork()
    add(n, "a", NodeType.PRODUCER)
    add(n, "b", "cold_store")
    edge_id = link(n, "a", "b", kind=RelationshipType.INVENTORY_FLOW)
    legacy_id = link(n, "a", "b", kind="control_signal")

    assert n.nodes["a"].node_type == "producer"
    assert type(n.nodes["a"].node_type) is str
    assert n.nodes["b"].kind == "cold_store"
    assert n.edges[edge_id].relationship_type == "inventory"
    assert n.edges[legacy_id].kind == "control"
    assert n.to_dict()["edges"][0]["relationship_type"] == "inventory"


def test_invalid_kind_rejected_by_model():
    n = EcosystemNetwork()
    with pytest.raises(ValidationError):
        add(n, "a", "Not Valid")
    add(n, "a")
    add(n, "b")
    with pytest.raises(ValidationError):
        link(n, "a", "b", kind="Inventory Flow")


def test_assignment_is_validated():
    n = EcosystemNetwork()
    add(n, "a")
    add(n, "b")
    edge = n.edges[link(n, "a", "b")]
    edge.relationship_type = "waste_flow"
    assert edge.relationship_type == "waste"
    with pytest.raises(ValidationError):
        edge.relationship_type = "Bad"


def test_filters_accept_aliases():
    n = EcosystemNetwork()
    add(n, "a", "producer")
    add(n, "b", "consumer")
    link(n, "a", "b", kind="inventory")
    link(n, "b", "a", kind="currency")
    assert len(n.get_edges_by_type("inventory_flow")) == 1
    assert len(n.get_edges_by_type(RelationshipType.CURRENCY_FLOW)) == 1
    assert [x.node_id for x in n.get_nodes_by_type(NodeType.CONSUMER)] == ["b"]


def test_geometry_needs_a_type():
    n = EcosystemNetwork()
    add(n, "a", geometry={"type": "Point", "coordinates": [1.0, 2.0]})
    with pytest.raises(ValidationError):
        add(n, "b", geometry={"coordinates": [1.0, 2.0]})


def test_polarity_values():
    n = EcosystemNetwork()
    add(n, "a")
    add(n, "b")
    eid = link(n, "a", "b", kind="control", polarity="negative")
    assert n.edges[eid].polarity == "negative"
    assert n.edges[link(n, "a", "b")].polarity == "positive"
    with pytest.raises(ValidationError):
        link(n, "a", "b", polarity="sideways")
