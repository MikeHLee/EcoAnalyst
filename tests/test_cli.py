import json
import subprocess
import sys

import pytest

from ecoanalyst import EcosystemNetwork, cli
from helpers import REPO_ROOT

DEMO_V2 = REPO_ROOT / "examples" / "demo_network.json"
DATA_V1 = REPO_ROOT / "data" / "network_data.json"


def test_demo_exits_zero(capsys):
    assert cli.main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "Best route loses 16.05%" in out
    assert "Valley Farm -> Cold Store -> Corner Grocer" in out


def test_demo_runs_as_module():
    result = subprocess.run(
        [sys.executable, "-m", "ecoanalyst.cli", "demo"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_summary_reads_any_format(capsys):
    for path in (DEMO_V2, DATA_V1):
        assert cli.main(["summary", str(path)]) == 0
        summary = json.loads(capsys.readouterr().out)
        assert summary["node_count"] > 0
    assert summary["edge_types"] == {"inventory": 5}


def test_hotspots(capsys):
    assert cli.main(["hotspots", str(DATA_V1), "--top", "2"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert [h["waste_rate"] for h in result["hotspots"]] == [0.08, 0.05]


def test_convert_both_directions(tmp_path):
    fg_path = tmp_path / "net.flowgraph.json"
    v3_path = tmp_path / "net.v3.json"
    assert cli.main(["convert", str(DATA_V1), str(fg_path), "--to", "flowgraph"]) == 0
    assert cli.main(["convert", str(fg_path), str(v3_path)]) == 0

    fg = json.loads(fg_path.read_text())
    assert fg["format"] == "ecoanalyst.flowgraph"
    v3 = json.loads(v3_path.read_text())
    assert {n["node_type"] for n in v3["nodes"]} == {"producer", "handler", "consumer"}
    assert EcosystemNetwork.from_dict(v3).to_flow_graph()["flows"] == fg["flows"]


def test_bad_input_reports_error(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text('{"hello": "world"}')
    assert cli.main(["summary", str(bad)]) == 1
    assert "unrecognized network JSON format" in capsys.readouterr().err
    assert cli.main(["summary", str(tmp_path / "missing.json")]) == 1


def test_requires_a_subcommand():
    with pytest.raises(SystemExit):
        cli.main([])
