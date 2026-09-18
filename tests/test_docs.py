"""Check that code and JSON examples in docs/ still work."""

import json
import re

import pytest

from ecoanalyst import EcosystemNetwork
from helpers import REPO_ROOT

DOCS = REPO_ROOT / "docs"


def fenced_blocks(path, language):
    return re.findall(rf"```{language}\n(.*?)```", path.read_text(), re.S)


def test_integration_guide_python_example_runs():
    (code,) = fenced_blocks(DOCS / "integration.md", "python")
    namespace = {}
    exec(compile(code, "integration.md", "exec"), namespace)
    assert namespace["path"] == ["solar", "sub", "town"]
    assert namespace["loss"] == pytest.approx(1 - 0.98 * 0.94 * 0.99 * 0.97)
    assert namespace["delivered"] == pytest.approx(95 * 0.98 * 0.94 * 0.99 * 0.97)


def test_flow_graph_doc_example_validates_and_imports():
    example = json.loads(fenced_blocks(DOCS / "flow_graph_format.md", "json")[0])
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((DOCS / "flowgraph.schema.json").read_text())
    jsonschema.validate(example, schema)

    network = EcosystemNetwork.from_flow_graph(example)
    assert network.edges["farm_to_shop"].flow.waste_rate == 0.15
    assert network.edges["farm_to_shop"].series_ref == "sensors/truck-12.csv"
    assert network.nodes["farm"].geometry["type"] == "Point"
    assert network.calculate_path_waste(["farm", "shop"])[0] == pytest.approx(1 - 0.95 * 0.85 * 0.92)
