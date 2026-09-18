# EcoAnalyst

EcoAnalyst models a supply chain, energy system, or other flow network as a directed graph of producers, processors, handlers, and consumers. Each node and edge can carry a capacity, a loss rate, and costs. The library computes how much is lost along a route, finds the route that delivers the most, prices the losses, and exchanges networks as JSON through a Python API, a command line tool, a local REST server, and an MCP server.

## Install

EcoAnalyst needs Python 3.10 or later.

```bash
git clone https://github.com/MikeHLee/ecoanalyst.git
cd ecoanalyst
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

The core install depends on networkx, numpy, and pydantic. Optional parts are extras:

| Extra | Adds | Needed for |
|-------|------|------------|
| `api` | fastapi, uvicorn, httpx | the REST server |
| `mcp` | mcp | the MCP server (`ecoanalyst-mcp`) |
| `viz` | matplotlib | drawing in the legacy modules and examples |
| `bayes` | pymc, arviz, pandas, scipy, matplotlib | the legacy regression module |
| `dev` | pytest, httpx, fastapi, jsonschema | running the tests |
| `all` | everything except `dev` | |

For example: `pip install -e ".[api,mcp]"`.

## Quick start

<!-- tests/test_readme.py runs the next code block and checks the commented output. -->
```python
from ecoanalyst import EconomicAnalysis, EcosystemNetwork, NodeType, RelationshipType

net = EcosystemNetwork(name="Produce chain", network_type="supply_chain")

farm = net.add_node(NodeType.PRODUCER, "Farm", "Valley Farm",
                    properties={"capacity": {"value": 1000, "unit": "kg/day"}, "waste_rate": 0.05})
store = net.add_node(NodeType.HANDLER, "ColdStorage", "Cold Store",
                     properties={"capacity": {"value": 5000, "unit": "kg"}, "waste_rate": 0.02})
shop = net.add_node(NodeType.CONSUMER, "Retailer", "Corner Grocer",
                    properties={"capacity": {"value": 800, "unit": "kg/day"}, "waste_rate": 0.08})

kg_day = "kg/day"
net.add_edge(farm, store, RelationshipType.INVENTORY,
             {"max_rate": {"value": 900, "unit": kg_day}, "waste_rate": 0.01})
net.add_edge(store, shop, RelationshipType.INVENTORY,
             {"max_rate": {"value": 800, "unit": kg_day}, "waste_rate": 0.01})
net.add_edge(farm, shop, RelationshipType.INVENTORY,
             {"max_rate": {"value": 300, "unit": kg_day}, "waste_rate": 0.15})
net.add_edge(shop, farm, RelationshipType.CURRENCY,
             {"max_rate": {"value": 2000, "unit": "USD/day"}})

path, loss, _ = net.find_minimum_waste_path(farm, shop, edge_kinds=["inventory"])
print(" -> ".join(net.nodes[n].name for n in path), f"loses {loss:.2%}")
# Valley Farm -> Cold Store -> Corner Grocer loses 16.05%

cost = EconomicAnalysis(net).calculate_path_cost(
    path, pricing_data={"Farm": 2.0, "ColdStorage": 2.5, "Retailer": 4.0}
)
print(f"{cost['delivered_quantity']:.1f} of {cost['input_quantity']:.0f} kg delivered, "
      f"losses cost ${cost['total_cost']:.2f}")
# 839.5 of 1000 kg delivered, losses cost $481.06
```

The route search is limited to inventory edges, so the payment edge from shop to farm is not treated as a route for goods. The direct farm-to-shop edge loses 15% in transit, so that route loses 1 - 0.95 × 0.85 × 0.92 = 25.71% and the search passes it over.

`ecoanalyst demo` builds and analyzes the same network from the command line.

## Node kinds

A node kind says what role a node plays. Kinds are lowercase identifiers. The library defines the kinds below, and any other value that matches `^[a-z][a-z0-9_]*$` (for example `cold_store` or `substation`) is accepted as a custom kind. `NodeType` holds the built-in kinds as constants.

| Kind | Set | Role | Examples |
|------|-----|------|----------|
| `producer` | canonical | material or energy enters the network | farm, mine, power plant |
| `processor` | canonical | transforms what passes through | packing plant, refinery, inverter |
| `handler` | canonical | stores or moves without transforming | warehouse, substation, battery |
| `consumer` | canonical | material or energy leaves the network | retailer, household load |
| `service` | extended | supports other nodes | cold chain operator, maintenance crew |
| `grid` | extended | external supply or sink | utility connection, open market |

## Flow kinds

A flow kind says what an edge carries. Kinds are stored in their short form. The 2.x names are accepted as aliases wherever a kind is read, including old JSON files. Custom kinds follow the same pattern as node kinds.

| Kind | Set | Carries | 2.x alias | Constant |
|------|-----|---------|-----------|----------|
| `inventory` | canonical | goods and materials | `inventory_flow` | `RelationshipType.INVENTORY` |
| `energy` | canonical | electricity, heat, fuel | `energy_flow` | `RelationshipType.ENERGY` |
| `currency` | canonical | payments | `currency_flow` | `RelationshipType.CURRENCY` |
| `information` | canonical | data and signals | `information_flow` | `RelationshipType.INFORMATION` |
| `service` | extended | service provision | `service_flow` | `RelationshipType.SERVICE` |
| `waste` | extended | waste and byproducts | `waste_flow` | `RelationshipType.WASTE` |
| `control` | extended | management and control signals | `control_signal` | `RelationshipType.CONTROL` |

The old member names still work: `RelationshipType.INVENTORY_FLOW` is the same member as `RelationshipType.INVENTORY`, and its value is `"inventory"`. `normalize_node_kind()` and `normalize_edge_kind()` apply these rules to any value.

Nodes and edges also take a few optional fields that the analysis does not use but that are stored and exported: `geometry` (a GeoJSON-like object) and `series_ref` (a string that points at a time series kept elsewhere) on nodes, and `polarity` (`"positive"` or `"negative"`) and `series_ref` on edges.

## How losses compound

A loss rate is the fraction of what reaches a component that the component loses. When material passes several components in a row, each one loses a share of what is left, so the losses multiply rather than add:

```
total loss = 1 - (1 - w1)(1 - w2)...(1 - wn)
```

Two steps that lose 10% and 20% lose 1 - 0.9 × 0.8 = 28% together, not 30%. The total never exceeds 100%.

`find_minimum_waste_path` weights each edge by -log(1 - w_edge) - log(1 - w_source_node). A shortest path under these weights is the path that keeps the largest fraction. An edge with a loss rate of 1 carries nothing and is skipped. When two nodes are joined by several edges, the path uses the one with the lowest loss rate; pass `edge_kinds` to limit which kinds are eligible.

There are two cost estimates in `EconomicAnalysis`:

| Method | What it computes |
|--------|------------------|
| `calculate_path_cost(path, input_quantity=...)` | Starts with a quantity (default: first node capacity × count) and removes each component's share in order along the path. Node losses are priced by node class, edge losses by the source node's class. |
| `calculate_waste_cost()` | Takes each node at capacity × count and each edge at its max rate, and multiplies by its own loss rate. It ranks components quickly but does not follow material between them, so it is not a mass balance. |

`identify_hotspots()` ranks components by loss rate or by the capacity-based loss quantity. `calculate_total_cost_of_ownership()` adds capex, installation, and discounted annual opex, and subtracts the discounted salvage value.

## Flow-graph export

`to_flow_graph()` writes a network in a portable JSON format with `actors` and `flows`, and `from_flow_graph()` reads it back without loss:

```python
import json

with open("chain.flowgraph.json", "w") as f:
    json.dump(net.to_flow_graph(), f, indent=2)

with open("chain.flowgraph.json") as f:
    again = EcosystemNetwork.from_flow_graph(json.load(f))
```

The format is described in [docs/flow_graph_format.md](docs/flow_graph_format.md), with a JSON Schema in [docs/flowgraph.schema.json](docs/flowgraph.schema.json). `EcosystemNetwork.load_from_json()` detects the format of a file: the native format written by `save_to_json()` (including 2.x files), a flow graph, or a 1.x `WasteNetwork` file.

## Command line

```bash
ecoanalyst demo                                   # build and analyze a small network
ecoanalyst summary data/network_data.json         # node and edge counts by kind
ecoanalyst hotspots examples/demo_network.json --top 3
ecoanalyst convert data/network_data.json out.json --to flowgraph
```

`convert` reads any supported format and writes the native format (`--to v3`, the default) or a flow graph. Use `-` as the output path to write to stdout.

## REST API

```bash
pip install -e ".[api]"
uvicorn ecoanalyst.api:app --reload
```

The REST server is a local development server. It has no authentication, keeps networks in memory, and loses them when it stops. Do not expose it to a network you do not control. Earlier versions asked for an `X-User-Id` header; it was never authentication, and the server now ignores it.

Browsers on other origins are refused by default. To allow a front end on another origin, list it in `ECOANALYST_CORS_ORIGINS`, separated by commas:

```bash
ECOANALYST_CORS_ORIGINS=http://localhost:5173 uvicorn ecoanalyst.api:app
```

The interactive API reference is at `http://localhost:8000/docs` while the server runs. [docs/integration.md](docs/integration.md) has curl examples for each endpoint.

## MCP server

The MCP server exposes the library to MCP clients such as Claude Desktop over stdio. Install the `mcp` extra, then add the server to the client configuration (for Claude Desktop, `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "ecoanalyst": {
      "command": "ecoanalyst-mcp"
    }
  }
}
```

If the client does not see your virtual environment's `PATH`, give the full path, for example `/path/to/ecoanalyst/.venv/bin/ecoanalyst-mcp`. Configurations that run `python mcp_server.py` from a clone keep working, as long as that Python has networkx, numpy, pydantic, and mcp installed.

The tools are `create_network`, `list_networks`, `get_network`, `delete_network`, `add_node`, `add_edge`, `calculate_waste`, `find_minimum_waste_path`, `identify_hotspots`, `compare_paths`, `export_flow_graph`, and `import_flow_graph`. Networks live in the server process and are lost when it exits; use `export_flow_graph` to keep one.

## Legacy modules

The 1.x modules live in `ecoanalyst.legacy` for existing scripts:

| Module | Contents |
|--------|----------|
| `ecoanalyst.legacy.network_model` | `WasteNetwork`, a directed graph with a loss rate on each node and edge |
| `ecoanalyst.legacy.advanced_network` | `AdvancedWasteNetwork`, typed node and edge classes, and pluggable loss functions |
| `ecoanalyst.legacy.causal_analysis` | `WasteCausalNetwork`, Bayesian linear regression of loss on its drivers (needs `bayes`) |
| `ecoanalyst.legacy.network_viz` | matplotlib helpers for `AdvancedWasteNetwork` (needs `viz`) |

`WasteCausalNetwork` fits linear models with PyMC. Its results describe associations in the data you give it. The names `get_causal_effect` and `discover_causal_structure` are kept for compatibility: the first multiplies weights that you attach to graph edges, and the second joins columns whose pairwise correlation passes a significance threshold. Neither estimates cause and effect.

The scripts in `examples/` show both the current API (`ecoanalyst_demo.py`) and the legacy modules. They write their output to `examples/output/`.

## Whitepaper

`whitepaper/main.pdf` (source in `whitepaper/main.tex`) sets out the graph model, loss functions, and regression approach behind the 1.x modules. Its path cost sums per-edge losses; the library now compounds them as described above.

## License

MIT. See [LICENSE](LICENSE).
