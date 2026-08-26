"""The reader ships before the validator that pins it, and something has to say so.

`release.yml` installs the reader from the working tree, so nothing in the gate
asks an index whether the pinned version exists, and `python -m build` does not
resolve runtime dependencies at all. Tagging `v*` before `sdk-v*` therefore
builds green and publishes a distribution `pip` cannot resolve -- under a number
PyPI will not let anyone reuse. `tools/check_release_order.py` is what refuses
that; these are the ways it has to refuse.

A tag is not a publication, which is the distinction that took the longest to
land here: the gate proved `sdk-v0.6.2` existed and printed *the reader this pins
has been released*. Tag the reader, watch its publish job stop at an environment
approval or a 5xx, and the sentence is false while the gate is green -- and the
validator burns a version number that PyPI will not hand back.
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
    shutil.copy(ROOT / "tools" / "check_version_is_new.py",
                tree / "tools" / "check_version_is_new.py")
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


def run(tree, *extra):
    return subprocess.run(
        [sys.executable, "tools/check_release_order.py", *extra],
        cwd=tree, capture_output=True, text=True, env=under_test())


def test_a_pinned_reader_that_is_tagged_is_allowed(tmp_path):
    """The premise: without it every refusal below could be for the wrong reason.

    `--offline` because the tag is only half the answer now; the other half is
    the index, and a test suite does not ask the network.
    """
    done = run(tree_with(tmp_path, ["sdk-v0.6.1", "sdk-v0.6.2"], "0.6.2"), "--offline")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "sdk-v0.6.2 is tagged" in done.stderr, done.stderr


def test_being_tagged_is_not_said_to_be_being_released(tmp_path):
    """The success sentence claimed a fact the gate had not checked.

    `git tag --list sdk-v*` and nothing else, under the words *the reader this
    pins has been released*. A tag exists the moment it is pushed; publication
    happens afterwards, in a job that can stop at an environment approval or a
    PyPI 5xx. In that window this gate was green and `pip install
    vdi2770-validate` could not resolve -- permanently, because the version
    number does not come back.
    """
    done = run(tree_with(tmp_path, ["sdk-v0.6.2"], "0.6.2"), "--offline")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "released" not in done.stderr, (
        "the offline half still claims the reader was published: " + done.stderr)


def test_a_tag_the_index_does_not_know_about_is_refused(monkeypatch, tmp_path):
    """Tagged, unpublished, and the validator would have shipped anyway."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tools"))
    import check_release_order as gate
    import check_version_is_new as index

    monkeypatch.setattr(index, "published", lambda name, timeout=15.0: {"0.6.1"})
    monkeypatch.chdir(tree_with(tmp_path, ["sdk-v0.6.1", "sdk-v0.6.2"], "0.6.2"))
    monkeypatch.setattr(gate, "ROOT", pathlib.Path.cwd())
    assert gate.main([]) == 1


def test_an_index_that_cannot_be_reached_is_refused(monkeypatch, tmp_path):
    """Fail closed. Not being able to see a publication is not a publication --
    the same rule the no-tags case above already applies to the tag history."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tools"))
    import check_release_order as gate
    import check_version_is_new as index

    def unreachable(name, timeout=15.0):
        raise OSError("no route to host")

    monkeypatch.setattr(index, "published", unreachable)
    monkeypatch.chdir(tree_with(tmp_path, ["sdk-v0.6.1", "sdk-v0.6.2"], "0.6.2"))
    monkeypatch.setattr(gate, "ROOT", pathlib.Path.cwd())
    assert gate.main([]) == 1


def test_the_index_says_yes_and_the_gate_agrees(monkeypatch, tmp_path):
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tools"))
    import check_release_order as gate
    import check_version_is_new as index

    monkeypatch.setattr(index, "published", lambda name, timeout=15.0: {"0.6.2"})
    monkeypatch.chdir(tree_with(tmp_path, ["sdk-v0.6.1", "sdk-v0.6.2"], "0.6.2"))
    monkeypatch.setattr(gate, "ROOT", pathlib.Path.cwd())
    assert gate.main([]) == 0


def test_a_pinned_reader_that_was_never_tagged_is_refused(tmp_path):
    done = run(tree_with(tmp_path, ["sdk-v0.6.1"], "0.6.2"), "--offline")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "sdk-v0.6.2 is not tagged" in done.stderr, done.stderr


def test_a_checkout_with_no_tags_at_all_is_refused(tmp_path):
    """Not the same as "the reader was never released", and answering yes to the
    second because you cannot see the first is how a release gate fails open.
    `actions/checkout` gives `--depth 1 --no-tags` by default."""
    done = run(tree_with(tmp_path, [], "0.6.2"), "--offline")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "no `sdk-v*` tags" in done.stderr, done.stderr


def test_a_pin_with_no_floor_is_refused(tmp_path):
    """`vdi2770` unpinned admits every reader ever published, including the ones
    these tests never ran against. There is no version to check the order of."""
    tree = tree_with(tmp_path, ["sdk-v0.6.1"], "0.6.2")
    body = pathlib.Path(tree / "pyproject.toml").read_text(encoding="utf-8")
    pathlib.Path(tree / "pyproject.toml").write_text(
        body.replace('"vdi2770~=0.6.2"', '"vdi2770"'), encoding="utf-8")
    done = run(tree, "--offline")
    assert done.returncode != 0, done.stdout + done.stderr
    assert "no lower bound" in done.stderr, done.stderr


def test_an_index_answer_without_releases_is_not_an_empty_index():
    """`.get("releases", {})` turned any 200 whose shape changed into a
    pass-everything. PyPI's legacy JSON API is deprecated; the day it drops that
    key, the gate that exists to refuse a duplicate upload starts approving them
    -- silently, and only at the upload does anyone find out. Not knowing is a
    refusal here, as it is everywhere else in this file."""
    import io
    import json as _json
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tools"))
    import check_version_is_new as index

    class Answer(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def answers(url, timeout=None):
        return Answer(_json.dumps({"info": {}}).encode())

    import urllib.request
    saved = urllib.request.urlopen
    urllib.request.urlopen = answers
    try:
        raised = None
        try:
            index.published("vdi2770")
        except Exception as e:          # noqa: BLE001 - that is the assertion
            raised = e
        assert raised is not None, (
            "an answer with no `releases` key was read as an empty index")
    finally:
        urllib.request.urlopen = saved


def test_a_version_is_compared_the_way_the_index_spells_it():
    """`0.7.0-rc1` and `0.7.0rc1` are one version, and PyPI stores the second.
    Compared as strings, a pre-release tag walked straight through the gate that
    exists to catch exactly that, and was rejected at the upload instead."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tools"))
    import check_version_is_new as index

    assert index.holds({"0.7.0rc1"}, "0.7.0-rc1"), "a pre-release slipped past"
    assert index.holds({"0.7.0"}, "0.7.0")
    assert not index.holds({"0.7.0"}, "0.7.1")
