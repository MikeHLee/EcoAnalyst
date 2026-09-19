"""
api.py: FastAPI application for EcoAnalyst.

This is a local development server. It keeps networks in process memory,
has no authentication, and forgets everything when it stops. Do not expose
it on a public network.

Cross-origin requests are refused unless the ``ECOANALYST_CORS_ORIGINS``
environment variable lists the allowed origins, separated by commas, for
example ``http://localhost:5173,http://127.0.0.1:5173``.

Run with: ``uvicorn ecoanalyst.api:app --reload``
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from ._version import __version__
from .analysis import HOTSPOT_METRICS, EconomicAnalysis
from .models import AddEdgeRequest, AddNodeRequest, CreateNetworkRequest
from .network import EcosystemNetwork, utc_now_iso

CORS_ENV_VAR = "ECOANALYST_CORS_ORIGINS"

# In-memory storage shared by every app instance in this process.
networks: Dict[str, EcosystemNetwork] = {}


def cors_origins_from_env(value: Optional[str] = None) -> List[str]:
    """Parse a comma-separated origin list (default: the environment variable)."""
    if value is None:
        value = os.environ.get(CORS_ENV_VAR, "")
    return [origin.strip() for origin in value.split(",") if origin.strip()]


def _get_network(network_id: str) -> EcosystemNetwork:
    network = networks.get(network_id)
    if network is None:
        raise HTTPException(status_code=404, detail="Network not found")
    return network


def create_app(cors_origins: Optional[List[str]] = None) -> FastAPI:
    """Build the FastAPI app.

    Args:
        cors_origins: Origins allowed to make cross-origin requests. ``None``
            reads ``ECOANALYST_CORS_ORIGINS``; an empty list allows none.
    """
    if cors_origins is None:
        cors_origins = cors_origins_from_env()

    app = FastAPI(
        title="EcoAnalyst API",
        description=(
            "Local, unauthenticated, in-memory server for building and analyzing "
            "EcoAnalyst networks."
        ),
        version=__version__,
    )

    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["Content-Type"],
        )

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "ecoanalyst",
            "version": __version__,
            "timestamp": utc_now_iso(),
        }

    # Networks -------------------------------------------------------------

    @app.post("/networks")
    async def create_network(request: CreateNetworkRequest):
        """Create an empty network."""
        network = EcosystemNetwork(
            name=request.name,
            description=request.description or "",
            network_type=request.network_type,
            efficiency_mode=request.efficiency_mode,
        )
        networks[network.network_id] = network
        return {
            "success": True,
            "network_id": network.network_id,
            "name": network.name,
            "network_type": network.network_type,
            "message": f"Created {network.network_type} network",
        }

    @app.get("/networks")
    async def list_networks(limit: int = Query(20, ge=1, le=100)):
        """List networks."""
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

    @app.post("/networks/flow-graph")
    async def import_flow_graph(flow_graph: Dict[str, Any] = Body(...)):
        """Create a network from a flow-graph document."""
        try:
            network = EcosystemNetwork.from_flow_graph(flow_graph)
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid flow graph: {exc}")
        networks[network.network_id] = network
        return {
            "success": True,
            "network_id": network.network_id,
            "node_count": len(network.nodes),
            "edge_count": len(network.edges),
        }

    @app.get("/networks/{network_id}")
    async def get_network(network_id: str):
        """Get a network with all nodes and edges (native format)."""
        return _get_network(network_id).to_dict()

    @app.get("/networks/{network_id}/flow-graph")
    async def export_flow_graph(network_id: str):
        """Export a network as a flow-graph document."""
        return _get_network(network_id).to_flow_graph()

    @app.put("/networks/{network_id}")
    async def update_network(network_id: str, request: CreateNetworkRequest):
        """Update network name, description, and type."""
        network = _get_network(network_id)
        network.name = request.name
        network.description = request.description or network.description
        network.network_type = request.network_type
        network.set_efficiency_mode(request.efficiency_mode)
        return {"success": True, "network_id": network_id, "message": "Network updated"}

    @app.delete("/networks/{network_id}")
    async def delete_network(network_id: str):
        """Delete a network."""
        _get_network(network_id)
        del networks[network_id]
        return {"success": True, "message": "Network deleted"}

    # Nodes ----------------------------------------------------------------

    @app.post("/networks/{network_id}/nodes")
    async def add_node(network_id: str, request: AddNodeRequest):
        """Add a node."""
        network = _get_network(network_id)
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
            geometry=request.geometry,
            series_ref=request.series_ref,
        )
        return {
            "success": True,
            "node_id": node_id,
            "node_type": request.node_type,
            "name": request.name,
            "message": f"Added {request.node_type} node: {request.name}",
        }

    @app.get("/networks/{network_id}/nodes/{node_id}")
    async def get_node(network_id: str, node_id: str):
        """Get one node."""
        node = _get_network(network_id).get_node(node_id)
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")
        return node.to_dict()

    @app.delete("/networks/{network_id}/nodes/{node_id}")
    async def delete_node(network_id: str, node_id: str):
        """Delete a node and its edges."""
        if not _get_network(network_id).remove_node(node_id):
            raise HTTPException(status_code=404, detail="Node not found")
        return {"success": True, "message": "Node deleted"}

    # Edges ----------------------------------------------------------------

    @app.post("/networks/{network_id}/edges")
    async def add_edge(network_id: str, request: AddEdgeRequest):
        """Add an edge between two existing nodes."""
        network = _get_network(network_id)
        try:
            edge_id = network.add_edge(
                source_node_id=request.source_node_id,
                target_node_id=request.target_node_id,
                relationship_type=request.relationship_type,
                flow=request.flow.model_dump(),
                constraints=request.constraints,
                metadata=request.metadata,
                polarity=request.polarity,
                series_ref=request.series_ref,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {
            "success": True,
            "edge_id": edge_id,
            "relationship_type": request.relationship_type,
            "message": "Edge added",
        }

    @app.delete("/networks/{network_id}/edges/{edge_id}")
    async def delete_edge(network_id: str, edge_id: str):
        """Delete an edge."""
        if not _get_network(network_id).remove_edge(edge_id):
            raise HTTPException(status_code=404, detail="Edge not found")
        return {"success": True, "message": "Edge deleted"}

    # Analysis -------------------------------------------------------------

    @app.post("/networks/{network_id}/calculate-waste")
    async def calculate_waste(
        network_id: str,
        pricing_data: Optional[Dict[str, float]] = Body(None),
    ):
        """Capacity-based loss quantity and cost across the network."""
        result = EconomicAnalysis(_get_network(network_id)).calculate_waste_cost(pricing_data)
        result["network_id"] = network_id
        return result

    @app.post("/networks/{network_id}/calculate-tco")
    async def calculate_tco(
        network_id: str,
        years: int = Query(10, ge=1, le=50),
        discount_rate: float = Query(0.05, ge=0.0, le=0.5),
    ):
        """Total cost of ownership."""
        analysis = EconomicAnalysis(_get_network(network_id))
        result = analysis.calculate_total_cost_of_ownership(years, discount_rate)
        result["network_id"] = network_id
        return result

    @app.get("/networks/{network_id}/optimize-paths")
    async def optimize_paths(
        network_id: str,
        source_node_id: str = Query(...),
        target_node_id: str = Query(...),
        edge_kinds: Optional[List[str]] = Query(None),
    ):
        """Minimum-loss path between two nodes, optionally limited to some flow kinds."""
        network = _get_network(network_id)
        try:
            path, waste, breakdown = network.find_minimum_waste_path(
                source_node_id, target_node_id, edge_kinds=edge_kinds
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

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
    ):
        """Rank nodes and edges by loss."""
        if metric not in HOTSPOT_METRICS:
            raise HTTPException(
                status_code=400, detail=f"metric must be one of {list(HOTSPOT_METRICS)}"
            )
        result = EconomicAnalysis(_get_network(network_id)).identify_hotspots(top_n, metric)
        result["network_id"] = network_id
        return result

    return app


app = create_app()
