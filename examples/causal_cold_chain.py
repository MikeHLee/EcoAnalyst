"""
A causal graph beside a cold chain.

The flow network: a farm ships produce either through a packhouse and a cold
store to a retailer, or straight to the retailer by an unrefrigerated truck.
The packhouse trims produce (conversion mode, 90% yield).

The causal graph explains two of the network's loss rates:

    ambient_temp --> power_outage --> cooling_uptime --> store_spoilage (cold store waste_rate)
         |                                                   ^
         +---------------------------------------------------+
         +--> truck_spoilage (direct edge waste_rate)

The script fits the graph to a synthetic sensor log, then asks what backup
power (no outages) would do to the produce that reaches the retailer.
"""

import numpy as np

from ecoanalyst import CausalModel, EcosystemNetwork, compare, simulate
from ecoanalyst.causal import best_route_delivered, link, waste_cost

# -- flow network ---------------------------------------------------------------
net = EcosystemNetwork(name="Produce cold chain", network_type="supply_chain",
                       efficiency_mode="conversion")
kg = {"value": 1000, "unit": "kg/day"}
net.add_node("producer", "Farm", "Farm", node_id="farm", properties={"capacity": kg, "waste_rate": 0.02})
net.add_node("processor", "Packhouse", "Packhouse", node_id="pack",
             properties={"capacity": kg, "waste_rate": 0.01, "efficiency": 0.90})
net.add_node("handler", "ColdStore", "Cold store", node_id="store", properties={"capacity": kg, "waste_rate": 0.03})
net.add_node("consumer", "Retailer", "Retailer", node_id="shop", properties={"capacity": kg, "waste_rate": 0.04})
net.add_edge("farm", "pack", "inventory", {"waste_rate": 0.01})
net.add_edge("pack", "store", "inventory", {"waste_rate": 0.01})
net.add_edge("store", "shop", "inventory", {"waste_rate": 0.01})
net.add_edge("farm", "shop", "inventory", {"waste_rate": 0.20}, edge_id="truck")

# -- causal graph (stated values are the prior guess) ---------------------------
model = CausalModel()
model.add_variable("ambient_temp", intercept=24.0, noise_sd=4.0, unit="C")
model.add_variable("power_outage", kind="binary", parents=["ambient_temp"])
model.add_variable("cooling_uptime", kind="rate", parents=["power_outage"], intercept=link("rate", 0.95))
model.add_variable("store_spoilage", kind="rate", parents=["ambient_temp", "cooling_uptime"],
                   intercept=link("rate", 0.03), binds="node:store:waste_rate")
model.add_variable("truck_spoilage", kind="rate", parents=["ambient_temp"],
                   intercept=link("rate", 0.20), binds="edge:truck:waste_rate")
net.causal = model

# -- a synthetic year of daily sensor readings -----------------------------------
rng = np.random.default_rng(42)
days = 365
temp = rng.normal(24, 4, days)
outage = (rng.random(days) < 1 / (1 + np.exp(-(-9.0 + 0.25 * temp)))).astype(float)
uptime = 1 / (1 + np.exp(-(3.5 - 3.0 * outage + rng.normal(0, 0.3, days))))
store = 1 / (1 + np.exp(-(-6.0 + 0.08 * temp - 4.0 * uptime + 3.0 + rng.normal(0, 0.2, days))))
truck = 1 / (1 + np.exp(-(-3.8 + 0.10 * temp + rng.normal(0, 0.2, days))))
log = {"ambient_temp": temp, "power_outage": outage, "cooling_uptime": uptime,
       "store_spoilage": store, "truck_spoilage": truck}

used = model.fit(log)
print(f"Fitted {len(used)} equations on {days} days of readings.")
for name in ("power_outage", "store_spoilage"):
    post = model.variables[name].posterior
    terms = ", ".join(f"{t} {m:+.3f}" for t, m in zip(post.terms, post.mean))
    print(f"  {name}: {terms}")

# -- what does the graph say about estimating from the log? ----------------------
adjust = model.adjustment_set("cooling_uptime", "store_spoilage")
print(f"To estimate cooling_uptime -> store_spoilage from the log, adjust for: {sorted(adjust)}")

# -- interventions ---------------------------------------------------------------
best = best_route_delivered("farm", "shop")
baseline = simulate(net, {"delivered": best}, n=4000, seed=1).summary()["delivered"]
print(f"Delivered fraction today: median {baseline['p50']:.3f} "
      f"(90% interval {baseline['p05']:.3f} to {baseline['p95']:.3f})")

backup = compare(net, best, do_a={"power_outage": 0.0}, do_b={}, n=4000, seed=1)
print(f"Backup power raises the delivered fraction by {backup['effect']:.4f} on average "
      f"(95th percentile day: {backup['effect_p95']:.4f}).")

hot = compare(net, waste_cost({"Farm": 1.2, "ColdStore": 2.0, "Retailer": 3.0}),
              do_a={"ambient_temp": 32.0}, do_b={"ambient_temp": 24.0}, n=4000, seed=1)
print(f"A 32 C heat wave adds {hot['effect']:.0f} to the daily loss cost estimate.")
