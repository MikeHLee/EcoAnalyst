"""
advanced_ecosystem_demo.py: fit loss regressions and apply them to an AdvancedWasteNetwork (needs the bayes extra).
"""

import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from ecoanalyst.legacy.advanced_network import (
    AdvancedWasteNetwork, NodeType, EdgeType, FlowType,
    InitialProducer, FoodProcessor, FoodHandler, EndConsumer, SolutionProvider,
    InventoryEdge, ServiceEdge, CurrencyEdge
)
from ecoanalyst.legacy.causal_analysis import WasteCausalNetwork, RegressionResult

def create_demo_causal_models():
    """Fit regressions of simulated node and edge losses."""
    # Create synthetic data
    np.random.seed(42)
    n_samples = 1000
    
    # Node data: storage time, temperature, humidity affect waste
    node_data = pd.DataFrame({
        'storage_time': np.random.uniform(0, 72, n_samples),
        'temperature': np.random.uniform(0, 30, n_samples),
        'humidity': np.random.uniform(30, 80, n_samples),
        'waste': np.zeros(n_samples)
    })
    
    # Generate waste with some noise
    node_data['waste'] = (
        0.1 +  # base waste
        0.005 * node_data['storage_time'] +  # time effect
        0.01 * node_data['temperature'] +    # temperature effect
        0.002 * node_data['humidity'] +      # humidity effect
        np.random.normal(0, 0.02, n_samples) # noise
    ).clip(0, 1)
    
    # Edge data: distance and transport time affect waste
    edge_data = pd.DataFrame({
        'distance': np.random.uniform(10, 500, n_samples),
        'transport_time': np.random.uniform(1, 48, n_samples),
        'waste': np.zeros(n_samples)
    })
    
    # Generate edge waste
    edge_data['waste'] = (
        0.05 +  # base waste
        0.0002 * edge_data['distance'] +     # distance effect
        0.004 * edge_data['transport_time'] + # time effect
        np.random.normal(0, 0.01, n_samples)  # noise
    ).clip(0, 1)
    
    # Fit one regression for node losses and one for edge losses
    node_model = WasteCausalNetwork()
    node_model.add_data(node_data)
    node_model.fit()
    
    edge_model = WasteCausalNetwork()
    edge_model.add_data(edge_data)
    edge_model.fit()
    
    return node_model, edge_model

def create_advanced_ecosystem():
    """Create an example network with five nodes of each type."""
    network = AdvancedWasteNetwork()
    
    # Create nodes (5 of each type)
    producers = [InitialProducer(f"producer_{i}") for i in range(5)]
    processors = [FoodProcessor(f"processor_{i}") for i in range(5)]
    handlers = [FoodHandler(f"handler_{i}") for i in range(5)]
    consumers = [EndConsumer(f"consumer_{i}") for i in range(5)]
    providers = [SolutionProvider(f"provider_{i}") for i in range(5)]
    
    # Add all nodes
    for node in producers + processors + handlers + consumers + providers:
        network.add_node(node)
    
    # Create edges between nodes
    for i in range(5):
        # Producer to Processor edges
        inventory_edge = InventoryEdge(capacity=1000.0)
        network.add_edge(f"producer_{i}", f"processor_{i}", inventory_edge)
        
        # Processor to Handler edges
        inventory_edge = InventoryEdge(capacity=800.0)
        network.add_edge(f"processor_{i}", f"handler_{i}", inventory_edge)
        
        # Handler to Consumer edges
        inventory_edge = InventoryEdge(capacity=500.0)
        network.add_edge(f"handler_{i}", f"consumer_{i}", inventory_edge)
        
        # Solution Provider services
        for j in range(5):
            # Add service edges to processors and handlers
            if i != j:  # Avoid self-loops
                service_edge = ServiceEdge(f"cooling_service_{i}", 0.8)
                network.add_edge(f"provider_{i}", f"processor_{j}", service_edge)
                
                service_edge = ServiceEdge(f"monitoring_service_{i}", 0.85)
                network.add_edge(f"provider_{i}", f"handler_{j}", service_edge)
    
    # Add currency edges for payments
    for i in range(5):
        # Payment edges from consumers
        currency_edge = CurrencyEdge("USD")
        currency_edge.amount = 1000.0
        network.add_edge(f"consumer_{i}", f"handler_{i}", currency_edge)
        
        # Payment edges between handlers and processors
        currency_edge = CurrencyEdge("USD")
        currency_edge.amount = 800.0
        network.add_edge(f"handler_{i}", f"processor_{i}", currency_edge)
        
        # Payment edges between processors and producers
        currency_edge = CurrencyEdge("USD")
        currency_edge.amount = 600.0
        network.add_edge(f"processor_{i}", f"producer_{i}", currency_edge)
        
        # Payment edges to solution providers
        currency_edge = CurrencyEdge("USD")
        currency_edge.amount = 200.0
        network.add_edge(f"processor_{i}", f"provider_{i}", currency_edge)
        
        currency_edge = CurrencyEdge("USD")
        currency_edge.amount = 200.0
        network.add_edge(f"handler_{i}", f"provider_{i}", currency_edge)
    
    return network

def main():
    # Fit loss regressions
    node_model, edge_model = create_demo_causal_models()
    
    # Create network
    network = create_advanced_ecosystem()
    
    # Use the fitted regressions as loss functions
    for node in network.nodes.values():
        node.set_waste_function(node_model.regression_results['waste'])
        # Set example features
        node.set_features(
            storage_time=np.random.uniform(0, 72),
            temperature=np.random.uniform(0, 30),
            humidity=np.random.uniform(30, 80)
        )
    
    for _, _, edge_data in network.graph.edges(data=True):
        edge = edge_data['edge']
        if isinstance(edge, InventoryEdge):
            edge.set_waste_function(edge_model.regression_results['waste'])
            # Set example features
            edge.set_features(
                distance=np.random.uniform(10, 500),
                transport_time=np.random.uniform(1, 48)
            )
    
    # Calculate and visualize results
    import matplotlib.pyplot as plt
    
    # Create visualization with regression results
    plt.figure(figsize=(15, 10))
    network.visualize_network(
        regression_results={
            'Node Waste': node_model.regression_results['waste'],
            'Edge Waste': edge_model.regression_results['waste']
        }
    )
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    plt.savefig(output_dir / "advanced_ecosystem.png", dpi=300, bbox_inches="tight")
    plt.close()
    
    # Run some example analyses
    # Find minimum waste paths
    for flow_type in FlowType:
        paths = network.find_minimum_path(flow_type)
        print(f"\nMinimum {flow_type.value} paths:")
        for path, cost in paths:
            print(f"Path: {' -> '.join(path)}")
            print(f"Cost: {cost:.3f}")
    
    # Calculate total system waste
    total_waste = 0
    waste_breakdown = {}
    
    for node_id, node in network.nodes.items():
        waste = node.calculate_waste()
        total_waste += waste
        waste_breakdown[node_id] = waste
        
    for _, _, edge_data in network.graph.edges(data=True):
        edge = edge_data['edge']
        if isinstance(edge, InventoryEdge):
            waste = edge.calculate_waste()
            total_waste += waste
    
    print(f"\nSum of loss rates over all nodes and inventory edges: {total_waste:.3f}")
    print("\nNode waste breakdown:")
    for node_id, waste in waste_breakdown.items():
        print(f"{node_id}: {waste:.3f}")

if __name__ == "__main__":
    main()
