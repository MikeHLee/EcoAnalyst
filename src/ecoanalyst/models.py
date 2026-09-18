"""
models.py: Pydantic data models for EcoAnalyst networks.

Node kinds and flow (edge) kinds are open sets of lowercase identifiers. The
library defines a canonical set and a few extended kinds, accepts the 2.x
names as aliases, and stores every kind as a plain normalized string.
"""

from __future__ import annotations

import re
import uuid
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Kind vocabulary
# ---------------------------------------------------------------------------

KIND_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

CANONICAL_NODE_KINDS = ("producer", "processor", "handler", "consumer")
EXTENDED_NODE_KINDS = ("service", "grid")
NODE_KIND_ALIASES: Dict[str, str] = {}

CANONICAL_EDGE_KINDS = ("inventory", "energy", "currency", "information")
EXTENDED_EDGE_KINDS = ("service", "waste", "control")
EDGE_KIND_ALIASES: Dict[str, str] = {
    "inventory_flow": "inventory",
    "energy_flow": "energy",
    "currency_flow": "currency",
    "information_flow": "information",
    "service_flow": "service",
    "waste_flow": "waste",
    "control_signal": "control",
}


def _normalize_kind(kind: Any, aliases: Dict[str, str], what: str) -> str:
    if isinstance(kind, Enum):
        kind = kind.value
    if not isinstance(kind, str):
        raise ValueError(f"{what} kind must be a string, got {type(kind).__name__}")
    kind = aliases.get(kind, kind)
    if not KIND_PATTERN.match(kind):
        raise ValueError(
            f"invalid {what} kind {kind!r}: use lowercase letters, digits and "
            "underscores, starting with a letter"
        )
    return kind


EFFICIENCY_MODES = ("ignore", "conversion", "retention")
EfficiencyMode = Literal["ignore", "conversion", "retention"]
"""How a component's ``efficiency`` enters the loss calculations.

- ``ignore``: ``efficiency`` is stored only. Loss comes from ``waste_rate``.
- ``conversion``: ``efficiency`` is a yield or conversion ratio applied in
  addition to ``waste_rate``: output = input x (1 - waste_rate) x efficiency.
  Use it when the component turns one thing into another (wheat into flour,
  sunlight into electricity) and also loses some of what it handles. The
  conversion shortfall is reported separately and is not priced as waste.
- ``retention``: ``efficiency`` is the fraction that gets through, so the
  loss rate is 1 - efficiency. Use it when a data source reports efficiency
  instead of loss. If ``waste_rate`` is also set, the two must agree.

A network has a default mode; a node or edge can override it.
"""


def normalize_node_kind(kind: Any) -> str:
    """Return the normalized node kind for ``kind``.

    Accepts a string or a :class:`NodeType` member. Canonical and extended
    kinds pass through; any other value matching ``^[a-z][a-z0-9_]*$`` is
    accepted as a custom kind. Anything else raises ``ValueError``.
    """
    return _normalize_kind(kind, NODE_KIND_ALIASES, "node")


def normalize_edge_kind(kind: Any) -> str:
    """Return the normalized flow kind for ``kind``.

    Accepts a string or a :class:`RelationshipType` member. The 2.x names
    (``inventory_flow``, ``control_signal`` and so on) map to their short
    forms. Any other value matching ``^[a-z][a-z0-9_]*$`` is accepted as a
    custom kind. Anything else raises ``ValueError``.
    """
    return _normalize_kind(kind, EDGE_KIND_ALIASES, "flow")


class NodeType(str, Enum):
    """Named constants for the built-in node kinds.

    Fields that hold a node kind accept these members, plain strings, or any
    custom kind that matches the kind pattern.
    """

    PRODUCER = "producer"      # where material or energy enters the network
    PROCESSOR = "processor"    # transforms what flows through it
    HANDLER = "handler"        # stores or moves without transforming
    CONSUMER = "consumer"      # where material or energy leaves the network
    SERVICE = "service"        # supports other nodes (cold chain, maintenance)
    GRID = "grid"              # external supply or sink (utility, environment)


class RelationshipType(str, Enum):
    """Named constants for the built-in flow kinds.

    The short names are the canonical members. The 2.x names
    (``INVENTORY_FLOW``, ``CONTROL_SIGNAL`` and so on) are aliases of the
    same members, so ``RelationshipType.INVENTORY_FLOW.value == "inventory"``.
    ``RelationshipType("inventory_flow")`` also works.
    """

    INVENTORY = "inventory"
    ENERGY = "energy"
    CURRENCY = "currency"
    INFORMATION = "information"
    SERVICE = "service"
    WASTE = "waste"
    CONTROL = "control"

    # 2.x member names, kept as aliases.
    INVENTORY_FLOW = "inventory"
    ENERGY_FLOW = "energy"
    CURRENCY_FLOW = "currency"
    INFORMATION_FLOW = "information"
    SERVICE_FLOW = "service"
    WASTE_FLOW = "waste"
    CONTROL_SIGNAL = "control"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str) and value in EDGE_KIND_ALIASES:
            return cls(EDGE_KIND_ALIASES[value])
        return None


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------


class Quantity(BaseModel):
    """Physical quantity with unit."""

    value: float
    unit: str  # "kg", "kWh", "USD", "tons/day", "%", "units"

    def __str__(self) -> str:
        return f"{self.value} {self.unit}"

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


class Cost(BaseModel):
    """Financial cost with currency."""

    value: float
    currency: str = "USD"

    def __str__(self) -> str:
        return f"{self.currency} {self.value:,.2f}"

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


class NodeProperties(BaseModel):
    """Physical properties of a node.

    ``capacity`` is per unit; ``count`` is the number of identical units.
    ``waste_rate`` is the fraction of what reaches the node that it loses.
    How ``efficiency`` is used depends on ``efficiency_mode``, or on the
    network's default when that is None (see ``EFFICIENCY_MODES``).
    """

    capacity: Quantity
    efficiency: Optional[float] = Field(None, ge=0.0, le=1.0)
    efficiency_mode: Optional[EfficiencyMode] = None
    lifetime_years: int = Field(10, ge=1, le=100)
    waste_rate: Optional[float] = Field(None, ge=0.0, le=1.0)
    degradation_rate: Optional[float] = Field(None, ge=0.0, le=1.0)  # per year
    count: int = Field(1, ge=1)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


class NodeFinancials(BaseModel):
    """Economic data for a node."""

    capex: Cost
    opex_annual: Cost
    installation: Optional[Cost] = None
    waste_cost_per_unit: Optional[Cost] = None
    salvage_value: Optional[Cost] = None

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


class NodeOperations(BaseModel):
    """Operational constraints for a node."""

    storage_days: Optional[float] = None
    temperature_range: Optional[Dict[str, Any]] = None  # {"min": 2, "max": 8, "unit": "C"}
    humidity_range: Optional[Dict[str, Any]] = None     # {"min": 30, "max": 70, "unit": "%"}
    annual_throughput: Optional[float] = None
    operating_hours: Optional[float] = Field(None, ge=0, le=24)  # hours per day
    constraints: List[str] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


class EdgeFlow(BaseModel):
    """Flow properties of an edge.

    ``waste_rate`` is the fraction lost in transit. How ``efficiency`` is
    used depends on ``efficiency_mode``, or on the network's default when
    that is None (see ``EFFICIENCY_MODES``).
    """

    max_rate: Quantity
    min_rate: Optional[Quantity] = None
    efficiency: Optional[float] = Field(None, ge=0.0, le=1.0)
    efficiency_mode: Optional[EfficiencyMode] = None
    direction: str = "unidirectional"  # or "bidirectional"
    transport_time: Optional[Quantity] = None
    waste_rate: Optional[float] = Field(None, ge=0.0, le=1.0)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


def _check_geometry(value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if value is not None and not isinstance(value.get("type"), str):
        raise ValueError('geometry must be a GeoJSON-like object with a string "type"')
    return value


# ---------------------------------------------------------------------------
# Graph elements
# ---------------------------------------------------------------------------


class EcosystemNode(BaseModel):
    """A node (actor) in the network.

    ``node_type`` holds the node kind as a normalized string. ``geometry`` is
    an optional GeoJSON-like object (for example
    ``{"type": "Point", "coordinates": [lon, lat]}``). ``series_ref`` is an
    optional handle to a time series stored elsewhere; the library stores it
    and exports it but does not read it.
    """

    model_config = ConfigDict(validate_assignment=True)

    node_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    node_type: str
    node_class: str  # "Farm", "ColdStorage", "Retailer", "PowerPlant", ...
    name: str
    properties: NodeProperties
    financials: Optional[NodeFinancials] = None
    operations: Optional[NodeOperations] = None
    position_x: float = 0.0
    position_y: float = 0.0
    geometry: Optional[Dict[str, Any]] = None
    series_ref: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("node_type", mode="before")
    @classmethod
    def _normalize_node_type(cls, value: Any) -> str:
        return normalize_node_kind(value)

    @field_validator("geometry")
    @classmethod
    def _validate_geometry(cls, value):
        return _check_geometry(value)

    @property
    def kind(self) -> str:
        """The node kind (same as ``node_type``)."""
        return self.node_type

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


class EcosystemEdge(BaseModel):
    """A directed edge (flow) between two nodes.

    ``relationship_type`` holds the flow kind as a normalized string.
    ``polarity`` records whether the flow adds to (``positive``) or draws
    down (``negative``) the target, for example a control signal that
    throttles it. The loss calculations do not use it. ``series_ref`` is an
    optional handle to a time series stored elsewhere.
    """

    model_config = ConfigDict(validate_assignment=True)

    edge_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_node_id: str
    target_node_id: str
    relationship_type: str
    flow: EdgeFlow
    polarity: Literal["positive", "negative"] = "positive"
    series_ref: Optional[str] = None
    constraints: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("relationship_type", mode="before")
    @classmethod
    def _normalize_relationship_type(cls, value: Any) -> str:
        return normalize_edge_kind(value)

    @property
    def kind(self) -> str:
        """The flow kind (same as ``relationship_type``)."""
        return self.relationship_type

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


# ---------------------------------------------------------------------------
# REST request and response bodies
# ---------------------------------------------------------------------------


class CreateNetworkRequest(BaseModel):
    """Request to create a new network."""

    name: str
    description: Optional[str] = None
    network_type: str = "ecosystem"  # "supply_chain", "energy", "ecosystem", "economy", ...
    efficiency_mode: EfficiencyMode = "ignore"


class AddNodeRequest(BaseModel):
    """Request to add a node to a network."""

    node_type: str
    node_class: str
    name: str
    properties: NodeProperties
    financials: Optional[NodeFinancials] = None
    operations: Optional[NodeOperations] = None
    position_x: float = 0.0
    position_y: float = 0.0
    geometry: Optional[Dict[str, Any]] = None
    series_ref: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("node_type", mode="before")
    @classmethod
    def _normalize_node_type(cls, value: Any) -> str:
        return normalize_node_kind(value)

    @field_validator("geometry")
    @classmethod
    def _validate_geometry(cls, value):
        return _check_geometry(value)


class AddEdgeRequest(BaseModel):
    """Request to add an edge to a network."""

    source_node_id: str
    target_node_id: str
    relationship_type: str
    flow: EdgeFlow
    polarity: Literal["positive", "negative"] = "positive"
    series_ref: Optional[str] = None
    constraints: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("relationship_type", mode="before")
    @classmethod
    def _normalize_relationship_type(cls, value: Any) -> str:
        return normalize_edge_kind(value)


class NetworkResponse(BaseModel):
    """Response containing network data."""

    network_id: str
    name: str
    description: Optional[str] = None
    network_type: str
    nodes: List[EcosystemNode] = Field(default_factory=list)
    edges: List[EcosystemEdge] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
