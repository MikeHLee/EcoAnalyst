"""Keep the README quick start honest: run it and compare its printed output."""

import contextlib
import io
import re

from helpers import REPO_ROOT

MARKER = "<!-- tests/test_readme.py runs the next code block"


def quick_start_block(marker=MARKER):
    text = (REPO_ROOT / "README.md").read_text()
    start = text.index(marker)
    match = re.compile(r"```python\n(.*?)```", re.S).search(text, start)
    assert match, "no python block after the quick start marker"
    return match.group(1)


CAUSAL_MARKER = "<!-- tests/test_readme.py runs the next code block and checks the commented output (causal)."


def test_readme_quick_start_runs_and_matches_its_comments():
    check_block(quick_start_block())


def test_readme_causal_example_runs_and_matches_its_comments():
    check_block(quick_start_block(CAUSAL_MARKER))


def check_block(code):
    expected = [line[2:] for line in code.splitlines() if line.startswith("# ")]
    assert expected, "the quick start block should show its output in comments"

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(code, "README.md quick start", "exec"), {})
    assert out.getvalue().splitlines() == expected
