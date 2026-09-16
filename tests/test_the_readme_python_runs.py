"""The README's Python is executed, not read.

The shell transcripts in this page have been checked against the real tool for
a long time; the Python blocks were not, and the first one written after that
gate existed was wrong in two ways at once. It named `reader`, which is the PDF
reader factory rather than the container entry point, and called it with no
arguments when it takes an allowance. Both are `AttributeError`/`TypeError` on
the first line — the kind of wrong that a reader hits immediately and that no
amount of proofreading catches, because the page reads fine.

This is the project's own README, and it is also the description PyPI shows on
the package page, so a broken example there is the first thing a new user runs.
"""
import re
import subprocess
import sys

from conftest import ROOT

README = (ROOT / "README.md").read_text(encoding="utf-8")
BLOCKS = re.findall(r"```python\n(.*?)```", README, re.S)


def test_the_page_has_python_to_check():
    """A guard on the guard: the blocks are found by a fence spelling, and a page
    that switched to ```py would leave this file passing over nothing."""
    assert BLOCKS, "no ```python block in README.md; this gate is looking for the wrong fence"


def test_every_python_block_runs():
    """From the repository root, because the page tells the reader to clone and
    `cd` in before it shows any path."""
    for i, block in enumerate(BLOCKS):
        done = subprocess.run([sys.executable, "-c", block], cwd=ROOT,
                              capture_output=True, text=True)
        assert done.returncode == 0, (
            f"README python block {i + 1} does not run:\n{block}\n"
            f"{done.stderr[-800:]}")
