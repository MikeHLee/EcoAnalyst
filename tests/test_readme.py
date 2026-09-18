"""Keep the README quick start honest: run it and compare its printed output."""

import contextlib
import io
import re

from helpers import REPO_ROOT

MARKER = "<!-- tests/test_readme.py runs the next code block"


def quick_start_block():
    text = (REPO_ROOT / "README.md").read_text()
    start = text.index(MARKER)
    match = re.compile(r"```python\n(.*?)```", re.S).search(text, start)
    assert match, "no python block after the quick start marker"
    return match.group(1)


def test_readme_quick_start_runs_and_matches_its_comments():
    code = quick_start_block()
    expected = [line[2:] for line in code.splitlines() if line.startswith("# ")]
    assert expected, "the quick start block should show its output in comments"

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(code, "README.md quick start", "exec"), {})
    assert out.getvalue().splitlines() == expected
