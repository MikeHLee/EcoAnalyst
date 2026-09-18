"""The causal layer: equations, sampling, interventions, fitting, identification, coupling."""

import json
from pathlib import Path

import networkx as nx
import numpy as np
import pytest

from ecoanalyst import CausalModel, EcosystemNetwork, compare, simulate
from ecoanalyst.causal import (
    Binding, best_route_delivered, inverse_link, link, path_delivered, path_waste, waste_cost,
)

SCHEMA = Path(__file__).resolve().parent.parent / "docs" / "flowgraph.schema.json"


# -- links and construction ---------------------------------------------------

@pytest.mark.parametrize("kind,value", [("continuous", -3.2), ("rate", 0.05), ("positive", 250.0)])
def test_link_round_trip(kind, value):
    assert inverse_link(kind, link(kind, value)) == pytest.approx(value)


def test_link_rejects_out_of_range():
    with pytest.raises(ValueError):
        link("rate", 1.5)
    with pytest.raises(ValueError):
        link("positive", 0.0)


def test_construction_rules():
    m = CausalModel()
    m.add_variable("temp")
    with pytest.raises(ValueError, match="before its children"):
        m.add_variable("spoil", kind="rate", parents=["humidity"])
    with pytest.raises(ValueError, match="non-parents"):
        m.add_variable("spoil", kind="rate", parents=["temp"], coefficients={"other": 1.0})
    with pytest.raises(ValueError, match="duplicate"):
        m.add_variable("temp")
    with pytest.raises(ValueError, match="needs a 'rate' variable"):
        m.add_variable("cap", kind="continuous", binds="node:n1:waste_rate")
    with pytest.raises(ValueError, match="field must be one of"):
        m.add_variable("cap2", kind="positive", binds="node:n1:colour")
    assert Binding.parse("edge:e1:max_rate") == Binding(target="edge", id="e1", field="max_rate")


# -- sampling and interventions ------------------------------------------------

def chain():
    """temp -> spoil (rate) ; temp -> demand ; spoil and demand independent otherwise."""
    m = CausalModel()
    m.add_variable("temp", intercept=20.0, noise_sd=3.0, unit="C")
    m.add_variable("spoil", kind="rate", parents=["temp"],
                   intercept=link("rate", 0.05) - 0.1 * 20, coefficients={"temp": 0.1}, noise_sd=0.2)
    m.add_variable("demand", kind="positive", parents=["temp"],
                   intercept=np.log(100) - 0.02 * 20, coefficients={"temp": 0.02}, noise_sd=0.1)
    m.add_variable("stockout", kind="binary", parents=["demand"],
                   intercept=-10.0, coefficients={"demand": 0.08})
    return m


def test_sample_moments_and_supports():
    s = chain().sample(20000, seed=1)
    assert s["temp"].mean() == pytest.approx(20.0, abs=0.1)
    assert s["temp"].std() == pytest.approx(3.0, rel=0.03)
    assert np.all((s["spoil"] > 0) & (s["spoil"] < 1))
    assert np.all(s["demand"] > 0)
    assert set(np.unique(s["stockout"])) <= {0.0, 1.0}
    # median of spoil at mean temp is the stated 5%
    assert np.median(s["spoil"]) == pytest.approx(0.05, rel=0.05)


def test_do_moves_descendants_only_and_shares_noise():
    m = chain()
    base = m.sample(5000, seed=7)
    hot = m.sample(5000, seed=7, do={"temp": 30.0})
    assert np.all(hot["temp"] == 30.0)
    assert hot["spoil"].mean() > base["spoil"].mean()
    # Common random numbers: with temp fixed at a value, spoil's own noise is the same draw.
    hot2 = m.sample(5000, seed=7, do={"temp": 30.0})
    assert np.array_equal(hot["spoil"], hot2["spoil"])
    # Intervening on spoil leaves its non-descendants untouched, draw for draw.
    cut = m.sample(5000, seed=7, do={"spoil": 0.01})
    assert np.array_equal(cut["temp"], base["temp"])
    assert np.array_equal(cut["demand"], base["demand"])


def test_do_value_checked():
    with pytest.raises(ValueError, match="between 0 and 1"):
        chain().sample(10, do={"spoil": 2.0})
    with pytest.raises(ValueError, match="0 or 1"):
        chain().sample(10, do={"stockout": 0.5})
    with pytest.raises(ValueError, match="unknown causal variable"):
        chain().sample(10, do={"nope": 1.0})


# -- fitting -------------------------------------------------------------------

def synthetic(n, seed=0):
    rng = np.random.default_rng(seed)
    temp = rng.normal(20, 3, n)
    spoil = 1 / (1 + np.exp(-(-4.0 + 0.12 * temp + rng.normal(0, 0.3, n))))
    flag = (rng.random(n) < 1 / (1 + np.exp(-(-6.0 + 0.25 * temp)))).astype(float)
    return {"temp": temp, "spoil": spoil, "flag": flag}


def fit_model():
    m = CausalModel()
    m.add_variable("temp")
    m.add_variable("spoil", kind="rate", parents=["temp"])
    m.add_variable("flag", kind="binary", parents=["temp"])
    return m


def test_fit_recovers_known_coefficients():
    m = fit_model()
    used = m.fit(synthetic(4000))
    assert used == {"temp": 4000, "spoil": 4000, "flag": 4000}
    temp = m.variables["temp"].posterior
    assert temp.mean[0] == pytest.approx(20.0, abs=0.2)
    assert temp.noise_sd() == pytest.approx(3.0, rel=0.05)
    spoil = m.variables["spoil"].posterior
    assert spoil.mean == pytest.approx([-4.0, 0.12], abs=0.08)
    assert spoil.noise_sd() == pytest.approx(0.3, rel=0.05)
    flag = m.variables["flag"].posterior
    assert flag.family == "laplace"
    assert flag.mean == pytest.approx([-6.0, 0.25], abs=0.8)


def test_posterior_narrows_with_more_data():
    small, large = fit_model(), fit_model()
    small.fit(synthetic(100, seed=1))
    large.fit(synthetic(5000, seed=1))
    sd = lambda m: np.sqrt(np.diag(np.asarray(m.variables["spoil"].posterior.scale)))[1]
    assert sd(large) < sd(small) / 4


def test_fit_skips_missing_columns_and_rows():
    m = fit_model()
    data = synthetic(500)
    data["temp"][:50] = np.nan
    del data["flag"]
    used = m.fit(data)
    assert used == {"temp": 450, "spoil": 450}
    assert m.variables["flag"].posterior is None


def test_sampling_uses_posterior_uncertainty():
    m = fit_model()
    m.fit(synthetic(30, seed=3))
    wide = m.sample(4000, seed=0)["spoil"]
    narrow = m.sample(4000, seed=0, parameter_uncertainty=False)["spoil"]
    assert wide.std() > narrow.std()


# -- identification ------------------------------------------------------------

def confounded(observed_z=True):
    m = CausalModel()
    m.add_variable("z", observed=observed_z)
    m.add_variable("x", parents=["z"])
    m.add_variable("m", parents=["x"])
    m.add_variable("y", parents=["m", "z"])
    return m


def test_backdoor_adjustment():
    m = confounded()
    assert m.adjustment_set("x", "y") == {"z"}
    assert m.is_valid_adjustment("x", "y", {"z"})
    assert not m.is_valid_adjustment("x", "y", set())
    assert not m.is_valid_adjustment("x", "y", {"z", "m"})  # m is a descendant of x
    assert m.adjustment_set("m", "y") == {"x"} or m.adjustment_set("m", "y") == {"z"}


def test_no_adjustment_when_confounder_unobserved():
    m = confounded(observed_z=False)
    assert m.adjustment_set("x", "y") is None
    assert not m.is_valid_adjustment("x", "y", {"z"})


def test_gml_export_round_trips():
    g = nx.parse_gml(chain().to_gml())
    assert set(g.edges) == {("temp", "spoil"), ("temp", "demand"), ("demand", "stockout")}


# -- coupling to the flow network ------------------------------------------------

def cold_chain():
    net = EcosystemNetwork(name="cold chain")
    for nid, kind in (("farm", "producer"), ("store", "handler"), ("shop", "consumer")):
        net.add_node(kind, nid.title(), nid.title(), node_id=nid,
                     properties={"capacity": {"value": 1000, "unit": "kg"}, "waste_rate": 0.02})
    net.add_edge("farm", "store", "inventory", {"waste_rate": 0.01}, edge_id="e1")
    net.add_edge("store", "shop", "inventory", {"waste_rate": 0.01}, edge_id="e2")
    net.add_edge("farm", "shop", "inventory", {"waste_rate": 0.12}, edge_id="direct")
    m = CausalModel()
    m.add_variable("ambient", intercept=20.0, noise_sd=2.0, unit="C")
    m.add_variable("uptime", kind="rate", intercept=link("rate", 0.95), noise_sd=0.3)
    m.add_variable("store_spoilage", kind="rate", parents=["ambient", "uptime"],
                   intercept=link("rate", 0.03) - 0.15 * 20 + 6.0 * 0.95,
                   coefficients={"ambient": 0.15, "uptime": -6.0}, noise_sd=0.2,
                   binds="node:store:waste_rate")
    net.causal = m
    return net


def test_simulation_drives_bound_parameter_and_restores_it():
    net = cold_chain()
    res = simulate(net, {"loss": path_waste(["farm", "store", "shop"]), "spoil": "store_spoilage"},
                   n=2000, seed=3)
    assert net.nodes["store"].properties.waste_rate == 0.02  # restored
    expected = 1 - (1 - 0.02) * (1 - 0.01) * (1 - res.variables["store_spoilage"]) * (1 - 0.01) * (1 - 0.02)
    assert np.allclose(res.outcomes["loss"], expected)
    assert np.array_equal(res.outcomes["spoil"], res.variables["store_spoilage"])
    summary = res.summary()
    assert summary["loss"]["p05"] < summary["loss"]["p50"] < summary["loss"]["p95"]


def test_intervention_effect_has_the_right_sign():
    net = cold_chain()
    route = path_delivered(["farm", "store", "shop"])
    eff = compare(net, route, do_a={"uptime": 0.99}, do_b={"uptime": 0.80}, n=2000, seed=11)
    assert eff["effect"] > 0          # better uptime delivers more
    assert eff["share_a_greater"] == 1.0  # shared noise: better in every sample
    assert eff["mean_a"] > eff["mean_b"]


def test_rerouting_responds_to_interventions():
    net = cold_chain()
    best = best_route_delivered("farm", "shop")
    fine = simulate(net, {"d": best}, n=500, seed=2, do={"uptime": 0.99}).outcomes["d"]
    broken = simulate(net, {"d": best}, n=500, seed=2, do={"uptime": 0.05}).outcomes["d"]
    # With the store failing, the direct 12%-loss edge caps the damage.
    direct = (1 - 0.02) * (1 - 0.12) * (1 - 0.02)
    assert np.all(broken >= direct - 1e-12)
    assert fine.mean() > broken.mean()


def test_negative_control_unbound_model_leaves_outcome_constant():
    net = cold_chain()
    net.causal.variables["store_spoilage"].binds = None
    res = simulate(net, {"loss": path_waste(["farm", "store", "shop"])}, n=200, seed=0)
    assert np.ptp(res.outcomes["loss"]) == 0.0


def test_bad_bindings_rejected():
    net = cold_chain()
    net.causal.add_variable("ghost", kind="rate", binds="edge:nope:waste_rate")
    with pytest.raises(ValueError, match="not in the network"):
        simulate(net, {"w": waste_cost()}, n=5)


@pytest.mark.parametrize("fmt", ["native", "flowgraph"])
def test_causal_model_survives_serialization(fmt):
    net = cold_chain()
    net.causal.fit({"ambient": np.random.default_rng(0).normal(20, 2, 300)})
    data = net.to_dict() if fmt == "native" else net.to_flow_graph()
    again = EcosystemNetwork.from_dict(json.loads(json.dumps(data)))
    assert again.causal.to_dict() == net.causal.to_dict()
    a = simulate(net, {"l": path_waste(["farm", "store", "shop"])}, n=300, seed=5).outcomes["l"]
    b = simulate(again, {"l": path_waste(["farm", "store", "shop"])}, n=300, seed=5).outcomes["l"]
    assert np.array_equal(a, b)


def test_flow_graph_with_causal_section_matches_schema():
    jsonschema = pytest.importorskip("jsonschema")
    net = cold_chain()
    net.causal.fit({"ambient": np.random.default_rng(0).normal(20, 2, 50)})
    schema = json.loads(SCHEMA.read_text())
    jsonschema.validate(json.loads(json.dumps(net.to_flow_graph())), schema)


# -- per-sample interventions, fixed parameter draws, prediction ------------------

def test_do_accepts_one_value_per_sample():
    m = chain()
    temps = np.linspace(10, 30, 400)
    s = m.sample(400, do={"temp": temps}, seed=0)
    assert np.array_equal(s["temp"], temps)
    # hotter rows spoil more on average
    assert s["spoil"][temps > 25].mean() > s["spoil"][temps < 15].mean()
    with pytest.raises(ValueError, match="expected a scalar or 400 values"):
        m.sample(400, do={"temp": temps[:10]})
    with pytest.raises(ValueError, match="between 0 and 1"):
        m.sample(3, do={"spoil": [0.1, 0.2, 1.5]})


def test_parameter_draw_is_reused_across_calls():
    m = fit_model()
    m.fit(synthetic(40, seed=4))
    draw = m.draw_parameters(300, seed=9)
    a = m.sample(300, seed=1, parameters=draw)
    b = m.sample(300, seed=2, parameters=draw)
    # Same coefficients per row, different noise: the conditional medians match.
    temps = np.full(300, 25.0)
    pa = m.sample(300, seed=1, parameters=draw, do={"temp": temps})
    pb = m.sample(300, seed=1, parameters=draw, do={"temp": temps})
    assert np.array_equal(pa["spoil"], pb["spoil"])
    assert not np.array_equal(a["spoil"], b["spoil"])
    beta = draw.coefficients["spoil"]
    assert beta.shape == (300, 2) and beta[:, 1].std() > 0  # uncertainty kept per row
    with pytest.raises(ValueError, match="drawn for n=300"):
        m.sample(10, parameters=draw)


def test_predict_matches_the_equation():
    m = chain()
    temp = np.array([15.0, 20.0, np.nan])
    pred = m.predict({"temp": temp})
    expected = inverse_link("rate", link("rate", 0.05) + 0.1 * (temp - 20.0))
    assert np.allclose(pred["spoil"][:2], expected[:2])
    assert np.isnan(pred["spoil"][2])
    assert "stockout" not in pred  # its parent (demand) is not a column
    assert pred["temp"] == pytest.approx(np.full(3, 20.0))
    only = m.predict({"temp": temp}, variables=["spoil"])
    assert set(only) == {"spoil"}
