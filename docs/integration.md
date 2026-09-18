# Integration guide

EcoAnalyst can be used from Python, from the shell, over HTTP, from an MCP client, or through JSON files that other programs read and write. Each section below is self-contained. All of them share one data model: nodes with a kind, a capacity, and a loss rate, joined by edges with a flow kind, a maximum rate, and a loss rate.

## Python

Install the package (`pip install -e .` in a clone) and import from `ecoanalyst`.

```python
from ecoanalyst import EconomicAnalysis, EcosystemNetwork

net = EcosystemNetwork(name="Grid feeder", network_type="energy")
plant = net.add_node("producer", "SolarFarm", "Solar farm", node_id="solar",
                     properties={"capacity": {"value": 100, "unit": "MW"}, "waste_rate": 0.02})
sub = net.add_node("handler", "Substation", "Substation", node_id="sub",
                   properties={"capacity": {"value": 150, "unit": "MW"}, "waste_rate": 0.01})
town = net.add_node("consumer", "Load", "Town load", node_id="town",
                    properties={"capacity": {"value": 80, "unit": "MW"}})
net.add_edge("solar", "sub", "energy", {"max_rate": {"value": 95, "unit": "MW"}, "waste_rate": 0.06})
net.add_edge("sub", "town", "energy", {"max_rate": {"value": 90, "unit": "MW"}, "waste_rate": 0.03})

path, loss, breakdown = net.find_minimum_waste_path("solar", "town", edge_kinds=["energy"])
delivered = EconomicAnalysis(net).calculate_path_cost(path, input_quantity=95)["delivered_quantity"]
```

Useful calls:

| Call | Returns |
|------|---------|
| `net.calculate_path_waste(path, edge_kinds=None)` | compounded loss fraction and per-component rates |
| `net.find_minimum_waste_path(src, tgt, edge_kinds=None)` | best path, its loss fraction, and its breakdown |
| `net.find_all_paths(src, tgt, max_paths=10, edge_kinds=None)` | up to `max_paths` paths, lowest loss first |
| `EconomicAnalysis(net).calculate_path_cost(path, pricing_data, input_quantity=None)` | quantity delivered and cost of each loss along a path |
| `EconomicAnalysis(net).calculate_waste_cost(pricing_data)` | capacity-based loss estimate for every component |
| `EconomicAnalysis(net).identify_hotspots(top_n, metric)` | components ranked by `waste_rate` or `waste_quantity` |
| `EconomicAnalysis(net).calculate_total_cost_of_ownership(years, discount_rate)` | capex, installation, opex NPV, salvage PV, and the total |
| `net.save_to_json(path)` / `EcosystemNetwork.load_from_json(path)` | native JSON; loading also accepts flow graphs and 1.x files |
| `net.to_flow_graph()` / `EcosystemNetwork.from_flow_graph(data)` | the exchange format described below |

Node and flow kinds can be given as strings (`"producer"`, `"energy"`), as `NodeType` and `RelationshipType` members, or as custom lowercase identifiers. Methods raise `ValueError` for unknown node IDs, malformed kinds, and paths with no eligible edge.

## Command line

The `ecoanalyst` command works on JSON files and needs no server.

```bash
ecoanalyst demo
ecoanalyst summary network.json
ecoanalyst hotspots network.json --top 5 --metric waste_quantity
ecoanalyst convert old_waste_network.json network.json
ecoanalyst convert network.json network.flowgraph.json --to flowgraph
ecoanalyst convert network.json - --to flowgraph | jq '.flows | length'
```

`summary` and `hotspots` print JSON, so their output can be piped to other tools. The input format is detected. A command exits with status 1 and a message on stderr if the file is missing or not a network.

## REST API

Install the `api` extra and start the server:

```bash
pip install -e ".[api]"
uvicorn ecoanalyst.api:app --port 8000
```

The server is for local use. It has no authentication, keeps networks in memory, and forgets them when it stops. Cross-origin browser requests are refused unless the origin is listed in `ECOANALYST_CORS_ORIGINS` (comma-separated), so a browser front end served from, say, `http://localhost:5173` needs:

```bash
ECOANALYST_CORS_ORIGINS=http://localhost:5173 uvicorn ecoanalyst.api:app --port 8000
```

### Endpoints

| Method | Path | Body or query | Purpose |
|--------|------|---------------|---------|
| GET | `/health` | | status and version |
| POST | `/networks` | `{"name", "description", "network_type"}` | create a network |
| GET | `/networks` | `?limit=` | list networks |
| GET | `/networks/{id}` | | full network, native format |
| PUT | `/networks/{id}` | same as create | rename or retype |
| DELETE | `/networks/{id}` | | delete |
| POST | `/networks/{id}/nodes` | node fields (see below) | add a node |
| GET | `/networks/{id}/nodes/{node_id}` | | one node |
| DELETE | `/networks/{id}/nodes/{node_id}` | | delete a node and its edges |
| POST | `/networks/{id}/edges` | edge fields (see below) | add an edge |
| DELETE | `/networks/{id}/edges/{edge_id}` | | delete an edge |
| GET | `/networks/{id}/optimize-paths` | `?source_node_id=&target_node_id=&edge_kinds=` | minimum-loss path |
| GET | `/networks/{id}/hotspots` | `?top_n=&metric=` | ranked components |
| POST | `/networks/{id}/calculate-waste` | optional `{"NodeClass": price}` | capacity-based loss cost |
| POST | `/networks/{id}/calculate-tco` | `?years=&discount_rate=` | total cost of ownership |
| GET | `/networks/{id}/flow-graph` | | export as a flow graph |
| POST | `/networks/flow-graph` | a flow-graph document | import as a new network |

A node body has `node_type`, `node_class`, `name`, and `properties` (with `capacity`), plus optional `financials`, `operations`, `position_x`, `position_y`, `geometry`, `series_ref`, and `metadata`. An edge body has `source_node_id`, `target_node_id`, `relationship_type`, and `flow` (with `max_rate`), plus optional `polarity`, `series_ref`, `constraints`, and `metadata`. The generated reference at `http://localhost:8000/docs` lists every field.

Errors use standard status codes: 404 for an unknown network, node, or edge; 400 for an edge whose endpoints do not exist, an unknown hotspot metric, or an invalid flow graph; 422 for a body that fails validation, such as a malformed kind.

### A session with curl

The commands below use [jq](https://jqlang.github.io/jq/) to pull IDs out of responses.

```bash
BASE=http://localhost:8000
JSON='Content-Type: application/json'

NET=$(curl -s -X POST $BASE/networks -H "$JSON" \
  -d '{"name": "Produce chain", "network_type": "supply_chain"}' | jq -r .network_id)

FARM=$(curl -s -X POST $BASE/networks/$NET/nodes -H "$JSON" -d '{
  "node_type": "producer", "node_class": "Farm", "name": "Valley Farm",
  "properties": {"capacity": {"value": 1000, "unit": "kg/day"}, "waste_rate": 0.05}}' | jq -r .node_id)

STORE=$(curl -s -X POST $BASE/networks/$NET/nodes -H "$JSON" -d '{
  "node_type": "handler", "node_class": "ColdStorage", "name": "Cold Store",
  "properties": {"capacity": {"value": 5000, "unit": "kg"}, "waste_rate": 0.02}}' | jq -r .node_id)

SHOP=$(curl -s -X POST $BASE/networks/$NET/nodes -H "$JSON" -d '{
  "node_type": "consumer", "node_class": "Retailer", "name": "Corner Grocer",
  "properties": {"capacity": {"value": 800, "unit": "kg/day"}, "waste_rate": 0.08}}' | jq -r .node_id)

edge() {  # source target kind max_rate waste_rate
  curl -s -X POST $BASE/networks/$NET/edges -H "$JSON" -d "{
    \"source_node_id\": \"$1\", \"target_node_id\": \"$2\", \"relationship_type\": \"$3\",
    \"flow\": {\"max_rate\": {\"value\": $4, \"unit\": \"kg/day\"}, \"waste_rate\": $5}}" | jq -r .edge_id
}
edge $FARM $STORE inventory 900 0.01
edge $STORE $SHOP inventory 800 0.01
edge $FARM $SHOP inventory 300 0.15
edge $SHOP $FARM currency 2000 null

curl -s "$BASE/networks/$NET/optimize-paths?source_node_id=$FARM&target_node_id=$SHOP&edge_kinds=inventory" \
  | jq '{path, total_waste}'
curl -s "$BASE/networks/$NET/hotspots?top_n=3" | jq '.hotspots[] | {type, waste_rate}'
curl -s -X POST $BASE/networks/$NET/calculate-waste -H "$JSON" \
  -d '{"Farm": 2.0, "ColdStorage": 2.5, "Retailer": 4.0}' | jq .total_waste_cost

curl -s $BASE/networks/$NET/flow-graph > chain.flowgraph.json
curl -s -X POST $BASE/networks/flow-graph -H "$JSON" --data @chain.flowgraph.json | jq .
```

The path query returns the route through the cold store with `total_waste` of about 0.1605, and the waste query returns 734.0.

## MCP

Install the `mcp` extra (`pip install -e ".[mcp]"`). The `ecoanalyst-mcp` command runs the server on stdio. A client configuration looks like this:

```json
{
  "mcpServers": {
    "ecoanalyst": {
      "command": "/path/to/ecoanalyst/.venv/bin/ecoanalyst-mcp"
    }
  }
}
```

| Tool | Arguments |
|------|-----------|
| `create_network` | `name`, `network_type`, `description` |
| `list_networks` | `limit` |
| `get_network` | `network_id` |
| `delete_network` | `network_id` |
| `add_node` | `network_id`, `node_type`, `node_class`, `name`, `capacity_value`, `capacity_unit`, `waste_rate`, `efficiency`, `count`, `metadata` |
| `add_edge` | `network_id`, `source_node_id`, `target_node_id`, `flow_type`, `max_rate_value`, `max_rate_unit`, `transport_waste_rate`, `transport_time_hours`, `polarity` |
| `calculate_waste` | `network_id`, `pricing_data` |
| `find_minimum_waste_path` | `network_id`, `source_node_id`, `target_node_id`, `edge_kinds` |
| `identify_hotspots` | `network_id`, `top_n`, `metric` |
| `compare_paths` | `network_id`, `source_node_id`, `target_node_id`, `max_paths`, `edge_kinds` |
| `export_flow_graph` | `network_id` |
| `import_flow_graph` | `flow_graph` |

The server also serves each network as the resource `network://{network_id}`. Networks exist only while the server runs. To keep one, call `export_flow_graph` and save the result; to restore it, pass that document to `import_flow_graph`.

The tool functions are ordinary Python functions in `ecoanalyst.mcp_server`, so they can also be called directly in tests or scripts.

## Flow-graph JSON

The flow graph is the format to use when another program needs to read or produce a network. Its structure is plain: a list of `actors` and a list of `flows`, each with an `id`, a `kind`, and a few common fields, and the full EcoAnalyst payload under `attrs`. [flow_graph_format.md](flow_graph_format.md) documents every field, and [flowgraph.schema.json](flowgraph.schema.json) is a JSON Schema for validation.

A program that does not use EcoAnalyst can read what it needs directly. For example, to list each flow with its loss rate:

```bash
jq -r '.flows[] | [.src, .tgt, .kind, (.attrs.flow.waste_rate // 0)] | @tsv' chain.flowgraph.json
```

A program that writes flow graphs only has to provide `id`, `kind`, and `name` for each actor and `id`, `kind`, `src`, `tgt`, `weight`, and `unit` for each flow; everything else has defaults. Loss rates go in `attrs.properties.waste_rate` (actors) and `attrs.flow.waste_rate` (flows).
