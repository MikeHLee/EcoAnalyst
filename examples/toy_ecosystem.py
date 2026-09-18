"""
toy_ecosystem.py: a 1.x WasteNetwork of growers, distributors, and a store.

The first half finds minimum-loss paths in data/network_data.json. The second
half simulates storage conditions and fits a Bayesian linear regression of
waste on them, which needs the bayes extra.
"""

from pathlib import Path

from ecoanalyst.legacy.network_model import WasteNetwork
from ecoanalyst.legacy.causal_analysis import WasteCausalNetwork
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import numpy as np

def visualize_network(network: WasteNetwork, highlight_path: list = None, title: str = "Waste Network"):
    """Create a visualization of the network with node types and edge weights."""
    plt.figure(figsize=(12, 8))
    
    # Create position layout
    pos = nx.spring_layout(network.graph)
    
    # Draw nodes with different colors based on type
    colors = {'grower': 'lightgreen', 'distributor': 'lightblue', 'store': 'salmon'}
    node_colors = [colors[network.graph.nodes[node]['node_type']] for node in network.graph.nodes()]
    
    nx.draw_networkx_nodes(network.graph, pos, node_color=node_colors, node_size=1500)
    nx.draw_networkx_labels(network.graph, pos)
    
    # Draw edges with waste rates
    edge_labels = {(u, v): f"{d['transport_waste']:.1%}" 
                  for u, v, d in network.graph.edges(data=True)}
    
    # Draw highlighted path if provided
    if highlight_path:
        path_edges = list(zip(highlight_path[:-1], highlight_path[1:]))
        
        # Draw highlighted edges in red
        nx.draw_networkx_edges(network.graph, pos,
                             edgelist=path_edges,
                             edge_color='red',
                             width=2)
        
        # Draw other edges in gray
        other_edges = [(u, v) for u, v in network.graph.edges()
                      if (u, v) not in path_edges]
        nx.draw_networkx_edges(network.graph, pos,
                             edgelist=other_edges,
                             edge_color='gray')
    else:
        nx.draw_networkx_edges(network.graph, pos, edge_color='gray')
        
    nx.draw_networkx_edge_labels(network.graph, pos, edge_labels=edge_labels)
    
    plt.title(title)
    plt.axis('off')
    return plt

def analyze_all_paths(network: WasteNetwork):
    """Analyze all possible paths between nodes in the network."""
    results = []
    nodes = list(network.graph.nodes())
    
    for i, source in enumerate(nodes):
        for target in nodes[i+1:]:
            path, total_waste = network.find_minimum_waste_path(source, target)
            if path:
                results.append({
                    'source': source,
                    'target': target,
                    'path': ' -> '.join(path),
                    'total_waste': total_waste
                })
    
    return pd.DataFrame(results)

def create_causal_network():
    """Build a variable graph and simulated data for a regression of waste on conditions."""
    causal_net = WasteCausalNetwork()
    
    # Add nodes representing different factors
    causal_net.add_node('temperature', 'cause', 
                        distribution='normal',
                        params={'mu': 20, 'sigma': 5})
    
    causal_net.add_node('humidity', 'cause',
                        distribution='normal',
                        params={'mu': 50, 'sigma': 10})
    
    causal_net.add_node('storage_time', 'cause',
                        distribution='normal',
                        params={'mu': 24, 'sigma': 6})
    
    causal_net.add_node('product_damage', 'effect',
                        distribution='normal',
                        params={'sigma': 1.0})
    
    causal_net.add_node('waste_amount', 'effect',
                        distribution='normal',
                        params={'sigma': 1.0})
    
    # Edge weights are the values used to simulate the data below.
    causal_net.add_edge('temperature', 'product_damage', effect_size=0.3)
    causal_net.add_edge('humidity', 'product_damage', effect_size=0.2)
    causal_net.add_edge('storage_time', 'product_damage', effect_size=0.4)
    causal_net.add_edge('product_damage', 'waste_amount', effect_size=0.8)
    
    # Simulate observations
    n_samples = 1000
    np.random.seed(42)
    
    # Storage conditions
    data = pd.DataFrame({
        'temperature': np.random.normal(20, 5, n_samples),
        'humidity': np.random.normal(50, 10, n_samples),
        'storage_time': np.random.normal(24, 6, n_samples)
    })
    
    # Product damage is not observed
    product_damage = (0.3 * data['temperature'] +
                     0.2 * data['humidity'] +
                     0.4 * data['storage_time'] +
                     np.random.normal(0, 1, n_samples))
    
    # Waste is observed and becomes the regression target
    waste_amount = (0.8 * product_damage +
                   np.random.normal(0, 1, n_samples))
    
    data['waste'] = waste_amount
    causal_net.add_data(data)
    return causal_net

def main():
    # Load the network from our JSON file
    data_path = Path(__file__).parent.parent / 'data' / 'network_data.json'
    network = WasteNetwork.load_from_json(data_path)
    
    # Analyze all paths
    print("\nAnalyzing all paths in the network:")
    all_paths_df = analyze_all_paths(network)
    print(all_paths_df.to_string(index=False))
    
    # Find and visualize minimum waste path from growerA to store
    source = 'growerA'
    target = 'store'
    min_path, total_waste = network.find_minimum_waste_path(source, target)
    
    print(f"\nDetailed analysis of minimum waste path from {source} to {target}:")
    print(f"Path: {' -> '.join(min_path)}")
    print(f"Total waste: {total_waste:.1%}")
    
    # Calculate detailed waste breakdown
    total_waste, waste_breakdown = network.calculate_path_waste(min_path)
    print("\nWaste breakdown:")
    for location, waste in waste_breakdown.items():
        print(f"{location}: {waste:.1%}")
    
    # Visualize the network with highlighted minimum waste path
    plt = visualize_network(network, highlight_path=min_path,
                          title="Waste Network (Minimum Waste Path Highlighted)")
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "network_visualization.png"
    plt.savefig(output_path)
    plt.close()
    
    # Regression of waste on storage conditions
    print("\nFitting a Bayesian linear regression of waste on storage conditions...")
    causal_net = create_causal_network()
    causal_net.fit(samples=1000)

    result = causal_net.regression_results['waste']
    print("\nPosterior mean coefficients (simulated with 0.24, 0.16, 0.32):")
    for name in ['temperature', 'humidity', 'storage_time', 'intercept']:
        mean, std = result.coefficients[name]
        print(f"{name:>12}: {mean:6.3f} (±{std:.3f})")
    print(f"R² = {result.r2_score:.3f}")
    
    # Draw the variable graph with the simulation weights
    plt = causal_net.plot_causal_graph()
    causal_output_path = output_dir / "causal_network.png"
    plt.savefig(causal_output_path)
    plt.close()
    
    print(f"\nNetwork visualizations saved to:")
    print(f"1. {output_path}")
    print(f"2. {causal_output_path}")

if __name__ == "__main__":
    main()
