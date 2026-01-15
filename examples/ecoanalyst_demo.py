#!/usr/bin/env python3
"""
EcoAnalyst Demo - Comprehensive example using the new v2.0 API

This example demonstrates:
1. Creating an ecosystem network with typed nodes and edges
2. Adding financial data for TCO analysis
3. Calculating waste costs and identifying hotspots
4. Finding optimal paths through the network
5. Comparing scenarios for optimization
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ecoanalyst import (
    EcosystemNetwork,
    EconomicAnalysis,
    NodeType,
    RelationshipType,
)


def create_supply_chain_network():
    """Create a sample food supply chain network."""
    
    print("=" * 70)
    print("ECOANALYST DEMO: Food Supply Chain Analysis")
    print("=" * 70)
    
    # Create network
    network = EcosystemNetwork(
        name="California Produce Supply Chain",
        description="Farm to retail distribution network for fresh produce",
        network_type="supply_chain"
    )
    
    print(f"\n✓ Created network: {network.name}")
    print(f"  ID: {network.network_id}")
    
    # ==========================================================================
    # Add Nodes
    # ==========================================================================
    print("\n" + "-" * 70)
    print("ADDING NODES")
    print("-" * 70)
    
    # Producer: Organic Farm
    farm_id = network.add_node(
        node_type=NodeType.PRODUCER,
        node_class="OrganicFarm",
        name="Salinas Valley Farm",
        properties={
            "capacity": {"value": 5000, "unit": "kg/day"},
            "efficiency": 0.95,
            "waste_rate": 0.05,  # 5% field waste
            "count": 1,
        },
        financials={
            "capex": {"value": 100000, "currency": "USD"},
            "opex_annual": {"value": 50000, "currency": "USD"},
            "waste_cost_per_unit": {"value": 0.50, "currency": "USD"},
        }
    )
    print(f"  ✓ Added farm: {farm_id[:8]}... (5% waste rate)")
    
    # Handler: Cold Storage Facility
    storage_id = network.add_node(
        node_type=NodeType.HANDLER,
        node_class="ColdStorage",
        name="Regional Cold Storage Facility",
        properties={
            "capacity": {"value": 20000, "unit": "kg"},
            "efficiency": 0.98,
            "waste_rate": 0.02,  # 2% storage waste
            "count": 1,
        },
        financials={
            "capex": {"value": 500000, "currency": "USD"},
            "opex_annual": {"value": 75000, "currency": "USD"},
            "waste_cost_per_unit": {"value": 1.00, "currency": "USD"},
        },
        operations={
            "storage_days": 14,
            "temperature_range": {"min": 2, "max": 8, "unit": "C"},
        }
    )
    print(f"  ✓ Added cold storage: {storage_id[:8]}... (2% waste rate)")
    
    # Processor: Packaging Facility
    packaging_id = network.add_node(
        node_type=NodeType.PROCESSOR,
        node_class="PackagingFacility",
        name="Fresh Pack Facility",
        properties={
            "capacity": {"value": 3000, "unit": "kg/day"},
            "efficiency": 0.96,
            "waste_rate": 0.04,  # 4% processing waste
            "count": 1,
        },
        financials={
            "capex": {"value": 250000, "currency": "USD"},
            "opex_annual": {"value": 60000, "currency": "USD"},
        }
    )
    print(f"  ✓ Added packaging: {packaging_id[:8]}... (4% waste rate)")
    
    # Consumer: Retail Store
    retailer_id = network.add_node(
        node_type=NodeType.CONSUMER,
        node_class="Retailer",
        name="Whole Foods Market",
        properties={
            "capacity": {"value": 500, "unit": "kg/day"},
            "efficiency": 0.92,
            "waste_rate": 0.08,  # 8% retail waste (highest!)
            "count": 1,
        },
        financials={
            "capex": {"value": 0, "currency": "USD"},
            "opex_annual": {"value": 10000, "currency": "USD"},
            "waste_cost_per_unit": {"value": 4.00, "currency": "USD"},
        }
    )
    print(f"  ✓ Added retailer: {retailer_id[:8]}... (8% waste rate)")
    
    # Service: Cold Chain Logistics
    logistics_id = network.add_node(
        node_type=NodeType.SERVICE,
        node_class="ColdChainLogistics",
        name="Premium Cold Transport",
        properties={
            "capacity": {"value": 10000, "unit": "kg/day"},
            "efficiency": 0.99,
            "waste_rate": 0.01,  # Only 1% with good service
            "count": 5,  # 5 trucks
        },
        financials={
            "capex": {"value": 150000, "currency": "USD"},
            "opex_annual": {"value": 40000, "currency": "USD"},
        }
    )
    print(f"  ✓ Added logistics: {logistics_id[:8]}... (1% waste rate)")
    
    # ==========================================================================
    # Add Edges
    # ==========================================================================
    print("\n" + "-" * 70)
    print("ADDING EDGES (Connections)")
    print("-" * 70)
    
    # Farm → Cold Storage
    network.add_edge(
        source_node_id=farm_id,
        target_node_id=storage_id,
        relationship_type=RelationshipType.INVENTORY_FLOW,
        flow={
            "max_rate": {"value": 4500, "unit": "kg/day"},
            "efficiency": 0.97,
            "waste_rate": 0.03,  # 3% transport loss
            "transport_time": {"value": 4, "unit": "hours"},
        }
    )
    print("  ✓ Farm → Cold Storage (3% transport waste)")
    
    # Cold Storage → Packaging
    network.add_edge(
        source_node_id=storage_id,
        target_node_id=packaging_id,
        relationship_type=RelationshipType.INVENTORY_FLOW,
        flow={
            "max_rate": {"value": 3000, "unit": "kg/day"},
            "efficiency": 0.99,
            "waste_rate": 0.01,  # 1% transport loss
            "transport_time": {"value": 1, "unit": "hours"},
        }
    )
    print("  ✓ Cold Storage → Packaging (1% transport waste)")
    
    # Packaging → Retailer
    network.add_edge(
        source_node_id=packaging_id,
        target_node_id=retailer_id,
        relationship_type=RelationshipType.INVENTORY_FLOW,
        flow={
            "max_rate": {"value": 500, "unit": "kg/day"},
            "efficiency": 0.98,
            "waste_rate": 0.02,  # 2% transport loss
            "transport_time": {"value": 2, "unit": "hours"},
        }
    )
    print("  ✓ Packaging → Retailer (2% transport waste)")
    
    # Service edge: Logistics provides service to Cold Storage
    network.add_edge(
        source_node_id=logistics_id,
        target_node_id=storage_id,
        relationship_type=RelationshipType.SERVICE_FLOW,
        flow={
            "max_rate": {"value": 10000, "unit": "kg/day"},
            "efficiency": 1.0,
        }
    )
    print("  ✓ Logistics → Cold Storage (service provision)")
    
    return network, {
        "farm": farm_id,
        "storage": storage_id,
        "packaging": packaging_id,
        "retailer": retailer_id,
        "logistics": logistics_id,
    }


def analyze_network(network, node_ids):
    """Perform comprehensive analysis on the network."""
    
    print("\n" + "=" * 70)
    print("NETWORK ANALYSIS")
    print("=" * 70)
    
    # Summary
    print("\n" + "-" * 70)
    print("NETWORK SUMMARY")
    print("-" * 70)
    
    summary = network.summary()
    print(f"  Name: {summary['name']}")
    print(f"  Type: {summary['network_type']}")
    print(f"  Total Nodes: {summary['node_count']}")
    print(f"  Total Edges: {summary['edge_count']}")
    print(f"  Node Types: {summary['node_types']}")
    print(f"  Edge Types: {summary['edge_types']}")
    
    # Economic Analysis
    print("\n" + "-" * 70)
    print("ECONOMIC ANALYSIS")
    print("-" * 70)
    
    analysis = EconomicAnalysis(network)
    
    # Define pricing by node class
    pricing = {
        "OrganicFarm": 2.00,       # $2/kg at farm gate
        "ColdStorage": 2.50,       # $2.50/kg stored value
        "PackagingFacility": 3.00, # $3/kg packaged value
        "Retailer": 4.00,          # $4/kg retail price
        "ColdChainLogistics": 2.50,
    }
    
    waste_result = analysis.calculate_waste_cost(pricing)
    
    print(f"\n  Total Waste Quantity: {waste_result['total_waste_quantity']:.2f} units")
    print(f"  Total Waste Cost: ${waste_result['total_waste_cost']:,.2f}")
    print(f"  Nodes with waste: {waste_result['node_count']}")
    print(f"  Edges with waste: {waste_result['edge_count']}")
    
    # Waste breakdown
    print("\n  Node Waste Breakdown:")
    for node_id, data in waste_result['breakdown']['nodes'].items():
        print(f"    - {data['name']}: {data['waste_quantity']:.1f} {data['unit']} (${data['waste_cost']:.2f})")
    
    print("\n  Edge Waste Breakdown:")
    for edge_id, data in waste_result['breakdown']['edges'].items():
        print(f"    - Transport: {data['waste_quantity']:.1f} {data['unit']} (${data['waste_cost']:.2f})")
    
    # Hotspot Analysis
    print("\n" + "-" * 70)
    print("HOTSPOT ANALYSIS")
    print("-" * 70)
    
    hotspots = analysis.identify_hotspots(top_n=5)
    print(f"\n  Top {len(hotspots['hotspots'])} Waste Hotspots:")
    
    for i, hotspot in enumerate(hotspots['hotspots'], 1):
        if hotspot['type'] == 'node':
            print(f"    {i}. {hotspot['name']} ({hotspot['node_class']})")
            print(f"       Waste Rate: {hotspot['waste_rate']:.1%}")
            print(f"       Waste Quantity: {hotspot['waste_quantity']:.1f}")
        else:
            print(f"    {i}. {hotspot['source']} → {hotspot['target']}")
            print(f"       Waste Rate: {hotspot['waste_rate']:.1%}")
    
    # Path Analysis
    print("\n" + "-" * 70)
    print("PATH ANALYSIS")
    print("-" * 70)
    
    farm_id = node_ids['farm']
    retailer_id = node_ids['retailer']
    
    path, total_waste, breakdown = network.find_minimum_waste_path(
        farm_id, retailer_id,
        relationship_type=RelationshipType.INVENTORY_FLOW
    )
    
    if path:
        print(f"\n  Optimal Path (Farm → Retailer):")
        print(f"    Path Length: {len(path)} nodes")
        print(f"    Total Waste: {total_waste:.1%}")
        print(f"\n    Breakdown:")
        for component, waste in breakdown.items():
            print(f"      - {component}: {waste:.1%}")
    else:
        print("  No path found")
    
    # TCO Analysis
    print("\n" + "-" * 70)
    print("TOTAL COST OF OWNERSHIP (10 years)")
    print("-" * 70)
    
    tco = analysis.calculate_total_cost_of_ownership(years=10, discount_rate=0.05)
    print(f"\n  CAPEX: ${tco['capex']:,.2f}")
    print(f"  Installation: ${tco['installation']:,.2f}")
    print(f"  OPEX (NPV): ${tco['opex_npv']:,.2f}")
    print(f"  Salvage Value (PV): ${tco['salvage_value_pv']:,.2f}")
    print(f"  ─────────────────────────")
    print(f"  Total TCO: ${tco['total_tco']:,.2f}")
    
    return analysis


def main():
    """Run the complete demo."""
    
    # Create and analyze network
    network, node_ids = create_supply_chain_network()
    analysis = analyze_network(network, node_ids)
    
    # Save network
    print("\n" + "=" * 70)
    print("SAVING NETWORK")
    print("=" * 70)
    
    output_file = Path(__file__).parent / "demo_network.json"
    network.save_to_json(str(output_file))
    print(f"\n  ✓ Saved to: {output_file}")
    
    # Summary
    print("\n" + "=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)
    print("\nKey Findings:")
    print("  1. Retailer has highest waste rate (8%)")
    print("  2. Farm → Storage transport has 3% loss")
    print("  3. Total supply chain waste is significant")
    print("\nNext Steps:")
    print("  - Optimize cold chain logistics")
    print("  - Reduce retail waste through better inventory management")
    print("  - Consider direct farm-to-retail paths for some products")


if __name__ == "__main__":
    main()
