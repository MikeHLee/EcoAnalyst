"""Run the example scripts that do not need PyMC."""

import os
import subprocess
import sys

import pytest

from helpers import REPO_ROOT

EXAMPLES = REPO_ROOT / "examples"


def run_example(name, tmp_path):
    env = dict(os.environ, MPLBACKEND="Agg")
    return subprocess.run(
        [sys.executable, str(EXAMPLES / name)],
        capture_output=True, text=True, cwd=tmp_path, env=env, timeout=300,
    )


def test_current_api_example(tmp_path):
    result = run_example("ecoanalyst_demo.py", tmp_path)
    assert result.returncode == 0, result.stderr
    assert "Total Waste: 22.6%" in result.stdout


@pytest.mark.parametrize("name", ["advanced_ecosystem.py", "network_visualization.py"])
def test_legacy_drawing_examples(name, tmp_path):
    pytest.importorskip("matplotlib")
    result = run_example(name, tmp_path)
    assert result.returncode == 0, result.stderr
