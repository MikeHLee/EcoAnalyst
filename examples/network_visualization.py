"""Example: drawing an AdvancedWasteNetwork and the losses along one path."""

from pathlib import Path

from ecoanalyst.legacy.advanced_network import (
    AdvancedWasteNetwork, InitialProducer, FoodProcessor,
    FoodHandler, EndConsumer, SolutionProvider,
    StaticWaste, TimeBasedWaste, MultiVariableWaste,
    InventoryEdge, ServiceEdge, CurrencyEdge, Inventory
)

def create_sample_network():
    """Create a sample network with various node and edge types."""
    network = AdvancedWasteNetwork()
    
    # Create nodes with different waste functions
    farm = InitialProducer("farm")
    farm.set_waste_function(TimeBasedWaste(0.02, 0.001))  # 2% base + 0.1%/hour
    
    processor = FoodProcessor("processor")
    processor.set_waste_function(StaticWaste(0.05))  # 5% fixed waste
    processor.add_transformation_rule(
        "raw_vegetables",
        {"cleaned_vegetables": 0.9, "waste": 0.1}
    )
    
    warehouse = FoodHandler("warehouse")
    def temp_humidity_waste(time: float = 0, temperature: float = 25.0, humidity: float = 60.0) -> float:
        return 0.01 + 0.001 * temperature + 0.0005 * humidity
    warehouse.set_waste_function(MultiVariableWaste(temp_humidity_waste))
    
    store = EndConsumer("store")
    store.set_waste_function(StaticWaste(0.15))  # 15% consumer waste
    
    cold_chain = SolutionProvider("cold_chain")
    cold_chain.add_service_effect("temperature_control", 0.7)  # 30% improvement
    
    # Add nodes to network
    for node in [farm, processor, warehouse, store, cold_chain]:
        network.add_node(node)
    
    # Create and add edges
    # Farm to Processor (inventory)
    inventory = Inventory(
        mass=1000.0,
        value=5000.0,
        composition={"raw_vegetables": 1.0},
        currency_type="USD"
    )
    edge1 = InventoryEdge(capacity=1000)
    edge1.current_flow = inventory
    network.add_edge("farm", "processor", edge1)
    
    # Cold Chain to Processor (service)
    edge2 = ServiceEdge("temperature_control", 0.7)
    network.add_edge("cold_chain", "processor", edge2)
    
    # Processor to Warehouse (inventory)
    inventory2 = Inventory(
        mass=900.0,
        value=6000.0,
        composition={"cleaned_vegetables": 1.0},
        currency_type="USD"
    )
    edge3 = InventoryEdge(capacity=1000)
    edge3.current_flow = inventory2
    network.add_edge("processor", "warehouse", edge3)
    
    # Warehouse to Store (inventory)
    inventory3 = Inventory(
        mass=850.0,
        value=7000.0,
        composition={"cleaned_vegetables": 1.0},
        currency_type="USD"
    )
    edge4 = InventoryEdge(capacity=1000)
    edge4.current_flow = inventory3
    network.add_edge("warehouse", "store", edge4)
    
    # Payment edges
    payment1 = CurrencyEdge("USD")
    payment1.amount = 5000.0
    network.add_edge("processor", "farm", payment1)
    
    payment2 = CurrencyEdge("USD")
    payment2.amount = 1000.0
    network.add_edge("processor", "cold_chain", payment2)
    
    return network

def main():
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    # Create and visualize network
    network = create_sample_network()
    
    # Generate network visualization with all annotations
    network.visualize_network(save_path=output_dir / "advanced_network_visualization.png")
    print("Generated advanced network visualization")
    
    # Analyze and visualize specific path
    path = ["farm", "processor", "warehouse", "store"]
    network.visualize_path_waste(path, save_path=output_dir / "network_visualization.png")
    print("Generated path waste visualization")
    
    print("\nVisualizations have been saved to:")
    print("- examples/output/advanced_network_visualization.png: Detailed network structure")
    print("- examples/output/network_visualization.png: Path-specific waste analysis")

if __name__ == '__main__':
    main()
