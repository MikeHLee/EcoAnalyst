import subprocess
import sys

import pytest

from ecoanalyst.legacy.advanced_network import (
    AdvancedWasteNetwork,
    EndConsumer,
    FlowType,
    FoodHandler,
    InitialProducer,
    InventoryEdge,
    CurrencyEdge,
    StaticWaste,
    TimeBasedWaste,
)
from ecoanalyst.legacy.network_model import WasteNetwork


def test_legacy_imports_do_not_pull_optional_dependencies():
    code = (
        "import sys, ecoanalyst.legacy, ecoanalyst.legacy.network_model, "
        "ecoanalyst.legacy.advanced_network, ecoanalyst.legacy.causal_analysis, "
        "ecoanalyst.legacy.network_viz\n"
        "heavy = sorted(m for m in sys.modules if m.split('.')[0] in "
        "('pymc', 'arviz', 'pandas', 'scipy', 'matplotlib'))\n"
        "print(heavy)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


def test_waste_network_compounds():
    net = WasteNetwork()
    net.add_node("a", "grower", 100, 0.1)
    net.add_node("b", "store", 100, 0.2)
    net.add_edge("a", "b", 100, 0.0, 1.0)
    total, breakdown = net.calculate_path_waste(["a", "b"])
    assert total == pytest.approx(0.28)
    assert breakdown["node_a"] == 0.1


def test_waste_network_routes_by_retained_fraction():
    net = WasteNetwork()
    for node in ("s", "m", "t"):
        net.add_node(node, "distributor", 100, 0.0)
    net.add_edge("s", "m", 100, 0.5, 1.0)
    net.add_edge("m", "t", 100, 0.5, 1.0)
    net.add_edge("s", "t", 100, 0.9, 1.0)
    path, loss = net.find_minimum_waste_path("s", "t")
    assert path == ["s", "m", "t"]
    assert loss == pytest.approx(0.75)


def advanced_network():
    net = AdvancedWasteNetwork()
    farm = InitialProducer("farm")
    farm.set_waste_function(TimeBasedWaste(0.02, 0.001))
    hub = FoodHandler("hub")
    hub.set_waste_function(StaticWaste(0.1))
    shop = EndConsumer("shop")
    for node in (farm, hub, shop):
        net.add_node(node)
    first = InventoryEdge(capacity=100)
    first.set_waste_function(StaticWaste(0.05))
    net.add_edge("farm", "hub", first)
    net.add_edge("hub", "shop", InventoryEdge(capacity=100))
    unrelated = InventoryEdge(capacity=100)
    unrelated.set_waste_function(StaticWaste(0.5))
    net.add_edge("farm", "shop", unrelated)
    net.add_edge("shop", "farm", CurrencyEdge())
    return net


def test_advanced_path_waste_only_counts_edges_on_the_path():
    net = advanced_network()
    total, breakdown = net.calculate_path_waste(["farm", "hub", "shop"], time=10)
    # farm 0.02 + 0.001 * 10 = 0.03, hub 0.1, farm->hub 0.05; the 0.5 edge is off the path.
    assert total == pytest.approx(1 - 0.97 * 0.9 * 0.95)
    assert breakdown["farm"] == pytest.approx(0.03)
    assert "farm->shop" not in breakdown


def test_advanced_minimum_path_uses_matching_edge_type():
    paths = advanced_network().find_minimum_path(FlowType.FOOD)
    assert paths[0][0] == ["farm", "hub", "shop"]
    assert paths[0][1] == pytest.approx(0.05)


def test_bayesian_regression_recovers_simulated_coefficients():
    pytest.importorskip("pymc")
    import numpy as np
    import pandas as pd

    from ecoanalyst.legacy.causal_analysis import WasteCausalNetwork

    rng = np.random.default_rng(0)
    x = rng.normal(size=(300, 2))
    y = 1.0 + 2.0 * x[:, 0] - 0.5 * x[:, 1] + rng.normal(scale=0.1, size=300)
    model = WasteCausalNetwork()
    model.add_data(pd.DataFrame({"a": x[:, 0], "b": x[:, 1], "y": y}))
    result = model.fit_regression("y", ["a", "b"], samples=300)

    # Features are standardized, so coefficients are per standard deviation.
    sd = x.std(axis=0)
    assert result.coefficients["a"][0] == pytest.approx(2.0 * sd[0], rel=0.05)
    assert result.coefficients["b"][0] == pytest.approx(-0.5 * sd[1], rel=0.1)
    assert result.r2_score > 0.99
