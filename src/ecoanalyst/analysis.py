"""
analysis.py: Loss and cost analysis for EcoAnalyst networks.

Two kinds of loss estimate are available:

- ``calculate_waste_cost`` and ``identify_hotspots`` look at each component
  on its own: loss = capacity (or edge max rate) x loss rate. This is quick
  and useful for ranking, but it is not a mass balance, because it does not
  follow material from one component to the next.
- ``calculate_path_cost`` follows a quantity along one path and removes each
  component's loss from what actually arrives there.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .network import EcosystemNetwork

HOTSPOT_METRICS = ("waste_rate", "waste_quantity")


class EconomicAnalysis:
    """Loss, cost, and total-cost-of-ownership calculations for one network."""

    def __init__(self, network: EcosystemNetwork):
        self.network = network

    def calculate_waste_cost(
        self,
        pricing_data: Optional[Dict[str, float]] = None,
        default_price: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Capacity-based estimate of loss quantity and cost across the network.

        Each node loses capacity x count x waste_rate and each edge loses
        max_rate x waste_rate, priced by the node class (edges use the
        source node's class). Each component is assumed to run at full
        capacity and is treated on its own, so the totals are an estimate
        for ranking and comparison, not a mass balance. Use
        ``calculate_path_cost`` to follow a quantity along a path.

        Args:
            pricing_data: Map of node_class -> price per unit
            default_price: Price for classes not in pricing_data

        Returns:
            Dict with total_waste_quantity, total_waste_cost, breakdown by
            node and edge, and currency
        """
        pricing_data = pricing_data or {}

        total_waste_cost = 0.0
        total_waste_quantity = 0.0
        breakdown: Dict[str, Dict[str, Any]] = {"nodes": {}, "edges": {}}

        for node_id, node in self.network.nodes.items():
            if not node.properties.waste_rate:
                continue

            throughput = node.properties.capacity.value * node.properties.count
            waste_rate = node.properties.waste_rate
            waste_quantity = throughput * waste_rate
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

        for edge_id, edge in self.network.edges.items():
            if not edge.flow.waste_rate:
                continue

            transport_waste = edge.flow.max_rate.value * edge.flow.waste_rate
            source_node = self.network.get_node(edge.source_node_id)
            if source_node:
                product_price = pricing_data.get(source_node.node_class, default_price)
            else:
                product_price = default_price
            edge_waste_cost = transport_waste * product_price

            breakdown["edges"][edge_id] = {
                "source": edge.source_node_id,
                "target": edge.target_node_id,
                "kind": edge.relationship_type,
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
        default_price: float = 1.0,
        input_quantity: Optional[float] = None,
        edge_kinds: Optional[Iterable[Any]] = None,
    ) -> Dict[str, Any]:
        """
        Follow a quantity along a path and price what each component loses.

        Starting from ``input_quantity`` (default: the first node's capacity
        x count), each component in order (node, edge to the next node,
        next node, ...) removes ``current x waste_rate`` from what reaches
        it. Node losses are priced by the node's class, edge losses by the
        source node's class. Between consecutive nodes the lowest-loss
        eligible edge is used.

        Args:
            path: Node IDs in order
            pricing_data: Map of node_class -> price per unit
            default_price: Price for classes not in pricing_data
            input_quantity: Quantity entering the first node
            edge_kinds: Optional flow kinds the path may use

        Returns:
            Dict with input_quantity, delivered_quantity, total_waste,
            total_cost, and a breakdown of the components that lose anything

        Raises:
            ValueError: on an empty path, an unknown node, or a missing edge
        """
        if not path:
            raise ValueError("path must contain at least one node")
        pricing_data = pricing_data or {}

        edges = self.network.select_path_edges(path, edge_kinds)
        first = self.network.nodes[path[0]]
        if input_quantity is None:
            input_quantity = first.properties.capacity.value * first.properties.count
        current = float(input_quantity)

        total_cost = 0.0
        breakdown: List[Dict[str, Any]] = []

        for i, node_id in enumerate(path):
            node = self.network.nodes[node_id]
            price = pricing_data.get(node.node_class, default_price)

            rate = node.properties.waste_rate or 0.0
            if rate:
                lost = current * rate
                cost = lost * price
                breakdown.append({
                    "type": "node",
                    "id": node_id,
                    "name": node.name,
                    "input": current,
                    "waste_rate": rate,
                    "waste": lost,
                    "cost": cost,
                })
                current -= lost
                total_cost += cost

            if i < len(edges):
                edge = edges[i]
                rate = edge.flow.waste_rate or 0.0
                if rate:
                    lost = current * rate
                    cost = lost * price
                    breakdown.append({
                        "type": "edge",
                        "id": edge.edge_id,
                        "source": edge.source_node_id,
                        "target": edge.target_node_id,
                        "input": current,
                        "waste_rate": rate,
                        "waste": lost,
                        "cost": cost,
                    })
                    current -= lost
                    total_cost += cost

        return {
            "path": list(path),
            "input_quantity": float(input_quantity),
            "delivered_quantity": current,
            "total_waste": float(input_quantity) - current,
            "total_cost": total_cost,
            "unit": first.properties.capacity.unit,
            "breakdown": breakdown,
            "currency": "USD",
        }

    def compare_scenarios(
        self,
        baseline: EcosystemNetwork,
        optimized: EcosystemNetwork,
        pricing_data: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Compare the capacity-based loss cost of two networks.

        Args:
            baseline: Original network
            optimized: Modified network
            pricing_data: Pricing for the loss calculation

        Returns:
            Costs, savings, and loss reduction
        """
        baseline_cost = EconomicAnalysis(baseline).calculate_waste_cost(pricing_data)
        optimized_cost = EconomicAnalysis(optimized).calculate_waste_cost(pricing_data)

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
        discount_rate: float = 0.05,
    ) -> Dict[str, Any]:
        """
        Total cost of ownership over ``years``.

        TCO = capex + installation + NPV(annual opex) - PV(salvage value),
        where opex is paid at the end of each year and salvage is received
        at the end of the period.

        Args:
            years: Analysis period in years
            discount_rate: Annual discount rate

        Returns:
            TCO and its parts
        """
        total_capex = 0.0
        total_installation = 0.0
        annual_opex = 0.0
        total_salvage = 0.0
        discount_at_end = (1 + discount_rate) ** years

        for node in self.network.nodes.values():
            if not node.financials:
                continue
            total_capex += node.financials.capex.value
            annual_opex += node.financials.opex_annual.value
            if node.financials.installation:
                total_installation += node.financials.installation.value
            if node.financials.salvage_value:
                total_salvage += node.financials.salvage_value.value / discount_at_end

        opex_npv = sum(
            annual_opex / (1 + discount_rate) ** year for year in range(1, years + 1)
        )
        total_tco = total_capex + total_installation + opex_npv - total_salvage

        return {
            "total_tco": total_tco,
            "capex": total_capex,
            "installation": total_installation,
            "opex_annual": annual_opex,
            "opex_npv": opex_npv,
            "salvage_value_pv": total_salvage,
            "years": years,
            "discount_rate": discount_rate,
            "currency": "USD",
        }

    def identify_hotspots(
        self,
        top_n: int = 5,
        metric: str = "waste_rate",
    ) -> Dict[str, Any]:
        """
        Rank nodes and edges by loss.

        ``waste_quantity`` uses the same capacity-based estimate as
        ``calculate_waste_cost`` (node capacity x count x rate, edge max_rate
        x rate).

        Args:
            top_n: Number of hotspots to return
            metric: "waste_rate" or "waste_quantity"

        Returns:
            Dict with the top hotspots, the number analyzed, and the metric

        Raises:
            ValueError: on an unknown metric
        """
        if metric not in HOTSPOT_METRICS:
            raise ValueError(f"metric must be one of {HOTSPOT_METRICS}, got {metric!r}")

        hotspots = []

        for node_id, node in self.network.nodes.items():
            if not node.properties.waste_rate:
                continue
            waste_rate = node.properties.waste_rate
            hotspots.append({
                "type": "node",
                "id": node_id,
                "name": node.name,
                "node_class": node.node_class,
                "kind": node.node_type,
                "waste_rate": waste_rate,
                "waste_quantity": node.properties.capacity.value * node.properties.count * waste_rate,
            })

        for edge_id, edge in self.network.edges.items():
            if not edge.flow.waste_rate:
                continue
            source_node = self.network.get_node(edge.source_node_id)
            target_node = self.network.get_node(edge.target_node_id)
            waste_rate = edge.flow.waste_rate
            hotspots.append({
                "type": "edge",
                "id": edge_id,
                "source": source_node.name if source_node else edge.source_node_id,
                "target": target_node.name if target_node else edge.target_node_id,
                "kind": edge.relationship_type,
                "waste_rate": waste_rate,
                "waste_quantity": edge.flow.max_rate.value * waste_rate,
            })

        hotspots.sort(key=lambda x: x[metric], reverse=True)

        return {
            "hotspots": hotspots[:top_n],
            "total_analyzed": len(hotspots),
            "metric": metric,
        }
