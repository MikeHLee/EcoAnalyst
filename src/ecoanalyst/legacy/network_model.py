"""
network_model.py: WasteNetwork, the EcoAnalyst 1.x network model.

A directed graph of nodes and edges, each with a loss rate (the fraction of
what passes through that is lost). Path losses compound:
total = 1 - prod(1 - rate_i).

To move a WasteNetwork JSON file to the current format, load it with
``ecoanalyst.EcosystemNetwork.load_from_json`` (the format is detected) or run
``ecoanalyst convert``.
"""

import json
import math
import networkx as nx
from typing import Dict, List, Tuple, Any

class WasteNetwork:
    def __init__(self):
        """Initialize an empty waste network."""
        self.graph = nx.DiGraph()
        self.node_types = {}  # Store node types (grower, distributor, store)
        
    def add_node(self, node_id: str, node_type: str, capacity: float,
                 waste_rate: float, **attrs):
        """
        Add a node to the network.
        
        Args:
            node_id: Unique identifier for the node
            node_type: Type of node (grower, distributor, store)
            capacity: Maximum handling capacity
            waste_rate: Percentage of goods wasted at this node
            **attrs: Additional node attributes
        """
        self.graph.add_node(node_id, 
                           node_type=node_type,
                           capacity=capacity,
                           waste_rate=waste_rate,
                           **attrs)
        self.node_types[node_id] = node_type
        
    def add_edge(self, source: str, target: str, flow_capacity: float,
                transport_waste: float, transport_time: float):
        """
        Add a directed edge between nodes.
        
        Args:
            source: Source node ID
            target: Target node ID
            flow_capacity: Maximum flow capacity
            transport_waste: Waste percentage during transportation
            transport_time: Time taken for transportation
        """
        self.graph.add_edge(source, target,
                           flow_capacity=flow_capacity,
                           transport_waste=transport_waste,
                           transport_time=transport_time)
        
    def calculate_path_waste(self, path: List[str]) -> Tuple[float, Dict[str, float]]:
        """
        Calculate the compounded loss along a path.

        Args:
            path: List of node IDs representing a path

        Returns:
            Tuple of (total loss fraction, loss rate by node and edge)
        """
        retained = 1.0
        waste_breakdown = {}

        for node in path:
            node_waste = self.graph.nodes[node]['waste_rate']
            retained *= 1.0 - node_waste
            waste_breakdown[f"node_{node}"] = node_waste

        for i in range(len(path)-1):
            source, target = path[i], path[i+1]
            edge_waste = self.graph.edges[source, target]['transport_waste']
            retained *= 1.0 - edge_waste
            waste_breakdown[f"transport_{source}_{target}"] = edge_waste

        return 1.0 - retained, waste_breakdown
    
    def find_minimum_waste_path(self, source: str, target: str) -> Tuple[List[str], float]:
        """
        Find the path that loses the smallest fraction between two nodes.

        Each edge u->v is weighted by -log(1 - transport_waste) - log(1 - waste_rate[u]),
        so the shortest path is the one that retains the most. Edges or
        source nodes with a rate of 1 carry nothing and are skipped.

        Args:
            source: Starting node ID
            target: Ending node ID

        Returns:
            Tuple of (path, total loss fraction), or (None, inf) if there is no path
        """
        def waste_weight(u, v, edge_data):
            edge_rate = edge_data['transport_waste']
            node_rate = self.graph.nodes[u]['waste_rate']
            if edge_rate >= 1.0 or node_rate >= 1.0:
                return None
            return -math.log1p(-edge_rate) - math.log1p(-node_rate)

        try:
            path = nx.shortest_path(self.graph, source, target,
                                    weight=waste_weight)
            total_waste, _ = self.calculate_path_waste(path)
            return path, total_waste
        except nx.NetworkXNoPath:
            return None, float('inf')
        
    def save_to_json(self, filepath: str):
        """Save network to JSON file."""
        data = {
            'nodes': [
                {
                    'id': node,
                    'type': self.graph.nodes[node]['node_type'],
                    'capacity': self.graph.nodes[node]['capacity'],
                    'waste_rate': self.graph.nodes[node]['waste_rate']
                }
                for node in self.graph.nodes
            ],
            'edges': [
                {
                    'source': u,
                    'target': v,
                    'flow_capacity': d['flow_capacity'],
                    'transport_waste': d['transport_waste'],
                    'transport_time': d['transport_time']
                }
                for u, v, d in self.graph.edges(data=True)
            ]
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
            
    @classmethod
    def load_from_json(cls, filepath: str) -> 'WasteNetwork':
        """Load network from JSON file."""
        network = cls()
        with open(filepath, 'r') as f:
            data = json.load(f)
            
        for node in data['nodes']:
            network.add_node(
                node['id'],
                node['type'],
                node['capacity'],
                node['waste_rate']
            )
            
        for edge in data['edges']:
            network.add_edge(
                edge['source'],
                edge['target'],
                edge['flow_capacity'],
                edge['transport_waste'],
                edge['transport_time']
            )
            
        return network
