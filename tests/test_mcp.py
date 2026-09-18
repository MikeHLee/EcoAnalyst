import asyncio

import pytest

pytest.importorskip("mcp")

from ecoanalyst import mcp_server as tools  # noqa: E402

EXPECTED_TOOLS = {
    "create_network", "list_networks", "get_network", "delete_network",
    "add_node", "add_edge", "calculate_waste", "find_minimum_waste_path",
    "identify_hotspots", "compare_paths", "export_flow_graph", "import_flow_graph",
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
