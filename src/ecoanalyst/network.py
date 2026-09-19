"""
network.py: EcosystemNetwork, the main graph container.

Nodes and edges are stored as validated pydantic models and mirrored into a
networkx MultiDiGraph, so two nodes can be joined by several edges of
different kinds (for example goods one way and payment the other).

Loss rates compound along a path. If a path passes components that lose
fractions w_1 ... w_n, the fraction lost end to end is 1 - prod(1 - w_i).
Components can also convert what passes through them (see
``models.EFFICIENCY_MODES``); each component then passes on
c_i x (1 - w_i) of what reaches it.
"""

from __future__ import annotations

import json
import math
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import networkx as nx

from .models import (
    EcosystemEdge,
    EcosystemNode,
    EdgeFlow,
    NodeFinancials,
    NodeOperations,
    EFFICIENCY_MODES,
    NodeProperties,
    RelationshipType,
    normalize_edge_kind,
    normalize_node_kind,
)


def utc_now_iso() -> str:
    """Current time as a timezone-aware UTC ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def compound_loss(rates: Iterable[Optional[float]]) -> float:
    """Fraction lost after passing through components with the given loss rates.

    ``None`` counts as zero. For rates 0.1 and 0.2 the result is
    1 - 0.9 * 0.8 = 0.28.
    """
    retained = 1.0
    for rate in rates:
        retained *= 1.0 - (rate or 0.0)
    return 1.0 - retained


RETENTION_TOLERANCE = 1e-6


@dataclass(frozen=True)
class Transfer:
    """What one node or edge does to the quantity that reaches it.

    It loses ``waste_rate`` of its input as waste, then passes on
    ``conversion`` of the remainder; the rest of the remainder is the
    conversion shortfall. ``conversion`` is 1 unless the component uses the
    ``conversion`` efficiency mode.
    """

    waste_rate: float = 0.0
    conversion: float = 1.0

    @property
    def retained(self) -> float:
        """Fraction of the input that the component passes on."""
        return (1.0 - self.waste_rate) * self.conversion


def resolve_transfer(params: Any, default_mode: str = "ignore", label: str = "component") -> Transfer:
    """Turn a NodeProperties or EdgeFlow into a Transfer.

    The component's ``efficiency_mode`` wins over ``default_mode``. A missing
    ``efficiency`` means "no conversion" in conversion mode and "use
    waste_rate" in retention mode.

    Raises:
        ValueError: in retention mode when ``efficiency`` and ``waste_rate``
            are both set and disagree
    """
    mode = getattr(params, "efficiency_mode", None) or default_mode
    waste = params.waste_rate or 0.0
    efficiency = params.efficiency
    if mode == "ignore" or efficiency is None:
        return Transfer(waste, 1.0)
    if mode == "conversion":
        return Transfer(waste, efficiency)
    if mode == "retention":
        implied = 1.0 - efficiency
        if params.waste_rate is not None and abs(implied - params.waste_rate) > RETENTION_TOLERANCE:
            raise ValueError(
                f"{label}: in retention mode efficiency {efficiency} implies a loss rate of "
                f"{implied:.6g}, but waste_rate is {params.waste_rate}. Remove one of them, "
                "make them agree, or use another efficiency_mode."
            )
        return Transfer(implied, 1.0)
    raise ValueError(f"{label}: unknown efficiency_mode {mode!r}; use one of {EFFICIENCY_MODES}")


def _check_mode(mode: str) -> str:
    if mode not in EFFICIENCY_MODES:
        raise ValueError(f"efficiency_mode must be one of {EFFICIENCY_MODES}, got {mode!r}")
    return mode


def _retention_weight(*transfers: Transfer) -> Optional[float]:
    """-log of the fraction passed on, or None if nothing passes."""
    weight = 0.0
    for transfer in transfers:
        retained = transfer.retained
        if retained <= 0.0:
            return None
        weight -= math.log(retained)
    return weight


def _kind_filter(
    relationship_type: Any = None,
    edge_kinds: Optional[Iterable[Any]] = None,
) -> Optional[frozenset]:
    kinds = set()
    if relationship_type is not None:
        kinds.add(normalize_edge_kind(relationship_type))
    if edge_kinds is not None:
        if isinstance(edge_kinds, (str, RelationshipType)):
            edge_kinds = [edge_kinds]
        kinds.update(normalize_edge_kind(k) for k in edge_kinds)
    return frozenset(kinds) if kinds else None


class EcosystemNetwork:
    """
    A graph model of producers, processors, handlers, consumers, and the
    flows between them.

    Nodes carry capacity, loss rate, and optional financial data. Edges carry
    a flow kind, a maximum rate, and an optional loss rate.
    """

    def __init__(
        self,
        name: str = "Unnamed Network",
        description: str = "",
        network_type: str = "ecosystem",
        efficiency_mode: str = "ignore",
    ):
        self.network_id = str(uuid.uuid4())
        self.name = name
        self.description = description
        self.network_type = network_type
        self.efficiency_mode = _check_mode(efficiency_mode)
        self.created_at = utc_now_iso()
        self.updated_at = self.created_at

        self.graph = nx.MultiDiGraph()
        self.nodes: Dict[str, EcosystemNode] = {}
        self.edges: Dict[str, EcosystemEdge] = {}
        # Optional ecoanalyst.causal.CausalModel whose variables drive node
        # and edge parameters (see simulate / compare in that module).
        self.causal = None

    # ------------------------------------------------------------------
    # Building the graph
    # ------------------------------------------------------------------

    def add_node(
        self,
        node_type: Any,
        node_class: str,
        name: str,
        properties: Optional[Dict[str, Any]] = None,
        financials: Optional[Dict[str, Any]] = None,
        operations: Optional[Dict[str, Any]] = None,
        position_x: float = 0.0,
        position_y: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
        geometry: Optional[Dict[str, Any]] = None,
        series_ref: Optional[str] = None,
        node_id: Optional[str] = None,
    ) -> str:
        """
        Add a node to the network.

        Args:
            node_type: Node kind: a NodeType member, a built-in kind string
                (producer, processor, handler, consumer, service, grid), or a
                custom lowercase kind such as "cold_store"
            node_class: Specific class (Farm, ColdStorage, Retailer, PowerPlant, ...)
            name: Display name
            properties: capacity, efficiency, waste_rate, count, ... If capacity
                is missing it defaults to 100 units/day.
            financials: Optional capex, opex_annual, installation,
                waste_cost_per_unit, salvage_value. capex and opex_annual
                default to 0.
            operations: Optional operational constraints
            position_x: X position for drawing
            position_y: Y position for drawing
            metadata: Free-form metadata
            geometry: Optional GeoJSON-like location
            series_ref: Optional handle to an external time series
            node_id: Optional explicit ID (a UUID is generated otherwise)

        Returns:
            The node ID
        """
        props = dict(properties or {})
        props.setdefault("capacity", {"value": 100, "unit": "units/day"})

        node_financials = None
        if financials:
            fin = dict(financials)
            fin.setdefault("capex", {"value": 0, "currency": "USD"})
            fin.setdefault("opex_annual", {"value": 0, "currency": "USD"})
            node_financials = NodeFinancials.model_validate(fin)

        fields: Dict[str, Any] = dict(
            node_type=node_type,
            node_class=node_class,
            name=name,
            properties=NodeProperties.model_validate(props),
            financials=node_financials,
            operations=NodeOperations.model_validate(operations) if operations else None,
            position_x=position_x,
            position_y=position_y,
            geometry=geometry,
            series_ref=series_ref,
            metadata=metadata or {},
        )
        if node_id is not None:
            fields["node_id"] = node_id
        node = EcosystemNode(**fields)
        self.add_node_model(node)
        return node.node_id

    def add_node_model(self, node: EcosystemNode) -> str:
        """Insert an already-built EcosystemNode. Raises ValueError on a duplicate ID."""
        if node.node_id in self.nodes:
            raise ValueError(f"Duplicate node id: {node.node_id}")
        self.nodes[node.node_id] = node
        self.graph.add_node(
            node.node_id,
            node_type=node.node_type,
            node_class=node.node_class,
            name=node.name,
        )
        self.updated_at = utc_now_iso()
        return node.node_id

    def add_edge(
        self,
        source_node_id: str,
        target_node_id: str,
        relationship_type: Any,
        flow: Optional[Dict[str, Any]] = None,
        constraints: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        polarity: str = "positive",
        series_ref: Optional[str] = None,
        edge_id: Optional[str] = None,
    ) -> str:
        """
        Add a directed edge between two existing nodes.

        Args:
            source_node_id: ID of the source node
            target_node_id: ID of the target node
            relationship_type: Flow kind: a RelationshipType member, a built-in
                kind string (inventory, energy, currency, information,
                service, waste, control), a 2.x name such as
                "inventory_flow", or a custom lowercase kind
            flow: max_rate, efficiency, waste_rate, transport_time, ... If
                max_rate is missing it defaults to 100 units/day.
            constraints: Optional list of constraints
            metadata: Free-form metadata
            polarity: "positive" or "negative"
            series_ref: Optional handle to an external time series
            edge_id: Optional explicit ID (a UUID is generated otherwise)

        Returns:
            The edge ID
        """
        flow_data = dict(flow or {})
        flow_data.setdefault("max_rate", {"value": 100, "unit": "units/day"})

        fields: Dict[str, Any] = dict(
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            relationship_type=relationship_type,
            flow=EdgeFlow.model_validate(flow_data),
            polarity=polarity,
            series_ref=series_ref,
            constraints=constraints or [],
            metadata=metadata or {},
        )
        if edge_id is not None:
            fields["edge_id"] = edge_id
        edge = EcosystemEdge(**fields)
        self.add_edge_model(edge)
        return edge.edge_id

    def add_edge_model(self, edge: EcosystemEdge) -> str:
        """Insert an already-built EcosystemEdge. Both endpoints must exist."""
        if edge.source_node_id not in self.nodes:
            raise ValueError(f"Source node not found: {edge.source_node_id}")
        if edge.target_node_id not in self.nodes:
            raise ValueError(f"Target node not found: {edge.target_node_id}")
        if edge.edge_id in self.edges:
            raise ValueError(f"Duplicate edge id: {edge.edge_id}")
        self.edges[edge.edge_id] = edge
        self.graph.add_edge(
            edge.source_node_id,
            edge.target_node_id,
            key=edge.edge_id,
            relationship_type=edge.relationship_type,
            edge=edge,
        )
        self.updated_at = utc_now_iso()
        return edge.edge_id

    def get_node(self, node_id: str) -> Optional[EcosystemNode]:
        """Get a node by ID."""
        return self.nodes.get(node_id)

    def get_edge(self, edge_id: str) -> Optional[EcosystemEdge]:
        """Get an edge by ID."""
        return self.edges.get(edge_id)

    def remove_node(self, node_id: str) -> bool:
        """Remove a node and all connected edges."""
        if node_id not in self.nodes:
            return False

        edges_to_remove = [
            eid for eid, edge in self.edges.items()
            if edge.source_node_id == node_id or edge.target_node_id == node_id
        ]
        for edge_id in edges_to_remove:
            del self.edges[edge_id]

        del self.nodes[node_id]
        self.graph.remove_node(node_id)
        self.updated_at = utc_now_iso()
        return True

    def remove_edge(self, edge_id: str) -> bool:
        """Remove an edge by ID."""
        if edge_id not in self.edges:
            return False

        edge = self.edges[edge_id]
        self.graph.remove_edge(edge.source_node_id, edge.target_node_id, key=edge_id)
        del self.edges[edge_id]
        self.updated_at = utc_now_iso()
        return True

    def get_edges_by_type(self, relationship_type: Any) -> List[EcosystemEdge]:
        """Get all edges of one flow kind (aliases such as "inventory_flow" work)."""
        kind = normalize_edge_kind(relationship_type)
        return [edge for edge in self.edges.values() if edge.relationship_type == kind]

    def get_nodes_by_type(self, node_type: Any) -> List[EcosystemNode]:
        """Get all nodes of one node kind."""
        kind = normalize_node_kind(node_type)
        return [node for node in self.nodes.values() if node.node_type == kind]

    # ------------------------------------------------------------------
    # Paths and losses
    # ------------------------------------------------------------------

    def _require_node(self, node_id: str) -> EcosystemNode:
        node = self.nodes.get(node_id)
        if node is None:
            raise ValueError(f"Node not found: {node_id}")
        return node

    def _eligible_edges(
        self, source_id: str, target_id: str, kinds: Optional[frozenset]
    ) -> List[EcosystemEdge]:
        data = self.graph.get_edge_data(source_id, target_id) or {}
        return [
            attrs["edge"] for attrs in data.values()
            if kinds is None or attrs["edge"].relationship_type in kinds
        ]

    def set_efficiency_mode(self, mode: str) -> None:
        """Set the default efficiency mode for nodes and edges that do not set their own."""
        self.efficiency_mode = _check_mode(mode)
        self.updated_at = utc_now_iso()

    def node_transfer(self, node_id: str) -> Transfer:
        """The Transfer of a node under the network's efficiency settings."""
        node = self._require_node(node_id)
        return resolve_transfer(node.properties, self.efficiency_mode, f"node {node.name!r}")

    def edge_transfer(self, edge: EcosystemEdge) -> Transfer:
        """The Transfer of an edge under the network's efficiency settings."""
        return resolve_transfer(
            edge.flow, self.efficiency_mode,
            f"edge {edge.source_node_id}->{edge.target_node_id}",
        )

    def check_loss_config(self) -> List[Dict[str, str]]:
        """Report efficiency settings that raise errors or may double count.

        Returns a list of ``{"level", "component", "message"}`` items:
        ``error`` for a retention-mode component whose efficiency and
        waste_rate disagree, and ``warning`` for a conversion-mode component
        whose efficiency equals 1 - waste_rate, which usually means both
        fields describe the same loss.
        """
        issues: List[Dict[str, str]] = []
        components = [
            (f"node {n.name!r}", n.properties) for n in self.nodes.values()
        ] + [
            (f"edge {e.source_node_id}->{e.target_node_id}", e.flow) for e in self.edges.values()
        ]
        for label, params in components:
            mode = params.efficiency_mode or self.efficiency_mode
            try:
                resolve_transfer(params, self.efficiency_mode, label)
            except ValueError as exc:
                issues.append({"level": "error", "component": label, "message": str(exc)})
                continue
            if (
                mode == "conversion"
                and params.efficiency is not None
                and params.waste_rate
                and abs((1.0 - params.efficiency) - params.waste_rate) <= RETENTION_TOLERANCE
            ):
                issues.append({
                    "level": "warning",
                    "component": label,
                    "message": (
                        f"efficiency {params.efficiency} equals 1 - waste_rate; conversion mode "
                        "applies both, so this loss is counted twice. Use retention mode for "
                        "this component if both fields describe the same loss."
                    ),
                })
        return issues

    def select_path_edges(
        self,
        path: List[str],
        edge_kinds: Optional[Iterable[Any]] = None,
    ) -> List[EcosystemEdge]:
        """
        Pick the edge used between each pair of consecutive nodes in ``path``.

        When several eligible edges join the same pair, the one that passes on
        the largest fraction is used (the lowest loss rate, unless conversion
        applies). ``edge_kinds`` restricts the choice to the given flow kinds.

        Raises:
            ValueError: if a node is unknown or a pair has no eligible edge
        """
        kinds = _kind_filter(edge_kinds=edge_kinds)
        for node_id in path:
            self._require_node(node_id)
        chosen = []
        for source_id, target_id in zip(path, path[1:]):
            candidates = self._eligible_edges(source_id, target_id, kinds)
            if not candidates:
                detail = f" of kind {sorted(kinds)}" if kinds else ""
                raise ValueError(f"No edge{detail} from {source_id} to {target_id}")
            chosen.append(max(candidates, key=lambda e: self.edge_transfer(e).retained))
        return chosen

    def _path_components(
        self,
        path: List[str],
        edge_kinds: Optional[Iterable[Any]] = None,
        include_nodes: bool = True,
        include_edges: bool = True,
    ) -> List[Tuple[str, str, str, Transfer]]:
        """(type, id, breakdown key, Transfer) for each component in path order."""
        edges = self.select_path_edges(path, edge_kinds) if include_edges else []
        if not include_edges:
            for node_id in path:
                self._require_node(node_id)
        components: List[Tuple[str, str, str, Transfer]] = []
        for i, node_id in enumerate(path):
            if include_nodes:
                components.append(("node", node_id, f"node:{node_id}", self.node_transfer(node_id)))
            if i < len(edges):
                edge = edges[i]
                key = f"edge:{edge.source_node_id}->{edge.target_node_id}"
                components.append(("edge", edge.edge_id, key, self.edge_transfer(edge)))
        return components

    def calculate_path_transfer(
        self,
        path: List[str],
        edge_kinds: Optional[Iterable[Any]] = None,
    ) -> Dict[str, Any]:
        """
        Follow one unit of input along a path.

        Each component loses ``waste_rate`` of what reaches it and then
        passes on ``conversion`` of the rest (see ``Transfer``).

        Returns:
            Dict with ``delivered_fraction``, ``waste_fraction``,
            ``conversion_fraction`` (these three sum to 1) and ``components``,
            one entry per node and edge with its rates and the fraction of
            the original input it wastes and converts.

        Raises:
            ValueError: if a node is unknown, a pair has no eligible edge, or
                a component's efficiency settings conflict
        """
        current = 1.0
        waste = converted = 0.0
        rows = []
        for ctype, cid, _, transfer in self._path_components(path, edge_kinds):
            lost = current * transfer.waste_rate
            after_waste = current - lost
            shortfall = after_waste * (1.0 - transfer.conversion)
            rows.append({
                "type": ctype,
                "id": cid,
                "input_fraction": current,
                "waste_rate": transfer.waste_rate,
                "conversion": transfer.conversion,
                "waste_fraction": lost,
                "conversion_fraction": shortfall,
            })
            waste += lost
            converted += shortfall
            current = after_waste - shortfall
        return {
            "path": list(path),
            "delivered_fraction": current,
            "waste_fraction": waste,
            "conversion_fraction": converted,
            "components": rows,
        }

    def calculate_path_waste(
        self,
        path: List[str],
        include_nodes: bool = True,
        include_edges: bool = True,
        edge_kinds: Optional[Iterable[Any]] = None,
    ) -> Tuple[float, Dict[str, float]]:
        """
        Calculate the fraction of the input lost as waste along a path.

        Losses compound: with no conversion, total = 1 - prod(1 - w_i) over
        the included node and edge loss rates. When components convert what
        they pass on, each loss applies to what actually reaches it, and the
        conversion shortfall is not counted as waste (see
        ``calculate_path_transfer``). Between consecutive nodes the eligible
        edge that passes on the most is used (see ``select_path_edges``).

        Args:
            path: Node IDs in order
            include_nodes: Include node loss rates
            include_edges: Include edge loss rates
            edge_kinds: Optional flow kinds the path may use

        Returns:
            Tuple of (waste fraction of the input, effective loss rate by
            component). Keys are "node:<id>" and "edge:<source>-><target>";
            components with no loss are left out.

        Raises:
            ValueError: if a node is unknown, a pair has no eligible edge, or
                a component's efficiency settings conflict
        """
        current = 1.0
        waste = 0.0
        breakdown: Dict[str, float] = {}
        for _, _, key, transfer in self._path_components(path, edge_kinds, include_nodes, include_edges):
            if transfer.waste_rate:
                breakdown[key] = transfer.waste_rate
            lost = current * transfer.waste_rate
            waste += lost
            current = (current - lost) * transfer.conversion
        return waste, breakdown

    def _routing_graph(self, kinds: Optional[frozenset]) -> nx.DiGraph:
        """DiGraph with one edge per node pair, weighted by -log(fraction passed on).

        The weight of u->v is -log(r_edge) - log(r_u), where r = (1 - w) x c
        is what a component passes on. Summed along a path this equals -log of
        the fraction passed on by every component except the last node, which
        is the same for all paths to a given target.
        """
        G = nx.DiGraph()
        G.add_nodes_from(self.nodes)
        for edge in self.edges.values():
            if kinds is not None and edge.relationship_type not in kinds:
                continue
            weight = _retention_weight(
                self.edge_transfer(edge), self.node_transfer(edge.source_node_id)
            )
            if weight is None:
                continue
            u, v = edge.source_node_id, edge.target_node_id
            if not G.has_edge(u, v) or weight < G[u][v]["weight"]:
                G.add_edge(u, v, weight=weight)
        return G

    def find_minimum_waste_path(
        self,
        source_id: str,
        target_id: str,
        relationship_type: Any = None,
        edge_kinds: Optional[Iterable[Any]] = None,
    ) -> Tuple[Optional[List[str]], float, Dict[str, float]]:
        """
        Find the path that delivers the largest fraction from source to target.

        Each edge is weighted by -log(r_edge) - log(r_source_node), where r is
        the fraction a component passes on, so the shortest path maximizes
        the delivered fraction. With no conversion this is also the path with
        the least waste. An edge, or an edge leaving a node, that passes on
        nothing is skipped. The returned total is the waste fraction; use
        ``calculate_path_transfer`` for the delivered fraction.

        Args:
            source_id: Starting node ID
            target_id: Ending node ID
            relationship_type: Optional single flow kind (2.x argument)
            edge_kinds: Optional flow kinds the path may use

        Returns:
            (path, total loss fraction, breakdown), or (None, inf, {}) when no
            path carries anything

        Raises:
            ValueError: if source or target is unknown
        """
        self._require_node(source_id)
        self._require_node(target_id)
        kinds = _kind_filter(relationship_type, edge_kinds)
        G = self._routing_graph(kinds)
        try:
            path = nx.shortest_path(G, source_id, target_id, weight="weight")
        except nx.NetworkXNoPath:
            return None, float("inf"), {}
        total_waste, breakdown = self.calculate_path_waste(path, edge_kinds=kinds)
        return path, total_waste, breakdown

    def find_all_paths(
        self,
        source_id: str,
        target_id: str,
        max_paths: int = 10,
        edge_kinds: Optional[Iterable[Any]] = None,
    ) -> List[Tuple[List[str], float]]:
        """
        List up to ``max_paths`` simple paths, largest delivered fraction first.

        With no conversion this is also lowest compounded loss first. Each
        entry is (path, waste fraction). Paths through a component that
        passes on nothing are left out.

        Raises:
            ValueError: if source or target is unknown
        """
        self._require_node(source_id)
        self._require_node(target_id)
        kinds = _kind_filter(edge_kinds=edge_kinds)
        if source_id == target_id:
            loss, _ = self.calculate_path_waste([source_id])
            return [([source_id], loss)]

        G = self._routing_graph(kinds)
        paths: List[Tuple[List[str], float]] = []
        try:
            for path in nx.shortest_simple_paths(G, source_id, target_id, weight="weight"):
                loss, _ = self.calculate_path_waste(path, edge_kinds=kinds)
                paths.append((path, loss))
                if len(paths) >= max_paths:
                    break
        except nx.NetworkXNoPath:
            pass
        return paths

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Convert the network to its native JSON-ready dictionary."""
        return {
            "network_id": self.network_id,
            "name": self.name,
            "description": self.description,
            "network_type": self.network_type,
            "efficiency_mode": self.efficiency_mode,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.edges.values()],
            **({"causal": self.causal.to_dict()} if self.causal is not None else {}),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EcosystemNetwork":
        """Build a network from a dictionary in any supported format.

        Accepts the native format (``to_dict``, including 2.x files), the
        flow-graph exchange format (``to_flow_graph``), and the 1.x
        ``WasteNetwork`` format. See ``ecoanalyst.formats.detect_format``.
        """
        from .formats import network_from_dict

        return network_from_dict(data, cls)

    def save_to_json(self, filepath: str):
        """Save the network to a JSON file in the native format."""
        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_from_json(cls, filepath: str) -> "EcosystemNetwork":
        """Load a network from a JSON file in any supported format."""
        with open(filepath, "r") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def to_flow_graph(self) -> Dict[str, Any]:
        """Export to the portable flow-graph format (see docs/flow_graph_format.md)."""
        from .formats import to_flow_graph

        return to_flow_graph(self)

    @classmethod
    def from_flow_graph(cls, data: Dict[str, Any]) -> "EcosystemNetwork":
        """Build a network from a flow-graph dictionary."""
        from .formats import from_flow_graph

        return from_flow_graph(data, cls)

    def summary(self) -> Dict[str, Any]:
        """Counts of nodes and edges by kind."""
        node_types: Dict[str, int] = defaultdict(int)
        for node in self.nodes.values():
            node_types[node.node_type] += 1

        edge_types: Dict[str, int] = defaultdict(int)
        for edge in self.edges.values():
            edge_types[edge.relationship_type] += 1

        return {
            "network_id": self.network_id,
            "name": self.name,
            "network_type": self.network_type,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "node_types": dict(node_types),
            "edge_types": dict(edge_types),
        }
