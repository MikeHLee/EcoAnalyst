"""
mcp_server.py: Model Context Protocol server for EcoAnalyst.

Exposes EcosystemNetwork and EconomicAnalysis as MCP tools over stdio.
Networks live in process memory for the life of the server.

Run with the ``ecoanalyst-mcp`` command (installed with the ``mcp`` extra)
or ``python -m ecoanalyst.mcp_server``.

The tool functions below are plain Python functions. They raise
``ValueError`` on bad input, which the MCP SDK reports to the client as a
tool error.
"""

import functools
from typing import Any, Callable, Dict, List, Optional

from .analysis import EconomicAnalysis
from .network import EcosystemNetwork

# In-memory storage for the server process.
NETWORKS: Dict[str, EcosystemNetwork] = {}


def _network(network_id: str) -> EcosystemNetwork:
    network = NETWORKS.get(network_id)
    if network is None:
        raise ValueError(f"Network not found: {network_id}")
    return network


def _names(network: EcosystemNetwork, path: List[str]) -> List[str]:
    return [network.nodes[node_id].name for node_id in path]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def create_network(
    name: str,
    network_type: str = "ecosystem",
    description: str = "",
    efficiency_mode: str = "ignore",
) -> Dict[str, Any]:
    """Create an empty network.

    network_type is free text, for example supply_chain, energy, ecosystem, or economy.
    efficiency_mode sets how node and edge efficiency values count: "ignore"
    (stored only), "conversion" (a yield applied after waste), or "retention"
    (efficiency is the fraction that gets through, so loss = 1 - efficiency).
    """
    network = EcosystemNetwork(
        name=name, description=description, network_type=network_type,
        efficiency_mode=efficiency_mode,
    )
    NETWORKS[network.network_id] = network
    return {
        "network_id": network.network_id,
        "name": network.name,
        "network_type": network.network_type,
    }


def list_networks(limit: int = 20) -> Dict[str, Any]:
    """List networks held by this server."""
    items = [network.summary() for network in list(NETWORKS.values())[:limit]]
    return {"networks": items, "total_count": len(NETWORKS)}


def get_network(network_id: str) -> Dict[str, Any]:
    """Return a network with all nodes and edges in the native JSON format."""
    return _network(network_id).to_dict()


def delete_network(network_id: str) -> Dict[str, Any]:
    """Delete a network."""
    _network(network_id)
    del NETWORKS[network_id]
    return {"deleted": network_id}


def add_node(
    network_id: str,
    node_type: str,
    node_class: str,
    name: str,
    capacity_value: float = 100.0,
    capacity_unit: str = "units/day",
    waste_rate: Optional[float] = None,
    efficiency: Optional[float] = None,
    efficiency_mode: Optional[str] = None,
    count: int = 1,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Add a node.

    node_type is a node kind: producer, processor, handler, consumer, service,
    grid, or a custom lowercase identifier. waste_rate is the fraction lost at
    the node (0 to 1). efficiency_mode overrides the network default for this
    node ("ignore", "conversion", or "retention").
    """
    network = _network(network_id)
    node_id = network.add_node(
        node_type=node_type,
        node_class=node_class,
        name=name,
        properties={
            "capacity": {"value": capacity_value, "unit": capacity_unit},
            "waste_rate": waste_rate,
            "efficiency": efficiency,
            "efficiency_mode": efficiency_mode,
            "count": count,
        },
        metadata=metadata,
    )
    node = network.nodes[node_id]
    return {"node_id": node_id, "node_type": node.node_type, "name": node.name}


def add_edge(
    network_id: str,
    source_node_id: str,
    target_node_id: str,
    flow_type: str = "inventory",
    max_rate_value: float = 100.0,
    max_rate_unit: str = "units/day",
    transport_waste_rate: Optional[float] = None,
    transport_time_hours: Optional[float] = None,
    polarity: str = "positive",
    efficiency: Optional[float] = None,
    efficiency_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Connect two nodes with a directed flow.

    flow_type is a flow kind: inventory, energy, currency, information,
    service, waste, control, a 2.x name such as inventory_flow, or a custom
    lowercase identifier. transport_waste_rate is the fraction lost in
    transit (0 to 1). efficiency and efficiency_mode work as for nodes.
    """
    network = _network(network_id)
    flow: Dict[str, Any] = {
        "max_rate": {"value": max_rate_value, "unit": max_rate_unit},
        "waste_rate": transport_waste_rate,
        "efficiency": efficiency,
        "efficiency_mode": efficiency_mode,
    }
    if transport_time_hours is not None:
        flow["transport_time"] = {"value": transport_time_hours, "unit": "hours"}
    edge_id = network.add_edge(
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        relationship_type=flow_type,
        flow=flow,
        polarity=polarity,
    )
    return {"edge_id": edge_id, "flow_type": network.edges[edge_id].relationship_type}


def calculate_waste(
    network_id: str,
    pricing_data: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Capacity-based loss quantity and cost for every node and edge.

    pricing_data maps node_class to price per unit (default 1.0). Each
    component is estimated on its own at full capacity; this is not a mass
    balance.
    """
    result = EconomicAnalysis(_network(network_id)).calculate_waste_cost(pricing_data)
    result["network_id"] = network_id
    return result


def find_minimum_waste_path(
    network_id: str,
    source_node_id: str,
    target_node_id: str,
    edge_kinds: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Find the path that delivers the largest fraction from source to target.

    Losses compound along the path. edge_kinds limits the flow kinds the
    path may use, for example ["inventory"].
    """
    network = _network(network_id)
    path, loss, breakdown = network.find_minimum_waste_path(
        source_node_id, target_node_id, edge_kinds=edge_kinds
    )
    if path is None:
        return {"network_id": network_id, "path": None, "message": "No path found"}
    return {
        "network_id": network_id,
        "path": path,
        "path_names": _names(network, path),
        "total_waste": loss,
        "retained_fraction": 1.0 - loss,
        "breakdown": breakdown,
    }


def identify_hotspots(
    network_id: str,
    top_n: int = 5,
    metric: str = "waste_rate",
) -> Dict[str, Any]:
    """Rank nodes and edges by loss. metric is waste_rate or waste_quantity."""
    result = EconomicAnalysis(_network(network_id)).identify_hotspots(top_n, metric)
    result["network_id"] = network_id
    return result


def compare_paths(
    network_id: str,
    source_node_id: str,
    target_node_id: str,
    max_paths: int = 5,
    edge_kinds: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """List up to max_paths routes from source to target, lowest compounded loss first."""
    network = _network(network_id)
    paths = network.find_all_paths(
        source_node_id, target_node_id, max_paths=max_paths, edge_kinds=edge_kinds
    )
    return {
        "network_id": network_id,
        "paths": [
            {"path": path, "path_names": _names(network, path), "total_waste": loss}
            for path, loss in paths
        ],
    }


def export_flow_graph(network_id: str) -> Dict[str, Any]:
    """Export a network as a flow-graph document (format ecoanalyst.flowgraph, version 1)."""
    return _network(network_id).to_flow_graph()


def import_flow_graph(flow_graph: Dict[str, Any]) -> Dict[str, Any]:
    """Create a network from a flow-graph document and return its new ID."""
    network = EcosystemNetwork.from_flow_graph(flow_graph)
    NETWORKS[network.network_id] = network
    return {
        "network_id": network.network_id,
        "node_count": len(network.nodes),
        "edge_count": len(network.edges),
    }


TOOLS = [
    create_network,
    list_networks,
    get_network,
    delete_network,
    add_node,
    add_edge,
    calculate_waste,
    find_minimum_waste_path,
    identify_hotspots,
    compare_paths,
    export_flow_graph,
    import_flow_graph,
]


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------


def _sdk():
    """Return (server class, ToolError class) from the installed MCP SDK.

    mcp 2.x names the server ``MCPServer``; mcp 1.x names it ``FastMCP``.
    """
    try:
        from mcp.server.mcpserver import MCPServer
        from mcp.server.mcpserver.exceptions import ToolError

        return MCPServer, ToolError
    except ImportError:
        from mcp.server.fastmcp import FastMCP
        from mcp.server.fastmcp.exceptions import ToolError

        return FastMCP, ToolError


def _reporting_errors(fn: Callable[..., Any], tool_error: type) -> Callable[..., Any]:
    """Re-raise expected input errors as the SDK's ToolError so the client sees the message."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except KeyError as exc:
            raise tool_error(f"Missing field: {exc}") from exc
        except (ValueError, TypeError) as exc:
            raise tool_error(str(exc)) from exc

    return wrapper


def build_server():
    """Create the MCP server with every tool and the network:// resource registered."""
    server_class, tool_error = _sdk()
    server = server_class("ecoanalyst")
    for tool in TOOLS:
        server.add_tool(_reporting_errors(tool, tool_error))

    @server.resource("network://{network_id}", mime_type="application/json")
    def network_resource(network_id: str) -> Dict[str, Any]:
        """A network in the native JSON format."""
        return get_network(network_id)

    return server


def main() -> None:
    """Run the MCP server on stdio."""
    try:
        server = build_server()
    except ImportError:
        raise SystemExit(
            "The MCP SDK is not installed. Install it with: pip install 'ecoanalyst[mcp]'"
        )
    server.run()


if __name__ == "__main__":
    main()
