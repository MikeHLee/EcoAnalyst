"""
cli.py: The ``ecoanalyst`` command.

Subcommands (all work offline):

- ``demo``: build a small supply chain in memory and print an analysis.
- ``summary FILE``: counts of nodes and edges by kind, as JSON.
- ``hotspots FILE [--top N] [--metric M]``: highest-loss nodes and edges, as JSON.
- ``convert IN OUT [--to v3|flowgraph]``: rewrite a network file.

FILE and IN may be native JSON (3.x or 2.x), flow-graph JSON, or 1.x
WasteNetwork JSON; the format is detected. OUT may be ``-`` for stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from ._version import __version__
from .analysis import HOTSPOT_METRICS, EconomicAnalysis
from .models import NodeType, RelationshipType
from .network import EcosystemNetwork


def build_demo_network() -> EcosystemNetwork:
    """A farm that can ship to a retailer directly or through a cold store."""
    network = EcosystemNetwork(
        name="Demo produce chain",
        description="Farm to retailer, direct or through cold storage",
        network_type="supply_chain",
    )
    farm = network.add_node(
        NodeType.PRODUCER, "Farm", "Valley Farm",
        properties={"capacity": {"value": 1000, "unit": "kg/day"}, "waste_rate": 0.05},
        financials={"capex": {"value": 100000}, "opex_annual": {"value": 20000}},
        node_id="farm",
    )
    store = network.add_node(
        NodeType.HANDLER, "ColdStorage", "Cold Store",
        properties={"capacity": {"value": 5000, "unit": "kg"}, "waste_rate": 0.02},
        financials={"capex": {"value": 250000}, "opex_annual": {"value": 30000}},
        node_id="cold_store",
    )
    retailer = network.add_node(
        NodeType.CONSUMER, "Retailer", "Corner Grocer",
        properties={"capacity": {"value": 800, "unit": "kg/day"}, "waste_rate": 0.08},
        node_id="retailer",
    )
    kg_day = {"unit": "kg/day"}
    network.add_edge(farm, store, RelationshipType.INVENTORY,
                     {"max_rate": {"value": 900, **kg_day}, "waste_rate": 0.01}, edge_id="farm_to_store")
    network.add_edge(store, retailer, RelationshipType.INVENTORY,
                     {"max_rate": {"value": 800, **kg_day}, "waste_rate": 0.01}, edge_id="store_to_retailer")
    network.add_edge(farm, retailer, RelationshipType.INVENTORY,
                     {"max_rate": {"value": 300, **kg_day}, "waste_rate": 0.15}, edge_id="farm_to_retailer")
    network.add_edge(retailer, farm, RelationshipType.CURRENCY,
                     {"max_rate": {"value": 2000, "unit": "USD/day"}}, edge_id="retailer_pays_farm")
    return network


def _load(path: str) -> EcosystemNetwork:
    return EcosystemNetwork.load_from_json(path)


def _write_json(data, out: str) -> None:
    text = json.dumps(data, indent=2)
    if out == "-":
        sys.stdout.write(text + "\n")
    else:
        with open(out, "w") as f:
            f.write(text + "\n")


def cmd_demo(args: argparse.Namespace) -> int:
    network = build_demo_network()
    analysis = EconomicAnalysis(network)
    pricing = {"Farm": 2.0, "ColdStorage": 2.5, "Retailer": 4.0}

    summary = network.summary()
    print(f"{network.name}: {summary['node_count']} nodes, {summary['edge_count']} edges")
    print(f"  node kinds: {summary['node_types']}")
    print(f"  flow kinds: {summary['edge_types']}")

    print("\nRoutes from farm to retailer (inventory flows, lowest loss first):")
    for path, loss in network.find_all_paths("farm", "retailer", edge_kinds=["inventory"]):
        names = " -> ".join(network.nodes[n].name for n in path)
        print(f"  {names}: {loss:.2%} lost")

    path, loss, _ = network.find_minimum_waste_path("farm", "retailer", edge_kinds=["inventory"])
    cost = analysis.calculate_path_cost(path, pricing_data=pricing, edge_kinds=["inventory"])
    print(f"\nBest route loses {loss:.2%}. Sending {cost['input_quantity']:.0f} {cost['unit']}:")
    for step in cost["breakdown"]:
        label = step.get("name") or f"{step['source']} -> {step['target']}"
        print(f"  {label}: {step['waste']:.1f} lost, ${step['cost']:.2f}")
    print(f"  delivered {cost['delivered_quantity']:.1f}, loss cost ${cost['total_cost']:.2f}")

    print("\nHotspots by loss rate:")
    for spot in analysis.identify_hotspots(top_n=3)["hotspots"]:
        label = spot.get("name") or f"{spot['source']} -> {spot['target']}"
        print(f"  {label}: {spot['waste_rate']:.0%}")

    tco = analysis.calculate_total_cost_of_ownership(years=10, discount_rate=0.05)
    print(f"\n10-year total cost of ownership at 5%: ${tco['total_tco']:,.0f}")
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    _write_json(_load(args.file).summary(), "-")
    return 0


def cmd_hotspots(args: argparse.Namespace) -> int:
    network = _load(args.file)
    result = EconomicAnalysis(network).identify_hotspots(top_n=args.top, metric=args.metric)
    _write_json(result, "-")
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    network = _load(args.input)
    data = network.to_flow_graph() if args.to == "flowgraph" else network.to_dict()
    _write_json(data, args.output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ecoanalyst",
        description="Analyze losses and costs in flow networks.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("demo", help="build and analyze a small example network")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("summary", help="print node and edge counts by kind")
    p.add_argument("file", help="network JSON file")
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("hotspots", help="print the highest-loss nodes and edges")
    p.add_argument("file", help="network JSON file")
    p.add_argument("--top", type=int, default=5, help="number of hotspots (default 5)")
    p.add_argument("--metric", choices=HOTSPOT_METRICS, default="waste_rate",
                   help="ranking metric (default waste_rate)")
    p.set_defaults(func=cmd_hotspots)

    p = sub.add_parser("convert", help="rewrite a network file in another format")
    p.add_argument("input", help="input JSON file (native, flow graph, or 1.x WasteNetwork)")
    p.add_argument("output", help="output file, or - for stdout")
    p.add_argument("--to", choices=("v3", "flowgraph"), default="v3",
                   help="output format (default v3, the native format)")
    p.set_defaults(func=cmd_convert)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        print(f"ecoanalyst: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
