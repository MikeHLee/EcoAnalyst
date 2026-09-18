"""
api.py: FastAPI application for EcoAnalyst.

Provides RESTful endpoints for network CRUD operations,
analysis, and optimization.
"""

from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
import json

from .models import (
    NodeType,
    RelationshipType,
    CreateNetworkRequest,
    AddNodeRequest,
    AddEdgeRequest,
    NetworkResponse,
    EcosystemNode,
    EcosystemEdge,
    Quantity,
    Cost,
    NodeProperties,
    NodeFinancials,
)
from .network import EcosystemNetwork
from .analysis import EconomicAnalysis


# In-memory storage (replace with database in production)
networks: Dict[str, EcosystemNetwork] = {}


app = FastAPI(
    title="EcoAnalyst API",
    description="API for modeling and analyzing ecosystems, economies, and physically interacting networks",
    version="2.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "ecoanalyst",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat(),
    }


# Network CRUD
@app.post("/networks", response_model=Dict[str, Any])
async def create_network(
    request: CreateNetworkRequest,
    x_user_id: str = Header(..., alias="X-User-Id"),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-Id"),
):
    """Create a new ecosystem network."""
    network = EcosystemNetwork(
        name=request.name,
        description=request.description or "",
        network_type=request.network_type,
    )
    
    networks[network.network_id] = network
    
    return {
        "success": True,
        "network_id": network.network_id,
        "name": network.name,
        "network_type": network.network_type,
        "message": f"Successfully created {network.network_type} network",
    }


@app.get("/networks")
async def list_networks(
    limit: int = Query(20, ge=1, le=100),
    x_user_id: str = Header(..., alias="X-User-Id"),
):
    """List all networks."""
    network_list = [
        {
            "network_id": net.network_id,
            "name": net.name,
            "network_type": net.network_type,
            "node_count": len(net.nodes),
            "edge_count": len(net.edges),
            "created_at": net.created_at,
        }
        for net in list(networks.values())[:limit]
    ]
    
    return {
        "networks": network_list,
        "total_count": len(networks),
        "displayed_count": len(network_list),
    }


@app.get("/networks/{network_id}")
async def get_network(
    network_id: str,
    x_user_id: str = Header(..., alias="X-User-Id"),
):
    """Get a network with all nodes and edges."""
    if network_id not in networks:
        raise HTTPException(status_code=404, detail="Network not found")
    
    network = networks[network_id]
    return network.to_dict()


@app.put("/networks/{network_id}")
async def update_network(
    network_id: str,
    request: CreateNetworkRequest,
    x_user_id: str = Header(..., alias="X-User-Id"),
):
    """Update network metadata."""
    if network_id not in networks:
        raise HTTPException(status_code=404, detail="Network not found")
    
    network = networks[network_id]
    network.name = request.name
    network.description = request.description or network.description
    network.network_type = request.network_type
    network.updated_at = datetime.now().isoformat()
    
    return {
        "success": True,
        "network_id": network_id,
        "message": "Network updated successfully",
    }


@app.delete("/networks/{network_id}")
async def delete_network(
    network_id: str,
    x_user_id: str = Header(..., alias="X-User-Id"),
):
    """Delete a network."""
    if network_id not in networks:
        raise HTTPException(status_code=404, detail="Network not found")
    
    del networks[network_id]
    
    return {
        "success": True,
        "message": "Network deleted successfully",
    }


# Node operations
@app.post("/networks/{network_id}/nodes")
async def add_node(
    network_id: str,
    request: AddNodeRequest,
    x_user_id: str = Header(..., alias="X-User-Id"),
):
    """Add a node to the network."""
    if network_id not in networks:
        raise HTTPException(status_code=404, detail="Network not found")
    
    network = networks[network_id]
    
    node_id = network.add_node(
        node_type=request.node_type,
        node_class=request.node_class,
        name=request.name,
        properties=request.properties.model_dump(),
        financials=request.financials.model_dump() if request.financials else None,
        operations=request.operations.model_dump() if request.operations else None,
        position_x=request.position_x,
        position_y=request.position_y,
        metadata=request.metadata,
    )
    
    return {
        "success": True,
        "node_id": node_id,
        "node_type": request.node_type,
        "name": request.name,
        "message": f"Added {request.node_type} node: {request.name}",
    }


@app.get("/networks/{network_id}/nodes/{node_id}")
async def get_node(
    network_id: str,
    node_id: str,
    x_user_id: str = Header(..., alias="X-User-Id"),
):
    """Get a specific node."""
    if network_id not in networks:
        raise HTTPException(status_code=404, detail="Network not found")
    
    network = networks[network_id]
    node = network.get_node(node_id)
    
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    return node.to_dict()


@app.delete("/networks/{network_id}/nodes/{node_id}")
async def delete_node(
    network_id: str,
    node_id: str,
    x_user_id: str = Header(..., alias="X-User-Id"),
):
    """Delete a node from the network."""
    if network_id not in networks:
        raise HTTPException(status_code=404, detail="Network not found")
    
    network = networks[network_id]
    
    if not network.remove_node(node_id):
        raise HTTPException(status_code=404, detail="Node not found")
    
    return {
        "success": True,
        "message": "Node deleted successfully",
    }


# Edge operations
@app.post("/networks/{network_id}/edges")
async def add_edge(
    network_id: str,
    request: AddEdgeRequest,
    x_user_id: str = Header(..., alias="X-User-Id"),
):
    """Add an edge to the network."""
    if network_id not in networks:
        raise HTTPException(status_code=404, detail="Network not found")
    
    network = networks[network_id]
    
    try:
        edge_id = network.add_edge(
            source_node_id=request.source_node_id,
            target_node_id=request.target_node_id,
            relationship_type=request.relationship_type,
            flow=request.flow.model_dump(),
            constraints=request.constraints,
            metadata=request.metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return {
        "success": True,
        "edge_id": edge_id,
        "relationship_type": request.relationship_type,
        "message": "Edge added successfully",
    }


@app.delete("/networks/{network_id}/edges/{edge_id}")
async def delete_edge(
    network_id: str,
    edge_id: str,
    x_user_id: str = Header(..., alias="X-User-Id"),
):
    """Delete an edge from the network."""
    if network_id not in networks:
        raise HTTPException(status_code=404, detail="Network not found")
    
    network = networks[network_id]
    
    if not network.remove_edge(edge_id):
        raise HTTPException(status_code=404, detail="Edge not found")
    
    return {
        "success": True,
        "message": "Edge deleted successfully",
    }


# Analysis endpoints
@app.post("/networks/{network_id}/calculate-waste")
async def calculate_waste(
    network_id: str,
    pricing_data: Optional[Dict[str, float]] = None,
    x_user_id: str = Header(..., alias="X-User-Id"),
):
    """Calculate total waste quantity and costs across the network."""
    if network_id not in networks:
        raise HTTPException(status_code=404, detail="Network not found")
    
    network = networks[network_id]
    analysis = EconomicAnalysis(network)
    
    result = analysis.calculate_waste_cost(pricing_data)
    result["network_id"] = network_id
    
    return result


@app.post("/networks/{network_id}/calculate-tco")
async def calculate_tco(
    network_id: str,
    years: int = Query(10, ge=1, le=50),
    discount_rate: float = Query(0.05, ge=0.0, le=0.5),
    x_user_id: str = Header(..., alias="X-User-Id"),
):
    """Calculate Total Cost of Ownership for the network."""
    if network_id not in networks:
        raise HTTPException(status_code=404, detail="Network not found")
    
    network = networks[network_id]
    analysis = EconomicAnalysis(network)
    
    result = analysis.calculate_total_cost_of_ownership(years, discount_rate)
    result["network_id"] = network_id
    
    return result


@app.get("/networks/{network_id}/optimize-paths")
async def optimize_paths(
    network_id: str,
    source_node_id: str = Query(...),
    target_node_id: str = Query(...),
    x_user_id: str = Header(..., alias="X-User-Id"),
):
    """Find minimum waste paths between two nodes."""
    if network_id not in networks:
        raise HTTPException(status_code=404, detail="Network not found")
    
    network = networks[network_id]
    
    path, waste, breakdown = network.find_minimum_waste_path(source_node_id, target_node_id)
    
    if path is None:
        return {
            "network_id": network_id,
            "source": source_node_id,
            "target": target_node_id,
            "path": None,
            "message": "No path found between nodes",
        }
    
    return {
        "network_id": network_id,
        "source": source_node_id,
        "target": target_node_id,
        "path": path,
        "total_waste": waste,
        "breakdown": breakdown,
    }


@app.get("/networks/{network_id}/hotspots")
async def get_hotspots(
    network_id: str,
    top_n: int = Query(5, ge=1, le=50),
    metric: str = Query("waste_rate"),
    x_user_id: str = Header(..., alias="X-User-Id"),
):
    """Identify waste hotspots in the network."""
    if network_id not in networks:
        raise HTTPException(status_code=404, detail="Network not found")
    
    network = networks[network_id]
    analysis = EconomicAnalysis(network)
    
    result = analysis.identify_hotspots(top_n, metric)
    result["network_id"] = network_id
    
    return result


# Run with: uvicorn ecoanalyst.api:app --reload
