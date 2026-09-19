import pytest

from ecoanalyst import EconomicAnalysis, EcosystemNetwork
from helpers import add, link


def cascade_network():
    n = EcosystemNetwork()
    add(n, "farm", "producer", rate=0.1, capacity=1000, node_class="Farm")
    add(n, "shop", "consumer", rate=0.2, capacity=5000, node_class="Store")
    link(n, "farm", "shop", 0.05, max_rate=2000)
    return n


def test_path_cost_cascades_from_first_node_capacity():
    result = EconomicAnalysis(cascade_network()).calculate_path_cost(
        ["farm", "shop"], pricing_data={"Farm": 2.0, "Store": 4.0}
    )
    # 1000 in: farm loses 100 ($200), transit loses 45 of 900 ($90 at the farm
    # price), shop loses 171 of 855 ($684). 684 arrive.
    assert [step["waste"] for step in result["breakdown"]] == pytest.approx([100, 45, 171])
    assert [step["cost"] for step in result["breakdown"]] == pytest.approx([200, 90, 684])
    assert [step["type"] for step in result["breakdown"]] == ["node", "edge", "node"]
    assert result["input_quantity"] == pytest.approx(1000)
    assert result["delivered_quantity"] == pytest.approx(684)
    assert result["total_waste"] == pytest.approx(316)
    assert result["total_cost"] == pytest.approx(974)
    assert result["total_waste"] / result["input_quantity"] == pytest.approx(
        cascade_network().calculate_path_waste(["farm", "shop"])[0]
    )


def test_path_cost_with_explicit_input_and_count():
    n = cascade_network()
    n.nodes["farm"].properties.count = 3
    analysis = EconomicAnalysis(n)
    assert analysis.calculate_path_cost(["farm", "shop"])["input_quantity"] == pytest.approx(3000)
    result = analysis.calculate_path_cost(["farm", "shop"], input_quantity=10)
    assert result["delivered_quantity"] == pytest.approx(6.84)
    assert result["total_cost"] == pytest.approx(3.16)  # default price 1.0


def test_path_cost_uses_lowest_loss_edge_of_allowed_kind():
    n = cascade_network()
    link(n, "farm", "shop", 0.5, kind="currency")
    analysis = EconomicAnalysis(n)
    assert analysis.calculate_path_cost(["farm", "shop"])["delivered_quantity"] == pytest.approx(684)
    only_currency = analysis.calculate_path_cost(["farm", "shop"], edge_kinds=["currency"])
    assert only_currency["delivered_quantity"] == pytest.approx(1000 * 0.9 * 0.5 * 0.8)


def test_path_cost_rejects_bad_paths():
    analysis = EconomicAnalysis(cascade_network())
    with pytest.raises(ValueError):
        analysis.calculate_path_cost([])
    with pytest.raises(ValueError):
        analysis.calculate_path_cost(["farm", "nowhere"])
    with pytest.raises(ValueError):
        analysis.calculate_path_cost(["shop", "farm"])


def test_waste_cost_is_capacity_based():
    result = EconomicAnalysis(cascade_network()).calculate_waste_cost(
        pricing_data={"Farm": 2.0, "Store": 4.0}
    )
    # Each component at its own capacity: 1000*0.1, 5000*0.2, 2000*0.05.
    assert result["total_waste_quantity"] == pytest.approx(100 + 1000 + 100)
    assert result["total_waste_cost"] == pytest.approx(200 + 4000 + 200)
    assert result["node_count"] == 2 and result["edge_count"] == 1


def tco_network():
    n = EcosystemNetwork()
    n.add_node("producer", "Plant", "p", financials={
        "capex": {"value": 100_000}, "opex_annual": {"value": 10_000},
        "installation": {"value": 5_000}, "salvage_value": {"value": 20_000},
    })
    n.add_node("handler", "Depot", "d", financials={
        "capex": {"value": 50_000}, "opex_annual": {"value": 5_000},
    })
    n.add_node("consumer", "Shop", "s")  # no financials
    return n


def test_total_cost_of_ownership():
    tco = EconomicAnalysis(tco_network()).calculate_total_cost_of_ownership(years=10, discount_rate=0.05)
    annuity = (1 - 1.05 ** -10) / 0.05
    assert tco["capex"] == pytest.approx(150_000)
    assert tco["installation"] == pytest.approx(5_000)
    assert tco["opex_annual"] == pytest.approx(15_000)
    assert tco["opex_npv"] == pytest.approx(15_000 * annuity)
    assert tco["opex_npv"] == pytest.approx(115_826.02, abs=0.01)
    assert tco["salvage_value_pv"] == pytest.approx(20_000 / 1.05 ** 10)
    assert tco["total_tco"] == pytest.approx(258_547.75, abs=0.01)


def test_total_cost_of_ownership_without_discounting():
    tco = EconomicAnalysis(tco_network()).calculate_total_cost_of_ownership(years=4, discount_rate=0.0)
    assert tco["opex_npv"] == pytest.approx(60_000)
    assert tco["total_tco"] == pytest.approx(150_000 + 5_000 + 60_000 - 20_000)


def test_hotspots_ranking(chain):
    analysis = EconomicAnalysis(chain)
    by_rate = analysis.identify_hotspots(top_n=2)
    assert [h["waste_rate"] for h in by_rate["hotspots"]] == [0.3, 0.2]
    assert by_rate["total_analyzed"] == 6

    by_qty = analysis.identify_hotspots(top_n=1, metric="waste_quantity")
    assert by_qty["hotspots"][0]["waste_quantity"] == pytest.approx(300)

    with pytest.raises(ValueError):
        analysis.identify_hotspots(metric="waste_cost")


def test_hotspot_quantity_includes_count():
    n = EcosystemNetwork()
    n.add_node("handler", "Truck", "fleet",
               properties={"capacity": {"value": 100, "unit": "kg"}, "waste_rate": 0.1, "count": 5})
    spot = EconomicAnalysis(n).identify_hotspots(metric="waste_quantity")["hotspots"][0]
    assert spot["waste_quantity"] == pytest.approx(50)


def test_compare_scenarios(chain):
    improved = EcosystemNetwork.from_dict(chain.to_dict())
    improved.nodes["shop"].properties.waste_rate = 0.1
    result = EconomicAnalysis(chain).compare_scenarios(chain, improved)
    assert result["waste_reduction"] == pytest.approx(1000 * 0.1)
    assert result["savings"] > 0
