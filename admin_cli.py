#!/usr/bin/env python3
"""
EcoAnalyst Admin CLI - Test and manage ecosystem networks

Usage:
    python admin_cli.py health                          - Check service health
    python admin_cli.py networks_list [limit]           - List networks
    python admin_cli.py network_create <json_file>      - Create network
    python admin_cli.py network_get <network_id>        - Get network details
    python admin_cli.py node_add <network_id> <json>    - Add node
    python admin_cli.py edge_add <network_id> <json>    - Add edge
    python admin_cli.py calculate_waste <network_id>    - Calculate waste
    python admin_cli.py test_features                   - Run all tests
    python admin_cli.py demo                            - Run interactive demo
"""

import sys
import json
from pathlib import Path

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


class EcoAnalystAdmin:
    """Admin client for EcoAnalyst API."""
    
    def __init__(self, base_url: str = "http://localhost:8000", user_id: str = "admin"):
        self.base_url = base_url.rstrip('/')
        self.user_id = user_id
        self.headers = {"X-User-Id": user_id}
        
        if HTTPX_AVAILABLE:
            self.client = httpx.Client(timeout=30.0, headers=self.headers)
        else:
            self.client = None
    
    def health_check(self) -> dict:
        """Check API health."""
        response = self.client.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()
    
    def list_networks(self, limit: int = 20) -> dict:
        """List all networks."""
        response = self.client.get(f"{self.base_url}/networks?limit={limit}")
        response.raise_for_status()
        return response.json()
    
    def create_network(self, data: dict) -> dict:
        """Create a new network."""
        response = self.client.post(f"{self.base_url}/networks", json=data)
        response.raise_for_status()
        return response.json()
    
    def get_network(self, network_id: str) -> dict:
        """Get network details."""
        response = self.client.get(f"{self.base_url}/networks/{network_id}")
        response.raise_for_status()
        return response.json()
    
    def add_node(self, network_id: str, node_data: dict) -> dict:
        """Add a node to a network."""
        response = self.client.post(
            f"{self.base_url}/networks/{network_id}/nodes",
            json=node_data
        )
        response.raise_for_status()
        return response.json()
    
    def add_edge(self, network_id: str, edge_data: dict) -> dict:
        """Add an edge to a network."""
        response = self.client.post(
            f"{self.base_url}/networks/{network_id}/edges",
            json=edge_data
        )
        response.raise_for_status()
        return response.json()
    
    def calculate_waste(self, network_id: str, pricing_data: dict = None) -> dict:
        """Calculate waste for a network."""
        payload = {"pricing_data": pricing_data} if pricing_data else {}
        response = self.client.post(
            f"{self.base_url}/networks/{network_id}/calculate-waste",
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    def get_hotspots(self, network_id: str, top_n: int = 5) -> dict:
        """Get waste hotspots."""
        response = self.client.get(
            f"{self.base_url}/networks/{network_id}/hotspots?top_n={top_n}"
        )
        response.raise_for_status()
        return response.json()
    
    def optimize_paths(self, network_id: str, source_id: str, target_id: str) -> dict:
        """Find optimal path."""
        response = self.client.get(
            f"{self.base_url}/networks/{network_id}/optimize-paths"
            f"?source_node_id={source_id}&target_node_id={target_id}"
        )
        response.raise_for_status()
        return response.json()


class LocalEcoAnalyst:
    """Local testing without API server."""
    
    def __init__(self):
        # Import local modules
        sys.path.insert(0, str(Path(__file__).parent / "src"))
        from ecoanalyst import EcosystemNetwork, EconomicAnalysis, NodeType, RelationshipType
        
        self.EcosystemNetwork = EcosystemNetwork
        self.EconomicAnalysis = EconomicAnalysis
        self.NodeType = NodeType
        self.RelationshipType = RelationshipType
        self.networks = {}
    
    def test_features(self):
        """Run comprehensive feature tests."""
        print("=" * 80)
        print("ECOANALYST FEATURE TESTING (Local Mode)")
        print("=" * 80)
        
        # Test 1: Create network
        print("\nTEST 1: Create Network")
        network = self.EcosystemNetwork(
            name="Test Food Supply Chain",
            description="Farm to table test network",
            network_type="supply_chain"
        )
        print(f"✓ Created network: {network.network_id}")
        print(f"  Name: {network.name}")
        print(f"  Type: {network.network_type}")
        
        # Test 2: Add nodes
        print("\nTEST 2: Add Nodes")
        
        # Farm (Producer)
        farm_id = network.add_node(
            node_type=self.NodeType.PRODUCER,
            node_class="Farm",
            name="Organic Farm",
            properties={
                "capacity": {"value": 1000, "unit": "kg/day"},
                "efficiency": 0.95,
                "waste_rate": 0.05,
                "count": 1
            },
            financials={
                "capex": {"value": 0, "currency": "USD"},
                "opex_annual": {"value": 50000, "currency": "USD"},
                "waste_cost_per_unit": {"value": 0.50, "currency": "USD"}
            }
        )
        print(f"  ✓ Added farm: {farm_id[:8]}...")
        
        # Cold Storage (Handler)
        storage_id = network.add_node(
            node_type=self.NodeType.HANDLER,
            node_class="ColdStorage",
            name="Regional Cold Storage",
            properties={
                "capacity": {"value": 5000, "unit": "kg"},
                "efficiency": 0.98,
                "waste_rate": 0.02,
                "count": 1
            },
            financials={
                "capex": {"value": 500000, "currency": "USD"},
                "opex_annual": {"value": 75000, "currency": "USD"}
            },
            operations={
                "storage_days": 14,
                "temperature_range": {"min": 2, "max": 8, "unit": "C"}
            }
        )
        print(f"  ✓ Added storage: {storage_id[:8]}...")
        
        # Retailer (Consumer)
        retailer_id = network.add_node(
            node_type=self.NodeType.CONSUMER,
            node_class="Retailer",
            name="Grocery Store",
            properties={
                "capacity": {"value": 500, "unit": "kg/day"},
                "efficiency": 0.92,
                "waste_rate": 0.08,
                "count": 1
            },
            financials={
                "capex": {"value": 0, "currency": "USD"},
                "opex_annual": {"value": 10000, "currency": "USD"}
            }
        )
        print(f"  ✓ Added retailer: {retailer_id[:8]}...")
        
        # Test 3: Add edges
        print("\nTEST 3: Add Edges")
        
        edge1_id = network.add_edge(
            source_node_id=farm_id,
            target_node_id=storage_id,
            relationship_type=self.RelationshipType.INVENTORY_FLOW,
            flow={
                "max_rate": {"value": 900, "unit": "kg/day"},
                "efficiency": 0.97,
                "waste_rate": 0.03,
                "transport_time": {"value": 4, "unit": "hours"}
            }
        )
        print(f"  ✓ Added farm → storage edge")
        
        edge2_id = network.add_edge(
            source_node_id=storage_id,
            target_node_id=retailer_id,
            relationship_type=self.RelationshipType.INVENTORY_FLOW,
            flow={
                "max_rate": {"value": 500, "unit": "kg/day"},
                "efficiency": 0.99,
                "waste_rate": 0.01,
                "transport_time": {"value": 2, "unit": "hours"}
            }
        )
        print(f"  ✓ Added storage → retailer edge")
        
        # Test 4: Network summary
        print("\nTEST 4: Network Summary")
        summary = network.summary()
        print(f"  Nodes: {summary['node_count']}")
        print(f"  Edges: {summary['edge_count']}")
        print(f"  Node types: {summary['node_types']}")
        print(f"  Edge types: {summary['edge_types']}")
        
        # Test 5: Calculate waste
        print("\nTEST 5: Calculate Waste")
        analysis = self.EconomicAnalysis(network)
        
        pricing = {
            "Farm": 2.50,
            "ColdStorage": 2.50,
            "Retailer": 3.00
        }
        
        result = analysis.calculate_waste_cost(pricing)
        print(f"  Total waste quantity: {result['total_waste_quantity']:.2f}")
        print(f"  Total waste cost: ${result['total_waste_cost']:.2f}")
        print(f"  Nodes with waste: {result['node_count']}")
        print(f"  Edges with waste: {result['edge_count']}")
        
        # Test 6: Find minimum waste path
        print("\nTEST 6: Find Minimum Waste Path")
        path, total_waste, breakdown = network.find_minimum_waste_path(farm_id, retailer_id)
        if path:
            print(f"  Path length: {len(path)} nodes")
            print(f"  Total waste: {total_waste:.2%}")
            print(f"  Breakdown:")
            for component, waste in breakdown.items():
                print(f"    - {component}: {waste:.2%}")
        else:
            print("  No path found")
        
        # Test 7: Identify hotspots
        print("\nTEST 7: Identify Hotspots")
        hotspots = analysis.identify_hotspots(top_n=3)
        print(f"  Top {len(hotspots['hotspots'])} hotspots:")
        for i, hotspot in enumerate(hotspots['hotspots'], 1):
            if hotspot['type'] == 'node':
                print(f"    {i}. {hotspot['name']} - {hotspot['waste_rate']:.1%} waste rate")
            else:
                print(f"    {i}. {hotspot['source']} → {hotspot['target']} - {hotspot['waste_rate']:.1%} waste rate")
        
        # Test 8: Save/Load JSON
        print("\nTEST 8: Save/Load JSON")
        test_file = Path(__file__).parent / "test_network.json"
        network.save_to_json(str(test_file))
        print(f"  ✓ Saved to {test_file}")
        
        loaded = self.EcosystemNetwork.load_from_json(str(test_file))
        print(f"  ✓ Loaded network: {loaded.name}")
        print(f"  ✓ Nodes: {len(loaded.nodes)}, Edges: {len(loaded.edges)}")
        
        # Clean up
        test_file.unlink()
        print(f"  ✓ Cleaned up test file")
        
        print("\n" + "=" * 80)
        print("All tests completed successfully!")
        print("=" * 80)
        
        return network
    
    def demo(self):
        """Run interactive demo."""
        print("=" * 80)
        print("ECOANALYST INTERACTIVE DEMO")
        print("=" * 80)
        print("\nThis demo creates a sample supply chain network and analyzes it.")
        print()
        
        # Run test features which creates a network
        network = self.test_features()
        
        print("\n" + "-" * 80)
        print("DEMO: Network Data Structure")
        print("-" * 80)
        print(json.dumps(network.to_dict(), indent=2, default=str)[:2000] + "...")
        
        return network


def main():
    """Main entry point."""
    command = sys.argv[1] if len(sys.argv) > 1 else "help"
    
    if command == "test_features" or command == "demo":
        # Use local mode for testing
        local = LocalEcoAnalyst()
        if command == "test_features":
            local.test_features()
        else:
            local.demo()
        return
    
    if not HTTPX_AVAILABLE:
        print("httpx not installed. For API mode, run: pip install httpx")
        print("For local testing, use: python admin_cli.py test_features")
        sys.exit(1)
    
    admin = EcoAnalystAdmin()
    
    try:
        if command == "health":
            result = admin.health_check()
            print(json.dumps(result, indent=2))
        
        elif command == "networks_list":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
            result = admin.list_networks(limit)
            print(json.dumps(result, indent=2))
        
        elif command == "network_create":
            if len(sys.argv) < 3:
                print("Usage: python admin_cli.py network_create <json_file>")
                sys.exit(1)
            with open(sys.argv[2]) as f:
                data = json.load(f)
            result = admin.create_network(data)
            print(json.dumps(result, indent=2))
        
        elif command == "network_get":
            if len(sys.argv) < 3:
                print("Usage: python admin_cli.py network_get <network_id>")
                sys.exit(1)
            result = admin.get_network(sys.argv[2])
            print(json.dumps(result, indent=2))
        
        elif command == "calculate_waste":
            if len(sys.argv) < 3:
                print("Usage: python admin_cli.py calculate_waste <network_id>")
                sys.exit(1)
            result = admin.calculate_waste(sys.argv[2])
            print(json.dumps(result, indent=2))
        
        else:
            print(__doc__)
    
    except httpx.ConnectError:
        print("Error: Cannot connect to API server at", admin.base_url)
        print("Start the server with: uvicorn src.ecoanalyst.api:app --reload")
        print("Or use local mode: python admin_cli.py test_features")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
