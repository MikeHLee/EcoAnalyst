# Changelog

## 3.0.0 (unreleased)

First release on PyPI (`pip install ecoanalyst`).

### Breaking changes

- Flow kinds are stored in short form: `inventory`, `energy`, `currency`, `information`, `service`, `waste`, `control`. `RelationshipType.INVENTORY_FLOW.value` is now `"inventory"`, and every JSON output uses the short names. The 2.x names (`inventory_flow`, `control_signal` and the rest) are still accepted as input, including in 2.x JSON files.
- `node_type` and `relationship_type` hold plain normalized strings rather than enum members. Custom kinds that match `^[a-z][a-z0-9_]*$` are accepted; anything else raises a validation error.
- Path losses compound as `1 - (1 - w1)(1 - w2)...` instead of being added. `calculate_path_waste`, `find_minimum_waste_path`, and `find_all_paths` return different numbers and can pick a different route. The legacy `WasteNetwork` and `AdvancedWasteNetwork` classes compound the same way.
- `calculate_path_waste` uses the lowest-loss edge between each pair of consecutive nodes (optionally limited with `edge_kinds`) instead of the first edge found. It raises `ValueError` for an unknown node or a pair with no eligible edge, where 2.x skipped the gap.
- `efficiency` defaults to `None` instead of `1.0`, and the default `ignore` mode keeps it out of the calculations as before.
- `find_minimum_waste_path` and `find_all_paths` raise `ValueError` for unknown node IDs. `find_all_paths` leaves out paths through a component whose loss rate is 1 and no longer lists the same path once per parallel edge.
- `EconomicAnalysis.calculate_path_cost` follows a quantity along the path, starting from `input_quantity` (default: first node capacity × count). 2.x priced each component's loss from that component's own capacity, so totals differ.
- `identify_hotspots` includes node `count` in `waste_quantity`, matching `calculate_waste_cost`, and raises `ValueError` for an unknown metric. 2.x accepted any metric name and sorted by rate.
- The 1.x modules moved from `src/` into the `ecoanalyst.legacy` package: `network_model`, `advanced_network`, `causal_analysis`, and `network_viz`. Import them as, for example, `from ecoanalyst.legacy.network_model import WasteNetwork`.
- The core install depends only on networkx (3.3 or later), numpy, and pydantic. pandas, scipy, and matplotlib moved to the `viz` and `bayes` extras.
- The REST server refuses cross-origin requests unless the origin is listed in `ECOANALYST_CORS_ORIGINS`, and it no longer allows credentials. The `X-User-Id` and `X-Tenant-Id` headers are no longer required and are ignored.
- The MCP server runs on `EcosystemNetwork` and `EconomicAnalysis` instead of its own copy of the logic. Tool results use the library's field names, `get_network` returns the native JSON format, and failures are reported as MCP tool errors instead of `{"error": ...}` results.

### Fixed

- The `ecoanalyst` console script declared in `setup.py` pointed at a module that did not exist. The command is now implemented.
- `calculate_total_cost_of_ownership` recomputed the annual opex sum inside the discount loop and kept an unused `total_opex`. It now sums opex once; results are unchanged, and the result includes `opex_annual`.
- Legacy `AdvancedWasteNetwork.calculate_path_waste` added the loss of every inventory edge in the network at each hop of the path. It now uses the edges between consecutive path nodes.
- Legacy `AdvancedWasteNetwork.find_minimum_path` compared `FlowType` with `EdgeType` and never found an edge. It now maps flow types to edge types.
- Legacy `set_waste_function` wrapped `StaticWaste`, `TimeBasedWaste`, and `MultiVariableWaste` objects as regression results and failed on first use, so `examples/advanced_ecosystem.py` and `examples/network_visualization.py` crashed. Loss function objects are now used directly, and `TimeBasedWaste` defaults `time` to 0.
- Legacy `WasteCausalNetwork` plots failed on edges added without an `effect_size`.
- Network timestamps are timezone-aware UTC.

### Added

- A causal layer, `ecoanalyst.causal`: a `CausalModel` of variables with linear equations on an identity, logit, or log link, bound to node and edge parameters. `simulate()` and `compare()` estimate the effect of interventions (`do`) on flow outcomes with shared random draws; `fit()` updates the equations from data (normal-inverse-gamma posterior, or a Laplace approximation for binary variables); `adjustment_set()` and `is_valid_adjustment()` apply the back-door criterion; `to_gml()` exports the graph for DoWhy. The model is saved in both JSON formats, and four MCP tools expose it. See `examples/causal_cold_chain.py`.
- Efficiency modes. A network's `efficiency_mode` (`ignore`, `conversion`, or `retention`), which a node or edge can override, sets how `efficiency` enters the loss calculations. `calculate_path_transfer()` splits a unit of input into delivered, wasted, and converted fractions, and `check_loss_config()` reports conflicting or doubled settings.
- A portable flow-graph JSON format: `EcosystemNetwork.to_flow_graph()` and `from_flow_graph()`, documented in `docs/flow_graph_format.md` with a JSON Schema in `docs/flowgraph.schema.json`.
- `EcosystemNetwork.load_from_json()` and `from_dict()` detect the format: native (3.x and 2.x), flow graph, or 1.x `WasteNetwork`.
- The `ecoanalyst` command with `demo`, `summary`, `hotspots`, and `convert`.
- The `ecoanalyst-mcp` command, and the `export_flow_graph` and `import_flow_graph` MCP tools. The server works with both the 1.x and 2.x MCP Python SDKs.
- REST endpoints `GET /networks/{id}/flow-graph` and `POST /networks/flow-graph`, and an `edge_kinds` filter on `/optimize-paths`.
- Optional node fields `geometry` and `series_ref`, and optional edge fields `polarity` and `series_ref`.
- `edge_kinds` filters on the path methods, `select_path_edges()`, `compound_loss()`, `normalize_node_kind()`, `normalize_edge_kind()`, and short `RelationshipType` member names such as `RelationshipType.INVENTORY`.
- A pytest suite and a GitHub Actions workflow for Python 3.10, 3.11, and 3.12.
- `docs/integration.md`, covering the Python API, the command line, the REST API with curl, MCP, and the flow-graph format.

### Changed

- Packaging uses `pyproject.toml`, and the version is defined once in `ecoanalyst/_version.py`. A GitHub Actions workflow publishes releases to PyPI.
- The whitepaper describes compounded losses, the efficiency modes, and the causal layer, and presents the 1.x regression as an associational analysis.
- The docstrings in `ecoanalyst.legacy.causal_analysis` describe what the code does: Bayesian linear regression of loss on its drivers. `discover_causal_structure` is documented as a correlation-threshold heuristic and `get_causal_effect` as a product of user-supplied edge weights. Names are unchanged.
- Example scripts import the installed package and write their files to `examples/output/`.

### Removed

- `setup.py` and `requirements.txt`, replaced by `pyproject.toml`.
- `admin_cli.py`. `docs/integration.md` shows the same REST calls with curl.
- Generated images, the LaTeX `.aux` file, and regression output that had been committed.

## 2.0.0 and earlier

See the git history.
