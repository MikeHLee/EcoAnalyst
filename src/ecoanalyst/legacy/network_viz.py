"""
network_viz.py: matplotlib drawing helpers for AdvancedWasteNetwork (EcoAnalyst 1.x).

matplotlib is imported inside the functions, so importing this module does
not need it. Install the ``viz`` extra to draw.
"""

from __future__ import annotations

from typing import Dict, List, Tuple, Any, Optional
import networkx as nx
from .advanced_network import (
    NodeType, EdgeType, AdvancedNode, AdvancedEdge,
    InventoryEdge, ServiceEdge, CurrencyEdge, RegressionResult
)

def create_node_style(node_type: NodeType) -> Dict[str, Any]:
    """Create node style based on type."""
    styles = {
        NodeType.SOLUTION_PROVIDER: {
            'shape': 'rectangle',
            'color': '#A8E6CE',  # Mint green
            'size': 2000
        },
        NodeType.END_CONSUMER: {
            'shape': 'circle',
            'color': '#FFB3BA',  # Light red
            'size': 1500
        },
        NodeType.INITIAL_PRODUCER: {
            'shape': 'rectangle',
            'color': '#BAFFC9',  # Light green
            'size': 2000
        },
        NodeType.FOOD_PROCESSOR: {
            'shape': 'rectangle',
            'color': '#BAE1FF',  # Light blue
            'size': 2000
        },
        NodeType.FOOD_HANDLER: {
            'shape': 'rectangle',
            'color': '#FFE4BA',  # Light orange
            'size': 2000
        }
    }
    return styles[node_type]

def create_edge_style(edge_type: EdgeType) -> Dict[str, Any]:
    """Create edge style based on type."""
    styles = {
        EdgeType.INVENTORY: {
            'style': 'solid',
            'color': '#2C3E50',  # Dark blue
            'width': 3,  # Increased width
            'arrowsize': 15  # Added arrow size
        },
        EdgeType.SERVICE: {
            'style': 'dashed',
            'color': '#8E44AD',  # Purple
            'width': 2,  # Increased width
            'arrowsize': 12  # Added arrow size
        },
        EdgeType.CURRENCY: {
            'style': 'dotted',
            'color': '#27AE60',  # Green
            'width': 2,  # Increased width
            'arrowsize': 12  # Added arrow size
        }
    }
    return styles[edge_type]

def annotate_node(
    ax: plt.Axes,
    pos: Dict[str, Tuple[float, float]],
    node_id: str,
    node: AdvancedNode,
    waste: Optional[float] = None
) -> None:
    """Add node annotations."""
    x, y = pos[node_id]
    
    # Node type and ID
    ax.annotate(
        f"{node.node_type.value}\n{node_id}",
        (x, y),
        xytext=(0, 20),
        textcoords="offset points",
        ha='center',
        va='bottom',
        bbox=dict(boxstyle='round,pad=0.5', fc='white', alpha=0.8)
    )
    
    # Waste percentage if available
    if waste is not None:
        ax.annotate(
            f"Waste: {waste:.1%}",
            (x, y),
            xytext=(0, -20),
            textcoords="offset points",
            ha='center',
            va='top',
            bbox=dict(boxstyle='round,pad=0.5', fc='#FFE4E1', alpha=0.8)
        )

def annotate_edge(
    ax: plt.Axes,
    pos: Dict[str, Tuple[float, float]],
    source: str,
    target: str,
    edge: AdvancedEdge,
    waste: Optional[float] = None
) -> None:
    """Add edge annotations."""
    x1, y1 = pos[source]
    x2, y2 = pos[target]
    x = (x1 + x2) / 2
    y = (y1 + y2) / 2
    
    # Edge type
    ax.annotate(
        edge.edge_type.value,
        (x, y),
        xytext=(0, 10),
        textcoords="offset points",
        ha='center',
        va='bottom',
        bbox=dict(boxstyle='round,pad=0.5', fc='white', alpha=0.8)
    )
    
    # Additional properties based on edge type
    props = []
    if isinstance(edge, InventoryEdge):
        if hasattr(edge, 'current_flow') and edge.current_flow:
            props.append(f"Flow: {edge.current_flow:.1f}")
        props.append(f"Cap: {edge.capacity:.1f}")
    elif isinstance(edge, ServiceEdge):
        props.append(f"Effect: {edge.effect_multiplier:.2f}")
    elif isinstance(edge, CurrencyEdge):
        props.append(f"{edge.currency_type}: {edge.amount:.2f}")
        
    if waste is not None:
        props.append(f"Waste: {waste:.1%}")
        
    if props:
        ax.annotate(
            "\n".join(props),
            (x, y),
            xytext=(0, -10),
            textcoords="offset points",
            ha='center',
            va='top',
            bbox=dict(boxstyle='round,pad=0.5', fc='#E8F8F5', alpha=0.8)
        )

def visualize_network(
    network: 'AdvancedWasteNetwork',
    title: str = "Waste Network Visualization",
    node_wastes: Optional[Dict[str, float]] = None,
    edge_wastes: Optional[Dict[Tuple[str, str], float]] = None,
    highlight_path: Optional[List[str]] = None,
    regression_results: Optional[Dict[str, RegressionResult]] = None
) -> plt.Figure:
    """Create an annotated visualization of the network."""
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Circle, FancyArrowPatch

    fig, ax = plt.subplots(figsize=(12, 8))
    
    # Create layout
    pos = nx.spring_layout(network.graph, k=1, iterations=50)
    
    # Draw nodes
    for node_id, node in network.nodes.items():
        style = create_node_style(node.node_type)
        if style['shape'] == 'rectangle':
            rect = Rectangle(
                (pos[node_id][0] - 0.05, pos[node_id][1] - 0.05),
                0.1, 0.1,
                facecolor=style['color'],
                edgecolor='black'
            )
            ax.add_patch(rect)
        else:
            circle = Circle(
                pos[node_id],
                radius=0.05,
                facecolor=style['color'],
                edgecolor='black'
            )
            ax.add_patch(circle)
            
        # Add node annotations
        waste = node_wastes.get(node_id) if node_wastes else None
        annotate_node(ax, pos, node_id, node, waste)
    
    # Draw edges
    for source, target, edge_data in network.graph.edges(data=True):
        edge = edge_data['edge']
        style = create_edge_style(edge.edge_type)
        
        # Draw edge
        arrow = FancyArrowPatch(
            pos[source],
            pos[target],
            arrowstyle=f'-|>,head_length={style["arrowsize"]},head_width={style["arrowsize"]/1.5}',
            connectionstyle='arc3,rad=0.2',
            color=style['color'],
            linestyle=style['style'],
            linewidth=style['width']
        )
        ax.add_patch(arrow)
        
        # Add edge annotations
        waste = edge_wastes.get((source, target)) if edge_wastes else None
        annotate_edge(ax, pos, source, target, edge, waste)
    
    # Highlight path if provided
    if highlight_path:
        path_edges = list(zip(highlight_path[:-1], highlight_path[1:]))
        for source, target in path_edges:
            arrow = FancyArrowPatch(
                pos[source],
                pos[target],
                arrowstyle='-|>',
                connectionstyle='arc3,rad=0.2',
                color='red',
                linewidth=3,
                alpha=0.5
            )
            ax.add_patch(arrow)
    
    # Add regression results if available
    if regression_results:
        for var, result in regression_results.items():
            bbox_props = dict(boxstyle="round,pad=0.5", fc="white", ec="gray", alpha=0.9)
            summary = f"{var} Regression:\n"
            for coef, (mean, std) in result.coefficients.items():
                summary += f"{coef}: {mean:.3f} ± {std:.3f}\n"
            summary += f"R² = {result.r2_score:.3f}"
            
            # Position at top of plot
            ax.text(0.02, 0.98, summary,
                   transform=ax.transAxes,
                   verticalalignment='top',
                   bbox=bbox_props,
                   fontsize=8)
    
    # Set plot limits and title
    ax.set_xlim((-1.2, 1.2))
    ax.set_ylim((-1.2, 1.2))
    ax.set_title(title)
    ax.axis('off')
    
    return fig
