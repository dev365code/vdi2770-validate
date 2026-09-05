"""The reader ships before the rules that pin it, and something has to say so.

`release.yml` installs from the working tree, so nothing in the build asks an
index whether the pinned reader exists, and `python -m build` does not resolve
runtime dependencies at all. Publishing `vdi2770-validate` first therefore
builds green and puts a distribution on the index `pip` cannot resolve -- under
a number PyPI will not let anyone reuse.
`tools/check_release_order.py` is what refuses that; these are the ways it has
to refuse.

The pin is exact, which gives this gate a question it could not ask while the
pin was a range: not *is the pinned version old enough to exist* but *is it this
release*. One tag names one pair, and a pin naming any other version means the
tag and the wheel disagree about which pair went out.

The one that took longest to land is still here. A tag is not a publication: the
gate proved a tag existed and printed *has been released*. Tag it, watch the
publish job stop at an environment approval or a 5xx, and the sentence is false
while the gate is green.
"""
import pathlib
import re
import shutil
import subprocess
import sys

from conftest import ROOT, under_test

TOOL = ROOT / "tools" / "check_release_order.py"


def tree_with(tmp_path, tags, pin="vdi2770==0.7.0", version="0.7.0"):
    """A throwaway checkout: this repository at `version`, pinning the reader as
    `pin`, with a history holding `tags`."""
    tree = tmp_path / "tree"
    (tree / "tools").mkdir(parents=True)
    shutil.copy(TOOL, tree / "tools" / "check_release_order.py")
    shutil.copy(ROOT / "tools" / "check_version_is_new.py",
                tree / "tools" / "check_version_is_new.py")

    body = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    stamped, n = re.subn(r'^version = "[^"]+"', f'version = "{version}"',
                         body, count=1, flags=re.M)
    assert n == 1, "the repository manifest declares no version"
    # Inside the dependencies list and nowhere else. Two narrower rules, each
    # learned from a fixture that lied: not the whole `dependencies = [...]`
    # line, because replacing it with one requirement leaves a file the tool
    # reads as declaring no dependencies at all and refuses for a different
    # reason; and not the first `"vdi2770..."` token in the file, because the
    # manifest declares `name = "vdi2770-validate"` above the list, so that
    # rewrote the distribution's own name and left the pin untouched. Every
    # case here would have passed on the wrong sentence.
    swapped, n = re.subn(
        r'(^dependencies = \[)([^\]]*)(\])',
        lambda m: m.group(1) + f'"{pin}", "xmlschema==4.2.0"' + m.group(3),
        stamped, count=1, flags=re.M)
    assert n == 1, "the manifest declares no dependencies list to aim at"
    assert f'"{pin}"' in swapped and 'name = "vdi2770-validate"' in swapped
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


def at(tmp_path, **kw):
    """The gate, with the index stubbed to hold `serving`."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tools"))
    import check_release_order as gate
    import check_version_is_new as index
    return gate, index


def test_a_release_whose_reader_is_tagged_is_allowed(tmp_path):
    """The premise: without it every refusal below could be for the wrong reason.

    `--offline` because the tag is only half the answer; the other half is the
    index, and a test suite does not ask the network.
    """
    done = run(tree_with(tmp_path, ["v0.6.0", "v0.7.0"]), "--offline")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "v0.7.0 is tagged" in done.stderr, done.stderr


def test_being_tagged_is_not_said_to_be_being_released(tmp_path):
    """The success sentence claimed a fact the gate had not checked.

    `git tag --list` and nothing else, under the words *the reader this pins has
    been released*. A tag exists the moment it is pushed; publication happens
    afterwards, in a job that can stop at an environment approval or a PyPI 5xx.
    In that window this gate was green and `pip install vdi2770-validate` could
    not resolve -- permanently, because the version number does not come back.
    """
    done = run(tree_with(tmp_path, ["v0.7.0"]), "--offline")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "released" not in done.stderr, (
        "the offline half still claims it was published: " + done.stderr)


def test_a_tag_the_index_does_not_know_about_is_refused(monkeypatch, tmp_path):
    """Tagged, unpublished, and the rules would have shipped anyway."""
    gate, index = at(tmp_path)
    monkeypatch.setattr(index, "published", lambda name, timeout=15.0: {"0.6.0"})
    monkeypatch.chdir(tree_with(tmp_path, ["v0.6.0", "v0.7.0"]))
    monkeypatch.setattr(gate, "ROOT", pathlib.Path.cwd())
    assert gate.main([]) == 1


def test_an_index_that_cannot_be_reached_is_refused(monkeypatch, tmp_path):
    """Fail closed. Not being able to see a publication is not a publication --
    the same rule the no-tags case below already applies to the tag history."""
    gate, index = at(tmp_path)

    def unreachable(name, timeout=15.0):
        raise OSError("no route to host")

    monkeypatch.setattr(index, "published", unreachable)
    monkeypatch.chdir(tree_with(tmp_path, ["v0.6.0", "v0.7.0"]))
    monkeypatch.setattr(gate, "ROOT", pathlib.Path.cwd())
    assert gate.main([]) == 1


def test_the_index_says_yes_and_the_gate_agrees(monkeypatch, tmp_path):
    gate, index = at(tmp_path)
    monkeypatch.setattr(index, "published", lambda name, timeout=15.0: {"0.7.0"})
    monkeypatch.chdir(tree_with(tmp_path, ["v0.6.0", "v0.7.0"]))
    monkeypatch.setattr(gate, "ROOT", pathlib.Path.cwd())
    assert gate.main([]) == 0


def test_a_reader_that_was_never_tagged_is_refused(tmp_path):
    done = run(tree_with(tmp_path, ["v0.6.0"]), "--offline")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "v0.7.0 is not tagged" in done.stderr, done.stderr


def test_a_pin_ahead_of_what_this_repository_publishes_is_refused(tmp_path):
    """One of two failures the index cannot report, because they are not about
    the index: pinning `==0.8.0` on the day 0.7.0 is published resolves to
    nothing, and every version PyPI holds could be healthy. Offline, and it runs
    before the tag history is even read."""
    done = run(tree_with(tmp_path, ["v0.7.0"], pin="vdi2770==0.8.0"), "--offline")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "one pair" in done.stderr, done.stderr


def test_a_pin_behind_what_this_repository_publishes_is_refused(tmp_path):
    """The other one, and it is the half a floor could never catch. `>=0.6.2`
    was satisfied by 0.7.0 and by 0.6.2, so a stale pin read as fine; `==0.6.2`
    resolves, installs, and hands the new rules the reader they were not run
    against. The tag says 0.7.0 and the wheel disagrees."""
    done = run(tree_with(tmp_path, ["v0.6.2", "v0.7.0"], pin="vdi2770==0.6.2"),
               "--offline")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "one pair" in done.stderr, done.stderr


def test_a_checkout_with_no_tags_at_all_is_refused(tmp_path):
    """Not the same as "the reader was never released", and answering yes to the
    second because you cannot see the first is how a release gate fails open.
    `actions/checkout` gives `--depth 1 --no-tags` by default."""
    done = run(tree_with(tmp_path, []), "--offline")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "no `v*` tags" in done.stderr, done.stderr


def test_a_pin_that_is_a_range_is_refused(tmp_path):
    """A range is what this release stopped using. `>=0.7` is satisfied by
    0.7.0 and by every later reader, so the pair that ships is whatever the
    index happens to hold at install time rather than the pair that was tested;
    there is no single version for this gate to check the order of."""
    done = run(tree_with(tmp_path, ["v0.7.0"], pin="vdi2770>=0.7"), "--offline")
    assert done.returncode != 0, done.stdout + done.stderr
    assert "not pinned exactly" in done.stderr, done.stderr


def test_a_pin_with_no_version_at_all_is_refused(tmp_path):
    """`vdi2770` bare is satisfied by every release ever published, including
    the one this release exists to replace."""
    done = run(tree_with(tmp_path, ["v0.7.0"], pin="vdi2770"), "--offline")
    assert done.returncode != 0, done.stdout + done.stderr
    assert "not pinned exactly" in done.stderr, done.stderr


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
