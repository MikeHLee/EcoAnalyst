"""
advanced_ecosystem.py: Example implementation of advanced waste network analysis
demonstrating complex node types, inventory management, and multi-dimensional edges.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx

from ecoanalyst.legacy.advanced_network import (
    AdvancedWasteNetwork, InitialProducer, FoodProcessor, FoodHandler,
    EndConsumer, SolutionProvider, InventoryEdge, ServiceEdge, CurrencyEdge,
    Inventory, StaticWaste, TimeBasedWaste, MultiVariableWaste
)

def create_sample_network():
    """Create a sample advanced waste network."""
    network = AdvancedWasteNetwork()
    
    # Create nodes
    farm = InitialProducer("farm")
    farm.set_waste_function(TimeBasedWaste(0.02, 0.001))  # 2% base + 0.1% per hour
    farm.material_inputs = {"fertilizer": 100, "water": 500}
    network.add_node(farm)
    
    processor = FoodProcessor("processor")
    processor.set_waste_function(StaticWaste(0.05))  # 5% static waste
    processor.add_transformation_rule(
        "raw_vegetables",
        {"cleaned_vegetables": 0.9, "waste": 0.1}
    )
    network.add_node(processor)
    
    warehouse = FoodHandler("warehouse")
    # Complex waste function based on temperature and humidity
    def temp_humidity_waste(**kwargs) -> float:
        # Default values if time is passed instead of temp/humidity
        temperature = kwargs.get('temperature', 25)
        humidity = kwargs.get('humidity', 60)
        return 0.01 + 0.001 * temperature + 0.0005 * humidity
    warehouse.set_waste_function(MultiVariableWaste(temp_humidity_waste))
    network.add_node(warehouse)
    
    store = FoodHandler("store")
    store.set_waste_function(TimeBasedWaste(0.01, 0.002))  # 1% base + 0.2% per hour
    network.add_node(store)
    
    consumer = EndConsumer("consumer")
    consumer.set_waste_function(StaticWaste(0.15))  # 15% consumer waste
    network.add_node(consumer)
    
    cold_chain = SolutionProvider("cold_chain")
    cold_chain.add_service_effect("temperature_control", 0.7)  # Reduces waste by 30%
    network.add_node(cold_chain)
    
    # Create edges
    # Farm to Processor
    inventory_edge = InventoryEdge(capacity=1000)
    inventory_edge.waste_function = TimeBasedWaste(0.01, 0.0005)
    network.add_edge("farm", "processor", inventory_edge)
    
    # Cold chain service to Processor
    service_edge = ServiceEdge("temperature_control", 0.7)
    network.add_edge("cold_chain", "processor", service_edge)
    
    # Processor to Warehouse
    inventory_edge = InventoryEdge(capacity=800)
    inventory_edge.waste_function = StaticWaste(0.02)
    network.add_edge("processor", "warehouse", inventory_edge)
    
    # Cold chain service to Warehouse
    service_edge = ServiceEdge("temperature_control", 0.7)
    network.add_edge("cold_chain", "warehouse", service_edge)
    
    # Warehouse to Store
    inventory_edge = InventoryEdge(capacity=500)
    inventory_edge.waste_function = StaticWaste(0.01)
    network.add_edge("warehouse", "store", inventory_edge)
    
    # Store to Consumer
    inventory_edge = InventoryEdge(capacity=100)
    inventory_edge.waste_function = StaticWaste(0.005)
    network.add_edge("store", "consumer", inventory_edge)
    
    # Payment edges
    for source, target in [
        ("processor", "farm"),
        ("warehouse", "processor"),
        ("store", "warehouse"),
        ("consumer", "store")
    ]:
        currency_edge = CurrencyEdge("USD")
        network.add_edge(source, target, currency_edge)
        
    return network

def visualize_advanced_network(network: AdvancedWasteNetwork, title: str = "Advanced Waste Network"):
    """Create a visualization of the advanced network."""
    plt.figure(figsize=(15, 10))
    
    # Create position layout
    pos = nx.spring_layout(network.graph, k=2)
    
    # Draw nodes with different colors based on type
    colors = {
        'initial_producer': 'lightgreen',
        'food_processor': 'lightblue',
        'food_handler': 'lightyellow',
        'end_consumer': 'salmon',
        'solution_provider': 'lightgray'
    }
    
    node_colors = [colors[network.nodes[node].node_type.value] for node in network.graph.nodes()]
    
    nx.draw_networkx_nodes(network.graph, pos, node_color=node_colors, node_size=2000)
    nx.draw_networkx_labels(network.graph, pos)
    
    # Draw edges with different styles based on type
    edge_styles = {
        'inventory': {'color': 'blue', 'style': 'solid'},
        'service': {'color': 'green', 'style': 'dashed'},
        'currency': {'color': 'red', 'style': 'dotted'}
    }
    
    for edge_type, style in edge_styles.items():
        edges = [(u, v) for u, v, d in network.graph.edges(data=True)
                if d['edge'].edge_type.value == edge_type]
        if edges:
            nx.draw_networkx_edges(
                network.graph, pos,
                edgelist=edges,
                edge_color=style['color'],
                style=style['style'],
                arrows=True,
                arrowsize=20
            )
    
    plt.title(title)
    plt.axis('off')
    return plt

def main():
    # Create and visualize the network
    network = create_sample_network()
    
    # Calculate waste along the main food path
    path = ['farm', 'processor', 'warehouse', 'store', 'consumer']
    total_waste, waste_breakdown = network.calculate_path_waste(path)
    
    print("\nWaste Analysis for Main Food Path:")
    print(f"Total waste along path: {total_waste:.1%}")
    print("\nWaste breakdown by location:")
    for location, waste in waste_breakdown.items():
        print(f"{location}: {waste:.1%}")
    
    # Visualize the network
    plt = visualize_advanced_network(network)
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "advanced_network_visualization.png"
    plt.savefig(output_path)
    plt.close()
    
    print(f"\nNetwork visualization saved to: {output_path}")
    
    # Demonstrate some advanced features
    print("\nNode Type Examples:")
    processor = network.nodes['processor']
    print(f"Processor transformation rule: {processor.transformation_rules}")
    
    cold_chain = network.nodes['cold_chain']
    print(f"Cold chain service effects: {cold_chain.service_effects}")
    
    # Calculate waste with environmental conditions
    warehouse = network.nodes['warehouse']
    waste = warehouse.waste_function.calculate(temperature=25, humidity=60)
    print(f"\nWarehouse waste at 25°C and 60% humidity: {waste:.1%}")

if __name__ == "__main__":
    main()
