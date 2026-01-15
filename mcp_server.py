#!/usr/bin/env python3
"""
MCP Server for EcoAnalyst

Provides AI assistant access to ecosystem modeling tools via the
Model Context Protocol (MCP).

Usage:
    python mcp_server.py

Configuration for Claude Desktop:
    Add to ~/Library/Application Support/Claude/claude_desktop_config.json:
    {
      "mcpServers": {
        "ecoanalyst": {
          "command": "python3",
          "args": ["/path/to/ecoanalyst/mcp_server.py"],
          "transport": "stdio"
        }
      }
    }
"""

import json
import uuid
import asyncio
from datetime import datetime
from typing import Dict, Any

try:
    from mcp.server import Server
    from mcp.server.models import InitializationOptions
    import mcp.types as types
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    print("Warning: MCP library not installed. Run: pip install mcp")

# In-memory storage
networks: Dict[str, Dict[str, Any]] = {}

if MCP_AVAILABLE:
    app = Server("ecoanalyst")

    @app.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        """Define available tools for AI assistants."""
        return [
            types.Tool(
                name="create_network",
                description="Create a new ecosystem network for modeling supply chains, energy systems, economies, or environmental flows",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the network (e.g., 'California Food Supply Chain', 'Regional Power Grid')"
                        },
                        "description": {
                            "type": "string",
                            "description": "Description of what this network models"
                        },
                        "network_type": {
                            "type": "string",
                            "enum": ["supply_chain", "energy", "ecosystem", "economy"],
                            "description": "Type: 'supply_chain' for goods, 'energy' for power, 'ecosystem' for environmental, 'economy' for financial"
                        }
                    },
                    "required": ["name", "network_type"]
                }
            ),
            types.Tool(
                name="add_node",
                description="Add a node (producer, processor, handler, consumer, service, or grid) to the network",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "network_id": {
                            "type": "string",
                            "description": "ID of the network to add node to"
                        },
                        "node_type": {
                            "type": "string",
                            "enum": ["producer", "processor", "handler", "consumer", "service", "grid"],
                            "description": "Type of node"
                        },
                        "node_class": {
                            "type": "string",
                            "description": "Specific class: Farm, ColdStorage, Warehouse, Retailer, PowerPlant, etc."
                        },
                        "name": {
                            "type": "string",
                            "description": "Display name for this node"
                        },
                        "capacity_value": {
                            "type": "number",
                            "description": "Capacity/throughput value"
                        },
                        "capacity_unit": {
                            "type": "string",
                            "description": "Unit: kg/day, kW, tons/hour, etc."
                        },
                        "waste_rate": {
                            "type": "number",
                            "description": "Percentage of goods lost/wasted (0-1, e.g., 0.05 = 5%)",
                            "minimum": 0,
                            "maximum": 1
                        },
                        "efficiency": {
                            "type": "number",
                            "description": "Conversion efficiency (0-1, default 1.0)",
                            "minimum": 0,
                            "maximum": 1
                        }
                    },
                    "required": ["network_id", "node_type", "node_class", "name"]
                }
            ),
            types.Tool(
                name="add_edge",
                description="Connect two nodes with a flow relationship (inventory, service, energy, or currency flow)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "network_id": {"type": "string"},
                        "source_node_id": {"type": "string"},
                        "target_node_id": {"type": "string"},
                        "flow_type": {
                            "type": "string",
                            "enum": ["inventory_flow", "service_flow", "energy_flow", "currency_flow", "waste_flow"],
                            "description": "Type of relationship/flow"
                        },
                        "max_rate_value": {"type": "number"},
                        "max_rate_unit": {"type": "string"},
                        "transport_waste_rate": {
                            "type": "number",
                            "description": "Loss during transport (0-1)"
                        },
                        "transport_time_hours": {"type": "number"}
                    },
                    "required": ["network_id", "source_node_id", "target_node_id", "flow_type"]
                }
            ),
            types.Tool(
                name="calculate_waste",
                description="Calculate total waste/loss quantity and costs across the entire network",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "network_id": {"type": "string"},
                        "pricing_data": {
                            "type": "object",
                            "description": "Map of node classes to price per unit (optional)",
                            "additionalProperties": {"type": "number"}
                        }
                    },
                    "required": ["network_id"]
                }
            ),
            types.Tool(
                name="find_minimum_waste_path",
                description="Find the path with minimum waste/loss between two nodes in the network",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "network_id": {"type": "string"},
                        "source_node_id": {"type": "string"},
                        "target_node_id": {"type": "string"}
                    },
                    "required": ["network_id", "source_node_id", "target_node_id"]
                }
            ),
            types.Tool(
                name="list_networks",
                description="List all available networks",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "default": 10}
                    }
                }
            ),
            types.Tool(
                name="get_network",
                description="Get complete network details including all nodes and edges",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "network_id": {"type": "string"}
                    },
                    "required": ["network_id"]
                }
            ),
            types.Tool(
                name="identify_hotspots",
                description="Identify the top waste/loss hotspots in the network",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "network_id": {"type": "string"},
                        "top_n": {
                            "type": "integer",
                            "default": 5,
                            "description": "Number of top hotspots to return"
                        }
                    },
                    "required": ["network_id"]
                }
            ),
            types.Tool(
                name="compare_paths",
                description="Compare multiple paths between nodes to find the optimal route",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "network_id": {"type": "string"},
                        "source_node_id": {"type": "string"},
                        "target_node_id": {"type": "string"},
                        "max_paths": {
                            "type": "integer",
                            "default": 5
                        }
                    },
                    "required": ["network_id", "source_node_id", "target_node_id"]
                }
            ),
            types.Tool(
                name="delete_network",
                description="Delete a network and all its nodes and edges",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "network_id": {"type": "string"}
                    },
                    "required": ["network_id"]
                }
            )
        ]

    @app.call_tool()
    async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        """Handle tool execution."""
        
        if name == "create_network":
            network_id = str(uuid.uuid4())
            networks[network_id] = {
                "id": network_id,
                "name": arguments["name"],
                "description": arguments.get("description", ""),
                "network_type": arguments["network_type"],
                "nodes": {},
                "edges": {},
                "created_at": datetime.now().isoformat()
            }
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "success": True,
                    "network_id": network_id,
                    "name": arguments["name"],
                    "network_type": arguments["network_type"],
                    "message": f"Successfully created {arguments['network_type']} network"
                }, indent=2)
            )]
        
        elif name == "add_node":
            network_id = arguments["network_id"]
            if network_id not in networks:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": "Network not found", "network_id": network_id})
                )]
            
            node_id = str(uuid.uuid4())
            networks[network_id]["nodes"][node_id] = {
                "id": node_id,
                "type": arguments["node_type"],
                "class": arguments["node_class"],
                "name": arguments["name"],
                "capacity": {
                    "value": arguments.get("capacity_value", 100),
                    "unit": arguments.get("capacity_unit", "units/day")
                },
                "waste_rate": arguments.get("waste_rate", 0.0),
                "efficiency": arguments.get("efficiency", 1.0)
            }
            
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "success": True,
                    "node_id": node_id,
                    "node_type": arguments["node_type"],
                    "name": arguments["name"],
                    "message": f"Added {arguments['node_type']} node: {arguments['name']}"
                }, indent=2)
            )]
        
        elif name == "add_edge":
            network_id = arguments["network_id"]
            if network_id not in networks:
                return [types.TextContent(type="text", text=json.dumps({"error": "Network not found"}))]
            
            source_id = arguments["source_node_id"]
            target_id = arguments["target_node_id"]
            
            if source_id not in networks[network_id]["nodes"] or target_id not in networks[network_id]["nodes"]:
                return [types.TextContent(type="text", text=json.dumps({"error": "Source or target node not found"}))]
            
            edge_id = str(uuid.uuid4())
            networks[network_id]["edges"][edge_id] = {
                "id": edge_id,
                "source": source_id,
                "target": target_id,
                "flow_type": arguments["flow_type"],
                "max_rate": {
                    "value": arguments.get("max_rate_value", 100),
                    "unit": arguments.get("max_rate_unit", "units/day")
                },
                "transport_waste_rate": arguments.get("transport_waste_rate", 0.0),
                "transport_time_hours": arguments.get("transport_time_hours", 24)
            }
            
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "success": True,
                    "edge_id": edge_id,
                    "flow_type": arguments["flow_type"],
                    "message": "Edge added successfully"
                }, indent=2)
            )]
        
        elif name == "calculate_waste":
            network_id = arguments["network_id"]
            if network_id not in networks:
                return [types.TextContent(type="text", text=json.dumps({"error": "Network not found"}))]
            
            network = networks[network_id]
            pricing_data = arguments.get("pricing_data", {})
            total_waste = 0
            total_cost = 0
            waste_breakdown = {"nodes": {}, "edges": {}}
            
            for node_id, node in network["nodes"].items():
                node_waste = node["capacity"]["value"] * node.get("waste_rate", 0)
                price = pricing_data.get(node["class"], 1.0)
                node_cost = node_waste * price
                
                waste_breakdown["nodes"][node_id] = {
                    "name": node["name"],
                    "waste": node_waste,
                    "cost": node_cost,
                    "unit": node["capacity"]["unit"]
                }
                total_waste += node_waste
                total_cost += node_cost
            
            for edge_id, edge in network["edges"].items():
                edge_waste = edge["max_rate"]["value"] * edge.get("transport_waste_rate", 0)
                source_node = network["nodes"].get(edge["source"], {})
                price = pricing_data.get(source_node.get("class", ""), 1.0)
                edge_cost = edge_waste * price
                
                waste_breakdown["edges"][edge_id] = {
                    "waste": edge_waste,
                    "cost": edge_cost,
                    "unit": edge["max_rate"]["unit"]
                }
                total_waste += edge_waste
                total_cost += edge_cost
            
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "network_id": network_id,
                    "total_waste": total_waste,
                    "total_cost": total_cost,
                    "breakdown": waste_breakdown,
                    "node_count": len(network["nodes"]),
                    "edge_count": len(network["edges"])
                }, indent=2)
            )]
        
        elif name == "find_minimum_waste_path":
            network_id = arguments["network_id"]
            if network_id not in networks:
                return [types.TextContent(type="text", text=json.dumps({"error": "Network not found"}))]
            
            network = networks[network_id]
            source_id = arguments["source_node_id"]
            target_id = arguments["target_node_id"]
            
            # Simple BFS pathfinding with waste as weight
            import networkx as nx
            G = nx.DiGraph()
            
            for node_id, node in network["nodes"].items():
                G.add_node(node_id)
            
            for edge_id, edge in network["edges"].items():
                weight = edge.get("transport_waste_rate", 0) + network["nodes"].get(edge["source"], {}).get("waste_rate", 0)
                G.add_edge(edge["source"], edge["target"], weight=weight, edge_id=edge_id)
            
            try:
                path = nx.shortest_path(G, source_id, target_id, weight="weight")
                total_waste = sum(
                    G[path[i]][path[i+1]]["weight"]
                    for i in range(len(path) - 1)
                )
                
                return [types.TextContent(
                    type="text",
                    text=json.dumps({
                        "network_id": network_id,
                        "path": path,
                        "path_names": [network["nodes"][n]["name"] for n in path],
                        "total_waste": total_waste,
                        "message": f"Found path with {total_waste:.2%} total waste"
                    }, indent=2)
                )]
            except nx.NetworkXNoPath:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({
                        "network_id": network_id,
                        "path": None,
                        "message": "No path found between specified nodes"
                    }, indent=2)
                )]
        
        elif name == "list_networks":
            limit = arguments.get("limit", 10)
            network_list = [
                {
                    "network_id": nid,
                    "name": net["name"],
                    "network_type": net["network_type"],
                    "node_count": len(net["nodes"]),
                    "edge_count": len(net["edges"])
                }
                for nid, net in list(networks.items())[:limit]
            ]
            
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "networks": network_list,
                    "total_count": len(networks),
                    "displayed_count": len(network_list)
                }, indent=2)
            )]
        
        elif name == "get_network":
            network_id = arguments["network_id"]
            if network_id not in networks:
                return [types.TextContent(type="text", text=json.dumps({"error": "Network not found"}))]
            
            return [types.TextContent(
                type="text",
                text=json.dumps(networks[network_id], indent=2)
            )]
        
        elif name == "identify_hotspots":
            network_id = arguments["network_id"]
            if network_id not in networks:
                return [types.TextContent(type="text", text=json.dumps({"error": "Network not found"}))]
            
            network = networks[network_id]
            top_n = arguments.get("top_n", 5)
            
            hotspots = []
            
            for node_id, node in network["nodes"].items():
                if node.get("waste_rate", 0) > 0:
                    hotspots.append({
                        "type": "node",
                        "id": node_id,
                        "name": node["name"],
                        "waste_rate": node["waste_rate"],
                        "waste_quantity": node["capacity"]["value"] * node["waste_rate"]
                    })
            
            for edge_id, edge in network["edges"].items():
                if edge.get("transport_waste_rate", 0) > 0:
                    hotspots.append({
                        "type": "edge",
                        "id": edge_id,
                        "source": network["nodes"][edge["source"]]["name"],
                        "target": network["nodes"][edge["target"]]["name"],
                        "waste_rate": edge["transport_waste_rate"],
                        "waste_quantity": edge["max_rate"]["value"] * edge["transport_waste_rate"]
                    })
            
            hotspots.sort(key=lambda x: x["waste_rate"], reverse=True)
            
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "network_id": network_id,
                    "hotspots": hotspots[:top_n],
                    "total_analyzed": len(hotspots)
                }, indent=2)
            )]
        
        elif name == "compare_paths":
            network_id = arguments["network_id"]
            if network_id not in networks:
                return [types.TextContent(type="text", text=json.dumps({"error": "Network not found"}))]
            
            network = networks[network_id]
            source_id = arguments["source_node_id"]
            target_id = arguments["target_node_id"]
            max_paths = arguments.get("max_paths", 5)
            
            import networkx as nx
            G = nx.DiGraph()
            
            for node_id in network["nodes"]:
                G.add_node(node_id)
            
            for edge_id, edge in network["edges"].items():
                weight = edge.get("transport_waste_rate", 0) + network["nodes"].get(edge["source"], {}).get("waste_rate", 0)
                G.add_edge(edge["source"], edge["target"], weight=weight)
            
            try:
                paths = []
                for path in nx.all_simple_paths(G, source_id, target_id):
                    total_waste = sum(
                        G[path[i]][path[i+1]]["weight"]
                        for i in range(len(path) - 1)
                    )
                    paths.append({
                        "path": path,
                        "path_names": [network["nodes"][n]["name"] for n in path],
                        "total_waste": total_waste
                    })
                    if len(paths) >= max_paths * 2:
                        break
                
                paths.sort(key=lambda x: x["total_waste"])
                
                return [types.TextContent(
                    type="text",
                    text=json.dumps({
                        "network_id": network_id,
                        "paths": paths[:max_paths],
                        "total_paths_found": len(paths)
                    }, indent=2)
                )]
            except nx.NetworkXNoPath:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({
                        "network_id": network_id,
                        "paths": [],
                        "message": "No paths found"
                    }, indent=2)
                )]
        
        elif name == "delete_network":
            network_id = arguments["network_id"]
            if network_id not in networks:
                return [types.TextContent(type="text", text=json.dumps({"error": "Network not found"}))]
            
            del networks[network_id]
            
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "success": True,
                    "message": "Network deleted successfully"
                }, indent=2)
            )]
        
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Unknown tool: {name}"})
        )]

    @app.list_resources()
    async def handle_list_resources() -> list[types.Resource]:
        """Provide access to network data as resources."""
        return [
            types.Resource(
                uri=f"network://{network_id}",
                name=f"Network: {data['name']}",
                description=f"{data['network_type']} network with {len(data['nodes'])} nodes",
                mimeType="application/json"
            )
            for network_id, data in networks.items()
        ]

    @app.read_resource()
    async def handle_read_resource(uri: str) -> str:
        """Read a network resource."""
        if uri.startswith("network://"):
            network_id = uri.replace("network://", "")
            if network_id in networks:
                return json.dumps(networks[network_id], indent=2)
        return json.dumps({"error": "Resource not found"})

    async def main():
        from mcp.server.stdio import stdio_server
        
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="ecoanalyst",
                    server_version="2.0.0"
                )
            )

if __name__ == "__main__":
    if MCP_AVAILABLE:
        asyncio.run(main())
    else:
        print("MCP library not available. Install with: pip install mcp")
