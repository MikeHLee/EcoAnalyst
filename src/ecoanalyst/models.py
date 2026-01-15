"""
models.py: Pydantic data models for EcoAnalyst ecosystem networks.

Provides typed, validated schemas for nodes, edges, and their properties,
enabling robust API design and data validation.
"""

from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
import uuid


class NodeType(str, Enum):
    """Ecosystem node types - applicable across domains."""
    PRODUCER = "producer"       # Where goods/resources enter (farms, power plants, sources)
    PROCESSOR = "processor"     # Transforms goods (factories, refineries, converters)
    HANDLER = "handler"         # Stores/moves goods (warehouses, distributors, buffers)
    CONSUMER = "consumer"       # Where goods exit (retail, end users, sinks)
    SERVICE = "service"         # Provides services that reduce loss (cold chain, maintenance)
    GRID = "grid"               # External supply (utilities, raw materials, environment)


class RelationshipType(str, Enum):
    """Edge types for ecosystem flows."""
    INVENTORY_FLOW = "inventory_flow"      # Goods/resource movement
    SERVICE_FLOW = "service_flow"          # Service provision
    CURRENCY_FLOW = "currency_flow"        # Financial transactions
    WASTE_FLOW = "waste_flow"              # Waste/byproduct movement
    ENERGY_FLOW = "energy_flow"            # Energy transfer
    INFORMATION_FLOW = "information_flow"  # Data/signal transfer
    CONTROL_SIGNAL = "control_signal"      # Management/coordination


class Quantity(BaseModel):
    """Physical quantity with unit."""
    value: float
    unit: str  # "kg", "kWh", "USD", "tons/day", "%", "units"
    
    def __str__(self) -> str:
        return f"{self.value} {self.unit}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {"value": self.value, "unit": self.unit}


class Cost(BaseModel):
    """Financial cost with currency."""
    value: float
    currency: str = "USD"
    
    def __str__(self) -> str:
        return f"{self.currency} {self.value:,.2f}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {"value": self.value, "currency": self.currency}


class NodeProperties(BaseModel):
    """Structured properties for any node."""
    capacity: Quantity                          # Processing/handling capacity
    efficiency: float = Field(1.0, ge=0.0, le=1.0)  # Conversion efficiency
    lifetime_years: int = Field(10, ge=1, le=100)
    waste_rate: Optional[float] = Field(None, ge=0.0, le=1.0)  # Static loss percentage
    degradation_rate: Optional[float] = Field(None, ge=0.0, le=1.0)  # % per year
    count: int = Field(1, ge=1)                 # Number of units
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "capacity": self.capacity.to_dict(),
            "efficiency": self.efficiency,
            "lifetime_years": self.lifetime_years,
            "waste_rate": self.waste_rate,
            "degradation_rate": self.degradation_rate,
            "count": self.count,
        }


class NodeFinancials(BaseModel):
    """Economic data for any node."""
    capex: Cost                                 # Capital expenditure
    opex_annual: Cost                           # Operating cost per year
    installation: Optional[Cost] = None
    waste_cost_per_unit: Optional[Cost] = None  # Cost of waste per unit
    salvage_value: Optional[Cost] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "capex": self.capex.to_dict(),
            "opex_annual": self.opex_annual.to_dict(),
            "installation": self.installation.to_dict() if self.installation else None,
            "waste_cost_per_unit": self.waste_cost_per_unit.to_dict() if self.waste_cost_per_unit else None,
            "salvage_value": self.salvage_value.to_dict() if self.salvage_value else None,
        }


class NodeOperations(BaseModel):
    """Operational constraints for a node."""
    storage_days: Optional[float] = None        # Max storage duration
    temperature_range: Optional[Dict[str, Any]] = None  # {"min": 2, "max": 8, "unit": "C"}
    humidity_range: Optional[Dict[str, Any]] = None     # {"min": 30, "max": 70, "unit": "%"}
    annual_throughput: Optional[float] = None
    operating_hours: Optional[float] = Field(None, ge=0, le=24)  # Hours per day
    constraints: List[str] = Field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "storage_days": self.storage_days,
            "temperature_range": self.temperature_range,
            "humidity_range": self.humidity_range,
            "annual_throughput": self.annual_throughput,
            "operating_hours": self.operating_hours,
            "constraints": self.constraints,
        }


class EcosystemNode(BaseModel):
    """A node in the ecosystem graph."""
    node_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    node_type: NodeType
    node_class: str                    # "Farm", "ColdStorage", "Retailer", "PowerPlant", etc.
    name: str
    properties: NodeProperties
    financials: Optional[NodeFinancials] = None
    operations: Optional[NodeOperations] = None
    position_x: float = 0.0
    position_y: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type if isinstance(self.node_type, str) else self.node_type.value,
            "node_class": self.node_class,
            "name": self.name,
            "properties": self.properties.to_dict(),
            "financials": self.financials.to_dict() if self.financials else None,
            "operations": self.operations.to_dict() if self.operations else None,
            "position_x": self.position_x,
            "position_y": self.position_y,
            "metadata": self.metadata,
        }


class EdgeFlow(BaseModel):
    """Flow properties for edges."""
    max_rate: Quantity                     # Max flow rate (kg/day, tons/hour, kW)
    min_rate: Optional[Quantity] = None
    efficiency: float = Field(1.0, ge=0.0, le=1.0)  # Transfer efficiency
    direction: str = "unidirectional"      # or "bidirectional"
    transport_time: Optional[Quantity] = None  # Duration
    waste_rate: Optional[float] = Field(None, ge=0.0, le=1.0)  # Loss during transport
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_rate": self.max_rate.to_dict(),
            "min_rate": self.min_rate.to_dict() if self.min_rate else None,
            "efficiency": self.efficiency,
            "direction": self.direction,
            "transport_time": self.transport_time.to_dict() if self.transport_time else None,
            "waste_rate": self.waste_rate,
        }


class EcosystemEdge(BaseModel):
    """An edge in the ecosystem graph."""
    edge_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_node_id: str
    target_node_id: str
    relationship_type: RelationshipType
    flow: EdgeFlow
    constraints: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "relationship_type": self.relationship_type if isinstance(self.relationship_type, str) else self.relationship_type.value,
            "flow": self.flow.to_dict(),
            "constraints": self.constraints,
            "metadata": self.metadata,
        }


# Request/Response models for API
class CreateNetworkRequest(BaseModel):
    """Request to create a new network."""
    name: str
    description: Optional[str] = None
    network_type: str = "ecosystem"  # "supply_chain", "energy", "ecosystem", "economy"


class AddNodeRequest(BaseModel):
    """Request to add a node to a network."""
    node_type: NodeType
    node_class: str
    name: str
    properties: NodeProperties
    financials: Optional[NodeFinancials] = None
    operations: Optional[NodeOperations] = None
    position_x: float = 0.0
    position_y: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AddEdgeRequest(BaseModel):
    """Request to add an edge to a network."""
    source_node_id: str
    target_node_id: str
    relationship_type: RelationshipType
    flow: EdgeFlow
    constraints: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


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
