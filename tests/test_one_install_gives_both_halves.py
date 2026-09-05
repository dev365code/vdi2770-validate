"""One name, one install, both halves.

The reader and the rules were two distributions, and the validator declared a
`~=` dependency on the reader. That worked while both were published in step and
broke the moment they were not: `pip install .` from this tree goes to the index
for a reader version that only exists here, and comes back with nothing.

The split was engineering hygiene and it cost the thing a user does first. One
distribution named `vdi2770` carries both, so `pip install vdi2770` gives
`import vdi2770` and a `vdi2770` command, and there is no pin between them to
get out of step.

Slow — it builds and installs — so it lives beside the other packaging gates
rather than in the fast suite.
"""
from __future__ import annotations

import subprocess
import sys
import venv

import pytest

from conftest import CLEAN_DOCUMENT, ROOT


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    """This tree, installed into a virtual environment of its own."""
    home = tmp_path_factory.mktemp("install")
    venv.create(home, with_pip=True, clear=True)
    python = home / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    done = subprocess.run([str(python), "-m", "pip", "install", "--quiet", str(ROOT)],
                          capture_output=True, text=True, timeout=900)
    assert done.returncode == 0, (
        "installing this tree failed:\n" + done.stdout[-2000:] + done.stderr[-2000:])
    return python


def test_the_reader_is_importable_from_the_same_install(installed):
    """No second `pip install`, and no pin to satisfy."""
    done = subprocess.run([str(installed), "-c",
                           "import vdi2770; print(vdi2770.__version__)"],
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-800:]
    assert done.stdout.strip(), done.stdout


def test_importing_the_reader_does_not_drag_in_the_dependency(installed):
    """The reader's "no dependencies" survives as a property of the import even
    though it is not a property of the install any more. Anyone embedding it —
    the reason it was ever separate — still pays nothing for the rule set."""
    done = subprocess.run(
        [str(installed), "-c",
         "import sys, vdi2770; print('xmlschema' in sys.modules)"],
        capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-800:]
    assert done.stdout.strip() == "False", (
        "importing the reader pulled in the validator's dependency")


@pytest.mark.parametrize("command", ["vdi2770", "vdi2770-validate"])
def test_both_command_names_check_a_container(installed, command):
    """The new name, and the one people already have in their scripts."""
    exe = installed.parent / command
    assert exe.exists(), f"{command} was not installed: {sorted(p.name for p in installed.parent.iterdir())}"
    done = subprocess.run([str(exe), "check", str(CLEAN_DOCUMENT)],
                          capture_output=True, text=True, timeout=180)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "0 error(s)" in done.stdout, done.stdout
