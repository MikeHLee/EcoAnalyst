"""
network.py: Core EcosystemNetwork class for graph-based modeling.

Provides the main network container with operations for adding nodes/edges,
calculating paths, and analyzing flows.
"""

import json
import uuid
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional, Callable
from collections import defaultdict

import networkx as nx
import numpy as np

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


class EcosystemNetwork:
    """
    A graph-based model for ecosystems, economies, and physically interacting networks.
    
    Supports typed nodes and edges, flow analysis, waste/loss calculation,
    and path optimization.
    """
    
    def __init__(
        self,
        name: str = "Unnamed Network",
        description: str = "",
        network_type: str = "ecosystem"
    ):
        self.network_id = str(uuid.uuid4())
        self.name = name
        self.description = description
        self.network_type = network_type
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
        
        self.graph = nx.MultiDiGraph()
        self.nodes: Dict[str, EcosystemNode] = {}
        self.edges: Dict[str, EcosystemEdge] = {}
    
    def add_node(
        self,
        node_type: NodeType,
        node_class: str,
        name: str,
        properties: Dict[str, Any],
        financials: Optional[Dict[str, Any]] = None,
        operations: Optional[Dict[str, Any]] = None,
        position_x: float = 0.0,
        position_y: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add a node to the network.
        
        Args:
            node_type: Type of node (producer, processor, handler, consumer, service, grid)
            node_class: Specific class (Farm, ColdStorage, Retailer, PowerPlant, etc.)
            name: Display name for the node
            properties: Node properties including capacity, efficiency, waste_rate
            financials: Optional financial data (capex, opex, etc.)
            operations: Optional operational constraints
            position_x: X position for visualization
            position_y: Y position for visualization
            metadata: Additional metadata
            
        Returns:
            node_id: Unique identifier for the created node
        """
        # Build NodeProperties
        capacity_data = properties.get("capacity", {"value": 100, "unit": "units/day"})
        node_props = NodeProperties(
            capacity=Quantity(**capacity_data) if isinstance(capacity_data, dict) else capacity_data,
            efficiency=properties.get("efficiency", 1.0),
            lifetime_years=properties.get("lifetime_years", 10),
            waste_rate=properties.get("waste_rate"),
            degradation_rate=properties.get("degradation_rate"),
            count=properties.get("count", 1),
        )
        
        # Build NodeFinancials if provided
        node_financials = None
        if financials:
            capex_data = financials.get("capex", {"value": 0, "currency": "USD"})
            opex_data = financials.get("opex_annual", {"value": 0, "currency": "USD"})
            node_financials = NodeFinancials(
                capex=Cost(**capex_data) if isinstance(capex_data, dict) else capex_data,
                opex_annual=Cost(**opex_data) if isinstance(opex_data, dict) else opex_data,
                installation=Cost(**financials["installation"]) if financials.get("installation") else None,
                waste_cost_per_unit=Cost(**financials["waste_cost_per_unit"]) if financials.get("waste_cost_per_unit") else None,
                salvage_value=Cost(**financials["salvage_value"]) if financials.get("salvage_value") else None,
            )
        
        # Build NodeOperations if provided
        node_operations = None
        if operations:
            node_operations = NodeOperations(**operations)
        
        # Create node
        node = EcosystemNode(
            node_type=node_type,
            node_class=node_class,
            name=name,
            properties=node_props,
            financials=node_financials,
            operations=node_operations,
            position_x=position_x,
            position_y=position_y,
            metadata=metadata or {},
        )
        
        self.nodes[node.node_id] = node
        self.graph.add_node(
            node.node_id,
            node_type=node_type.value if isinstance(node_type, NodeType) else node_type,
            node_class=node_class,
            name=name,
        )
        
        self.updated_at = datetime.now().isoformat()
        return node.node_id
    
    def add_edge(
        self,
        source_node_id: str,
        target_node_id: str,
        relationship_type: RelationshipType,
        flow: Dict[str, Any],
        constraints: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add an edge connecting two nodes.
        
        Args:
            source_node_id: ID of source node
            target_node_id: ID of target node
            relationship_type: Type of relationship
            flow: Flow properties (max_rate, efficiency, waste_rate, etc.)
            constraints: Optional list of constraints
            metadata: Additional metadata
            
        Returns:
            edge_id: Unique identifier for the created edge
        """
        if source_node_id not in self.nodes:
            raise ValueError(f"Source node not found: {source_node_id}")
        if target_node_id not in self.nodes:
            raise ValueError(f"Target node not found: {target_node_id}")
        
        # Build EdgeFlow
        max_rate_data = flow.get("max_rate", {"value": 100, "unit": "units/day"})
        edge_flow = EdgeFlow(
            max_rate=Quantity(**max_rate_data) if isinstance(max_rate_data, dict) else max_rate_data,
            min_rate=Quantity(**flow["min_rate"]) if flow.get("min_rate") else None,
            efficiency=flow.get("efficiency", 1.0),
            direction=flow.get("direction", "unidirectional"),
            transport_time=Quantity(**flow["transport_time"]) if flow.get("transport_time") else None,
            waste_rate=flow.get("waste_rate"),
        )
        
        # Create edge
        edge = EcosystemEdge(
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            relationship_type=relationship_type,
            flow=edge_flow,
            constraints=constraints or [],
            metadata=metadata or {},
        )
        
        self.edges[edge.edge_id] = edge
        self.graph.add_edge(
            source_node_id,
            target_node_id,
            key=edge.edge_id,
            relationship_type=relationship_type.value if isinstance(relationship_type, RelationshipType) else relationship_type,
            edge=edge,
        )
        
        self.updated_at = datetime.now().isoformat()
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
        
        # Remove connected edges
        edges_to_remove = [
            eid for eid, edge in self.edges.items()
            if edge.source_node_id == node_id or edge.target_node_id == node_id
        ]
        for edge_id in edges_to_remove:
            del self.edges[edge_id]
        
        del self.nodes[node_id]
        self.graph.remove_node(node_id)
        self.updated_at = datetime.now().isoformat()
        return True
    
    def remove_edge(self, edge_id: str) -> bool:
        """Remove an edge by ID."""
        if edge_id not in self.edges:
            return False
        
        edge = self.edges[edge_id]
        self.graph.remove_edge(edge.source_node_id, edge.target_node_id, key=edge_id)
        del self.edges[edge_id]
        self.updated_at = datetime.now().isoformat()
        return True
    
    def get_edges_by_type(self, relationship_type: RelationshipType) -> List[EcosystemEdge]:
        """Get all edges of a specific type."""
        return [
            edge for edge in self.edges.values()
            if edge.relationship_type == relationship_type or 
               edge.relationship_type == relationship_type.value
        ]
    
    def get_nodes_by_type(self, node_type: NodeType) -> List[EcosystemNode]:
        """Get all nodes of a specific type."""
        return [
            node for node in self.nodes.values()
            if node.node_type == node_type or node.node_type == node_type.value
        ]
    
    def calculate_path_waste(
        self,
        path: List[str],
        include_nodes: bool = True,
        include_edges: bool = True
    ) -> Tuple[float, Dict[str, float]]:
        """
        Calculate total waste/loss along a path.
        
        Args:
            path: List of node IDs representing a path
            include_nodes: Include node waste in calculation
            include_edges: Include edge waste in calculation
            
        Returns:
            Tuple of (total_waste_percentage, breakdown_by_component)
        """
        total_waste = 0.0
        breakdown = {}
        
        if include_nodes:
            for node_id in path:
                node = self.nodes.get(node_id)
                if node and node.properties.waste_rate:
                    waste = node.properties.waste_rate
                    total_waste += waste
                    breakdown[f"node:{node_id}"] = waste
        
        if include_edges:
            for i in range(len(path) - 1):
                source_id, target_id = path[i], path[i + 1]
                for edge in self.edges.values():
                    if edge.source_node_id == source_id and edge.target_node_id == target_id:
                        if edge.flow.waste_rate:
                            waste = edge.flow.waste_rate
                            total_waste += waste
                            breakdown[f"edge:{source_id}->{target_id}"] = waste
                        break
        
        return total_waste, breakdown
    
    def find_minimum_waste_path(
        self,
        source_id: str,
        target_id: str,
        relationship_type: Optional[RelationshipType] = None
    ) -> Tuple[Optional[List[str]], float, Dict[str, float]]:
        """
        Find the path with minimum waste between two nodes.
        
        Args:
            source_id: Starting node ID
            target_id: Ending node ID
            relationship_type: Optional filter by edge type
            
        Returns:
            Tuple of (path, total_waste, breakdown)
        """
        # Build weighted graph for pathfinding
        G = nx.DiGraph()
        
        for node_id in self.nodes:
            G.add_node(node_id)
        
        for edge in self.edges.values():
            if relationship_type and edge.relationship_type != relationship_type.value:
                continue
            
            # Weight is waste rate (default 0 if not set)
            weight = edge.flow.waste_rate or 0.0
            source_node = self.nodes.get(edge.source_node_id)
            if source_node and source_node.properties.waste_rate:
                weight += source_node.properties.waste_rate
            
            G.add_edge(edge.source_node_id, edge.target_node_id, weight=weight)
        
        try:
            path = nx.shortest_path(G, source_id, target_id, weight="weight")
            total_waste, breakdown = self.calculate_path_waste(path)
            return path, total_waste, breakdown
        except nx.NetworkXNoPath:
            return None, float("inf"), {}
    
    def find_all_paths(
        self,
        source_id: str,
        target_id: str,
        max_paths: int = 10
    ) -> List[Tuple[List[str], float]]:
        """Find all paths between two nodes, sorted by waste."""
        paths = []
        
        try:
            for path in nx.all_simple_paths(self.graph, source_id, target_id):
                waste, _ = self.calculate_path_waste(path)
                paths.append((path, waste))
        except nx.NetworkXNoPath:
            pass
        
        paths.sort(key=lambda x: x[1])
        return paths[:max_paths]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert network to dictionary representation."""
        return {
            "network_id": self.network_id,
            "name": self.name,
            "description": self.description,
            "network_type": self.network_type,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.edges.values()],
        }
    
    def save_to_json(self, filepath: str):
        """Save network to JSON file."""
        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load_from_json(cls, filepath: str) -> "EcosystemNetwork":
        """Load network from JSON file."""
        with open(filepath, "r") as f:
            data = json.load(f)
        
        network = cls(
            name=data.get("name", "Loaded Network"),
            description=data.get("description", ""),
            network_type=data.get("network_type", "ecosystem"),
        )
        network.network_id = data.get("network_id", network.network_id)
        network.created_at = data.get("created_at", network.created_at)
        
        # Load nodes
        for node_data in data.get("nodes", []):
            node = EcosystemNode(**node_data)
            network.nodes[node.node_id] = node
            network.graph.add_node(
                node.node_id,
                node_type=node.node_type,
                node_class=node.node_class,
                name=node.name,
            )
        
        # Load edges
        for edge_data in data.get("edges", []):
            edge = EcosystemEdge(**edge_data)
            network.edges[edge.edge_id] = edge
            network.graph.add_edge(
                edge.source_node_id,
                edge.target_node_id,
                key=edge.edge_id,
                relationship_type=edge.relationship_type,
                edge=edge,
            )
        
        return network
    
    def summary(self) -> Dict[str, Any]:
        """Get a summary of the network."""
        node_types = defaultdict(int)
        for node in self.nodes.values():
            node_types[node.node_type] += 1
        
        edge_types = defaultdict(int)
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
