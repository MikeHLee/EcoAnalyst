import copy
import json

import pytest

from ecoanalyst import FLOW_GRAPH_FORMAT, EcosystemNetwork, detect_format
from ecoanalyst.legacy.network_model import WasteNetwork
from helpers import REPO_ROOT, add, link

DEMO_V2 = REPO_ROOT / "examples" / "demo_network.json"
DATA_V1 = REPO_ROOT / "data" / "network_data.json"
SCHEMA = REPO_ROOT / "docs" / "flowgraph.schema.json"


def rich_network():
    n = EcosystemNetwork(name="rich", description="all optional fields", network_type="energy")
    add(n, "plant", "producer", rate=0.02, geometry={"type": "Point", "coordinates": [-122.4, 37.8]},
        series_ref="s3://bucket/plant.parquet#output_mw", metadata={"owner": "utility"},
        financials={"capex": {"value": 1e6}, "opex_annual": {"value": 5e4},
                    "salvage_value": {"value": 1e5}},
        operations={"operating_hours": 20, "constraints": ["no night output"]},
        position_x=1.5, position_y=-2.0)
    add(n, "sub", "handler", rate=0.01)
    add(n, "battery", "storage_bank")  # custom kind
    link(n, "plant", "sub", 0.06, kind="energy", series_ref="sensor:line-7",
         constraints=["thermal limit"], metadata={"voltage_kv": 230})
    link(n, "sub", "plant", kind="control", polarity="negative")
    link(n, "sub", "battery", 0.03, kind="energy")
    return n


def test_native_json_round_trip(tmp_path):
    n = rich_network()
    path = tmp_path / "net.json"
    n.save_to_json(str(path))
    loaded = EcosystemNetwork.load_from_json(str(path))
    assert loaded.to_dict() == n.to_dict()
    assert json.loads(path.read_text())["edges"][1]["polarity"] == "negative"


def test_load_v2_demo_file_with_legacy_kind_names():
    raw = json.loads(DEMO_V2.read_text())
    assert {e["relationship_type"] for e in raw["edges"]} == {"inventory_flow", "service_flow"}
    assert detect_format(raw) == "native"

    n = EcosystemNetwork.load_from_json(str(DEMO_V2))
    assert len(n.nodes) == 5 and len(n.edges) == 4
    assert {e.relationship_type for e in n.edges.values()} == {"inventory", "service"}
    assert n.network_id == raw["network_id"]
    farm = next(x for x in n.nodes.values() if x.node_class == "OrganicFarm")
    shop = next(x for x in n.nodes.values() if x.node_class == "Retailer")
    path, loss, _ = n.find_minimum_waste_path(farm.node_id, shop.node_id, edge_kinds=["inventory"])
    assert len(path) == 4
    assert loss == pytest.approx(1 - 0.95 * 0.97 * 0.98 * 0.99 * 0.96 * 0.98 * 0.92)


def test_v1_file_loads_with_legacy_waste_network():
    net = WasteNetwork.load_from_json(str(DATA_V1))
    assert net.graph.number_of_nodes() == 6 and net.graph.number_of_edges() == 5
    path, loss = net.find_minimum_waste_path("growerA", "store")
    assert path == ["growerA", "distributor1", "store"]
    assert loss == pytest.approx(1 - 0.95 * 0.98 * 0.97 * 0.985 * 0.92)


def test_v1_file_converts_to_current_format():
    raw = json.loads(DATA_V1.read_text())
    assert detect_format(raw) == "waste_network_v1"
    n = EcosystemNetwork.load_from_json(str(DATA_V1))
    assert n.nodes["growerA"].node_type == "producer"
    assert n.nodes["growerA"].node_class == "grower"
    assert n.nodes["distributor2"].node_type == "handler"
    assert n.nodes["store"].node_type == "consumer"
    assert n.edges["growerA->distributor1"].flow.waste_rate == 0.02
    assert n.edges["growerA->distributor1"].relationship_type == "inventory"

    legacy = WasteNetwork.load_from_json(str(DATA_V1))
    for source, target in [("growerA", "store"), ("growerB", "store")]:
        path, loss, _ = n.find_minimum_waste_path(source, target)
        legacy_path, legacy_loss = legacy.find_minimum_waste_path(source, target)
        assert path == legacy_path
        assert loss == pytest.approx(legacy_loss)


def test_detect_format_errors():
    with pytest.raises(ValueError):
        detect_format({"something": "else"})
    with pytest.raises(ValueError, match="format"):
        detect_format({"actors": [], "flows": []})


def test_flow_graph_shape():
    fg = rich_network().to_flow_graph()
    assert fg["format"] == FLOW_GRAPH_FORMAT and fg["version"] == 1
    plant = next(a for a in fg["actors"] if a["id"] == "plant")
    assert plant["kind"] == "producer" and plant["class"] == "Plant"
    assert plant["geometry"]["type"] == "Point"
    assert plant["series_ref"].startswith("s3://")
    assert plant["attrs"]["position"] == {"x": 1.5, "y": -2.0}
    assert set(plant["attrs"]) == {"properties", "financials", "operations", "position", "metadata"}
    sub = next(a for a in fg["actors"] if a["id"] == "sub")
    assert "geometry" not in sub and "series_ref" not in sub and "financials" not in sub["attrs"]

    line = next(f for f in fg["flows"] if f["src"] == "plant")
    assert line["kind"] == "energy" and line["tgt"] == "sub"
    assert line["weight"] == 1000 and line["unit"] == "kg/day"
    assert line["polarity"] == "positive"
    assert line["attrs"]["flow"]["waste_rate"] == 0.06
    control = next(f for f in fg["flows"] if f["kind"] == "control")
    assert control["polarity"] == "negative"


def test_flow_graph_round_trip_is_lossless():
    original = rich_network()
    fg = original.to_flow_graph()
    restored = EcosystemNetwork.from_flow_graph(copy.deepcopy(fg))
    assert restored.to_flow_graph() == fg
    assert [x.to_dict() for x in restored.nodes.values()] == [x.to_dict() for x in original.nodes.values()]
    assert [x.to_dict() for x in restored.edges.values()] == [x.to_dict() for x in original.edges.values()]
    assert EcosystemNetwork.from_dict(fg).to_flow_graph() == fg


def test_flow_graph_import_rules():
    fg = {
        "format": FLOW_GRAPH_FORMAT,
        "version": 1,
        "actors": [
            {"id": "a", "kind": "producer", "name": "A"},
            {"id": "b", "kind": "consumer", "name": "B", "class": "Shop"},
        ],
        "flows": [
            {"id": "f", "kind": "inventory_flow", "src": "a", "tgt": "b", "weight": 42, "unit": "t/day",
             "attrs": {"flow": {"max_rate": {"value": 1, "unit": "x"}, "waste_rate": 0.1}}},
        ],
    }
    n = EcosystemNetwork.from_flow_graph(fg)
    assert n.nodes["a"].node_class == "producer"  # class falls back to kind
    edge = n.edges["f"]
    assert edge.relationship_type == "inventory"
    assert edge.flow.max_rate.value == 42 and edge.flow.max_rate.unit == "t/day"
    assert edge.flow.waste_rate == 0.1
    assert edge.polarity == "positive"

    bad = copy.deepcopy(fg)
    bad["flows"][0]["tgt"] = "zzz"
    with pytest.raises(ValueError, match="unknown tgt"):
        EcosystemNetwork.from_flow_graph(bad)
    with pytest.raises(ValueError, match="version"):
        EcosystemNetwork.from_flow_graph({**fg, "version": 2})


def test_flow_graph_export_matches_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)

    for network in (rich_network(), EcosystemNetwork.load_from_json(str(DEMO_V2)),
                    EcosystemNetwork.load_from_json(str(DATA_V1))):
        errors = list(validator.iter_errors(network.to_flow_graph()))
        assert errors == []

    broken = rich_network().to_flow_graph()
    broken["actors"][0]["kind"] = "Not A Kind"
    del broken["flows"][0]["unit"]
    assert len(list(validator.iter_errors(broken))) == 2
