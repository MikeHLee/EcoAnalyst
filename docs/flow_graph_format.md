# Flow-graph exchange format

The flow graph is a JSON format for moving an EcoAnalyst network between programs. It lists the network's actors (nodes) and flows (edges) with a small set of common fields, and keeps the full typed payload of each element under `attrs`, so an export can be read back without loss.

`EcosystemNetwork.to_flow_graph()` writes it, `EcosystemNetwork.from_flow_graph()` reads it, and `EcosystemNetwork.load_from_json()` recognizes it by its `format` field. The JSON Schema is [flowgraph.schema.json](flowgraph.schema.json).

## Example

```json
{
  "format": "ecoanalyst.flowgraph",
  "version": 1,
  "name": "Produce chain",
  "description": "",
  "network_type": "supply_chain",
  "actors": [
    {
      "id": "farm",
      "kind": "producer",
      "name": "Valley Farm",
      "class": "Farm",
      "geometry": {"type": "Point", "coordinates": [-121.65, 36.68]},
      "attrs": {
        "properties": {
          "capacity": {"value": 1000.0, "unit": "kg/day"},
          "efficiency": 1.0,
          "lifetime_years": 10,
          "waste_rate": 0.05,
          "degradation_rate": null,
          "count": 1
        },
        "position": {"x": 0.0, "y": 0.0},
        "metadata": {}
      }
    },
    {
      "id": "shop",
      "kind": "consumer",
      "name": "Corner Grocer",
      "class": "Retailer",
      "attrs": {
        "properties": {"capacity": {"value": 800.0, "unit": "kg/day"}, "waste_rate": 0.08},
        "position": {"x": 0.0, "y": 0.0},
        "metadata": {}
      }
    }
  ],
  "flows": [
    {
      "id": "farm_to_shop",
      "kind": "inventory",
      "src": "farm",
      "tgt": "shop",
      "polarity": "positive",
      "weight": 300.0,
      "unit": "kg/day",
      "series_ref": "sensors/truck-12.csv",
      "attrs": {
        "flow": {
          "max_rate": {"value": 300.0, "unit": "kg/day"},
          "min_rate": null,
          "efficiency": 1.0,
          "direction": "unidirectional",
          "transport_time": {"value": 3.0, "unit": "hours"},
          "waste_rate": 0.15
        },
        "constraints": [],
        "metadata": {}
      }
    }
  ]
}
```

## Top level

| Field | Required | Meaning |
|-------|----------|---------|
| `format` | yes | Always `"ecoanalyst.flowgraph"`. |
| `version` | yes | Always `1` for this version of the format. Readers reject other values. |
| `name` | no | Network name. |
| `description` | no | Free text. |
| `network_type` | no | Free text such as `supply_chain` or `energy`. |
| `settings` | no | `{"efficiency_mode": "ignore" \| "conversion" \| "retention"}`, the network's default efficiency mode. Missing means `ignore`. |
| `actors` | yes | List of actors. |
| `flows` | yes | List of flows. |
| `causal` | no | `{"variables": [...]}`, the causal graph that runs beside the network. See below. Written only when the network has one. |

## Actors

| Field | Required | Meaning |
|-------|----------|---------|
| `id` | yes | Unique within the document. |
| `kind` | yes | Node kind, matching `^[a-z][a-z0-9_]*$`. See the node kind table in the README. |
| `name` | yes | Display name. |
| `class` | no | Specific class such as `Farm` or `Substation`. Defaults to the kind on import. |
| `geometry` | no | GeoJSON-like object with a string `type`, for example a `Point`. Written only when set. |
| `series_ref` | no | String that points at a time series stored elsewhere (a path, URL, or key). EcoAnalyst stores it and does not read it. Written only when set. |
| `attrs.properties` | no | `NodeProperties`: `capacity` (`value`, `unit`), `efficiency` (or null), `efficiency_mode` (or null for the network default), `lifetime_years`, `waste_rate`, `degradation_rate`, `count`. A missing capacity becomes 100 units/day on import. |
| `attrs.financials` | no | `NodeFinancials`: `capex`, `opex_annual`, `installation`, `waste_cost_per_unit`, `salvage_value`, each `{"value", "currency"}`. Written only when set. |
| `attrs.operations` | no | `NodeOperations`: `storage_days`, `temperature_range`, `humidity_range`, `annual_throughput`, `operating_hours`, `constraints`. Written only when set. |
| `attrs.position` | no | Drawing position `{"x", "y"}`. |
| `attrs.metadata` | no | Free-form object. |

## Flows

| Field | Required | Meaning |
|-------|----------|---------|
| `id` | yes | Unique within the document. Import generates one if it is missing. |
| `kind` | yes | Flow kind, matching `^[a-z][a-z0-9_]*$`. The 2.x names such as `inventory_flow` are accepted and stored in short form. |
| `src`, `tgt` | yes | Actor IDs. Import fails if either is unknown. |
| `polarity` | no | `"positive"` (default) or `"negative"`. Stored and exported; the loss calculations do not use it. |
| `weight`, `unit` | yes | The flow's maximum rate and its unit. On import these set `max_rate` and take precedence over `attrs.flow.max_rate`. |
| `series_ref` | no | Same meaning as for actors. Written only when set. |
| `attrs.flow` | no | `EdgeFlow`: `max_rate`, `min_rate`, `efficiency`, `efficiency_mode`, `direction`, `transport_time`, `waste_rate`. |
| `attrs.constraints` | no | List of strings. |
| `attrs.metadata` | no | Free-form object. |

## Causal variables

Each entry of `causal.variables` is one variable, listed parents first:

| Field | Required | Meaning |
|-------|----------|---------|
| `name` | yes | Identifier (`^[A-Za-z_][A-Za-z0-9_]*$`), unique in the graph. |
| `kind` | no | `continuous` (default), `rate`, `positive`, or `binary`. |
| `parents` | no | Names of earlier variables. |
| `intercept`, `coefficients`, `noise_sd` | no | The equation on the kind's link scale. `coefficients` maps parent names to numbers. |
| `observed` | no | `false` for a variable that exists but cannot be measured. Default `true`. |
| `unit`, `description` | no | Free text. |
| `binds` | no | `{"target": "node" \| "edge", "id", "field"}`: the network parameter this variable drives. |
| `posterior` | no | Written by `fit()`: `family`, `terms`, `mean`, `scale`, `a`, `b`, `n_obs`. |

Import fails if a binding points at an actor or flow that is not in the document.

## Round trip

For any network `n`, `EcosystemNetwork.from_flow_graph(n.to_flow_graph())` has the same nodes and edges as `n`, field for field, and exporting it again gives an identical document. The network's ID and timestamps are not part of the format; an import gets a new ID.

## Validating a file

```python
import json
import jsonschema

schema = json.load(open("docs/flowgraph.schema.json"))
jsonschema.validate(json.load(open("chain.flowgraph.json")), schema)
```

The schema checks structure and field types. It cannot check that `src` and `tgt` refer to actors in the same document; `from_flow_graph()` does that.
