import asyncio

import pytest

pytest.importorskip("mcp")

from ecoanalyst import mcp_server as tools  # noqa: E402

EXPECTED_TOOLS = {
    "create_network", "list_networks", "get_network", "delete_network",
    "add_node", "add_edge", "calculate_waste", "find_minimum_waste_path",
    "identify_hotspots", "compare_paths", "export_flow_graph", "import_flow_graph",
    "add_causal_variable", "simulate_intervention", "compare_interventions",
    "causal_adjustment_set",
}


@pytest.fixture(autouse=True)
def clean_store():
    tools.NETWORKS.clear()
    yield
    tools.NETWORKS.clear()


def build_routing_network():
    net = tools.create_network("route test", network_type="supply_chain")["network_id"]
    s = tools.add_node(net, "producer", "Farm", "S")["node_id"]
    m = tools.add_node(net, "handler", "Hub", "M")["node_id"]
    t = tools.add_node(net, "consumer", "Shop", "T", waste_rate=0.1)["node_id"]
    tools.add_edge(net, s, m, transport_waste_rate=0.5)
    tools.add_edge(net, m, t, "inventory_flow", transport_waste_rate=0.5)
    tools.add_edge(net, s, t, transport_waste_rate=0.9)
    tools.add_edge(net, t, s, "currency")
    return net, s, m, t


def test_tool_functions_end_to_end():
    net, s, m, t = build_routing_network()

    assert tools.list_networks()["total_count"] == 1
    assert len(tools.get_network(net)["nodes"]) == 3

    best = tools.find_minimum_waste_path(net, s, t, edge_kinds=["inventory"])
    assert best["path"] == [s, m, t]
    assert best["path_names"] == ["S", "M", "T"]
    assert best["total_waste"] == pytest.approx(1 - 0.5 * 0.5 * 0.9)

    ranked = tools.compare_paths(net, s, t, edge_kinds=["inventory"])
    assert [p["path_names"] for p in ranked["paths"]] == [["S", "M", "T"], ["S", "T"]]

    hotspots = tools.identify_hotspots(net, top_n=1)
    assert hotspots["hotspots"][0]["waste_rate"] == 0.9

    waste = tools.calculate_waste(net, pricing_data={"Shop": 3.0})
    assert waste["node_count"] == 1

    fg = tools.export_flow_graph(net)
    copy = tools.import_flow_graph(fg)
    assert copy["node_count"] == 3 and copy["edge_count"] == 4
    assert tools.export_flow_graph(copy["network_id"])["flows"] == fg["flows"]

    assert tools.delete_network(net) == {"deleted": net}
    with pytest.raises(ValueError, match="Network not found"):
        tools.get_network(net)


def test_tool_input_errors():
    net = tools.create_network("errors")["network_id"]
    with pytest.raises(ValueError):
        tools.add_node(net, "Not A Kind", "X", "x")
    a = tools.add_node(net, "producer", "A", "a")["node_id"]
    with pytest.raises(ValueError, match="Target node not found"):
        tools.add_edge(net, a, "missing")


def test_server_registers_every_tool():
    server = tools.build_server()
    registered = asyncio.run(server.list_tools())
    assert {tool.name for tool in registered} == EXPECTED_TOOLS
    assert len(tools.TOOLS) == len(EXPECTED_TOOLS)


def test_server_reports_tool_errors_with_message():
    server = tools.build_server()
    with pytest.raises(Exception) as info:
        asyncio.run(server.call_tool("get_network", {"network_id": "nope"}))
    assert "Network not found: nope" in str(info.value)


def test_causal_tools():
    net, s, m, t = build_routing_network()
    tools.add_causal_variable(net, "heat", intercept=20.0, noise_sd=2.0)
    tools.add_causal_variable(
        net, "hub_loss", kind="rate", parents=["heat"], intercept=-6.0,
        coefficients={"heat": 0.2}, noise_sd=0.1, binds=f"node:{m}:waste_rate",
    )
    with pytest.raises(ValueError, match="not in the network"):
        tools.add_causal_variable(net, "ghost", kind="rate", binds="node:missing:waste_rate")
    assert "ghost" not in tools.NETWORKS[net].causal.variables

    sim = tools.simulate_intervention(net, "path_delivered", path=[s, m, t], n=300, seed=1,
                                      edge_kinds=["inventory"])
    assert set(sim["summary"]) >= {"path_delivered", "heat", "hub_loss"}
    eff = tools.compare_interventions(net, "path_delivered", {"heat": 15.0}, {"heat": 35.0},
                                      path=[s, m, t], n=300, edge_kinds=["inventory"])
    assert eff["effect"] > 0
    with pytest.raises(ValueError, match="path is required"):
        tools.simulate_intervention(net, "path_waste", n=10)
    assert tools.causal_adjustment_set(net, "heat", "hub_loss")["adjustment_set"] == []
