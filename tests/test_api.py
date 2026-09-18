import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from ecoanalyst import api  # noqa: E402

ORIGIN = "https://attacker.example"


@pytest.fixture
def client():
    api.networks.clear()
    with TestClient(api.create_app(cors_origins=[])) as c:
        yield c
    api.networks.clear()


def node_body(kind, name, rate, capacity=1000):
    return {
        "node_type": kind,
        "node_class": name,
        "name": name,
        "properties": {"capacity": {"value": capacity, "unit": "kg/day"}, "waste_rate": rate},
    }


def edge_body(src, tgt, rate, kind="inventory_flow"):
    return {
        "source_node_id": src,
        "target_node_id": tgt,
        "relationship_type": kind,
        "flow": {"max_rate": {"value": 500, "unit": "kg/day"}, "waste_rate": rate},
    }


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "healthy"
    assert body["version"] == "3.0.0"


def test_build_analyze_and_exchange(client):
    net_id = client.post("/networks", json={"name": "api", "network_type": "supply_chain"}).json()["network_id"]

    farm = client.post(f"/networks/{net_id}/nodes", json=node_body("producer", "Farm", 0.1)).json()["node_id"]
    shop = client.post(f"/networks/{net_id}/nodes", json=node_body("consumer", "Shop", 0.2)).json()["node_id"]
    r = client.post(f"/networks/{net_id}/edges", json=edge_body(farm, shop, 0.05))
    assert r.status_code == 200
    assert r.json()["relationship_type"] == "inventory"

    assert client.post(f"/networks/{net_id}/nodes", json=node_body("Bad Kind", "X", 0.1)).status_code == 422
    assert client.post(f"/networks/{net_id}/edges", json=edge_body(farm, "missing", 0.1)).status_code == 400

    hotspots = client.get(f"/networks/{net_id}/hotspots", params={"top_n": 2}).json()
    assert [h["waste_rate"] for h in hotspots["hotspots"]] == [0.2, 0.1]
    assert client.get(f"/networks/{net_id}/hotspots", params={"metric": "nope"}).status_code == 400

    route = client.get(f"/networks/{net_id}/optimize-paths",
                       params={"source_node_id": farm, "target_node_id": shop, "edge_kinds": ["inventory"]}).json()
    assert route["path"] == [farm, shop]
    assert route["total_waste"] == pytest.approx(1 - 0.9 * 0.95 * 0.8)

    waste = client.post(f"/networks/{net_id}/calculate-waste", json={"Farm": 2.0}).json()
    assert waste["total_waste_cost"] == pytest.approx(1000 * 0.1 * 2 + 1000 * 0.2 + 500 * 0.05 * 2)

    fg = client.get(f"/networks/{net_id}/flow-graph").json()
    assert fg["format"] == "ecoanalyst.flowgraph"
    assert len(fg["actors"]) == 2 and len(fg["flows"]) == 1

    imported = client.post("/networks/flow-graph", json=fg).json()
    assert imported["node_count"] == 2 and imported["edge_count"] == 1
    copy_id = imported["network_id"]
    assert copy_id != net_id
    assert client.get(f"/networks/{copy_id}/flow-graph").json()["flows"] == fg["flows"]
    assert client.post("/networks/flow-graph", json={"format": "other"}).status_code == 400

    listing = client.get("/networks").json()
    assert listing["total_count"] == 2
    assert client.delete(f"/networks/{copy_id}").status_code == 200
    assert client.get(f"/networks/{copy_id}").status_code == 404


def test_cors_denies_unknown_origin_by_default(client):
    r = client.get("/health", headers={"Origin": ORIGIN})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers

    preflight = client.options(
        "/networks",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in preflight.headers


def test_cors_env_parsing(monkeypatch):
    monkeypatch.setenv(api.CORS_ENV_VAR, " http://localhost:5173 , ,http://127.0.0.1:5173")
    assert api.cors_origins_from_env() == ["http://localhost:5173", "http://127.0.0.1:5173"]
    monkeypatch.delenv(api.CORS_ENV_VAR)
    assert api.cors_origins_from_env() == []


def test_cors_allows_configured_origin_without_credentials():
    allowed = "http://localhost:5173"
    with TestClient(api.create_app(cors_origins=[allowed])) as c:
        ok = c.get("/health", headers={"Origin": allowed})
        assert ok.headers["access-control-allow-origin"] == allowed
        assert "access-control-allow-credentials" not in ok.headers
        denied = c.get("/health", headers={"Origin": ORIGIN})
        assert "access-control-allow-origin" not in denied.headers
