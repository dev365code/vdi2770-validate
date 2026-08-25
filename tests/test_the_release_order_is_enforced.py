"""The reader ships before the validator that pins it, and something has to say so.

`release.yml` installs the reader from the working tree, so nothing in the gate
asks an index whether the pinned version exists, and `python -m build` does not
resolve runtime dependencies at all. Tagging `v*` before `sdk-v*` therefore
builds green and publishes a distribution `pip` cannot resolve -- under a number
PyPI will not let anyone reuse. `tools/check_release_order.py` is what refuses
that; these are the ways it has to refuse.
"""
import pathlib
import shutil
import subprocess
import sys

from conftest import ROOT, under_test

TOOL = ROOT / "tools" / "check_release_order.py"


def tree_with(tmp_path, tags, pin):
    """A throwaway checkout whose pin says `pin` and whose history holds `tags`."""
    tree = tmp_path / "tree"
    (tree / "tools").mkdir(parents=True)
    shutil.copy(TOOL, tree / "tools" / "check_release_order.py")
    import re

    body = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # The pin token, not the line it sits on: `dependencies = [...]` holds the
    # whole list, and replacing the line with one requirement leaves a file the
    # tool reads as declaring no dependencies at all -- which it refuses for a
    # different reason, so every case below would pass on the wrong sentence.
    swapped, n = re.subn(r'"vdi2770[^"]*"', f'"vdi2770~={pin}"', body, count=1)
    assert n == 1, "the validator no longer pins the reader"
    (tree / "pyproject.toml").write_text(swapped, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tree, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "x"], cwd=tree, check=True)
    for tag in tags:
        subprocess.run(["git", "tag", tag], cwd=tree, check=True)
    return tree


def run(tree):
    return subprocess.run([sys.executable, "tools/check_release_order.py"],
                          cwd=tree, capture_output=True, text=True, env=under_test())


def test_a_pinned_reader_that_is_tagged_is_allowed(tmp_path):
    """The premise: without it every refusal below could be for the wrong reason."""
    done = run(tree_with(tmp_path, ["sdk-v0.6.1", "sdk-v0.6.2"], "0.6.2"))
    assert done.returncode == 0, done.stdout + done.stderr
    assert "sdk-v0.6.2 is tagged" in done.stderr, done.stderr


def test_a_pinned_reader_that_was_never_tagged_is_refused(tmp_path):
    done = run(tree_with(tmp_path, ["sdk-v0.6.1"], "0.6.2"))
    assert done.returncode == 1, done.stdout + done.stderr
    assert "sdk-v0.6.2 is not tagged" in done.stderr, done.stderr


def test_a_checkout_with_no_tags_at_all_is_refused(tmp_path):
    """Not the same as "the reader was never released", and answering yes to the
    second because you cannot see the first is how a release gate fails open.
    `actions/checkout` gives `--depth 1 --no-tags` by default."""
    done = run(tree_with(tmp_path, [], "0.6.2"))
    assert done.returncode == 1, done.stdout + done.stderr
    assert "no `sdk-v*` tags" in done.stderr, done.stderr


def test_a_pin_with_no_floor_is_refused(tmp_path):
    """`vdi2770` unpinned admits every reader ever published, including the ones
    these tests never ran against. There is no version to check the order of."""
    tree = tree_with(tmp_path, ["sdk-v0.6.1"], "0.6.2")
    body = pathlib.Path(tree / "pyproject.toml").read_text(encoding="utf-8")
    pathlib.Path(tree / "pyproject.toml").write_text(
        body.replace('"vdi2770~=0.6.2"', '"vdi2770"'), encoding="utf-8")
    done = run(tree)
    assert done.returncode != 0, done.stdout + done.stderr
    assert "no lower bound" in done.stderr, done.stderr
