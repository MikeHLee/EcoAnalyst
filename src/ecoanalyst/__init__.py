"""
EcoAnalyst: A library for understanding ecosystems, economies, and abstract 
physically interacting networks through graph-based modeling and analysis.

This library provides tools for:
- Modeling complex networks with typed nodes and edges
- Analyzing flows of mass, energy, and information through networks
- Calculating losses, inefficiencies, and bottlenecks
- Causal analysis using Bayesian inference
- Economic impact assessment and TCO analysis
- Path optimization across supply chains, energy grids, and ecological systems
"""

from .models import (
    NodeType,
    RelationshipType,
    Quantity,
    Cost,
    NodeProperties,
    NodeFinancials,
    NodeOperations,
    EcosystemNode,
    EdgeFlow,
    EcosystemEdge,
)

from .network import EcosystemNetwork
from .analysis import EconomicAnalysis

__version__ = "2.0.0"
__all__ = [
    # Enums
    "NodeType",
    "RelationshipType",
    # Data models
    "Quantity",
    "Cost",
    "NodeProperties",
    "NodeFinancials",
    "NodeOperations",
    "EcosystemNode",
    "EdgeFlow",
    "EcosystemEdge",
    # Core classes
    "EcosystemNetwork",
    "EconomicAnalysis",
]
