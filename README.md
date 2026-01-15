# EcoAnalyst

A comprehensive library for understanding **ecosystems**, **economies**, and **abstract physically interacting networks** through graph-based modeling, causal inference, and economic analysis.

## What is EcoAnalyst?

EcoAnalyst provides tools for modeling and analyzing complex networks where **mass**, **energy**, and **information** flow between interconnected entities. The library applies graph theory, causal inference, and economic analysis to understand physical, economic, and ecological systems.

### Applications

- **Supply Chains**: Track material flows, identify loss points, optimize logistics
- **Energy Systems**: Model power grids, analyze transmission losses, optimize distribution
- **Ecological Networks**: Study nutrient flows, energy transfer, population dynamics
- **Economic Systems**: Analyze resource allocation, financial flows, market inefficiencies
- **Information Networks**: Model data flows, identify bottlenecks, optimize routing

### Core Capabilities

1. **Model the Network**: Create typed, validated graph representations with nodes (producers, processors, handlers, consumers) and edges (inventory, service, currency, energy, information flows)
2. **Quantify Flows**: Track mass, energy, and information transfer with loss/efficiency metrics
3. **Find Inefficiencies**: Identify loss hotspots and bottlenecks using graph algorithms
4. **Understand Causes**: Use Bayesian inference to discover what factors drive losses
5. **Optimize Paths**: Find minimum-loss routes through the network
6. **Calculate Economics**: Assess total cost of ownership and economic impact

## Key Features (v2.0)

- **Typed Node/Edge System**: Pydantic-validated schemas for robust data modeling
- **Multi-Domain Support**: Model supply chains, energy grids, ecological systems, or economic networks
- **Flow Analysis**: Track mass, energy, currency, and information flows with loss/efficiency metrics
- **RESTful API**: FastAPI endpoints for CRUD operations and analysis
- **MCP Integration**: AI assistant access via Model Context Protocol
- **Economic Analysis**: TCO, loss cost calculation, and scenario comparison
- **Path Optimization**: Find minimum-loss paths through networks
- **Causal Analysis**: Bayesian inference for understanding loss drivers and system dynamics

## Installation

```bash
# Clone the repository
git clone https://github.com/MikeHLee/ecoanalyst.git
cd ecoanalyst

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Quick Start

### Python API

#### Example 1: Supply Chain (Mass Flow)

```python
from src.ecoanalyst import (
    EcosystemNetwork, 
    EconomicAnalysis,
    NodeType, 
    RelationshipType
)

# Create a supply chain network
network = EcosystemNetwork(
    name="Regional Food Distribution",
    description="Farm to retail with cold chain",
    network_type="supply_chain"
)

# Add producer (mass input)
farm_id = network.add_node(
    node_type=NodeType.PRODUCER,
    node_class="Farm",
    name="Organic Farm",
    properties={
        "capacity": {"value": 5000, "unit": "kg/day"},
        "efficiency": 0.95,
        "waste_rate": 0.05,  # 5% mass loss
    }
)

# Add handler (mass storage)
storage_id = network.add_node(
    node_type=NodeType.HANDLER,
    node_class="ColdStorage",
    name="Cold Storage Facility",
    properties={
        "capacity": {"value": 20000, "unit": "kg"},
        "waste_rate": 0.02,  # 2% spoilage
    },
    operations={
        "temperature_range": {"min": 2, "max": 8, "unit": "C"}
    }
)

# Connect with inventory flow (mass transfer)
network.add_edge(
    source_node_id=farm_id,
    target_node_id=storage_id,
    relationship_type=RelationshipType.INVENTORY_FLOW,
    flow={
        "max_rate": {"value": 4500, "unit": "kg/day"},
        "efficiency": 0.97,
        "waste_rate": 0.03,  # 3% transport loss
    }
)

# Analyze losses
analysis = EconomicAnalysis(network)
result = analysis.calculate_waste_cost(
    pricing_data={"Farm": 2.00, "ColdStorage": 2.50}
)
print(f"Total mass loss cost: ${result['total_waste_cost']:,.2f}")
```

#### Example 2: Energy Grid (Energy Flow)

```python
# Create an energy network
grid = EcosystemNetwork(
    name="Regional Power Grid",
    description="Generation to distribution",
    network_type="energy"
)

# Power plant (energy producer)
plant_id = grid.add_node(
    node_type=NodeType.PRODUCER,
    node_class="SolarFarm",
    name="Desert Solar Array",
    properties={
        "capacity": {"value": 100, "unit": "MW"},
        "efficiency": 0.22,  # 22% solar conversion
        "waste_rate": 0.02,  # 2% inverter loss
    }
)

# Substation (energy handler)
substation_id = grid.add_node(
    node_type=NodeType.HANDLER,
    node_class="Substation",
    name="Regional Substation",
    properties={
        "capacity": {"value": 150, "unit": "MW"},
        "efficiency": 0.98,
        "waste_rate": 0.01,  # 1% transformer loss
    }
)

# Transmission line (energy flow)
grid.add_edge(
    source_node_id=plant_id,
    target_node_id=substation_id,
    relationship_type=RelationshipType.ENERGY_FLOW,
    flow={
        "max_rate": {"value": 95, "unit": "MW"},
        "efficiency": 0.94,  # 6% transmission loss
        "waste_rate": 0.06,
    }
)
```

### CLI Testing

```bash
# Run feature tests
python admin_cli.py test_features

# Run interactive demo
python admin_cli.py demo
```

### REST API

```bash
# Start the API server
uvicorn src.ecoanalyst.api:app --reload

# Create a network
curl -X POST http://localhost:8000/networks \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user1" \
  -d '{"name": "My Network", "network_type": "supply_chain"}'
```

### MCP Server (AI Assistant Integration)

Add to Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ecoanalyst": {
      "command": "python3",
      "args": ["/path/to/ecoanalyst/mcp_server.py"],
      "transport": "stdio"
    }
  }
}
```

## Node Types

Nodes represent entities that produce, process, handle, or consume flows of mass, energy, or information.

| Type | Description | Supply Chain | Energy System | Ecological | Economic |
|------|-------------|--------------|---------------|------------|----------|
| `producer` | Where flows enter | Farms, mines | Power plants, solar | Primary producers | Capital sources |
| `processor` | Transforms flows | Factories, mills | Refineries, converters | Decomposers | Processors |
| `handler` | Stores/moves flows | Warehouses, ports | Batteries, substations | Reservoirs | Banks, exchanges |
| `consumer` | Where flows exit | Retail, end users | Loads, consumers | Apex predators | End consumers |
| `service` | Supporting services | Cold chain, QA | Maintenance, control | Symbiotic species | Service providers |
| `grid` | External supply/sink | Imports/exports | Grid connection | Environment | External markets |

## Relationship Types

Edges represent flows of mass, energy, currency, or information between nodes.

| Type | Flow Category | Description | Examples |
|------|---------------|-------------|----------|
| `inventory_flow` | Mass | Physical goods/materials | Food, raw materials, products |
| `energy_flow` | Energy | Power/energy transfer | Electricity, heat, fuel |
| `information_flow` | Information | Data/signals | Sensor data, control signals |
| `currency_flow` | Economic | Financial transactions | Payments, investments |
| `service_flow` | Service | Service provision | Maintenance, logistics |
| `waste_flow` | Mass/Energy | Waste/byproduct movement | Emissions, waste disposal |

## Project Structure

```
ecoanalyst/
├── src/
│   ├── ecoanalyst/           # New typed API (v2.0)
│   │   ├── __init__.py
│   │   ├── models.py         # Pydantic schemas
│   │   ├── network.py        # EcosystemNetwork class
│   │   ├── analysis.py       # EconomicAnalysis class
│   │   └── api.py            # FastAPI endpoints
│   ├── network_model.py      # Legacy network model
│   ├── advanced_network.py   # Advanced features
│   ├── causal_analysis.py    # Bayesian inference
│   └── network_viz.py        # Visualization
├── examples/                  # Example scripts
├── whitepaper/               # Academic documentation
├── mcp_server.py             # MCP server for AI assistants
├── admin_cli.py              # CLI admin tool
└── requirements.txt
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/networks` | Create network |
| GET | `/networks` | List networks |
| GET | `/networks/{id}` | Get network |
| DELETE | `/networks/{id}` | Delete network |
| POST | `/networks/{id}/nodes` | Add node |
| DELETE | `/networks/{id}/nodes/{node_id}` | Delete node |
| POST | `/networks/{id}/edges` | Add edge |
| POST | `/networks/{id}/calculate-waste` | Calculate waste |
| GET | `/networks/{id}/optimize-paths` | Find optimal path |
| GET | `/networks/{id}/hotspots` | Identify hotspots |

## Documentation

- **Whitepaper**: See `whitepaper/` for mathematical formulation
- **API Docs**: Run server and visit `http://localhost:8000/docs`
- **Examples**: See `examples/` directory

## Migration from v1.x

The legacy `WasteNetwork` class is still available in `src/network_model.py`. For new projects, use the typed `EcosystemNetwork` class from `src/ecoanalyst/`.

## Contributing

Contributions welcome! Please read our contributing guidelines.

## License

MIT License - see LICENSE file for details.
