"""
analysis.py: Economic and waste analysis for EcoAnalyst networks.

Provides tools for calculating waste costs, comparing scenarios,
and performing economic impact assessments.
"""

from typing import Dict, Any, Optional, List
from .network import EcosystemNetwork
from .models import EcosystemNode, EcosystemEdge


class EconomicAnalysis:
    """Economic analysis tools for ecosystem networks."""
    
    def __init__(self, network: EcosystemNetwork):
        self.network = network
    
    def calculate_waste_cost(
        self,
        pricing_data: Optional[Dict[str, float]] = None,
        default_price: float = 1.0
    ) -> Dict[str, Any]:
        """
        Calculate economic impact of waste in the network.
        
        Args:
            pricing_data: Map of node_class -> price_per_unit
            default_price: Default price if node_class not in pricing_data
            
        Returns:
            Dict with total_waste_cost, breakdown by node/edge, and currency
        """
        if pricing_data is None:
            pricing_data = {}
        
        total_waste_cost = 0.0
        total_waste_quantity = 0.0
        breakdown = {"nodes": {}, "edges": {}}
        
        # Calculate node waste
        for node_id, node in self.network.nodes.items():
            if not node.properties.waste_rate:
                continue
            
            # Calculate throughput
            throughput = node.properties.capacity.value * node.properties.count
            waste_rate = node.properties.waste_rate
            waste_quantity = throughput * waste_rate
            
            # Get price
            product_price = pricing_data.get(node.node_class, default_price)
            node_waste_cost = waste_quantity * product_price
            
            breakdown["nodes"][node_id] = {
                "name": node.name,
                "node_class": node.node_class,
                "waste_rate": waste_rate,
                "waste_quantity": waste_quantity,
                "waste_cost": node_waste_cost,
                "unit": node.properties.capacity.unit,
            }
            
            total_waste_quantity += waste_quantity
            total_waste_cost += node_waste_cost
        
        # Calculate edge waste
        for edge_id, edge in self.network.edges.items():
            if not edge.flow.waste_rate:
                continue
            
            flow_rate = edge.flow.max_rate.value
            transport_waste = flow_rate * edge.flow.waste_rate
            
            # Get source node for pricing
            source_node = self.network.get_node(edge.source_node_id)
            if source_node:
                product_price = pricing_data.get(source_node.node_class, default_price)
            else:
                product_price = default_price
            
            edge_waste_cost = transport_waste * product_price
            
            breakdown["edges"][edge_id] = {
                "source": edge.source_node_id,
                "target": edge.target_node_id,
                "waste_rate": edge.flow.waste_rate,
                "waste_quantity": transport_waste,
                "waste_cost": edge_waste_cost,
                "unit": edge.flow.max_rate.unit,
            }
            
            total_waste_quantity += transport_waste
            total_waste_cost += edge_waste_cost
        
        return {
            "total_waste_quantity": total_waste_quantity,
            "total_waste_cost": total_waste_cost,
            "breakdown": breakdown,
            "currency": "USD",
            "node_count": len(breakdown["nodes"]),
            "edge_count": len(breakdown["edges"]),
        }
    
    def calculate_path_cost(
        self,
        path: List[str],
        pricing_data: Optional[Dict[str, float]] = None,
        default_price: float = 1.0
    ) -> Dict[str, Any]:
        """
        Calculate waste cost along a specific path.
        
        Args:
            path: List of node IDs
            pricing_data: Map of node_class -> price_per_unit
            default_price: Default price if not found
            
        Returns:
            Dict with path waste cost details
        """
        if pricing_data is None:
            pricing_data = {}
        
        total_cost = 0.0
        breakdown = []
        
        for i, node_id in enumerate(path):
            node = self.network.get_node(node_id)
            if not node:
                continue
            
            # Node waste cost
            if node.properties.waste_rate:
                throughput = node.properties.capacity.value
                waste = throughput * node.properties.waste_rate
                price = pricing_data.get(node.node_class, default_price)
                cost = waste * price
                total_cost += cost
                breakdown.append({
                    "type": "node",
                    "id": node_id,
                    "name": node.name,
                    "waste": waste,
                    "cost": cost,
                })
            
            # Edge waste cost to next node
            if i < len(path) - 1:
                next_id = path[i + 1]
                for edge in self.network.edges.values():
                    if edge.source_node_id == node_id and edge.target_node_id == next_id:
                        if edge.flow.waste_rate:
                            flow = edge.flow.max_rate.value
                            waste = flow * edge.flow.waste_rate
                            price = pricing_data.get(node.node_class, default_price)
                            cost = waste * price
                            total_cost += cost
                            breakdown.append({
                                "type": "edge",
                                "source": node_id,
                                "target": next_id,
                                "waste": waste,
                                "cost": cost,
                            })
                        break
        
        return {
            "path": path,
            "total_cost": total_cost,
            "breakdown": breakdown,
            "currency": "USD",
        }
    
    def compare_scenarios(
        self,
        baseline: EcosystemNetwork,
        optimized: EcosystemNetwork,
        pricing_data: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Compare two network scenarios.
        
        Args:
            baseline: Original network
            optimized: Modified network
            pricing_data: Pricing for waste calculation
            
        Returns:
            Comparison with savings analysis
        """
        baseline_analysis = EconomicAnalysis(baseline)
        optimized_analysis = EconomicAnalysis(optimized)
        
        baseline_cost = baseline_analysis.calculate_waste_cost(pricing_data)
        optimized_cost = optimized_analysis.calculate_waste_cost(pricing_data)
        
        savings = baseline_cost["total_waste_cost"] - optimized_cost["total_waste_cost"]
        savings_percent = 0.0
        if baseline_cost["total_waste_cost"] > 0:
            savings_percent = (savings / baseline_cost["total_waste_cost"]) * 100
        
        return {
            "baseline_cost": baseline_cost["total_waste_cost"],
            "optimized_cost": optimized_cost["total_waste_cost"],
            "savings": savings,
            "savings_percent": savings_percent,
            "baseline_waste_quantity": baseline_cost["total_waste_quantity"],
            "optimized_waste_quantity": optimized_cost["total_waste_quantity"],
            "waste_reduction": baseline_cost["total_waste_quantity"] - optimized_cost["total_waste_quantity"],
            "currency": "USD",
        }
    
    def calculate_total_cost_of_ownership(
        self,
        years: int = 10,
        discount_rate: float = 0.05
    ) -> Dict[str, Any]:
        """
        Calculate Total Cost of Ownership (TCO) for the network.
        
        Args:
            years: Analysis period in years
            discount_rate: Annual discount rate for NPV calculation
            
        Returns:
            TCO breakdown including CAPEX, OPEX, and waste costs
        """
        total_capex = 0.0
        total_opex = 0.0
        total_installation = 0.0
        total_salvage = 0.0
        
        for node in self.network.nodes.values():
            if not node.financials:
                continue
            
            total_capex += node.financials.capex.value
            total_opex += node.financials.opex_annual.value * years
            
            if node.financials.installation:
                total_installation += node.financials.installation.value
            
            if node.financials.salvage_value:
                # Discount salvage value to present value
                salvage_pv = node.financials.salvage_value.value / ((1 + discount_rate) ** years)
                total_salvage += salvage_pv
        
        # Calculate NPV of OPEX
        opex_npv = 0.0
        for year in range(1, years + 1):
            annual_opex = sum(
                node.financials.opex_annual.value
                for node in self.network.nodes.values()
                if node.financials
            )
            opex_npv += annual_opex / ((1 + discount_rate) ** year)
        
        total_tco = total_capex + total_installation + opex_npv - total_salvage
        
        return {
            "total_tco": total_tco,
            "capex": total_capex,
            "installation": total_installation,
            "opex_npv": opex_npv,
            "salvage_value_pv": total_salvage,
            "years": years,
            "discount_rate": discount_rate,
            "currency": "USD",
        }
    
    def identify_hotspots(
        self,
        top_n: int = 5,
        metric: str = "waste_rate"
    ) -> Dict[str, Any]:
        """
        Identify waste hotspots in the network.
        
        Args:
            top_n: Number of top hotspots to return
            metric: Metric to rank by ("waste_rate", "waste_quantity", "waste_cost")
            
        Returns:
            List of hotspots with their details
        """
        hotspots = []
        
        # Analyze nodes
        for node_id, node in self.network.nodes.items():
            if not node.properties.waste_rate:
                continue
            
            waste_rate = node.properties.waste_rate
            waste_quantity = node.properties.capacity.value * waste_rate
            
            hotspots.append({
                "type": "node",
                "id": node_id,
                "name": node.name,
                "node_class": node.node_class,
                "waste_rate": waste_rate,
                "waste_quantity": waste_quantity,
            })
        
        # Analyze edges
        for edge_id, edge in self.network.edges.items():
            if not edge.flow.waste_rate:
                continue
            
            source_node = self.network.get_node(edge.source_node_id)
            target_node = self.network.get_node(edge.target_node_id)
            
            waste_rate = edge.flow.waste_rate
            waste_quantity = edge.flow.max_rate.value * waste_rate
            
            hotspots.append({
                "type": "edge",
                "id": edge_id,
                "source": source_node.name if source_node else edge.source_node_id,
                "target": target_node.name if target_node else edge.target_node_id,
                "waste_rate": waste_rate,
                "waste_quantity": waste_quantity,
            })
        
        # Sort by metric
        if metric == "waste_quantity":
            hotspots.sort(key=lambda x: x.get("waste_quantity", 0), reverse=True)
        else:
            hotspots.sort(key=lambda x: x.get("waste_rate", 0), reverse=True)
        
        return {
            "hotspots": hotspots[:top_n],
            "total_analyzed": len(hotspots),
            "metric": metric,
        }
