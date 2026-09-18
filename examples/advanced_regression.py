"""Example: Bayesian linear regression of inventory loss on storage conditions."""

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from ecoanalyst.legacy.advanced_network import AdvancedWasteNetwork, AdvancedNode, TimeBasedWaste
from ecoanalyst.legacy.causal_analysis import WasteCausalNetwork
import networkx as nx

def create_sample_data():
    """Create sample data for regression analysis with inventory loss percentages."""
    np.random.seed(42)
    n_samples = 100
    
    # Generate synthetic data
    storage_time = np.random.uniform(0, 10, n_samples)  # days
    temperature = np.random.normal(20, 5, n_samples)    # Celsius
    humidity = np.random.uniform(30, 70, n_samples)     # %
    initial_inventory = np.random.uniform(100, 1000, n_samples)  # units
    
    # Calculate percentage loss based on realistic factors
    # Base degradation rate (0.5% per day)
    base_loss = 0.005 * storage_time
    
    # Temperature effect (increases by 0.1% per degree above 15°C)
    temp_effect = np.maximum(0, 0.001 * (temperature - 15))
    
    # Humidity effect (optimal range 40-60%, increases outside this range)
    humidity_effect = 0.0005 * np.abs(humidity - 50)
    
    # Combine effects and add some random variation
    loss_percentage = (
        base_loss +                    # Time-based degradation
        temp_effect * storage_time +   # Temperature effect increases with time
        humidity_effect +              # Humidity effect
        np.random.normal(0, 0.01, n_samples)  # Random variation
    ) * 100  # Convert to percentage
    
    # Ensure loss percentage is between 0 and 100
    loss_percentage = np.clip(loss_percentage, 0, 100)
    
    # Calculate actual inventory loss
    inventory_loss = (loss_percentage / 100) * initial_inventory
    
    return pd.DataFrame({
        'storage_time': storage_time,
        'temperature': temperature,
        'humidity': humidity,
        'initial_inventory': initial_inventory,
        'loss_percentage': loss_percentage,
        'inventory_loss': inventory_loss
    })

OUTPUT_DIR = Path(__file__).parent / "output"


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Create sample network and data
    network = AdvancedWasteNetwork()
    data = create_sample_data()
    
    # Variable graph and data
    causal_net = WasteCausalNetwork()
    
    # Add nodes and relationships
    causal_net.add_node('storage_time', 'cause', 'normal')
    causal_net.add_node('temperature', 'cause', 'normal')
    causal_net.add_node('humidity', 'cause', 'normal')
    causal_net.add_node('initial_inventory', 'cause', 'normal')
    causal_net.add_node('loss_percentage', 'effect', 'normal')
    
    # Edge weights are illustrative labels for the drawing
    causal_net.add_edge('storage_time', 'loss_percentage', 0.5)
    causal_net.add_edge('temperature', 'loss_percentage', 0.3)
    causal_net.add_edge('humidity', 'loss_percentage', 0.1)
    causal_net.add_edge('initial_inventory', 'loss_percentage', 0.05)
    
    # Add data
    causal_net.add_data(data)
    
    # Fit regression for loss percentage prediction
    print("Fitting regression for inventory loss percentage prediction...")
    features = ['storage_time', 'temperature', 'humidity', 'initial_inventory']
    result = causal_net.fit_regression(target='loss_percentage', features=features)

    # fit_regression standardizes features, so scenarios are standardized the same way.
    feature_mean = data[features].mean()
    feature_std = data[features].std(ddof=0)
    
    # Save regression results
    with open(OUTPUT_DIR / "regression_results.txt", "w") as f:
        f.write(result.model_summary)
        f.write("\n\nSample Predictions:\n")
        f.write("-" * 50 + "\n")
        f.write(f"{'Storage Time':>12} {'Temperature':>12} {'Humidity':>12} {'Initial Inv':>12} {'Pred Loss %':>12}\n")
        
        # Generate predictions for some example scenarios
        scenarios = [
            (1, 20, 50, 500),   # Optimal conditions, short storage
            (5, 25, 55, 500),   # Moderate conditions
            (10, 30, 70, 500),  # Suboptimal conditions, long storage
        ]
        
        for st, temp, hum, inv in scenarios:
            values = dict(zip(features, (st, temp, hum, inv)))
            pred = result.coefficients['intercept'][0] + sum(
                result.coefficients[name][0] * (values[name] - feature_mean[name]) / feature_std[name]
                for name in features
            )
            
            f.write(f"{st:12.1f} {temp:12.1f} {hum:12.1f} {inv:12.1f} {pred:12.1f}\n")
    
    # Plot regression results for storage time
    fig1 = causal_net.plot_regression_results('loss_percentage', 'storage_time')
    ax1 = fig1.axes[0]
    ax1.set_title('Inventory Loss vs Storage Time\nR² = {:.3f}'.format(result.r2_score))
    ax1.set_xlabel('Storage Time (days)')
    ax1.set_ylabel('Loss Percentage (%)')
    ax1.grid(True, alpha=0.3)
    ax1.text(0.05, 0.95, 
             f'Coefficient per SD: {result.coefficients["storage_time"][0]:.2f}\n'
             f'95% CI: [{result.coefficients["storage_time"][0] - 1.96*result.coefficients["storage_time"][1]:.2f}, '
             f'{result.coefficients["storage_time"][0] + 1.96*result.coefficients["storage_time"][1]:.2f}]',
             transform=ax1.transAxes, 
             bbox=dict(facecolor='white', alpha=0.8))
    fig1.savefig(OUTPUT_DIR / "loss_vs_storage.png", dpi=300, bbox_inches='tight')
    
    # Plot regression results for temperature
    fig2 = causal_net.plot_regression_results('loss_percentage', 'temperature')
    ax2 = fig2.axes[0]
    ax2.set_title('Inventory Loss vs Temperature\nR² = {:.3f}'.format(result.r2_score))
    ax2.set_xlabel('Temperature (°C)')
    ax2.set_ylabel('Loss Percentage (%)')
    ax2.grid(True, alpha=0.3)
    ax2.text(0.05, 0.95,
             f'Coefficient per SD: {result.coefficients["temperature"][0]:.2f}\n'
             f'95% CI: [{result.coefficients["temperature"][0] - 1.96*result.coefficients["temperature"][1]:.2f}, '
             f'{result.coefficients["temperature"][0] + 1.96*result.coefficients["temperature"][1]:.2f}]',
             transform=ax2.transAxes,
             bbox=dict(facecolor='white', alpha=0.8))
    fig2.savefig(OUTPUT_DIR / "loss_vs_temperature.png", dpi=300, bbox_inches='tight')
    
    # Draw the variable graph with the fitted coefficients
    fig3, ax3 = plt.subplots(figsize=(15, 10))
    pos = nx.spring_layout(causal_net.graph, k=2)
    
    # Draw nodes with different colors based on type
    cause_nodes = [n for n, d in causal_net.graph.nodes(data=True) if d.get('node_type') == 'cause']
    effect_nodes = [n for n, d in causal_net.graph.nodes(data=True) if d.get('node_type') == 'effect']
    
    # Draw nodes
    nx.draw_networkx_nodes(causal_net.graph, pos, nodelist=cause_nodes,
                          node_color='lightblue', node_size=3000, alpha=0.7)
    nx.draw_networkx_nodes(causal_net.graph, pos, nodelist=effect_nodes,
                          node_color='lightgreen', node_size=3000, alpha=0.7)
    
    # Draw edges with effect sizes
    edge_labels = {}
    edges = []
    edge_colors = []
    edge_widths = []
    
    for u, v, data in causal_net.graph.edges(data=True):
        effect_size = data.get('effect_size', 0)
        edge_labels[(u, v)] = f'β = {effect_size:.2f}'
        edges.append((u, v))
        # Color edges based on effect size (red for strong, blue for weak)
        edge_colors.append(plt.cm.RdYlBu(1 - abs(effect_size)))
        edge_widths.append(abs(effect_size) * 3)
    
    nx.draw_networkx_edges(causal_net.graph, pos, edgelist=edges,
                          edge_color=edge_colors, width=edge_widths,
                          arrowsize=20)
    
    # Add node labels with coefficient information
    node_labels = {}
    for node in causal_net.graph.nodes():
        if node in result.coefficients:
            coef, std = result.coefficients[node]
            node_labels[node] = f'{node}\nβ = {coef:.2f}\nσ = {std:.2f}'
        else:
            node_labels[node] = node
    
    nx.draw_networkx_labels(causal_net.graph, pos, labels=node_labels,
                           font_size=10)
    
    # Add edge labels
    nx.draw_networkx_edge_labels(causal_net.graph, pos,
                                edge_labels=edge_labels,
                                font_size=8)
    
    # Add title and legend
    ax3.set_title('Loss drivers\nBayesian linear regression of inventory loss', 
                  fontsize=16, pad=20)
    
    # Add legend
    legend_elements = [
        plt.Line2D([0], [0], color='lightblue', marker='o',
                  markersize=15, label='Driver variables', linestyle='None'),
        plt.Line2D([0], [0], color='lightgreen', marker='o',
                  markersize=15, label='Outcome', linestyle='None'),
        plt.Line2D([0], [0], color='red', linewidth=2,
                  label='Large edge weight'),
        plt.Line2D([0], [0], color='blue', linewidth=2,
                  label='Small edge weight')
    ]
    ax3.legend(handles=legend_elements, loc='upper left',
               bbox_to_anchor=(1, 1))
    
    # Add R² score annotation
    ax3.text(0.95, 0.05,
             f'Model R² = {result.r2_score:.3f}',
             transform=ax3.transAxes,
             bbox=dict(facecolor='white', alpha=0.8),
             horizontalalignment='right')
    
    ax3.axis('off')
    fig3.tight_layout()
    fig3.savefig(OUTPUT_DIR / "causal_graph.png", dpi=300, bbox_inches='tight')
    
    print("\nResults have been saved to:")
    print("- examples/output/regression_results.txt: Detailed regression analysis and predictions")
    print("- examples/output/loss_vs_storage.png: Loss percentage vs storage time visualization")
    print("- examples/output/loss_vs_temperature.png: Loss percentage vs temperature visualization")
    print("- examples/output/causal_graph.png: variable graph with the regression coefficients")

if __name__ == '__main__':
    main()
