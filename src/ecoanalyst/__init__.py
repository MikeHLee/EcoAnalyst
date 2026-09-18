"""
EcoAnalyst: graph models of material, energy, money, and information flows
between producers, processors, handlers, and consumers, with loss, routing,
and cost analysis.

Main entry points:

- :class:`EcosystemNetwork` builds the graph, computes compounded path
  losses, finds minimum-loss routes, and reads and writes JSON.
- :class:`EconomicAnalysis` prices losses, follows a quantity along a path,
  ranks hotspots, and computes total cost of ownership.

The REST server (``ecoanalyst.api``), the MCP server
(``ecoanalyst.mcp_server``), and the 1.x modules (``ecoanalyst.legacy``) are
imported separately because they need optional dependencies.
"""

from ._version import __version__
from .analysis import EconomicAnalysis
from .formats import FLOW_GRAPH_FORMAT, FLOW_GRAPH_VERSION, detect_format
from .models import (
    CANONICAL_EDGE_KINDS,
    CANONICAL_NODE_KINDS,
    EDGE_KIND_ALIASES,
    EXTENDED_EDGE_KINDS,
    EXTENDED_NODE_KINDS,
    Cost,
    EcosystemEdge,
    EcosystemNode,
    EdgeFlow,
    NodeFinancials,
    NodeOperations,
    NodeProperties,
    NodeType,
    Quantity,
    RelationshipType,
    normalize_edge_kind,
    normalize_node_kind,
)
from .network import EcosystemNetwork, compound_loss

__all__ = [
    "__version__",
    # Kind vocabulary
    "NodeType",
    "RelationshipType",
    "CANONICAL_NODE_KINDS",
    "EXTENDED_NODE_KINDS",
    "CANONICAL_EDGE_KINDS",
    "EXTENDED_EDGE_KINDS",
    "EDGE_KIND_ALIASES",
    "normalize_node_kind",
    "normalize_edge_kind",
    # Data models
    "Quantity",
    "Cost",
    "NodeProperties",
    "NodeFinancials",
    "NodeOperations",
    "EcosystemNode",
    "EdgeFlow",
    "EcosystemEdge",
    # Core classes and helpers
    "EcosystemNetwork",
    "EconomicAnalysis",
    "compound_loss",
    # Formats
    "FLOW_GRAPH_FORMAT",
    "FLOW_GRAPH_VERSION",
    "detect_format",
]
