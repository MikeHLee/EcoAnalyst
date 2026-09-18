"""Efficiency modes: ignore (default), conversion, retention."""

import pytest

from ecoanalyst import EconomicAnalysis, EcosystemNetwork


def mill_chain(mode="ignore", mill_mode=None):
    """farm (w 0.05) -> edge (w 0.01) -> mill (w 0.02, efficiency 0.75)."""
    net = EcosystemNetwork(name="mill", efficiency_mode=mode)
    farm = net.add_node("producer", "Farm", "Farm", node_id="farm",
                        properties={"capacity": {"value": 1000, "unit": "kg"}, "waste_rate": 0.05})
    mill_props = {"capacity": {"value": 1000, "unit": "kg"}, "waste_rate": 0.02, "efficiency": 0.75}
    if mill_mode:
        mill_props["efficiency_mode"] = mill_mode
    mill = net.add_node("processor", "Mill", "Mill", node_id="mill", properties=mill_props)
    net.add_edge(farm, mill, "inventory", {"max_rate": {"value": 1000, "unit": "kg"}, "waste_rate": 0.01})
    return net


def test_ignore_mode_matches_waste_only():
    net = mill_chain("ignore")
    t = net.calculate_path_transfer(["farm", "mill"])
    assert t["conversion_fraction"] == 0.0
    assert t["delivered_fraction"] == pytest.approx(0.95 * 0.99 * 0.98)


def test_conversion_mode_hand_computed():
    net = mill_chain("conversion")
    t = net.calculate_path_transfer(["farm", "mill"])
    # 1 -> 0.95 -> 0.9405 -> 0.92169 after mill waste -> x0.75 = 0.6912675
    assert t["waste_fraction"] == pytest.approx(0.05 + 0.0095 + 0.01881)
    assert t["conversion_fraction"] == pytest.approx(0.92169 * 0.25)
    assert t["delivered_fraction"] == pytest.approx(0.6912675)
    total = t["delivered_fraction"] + t["waste_fraction"] + t["conversion_fraction"]
    assert total == pytest.approx(1.0)
    # conversion is not waste
    waste, _ = net.calculate_path_waste(["farm", "mill"])
    assert waste == pytest.approx(0.07831)


def test_component_override_beats_network_default():
    net = mill_chain("ignore", mill_mode="conversion")
    assert net.calculate_path_transfer(["farm", "mill"])["delivered_fraction"] == pytest.approx(0.6912675)


def test_conversion_is_reported_not_priced():
    net = mill_chain("conversion")
    cost = EconomicAnalysis(net).calculate_path_cost(
        ["farm", "mill"], pricing_data={"Farm": 2.0, "Mill": 3.0}, input_quantity=1000)
    assert cost["delivered_quantity"] == pytest.approx(691.2675)
    assert cost["total_converted"] == pytest.approx(230.4225)
    assert cost["total_waste"] == pytest.approx(78.31)
    # farm 50 kg and edge 9.5 kg at the farm price, mill 18.81 kg at the mill price
    assert cost["total_cost"] == pytest.approx(50 * 2 + 9.5 * 2 + 18.81 * 3)


def test_retention_mode_uses_efficiency_as_pass_through():
    net = EcosystemNetwork(efficiency_mode="retention")
    a = net.add_node("producer", "Plant", "Plant", node_id="a", properties={"efficiency": 0.9})
    b = net.add_node("consumer", "Load", "Load", node_id="b")
    net.add_edge(a, b, "energy", {"efficiency": 0.94})
    waste, breakdown = net.calculate_path_waste(["a", "b"])
    assert waste == pytest.approx(1 - 0.9 * 0.94)
    assert breakdown["node:a"] == pytest.approx(0.1)
    assert breakdown["edge:a->b"] == pytest.approx(0.06)


def test_retention_mode_accepts_agreeing_fields_and_rejects_conflicts():
    net = EcosystemNetwork(efficiency_mode="retention")
    net.add_node("producer", "Plant", "Agrees", node_id="ok",
                 properties={"efficiency": 0.9, "waste_rate": 0.1})
    net.add_node("producer", "Plant", "Conflicts", node_id="bad",
                 properties={"efficiency": 0.9, "waste_rate": 0.05})
    assert net.node_transfer("ok").waste_rate == pytest.approx(0.1)
    with pytest.raises(ValueError, match="retention mode"):
        net.node_transfer("bad")
    issues = net.check_loss_config()
    assert [i["level"] for i in issues] == ["error"]
    assert "Conflicts" in issues[0]["component"]


def test_conversion_mode_warns_about_double_counting():
    net = EcosystemNetwork(efficiency_mode="conversion")
    net.add_node("handler", "Store", "Store", properties={"efficiency": 0.97, "waste_rate": 0.03})
    issues = net.check_loss_config()
    assert [i["level"] for i in issues] == ["warning"]


def test_routing_maximizes_delivery_under_conversion():
    # Route via the 50% converter wastes nothing but delivers 0.5; the direct
    # edge wastes 30% and delivers 0.7. The router must take the direct edge.
    net = EcosystemNetwork(efficiency_mode="conversion")
    for nid in ("s", "p", "t"):
        net.add_node("handler", "X", nid, node_id=nid)
    net.nodes["p"].properties.efficiency = 0.5
    net.add_edge("s", "p", "inventory")
    net.add_edge("p", "t", "inventory")
    net.add_edge("s", "t", "inventory", {"waste_rate": 0.3})
    path, waste, _ = net.find_minimum_waste_path("s", "t")
    assert path == ["s", "t"]
    assert waste == pytest.approx(0.3)


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        EcosystemNetwork(efficiency_mode="sometimes")
    with pytest.raises(ValueError):
        mill_chain().set_efficiency_mode("sometimes")


@pytest.mark.parametrize("roundtrip", ["native", "flowgraph"])
def test_modes_survive_serialization(roundtrip):
    net = mill_chain("retention", mill_mode="conversion")
    if roundtrip == "native":
        again = EcosystemNetwork.from_dict(net.to_dict())
    else:
        again = EcosystemNetwork.from_flow_graph(net.to_flow_graph())
    assert again.efficiency_mode == "retention"
    assert again.nodes["mill"].properties.efficiency_mode == "conversion"
    assert again.calculate_path_transfer(["farm", "mill"]) == net.calculate_path_transfer(["farm", "mill"])
