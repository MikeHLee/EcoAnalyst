"""
formats.py: Reading and writing networks in the supported JSON formats.

Three formats are recognized:

- ``native``: the output of ``EcosystemNetwork.to_dict`` (3.x and 2.x files;
  2.x kind names such as ``"inventory_flow"`` are normalized on load).
- ``flowgraph``: the portable exchange format described in
  ``docs/flow_graph_format.md``.
- ``waste_network_v1``: the 1.x ``WasteNetwork.save_to_json`` output
  (``nodes`` with ``id``/``type``/``capacity``/``waste_rate`` and ``edges``
  with ``source``/``target``/``flow_capacity``/``transport_waste``).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Dict, Optional, Type

from .models import (
    EcosystemEdge,
    EcosystemNode,
    EdgeFlow,
    NodeFinancials,
    NodeOperations,
    NodeProperties,
    Quantity,
    normalize_node_kind,
)

if TYPE_CHECKING:  # pragma: no cover
    from .network import EcosystemNetwork

FLOW_GRAPH_FORMAT = "ecoanalyst.flowgraph"
FLOW_GRAPH_VERSION = 1

# 1.x WasteNetwork node types and the node kinds they map to.
V1_NODE_KINDS = {
    "grower": "producer",
    "distributor": "handler",
    "store": "consumer",
}


def _network_class(cls):
    if cls is None:
        from .network import EcosystemNetwork

        return EcosystemNetwork
    return cls


def detect_format(data: Dict[str, Any]) -> str:
    """Return "flowgraph", "native", or "waste_network_v1" for a loaded JSON object.

    Raises:
        ValueError: if the object matches none of them
    """
    if not isinstance(data, dict):
        raise ValueError("network JSON must be an object")
    if data.get("format") == FLOW_GRAPH_FORMAT:
        return "flowgraph"
    nodes = data.get("nodes")
    if isinstance(nodes, list):
        if not nodes:
            edges = data.get("edges") or []
            if edges and "transport_waste" in edges[0]:
                return "waste_network_v1"
            return "native"
        first = nodes[0]
        if isinstance(first, dict) and "node_id" in first:
            return "native"
        if isinstance(first, dict) and "id" in first and "waste_rate" in first:
            return "waste_network_v1"
    if "actors" in data and "flows" in data:
        raise ValueError(
            f'flow graph is missing "format": "{FLOW_GRAPH_FORMAT}"'
        )
    raise ValueError("unrecognized network JSON format")


def network_from_dict(data: Dict[str, Any], cls: Optional[Type["EcosystemNetwork"]] = None) -> "EcosystemNetwork":
    """Build a network from a dictionary in any supported format."""
    fmt = detect_format(data)
    if fmt == "flowgraph":
        return from_flow_graph(data, cls)
    if fmt == "waste_network_v1":
        return from_waste_network_v1(data, cls)
    return from_native(data, cls)


def from_native(data: Dict[str, Any], cls=None) -> "EcosystemNetwork":
    """Build a network from ``EcosystemNetwork.to_dict`` output (3.x or 2.x)."""
    network = _network_class(cls)(
        name=data.get("name", "Loaded Network"),
        description=data.get("description", ""),
        network_type=data.get("network_type", "ecosystem"),
        efficiency_mode=data.get("efficiency_mode") or "ignore",
    )
    network.network_id = data.get("network_id", network.network_id)
    network.created_at = data.get("created_at", network.created_at)

    for node_data in data.get("nodes", []):
        network.add_node_model(EcosystemNode.model_validate(node_data))
    for edge_data in data.get("edges", []):
        network.add_edge_model(EcosystemEdge.model_validate(edge_data))

    network.updated_at = data.get("updated_at", network.updated_at)
    return network


def from_waste_network_v1(data: Dict[str, Any], cls=None) -> "EcosystemNetwork":
    """Convert 1.x ``WasteNetwork`` JSON into an EcosystemNetwork.

    Node types grower, distributor, and store become producer, handler, and
    consumer; the original type is kept as ``node_class``. Other types are
    used as custom kinds if they are valid kind names. Edges become
    ``inventory`` flows with IDs of the form ``"<source>-><target>"``. The
    1.x format stored no units, so quantities get the unit ``"units"`` and
    transport times get ``"unspecified"``.
    """
    network = _network_class(cls)(
        name=data.get("name", "Converted WasteNetwork"),
        description=data.get("description", "Converted from 1.x WasteNetwork JSON"),
        network_type=data.get("network_type", "supply_chain"),
    )
    for node in data.get("nodes", []):
        legacy_type = str(node.get("type", "handler"))
        kind = V1_NODE_KINDS.get(legacy_type, legacy_type)
        network.add_node(
            node_type=kind,
            node_class=legacy_type,
            name=node["id"],
            node_id=node["id"],
            properties={
                "capacity": {"value": node.get("capacity", 0.0), "unit": "units"},
                "waste_rate": node.get("waste_rate"),
            },
        )
    for edge in data.get("edges", []):
        flow: Dict[str, Any] = {
            "max_rate": {"value": edge.get("flow_capacity", 0.0), "unit": "units"},
            "waste_rate": edge.get("transport_waste"),
        }
        if edge.get("transport_time") is not None:
            flow["transport_time"] = {"value": edge["transport_time"], "unit": "unspecified"}
        network.add_edge(
            source_node_id=edge["source"],
            target_node_id=edge["target"],
            relationship_type="inventory",
            flow=flow,
            edge_id=f'{edge["source"]}->{edge["target"]}',
        )
    return network


# ---------------------------------------------------------------------------
# Flow-graph exchange format
# ---------------------------------------------------------------------------


def to_flow_graph(network: "EcosystemNetwork") -> Dict[str, Any]:
    """Export a network to the flow-graph exchange format."""
    actors = []
    for node in network.nodes.values():
        attrs: Dict[str, Any] = {"properties": node.properties.to_dict()}
        if node.financials is not None:
            attrs["financials"] = node.financials.to_dict()
        if node.operations is not None:
            attrs["operations"] = node.operations.to_dict()
        attrs["position"] = {"x": node.position_x, "y": node.position_y}
        attrs["metadata"] = dict(node.metadata)

        actor: Dict[str, Any] = {
            "id": node.node_id,
            "kind": node.node_type,
            "name": node.name,
            "class": node.node_class,
        }
        if node.geometry is not None:
            actor["geometry"] = node.geometry
        if node.series_ref is not None:
            actor["series_ref"] = node.series_ref
        actor["attrs"] = attrs
        actors.append(actor)

    flows = []
    for edge in network.edges.values():
        flow_payload = edge.flow.to_dict()
        record: Dict[str, Any] = {
            "id": edge.edge_id,
            "kind": edge.relationship_type,
            "src": edge.source_node_id,
            "tgt": edge.target_node_id,
            "polarity": edge.polarity,
            "weight": edge.flow.max_rate.value,
            "unit": edge.flow.max_rate.unit,
        }
        if edge.series_ref is not None:
            record["series_ref"] = edge.series_ref
        record["attrs"] = {
            "flow": flow_payload,
            "constraints": list(edge.constraints),
            "metadata": dict(edge.metadata),
        }
        flows.append(record)

    return {
        "format": FLOW_GRAPH_FORMAT,
        "version": FLOW_GRAPH_VERSION,
        "name": network.name,
        "description": network.description,
        "network_type": network.network_type,
        "settings": {"efficiency_mode": network.efficiency_mode},
        "actors": actors,
        "flows": flows,
    }


def from_flow_graph(data: Dict[str, Any], cls=None) -> "EcosystemNetwork":
    """Build a network from a flow-graph dictionary.

    ``weight`` and ``unit`` set the flow's ``max_rate`` and take precedence
    over ``attrs.flow.max_rate``. Missing optional fields get their defaults:
    ``class`` falls back to the kind, ``polarity`` to "positive", a missing
    flow ``id`` gets a new UUID, and a missing capacity gets 100 units/day.

    Raises:
        ValueError: on a wrong format tag or version, or a flow that points
            at an unknown actor
    """
    if data.get("format") != FLOW_GRAPH_FORMAT:
        raise ValueError(f'expected "format": "{FLOW_GRAPH_FORMAT}"')
    version = data.get("version")
    if version != FLOW_GRAPH_VERSION:
        raise ValueError(f"unsupported flow-graph version: {version!r}")

    settings = data.get("settings") or {}
    network = _network_class(cls)(
        name=data.get("name", "Imported flow graph"),
        description=data.get("description", ""),
        network_type=data.get("network_type", "ecosystem"),
        efficiency_mode=settings.get("efficiency_mode") or "ignore",
    )

    for actor in data.get("actors", []):
        attrs = actor.get("attrs") or {}
        props = dict(attrs.get("properties") or {})
        props.setdefault("capacity", {"value": 100, "unit": "units/day"})
        position = attrs.get("position") or {}
        kind = normalize_node_kind(actor["kind"])
        node = EcosystemNode(
            node_id=actor["id"],
            node_type=kind,
            node_class=actor.get("class") or kind,
            name=actor.get("name", actor["id"]),
            properties=NodeProperties.model_validate(props),
            financials=(
                NodeFinancials.model_validate(attrs["financials"])
                if attrs.get("financials") else None
            ),
            operations=(
                NodeOperations.model_validate(attrs["operations"])
                if attrs.get("operations") else None
            ),
            position_x=position.get("x", 0.0),
            position_y=position.get("y", 0.0),
            geometry=actor.get("geometry"),
            series_ref=actor.get("series_ref"),
            metadata=dict(attrs.get("metadata") or {}),
        )
        network.add_node_model(node)

    for record in data.get("flows", []):
        attrs = record.get("attrs") or {}
        flow_data = dict(attrs.get("flow") or {})
        if "weight" in record or "unit" in record:
            current = flow_data.get("max_rate") or {}
            flow_data["max_rate"] = Quantity(
                value=record.get("weight", current.get("value", 0.0)),
                unit=record.get("unit", current.get("unit", "units")),
            )
        flow_data.setdefault("max_rate", {"value": 100, "unit": "units/day"})

        src, tgt = record["src"], record["tgt"]
        for end, label in ((src, "src"), (tgt, "tgt")):
            if end not in network.nodes:
                raise ValueError(f"flow {record.get('id')!r} has unknown {label} actor {end!r}")

        edge = EcosystemEdge(
            edge_id=record.get("id") or str(uuid.uuid4()),
            source_node_id=src,
            target_node_id=tgt,
            relationship_type=record["kind"],
            flow=EdgeFlow.model_validate(flow_data),
            polarity=record.get("polarity", "positive"),
            series_ref=record.get("series_ref"),
            constraints=list(attrs.get("constraints") or []),
            metadata=dict(attrs.get("metadata") or {}),
        )
        network.add_edge_model(edge)

    return network
