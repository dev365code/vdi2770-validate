"""`API.json` is evidence about a published library. Three edits to the JSON
itself used to make `--write` record a changed surface anyway: setting `format`
back a version disabled the refusal outright, a made-up `version` made it
compare against nothing, and `rm` plus `--first` claimed there had never been a
record.

All three are only a problem once a release tag names the version — before that
it is still being written and the record moves with it. That distinction is the
fix: the tool asks the tag history, not the file it is about to overwrite. The
tag is `v<version>` from 0.7.0, when the reader and the rules became one
distribution, and `sdk-v<version>` below it, when the reader was published on
its own.
"""
import json
import shutil
import subprocess
import sys

import pytest

from conftest import ROOT

TOOL = ROOT / "tools" / "api_fingerprint.py"
BASELINE = ROOT / "packages" / "vdi2770" / "API.json"


def tag_for(version: str) -> str:
    """The tag that would publish a reader version, in its own namespace.

    Mirrors `api_fingerprint._prefix_for`. The two namespaces share their
    numbers: `v0.5.0` is a validator release whose reader said 0.3.1, so a
    fixture that tags the wrong one is testing a different distribution.
    """
    parts = tuple(int(x) for x in version.split(".")[:3])
    return ("v" if parts >= (0, 7, 0) else "sdk-v") + version


def run(tmp_path, *args, published=True):
    """Run the tool against a copy whose `ROOT` is a throwaway git repo."""
    tree = tmp_path / "tree"
    shutil.copytree(ROOT / "packages", tree / "packages")
    (tree / "tools").mkdir()
    shutil.copy(TOOL, tree / "tools" / "api_fingerprint.py")
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
    version = json.loads((tree / "packages" / "vdi2770" / "API.json").read_text())["version"]
    # Commit the tree, not an empty commit. Tagging nothing made `_at_tag` return
    # None for every test in this file, so the comparison that matters --
    # "the baseline is not what its tag published" -- was never exercised: every
    # test took the `published is None` path and a mutation weakening
    # `published != recorded` to `published is None` survived the whole suite.
    subprocess.run(["git", "add", "-A"], cwd=tree, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "x"], cwd=tree, check=True)
    # Some tag history always, because "this version has not shipped" and "this
    # package has never shipped anything" are different claims and the tool
    # refuses the second one outright. A copy with no tags at all used to make
    # every guard in the tool answer "not published".
    subprocess.run(["git", "tag", "v0.0.1"], cwd=tree, check=True)
    if published:
        subprocess.run(["git", "tag", tag_for(version)], cwd=tree, check=True)
    # Move the surface.
    zr = tree / "packages" / "vdi2770" / "src" / "vdi2770" / "zipread.py"
    text = zr.read_text(encoding="utf-8")
    anchor = "    member_name: Optional[str] = None"
    assert text.count(anchor) == 1
    zr.write_text(text.replace(anchor, anchor + "\n    sneak: Optional[str] = None"),
                  encoding="utf-8")
    return tree, subprocess.run([sys.executable, "tools/api_fingerprint.py", "--write", *args],
                                cwd=tree, capture_output=True, text=True)


def test_a_moved_surface_under_a_published_version_is_refused(tmp_path):
    _, done = run(tmp_path)
    assert done.returncode == 1, done.stdout + done.stderr


@pytest.mark.parametrize("field,value", [("format", 1), ("version", "0.0.9")])
def test_editing_the_record_does_not_steer_the_refusal(tmp_path, field, value):
    tree, _ = run(tmp_path)
    baseline = tree / "packages" / "vdi2770" / "API.json"
    body = json.loads(baseline.read_text(encoding="utf-8"))
    body[field] = value
    if field == "version":
        subprocess.run(["git", "tag", tag_for(value)], cwd=tree, check=True)
    baseline.write_text(json.dumps(body, indent=2), encoding="utf-8")
    done = subprocess.run([sys.executable, "tools/api_fingerprint.py", "--write"],
                          cwd=tree, capture_output=True, text=True)
    assert done.returncode == 1, f"editing {field} let it record: {done.stdout}{done.stderr}"


def test_a_version_from_before_the_merge_is_looked_up_in_the_old_namespace():
    """The reader was its own distribution once, released on `sdk-v*`, and those
    releases are on PyPI under numbers nobody can reuse. The tags this file
    reads moved to `v*` when the two distributions became one at 0.7.0.

    A rename of the evidence is not a deletion of it — but the two namespaces
    share their numbers and do not share their meaning. `v0.5.0` is a
    *validator* release and the reader inside it said 0.3.1; PyPI has no reader
    0.5.0 at all. So the namespace is chosen by version rather than tried in
    turn, which is what stops this file answering about the wrong distribution.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    import api_fingerprint as fp

    assert fp._prefix_for("0.6.1") == "sdk-v"
    assert fp._prefix_for("0.4.0") == "sdk-v"
    assert fp._prefix_for("0.7.0") == "v", "the merge release is in the new one"
    assert fp._prefix_for("1.2.3") == "v"


def test_a_reader_release_made_under_the_old_name_still_reads_as_published():
    """The live half of the same claim, against this repository's own history:
    `sdk-v0.6.1` exists and `v0.6.1` does not. Reading only the current spelling
    would make the newest published reader look unreleased, which turns every
    guard in this file off for exactly the version people have installed."""
    sys.path.insert(0, str(ROOT / "tools"))
    import api_fingerprint as fp

    got = subprocess.run(["git", "tag", "--list", "sdk-v0.6.1"], cwd=ROOT,
                         capture_output=True, text=True)
    if got.returncode or not got.stdout.strip():
        pytest.skip("no tag history here; this reads the repository's own")
    assert fp._published("0.6.1")


def test_deleting_the_record_does_not_make_it_the_first_one(tmp_path):
    tree, _ = run(tmp_path)
    (tree / "packages" / "vdi2770" / "API.json").unlink()
    done = subprocess.run([sys.executable, "tools/api_fingerprint.py", "--write", "--first"],
                          cwd=tree, capture_output=True, text=True)
    assert done.returncode == 1, done.stdout + done.stderr


def test_an_unpublished_version_may_still_be_written(tmp_path):
    """Before the tag exists the version is being written and the record moves
    with it. Refusing here would mean a version bump per commit."""
    _, done = run(tmp_path, published=False)
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_breaking_change_needs_the_minor_to_move_not_the_patch():
    """"Bump the version" is not enough when the validator pins with `~=`.

    `vdi2770~=0.6.0` admits 0.6.1 through 0.6.9. The gate compared record to
    surface and asked for *a* bump, so removing a name and calling it 0.6.1
    satisfied it — and every installed validator would take that release without
    being asked. This project has already shipped that exact mistake once:
    `vdi2770~=0.3.0` accepted 0.3.1 and pip installed the reader whose fix was
    the whole point of the release.

    Adding a name is compatible and a patch bump is honest for it. Removing one,
    or changing its signature, is not.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    import api_fingerprint as fp

    was = {"format": fp.FORMAT, "version": "0.6.0",
           "surface": {"read": "(data, path)", "nfc": "(name)"}}

    def verdict(version, surface):
        return fp.compatible(was, {"format": fp.FORMAT, "version": version, "surface": surface})

    added = {**was["surface"], "ClassName": "(language, text, src)"}
    assert verdict("0.6.1", added) is None, "adding a name is compatible; a patch bump is honest"

    removed = {"read": "(data, path)"}
    assert verdict("0.6.1", removed), "removing `nfc` in a patch release is not compatible"
    assert verdict("0.7.0", removed) is None, "a minor bump is how a removal is announced"

    moved = {**was["surface"], "read": "(data, path, depth)"}
    assert verdict("0.6.1", moved), "changing a signature in a patch release is not compatible"
    assert verdict("0.7.0", moved) is None


def test_the_version_itself_is_not_a_breaking_change():
    """The synthetic surface in the test above is why this was missed.

    `vdi2770.__all__` carries `__version__`, and `surface()` records its *value*.
    `compatible()` is only ever consulted when the version moved — so
    `__version__` is in `moved` every single time, the "nothing incompatible
    changed" branch is unreachable, and the verdict collapses to "the minor must
    move, always". A patch release of the reader with no surface change at all
    was refused, and `--check` fails until `--write` succeeds, so the release
    path was closed in both directions.

    Built from the real recorded surface, not a two-entry stand-in.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    import api_fingerprint as fp

    was = json.loads((ROOT / "packages" / "vdi2770" / "API.json").read_text(encoding="utf-8"))
    assert "__version__" in was["surface"], (
        "this test exists because the version is part of the recorded surface")

    # Derived from the record. Written as a literal it asserted something about
    # a *backwards* move the day the recorded version passed it, which is the
    # opposite of what this test is named for.
    major, minor, patch = (int(x) for x in was["version"].split(".")[:3])
    later = f"{major}.{minor}.{patch + 1}"
    now = json.loads(json.dumps(was))
    now["version"] = later
    now["surface"]["__version__"] = {"kind": "str", "value": f"'{later}'"}
    assert fp.compatible(was, now) is None, fp.compatible(was, now)

    # And the thing it is for still bites.
    now["surface"].pop("nfc")
    assert fp.compatible(was, now), "removing a name in a patch release is not compatible"


def test_a_release_past_a_published_version_is_not_a_wall():
    """`sdk-v0.6.0` was the first baseline recorded under a tag that exists, and
    the branch that noticed "the recorded version is published and the package
    has moved past it" refused outright — across the one operation a release
    performs. Every later release of the reader would have had to edit this tool.

    What it may not do is take the recorded version's word for itself. The tag
    is the evidence; this file is a copy of it, and a copy whose `version` says
    something the tag did not publish is how you make the tool compare against a
    past that never existed.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    import api_fingerprint as fp

    recorded = json.loads(BASELINE.read_text(encoding="utf-8"))
    published = fp._at_tag(recorded["version"])
    if published is None:
        pytest.skip(f"{tag_for(recorded['version'])} is not tagged here yet")
    assert published == recorded, (
        "the checked-in baseline is not what its own tag published; the release "
        "path compares against the tag and this would refuse every release")


def test_a_baseline_that_is_not_what_its_tag_published_is_refused(tmp_path):
    """The steering move, in the shape the release path opened for it: leave the
    surface changed, point `version` at some tag that exists, and let the
    compatibility check wave the move through on the strength of a minor bump
    from a version this baseline never was."""
    tree, _ = run(tmp_path)
    baseline = tree / "packages" / "vdi2770" / "API.json"
    body = json.loads(baseline.read_text(encoding="utf-8"))
    body["version"] = "0.0.9"                       # tagged below, and a minor behind
    subprocess.run(["git", "tag", tag_for("0.0.9")], cwd=tree, check=True)
    baseline.write_text(json.dumps(body, indent=2), encoding="utf-8")

    done = subprocess.run([sys.executable, "tools/api_fingerprint.py", "--write"],
                          cwd=tree, capture_output=True, text=True)
    assert done.returncode == 1, done.stdout + done.stderr
    assert f"not what {tag_for('0.0.9')} published" in done.stderr, done.stderr


def test_a_checkout_without_tags_is_refused_rather_than_waved_through(tmp_path):
    """"No such tag" and "this checkout has no tags" were the same answer, and
    the second turns every judgement in the tool off. A `--depth 1 --no-tags`
    clone — which is what `actions/checkout` gives you by default — recorded a
    moved surface under a version that is live on PyPI, with the whole gate
    green. A guard that cannot see is a guard that says yes.
    """
    tree = tmp_path / "tree"
    shutil.copytree(ROOT / "packages", tree / "packages")
    (tree / "tools").mkdir()
    shutil.copy(TOOL, tree / "tools" / "api_fingerprint.py")
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)      # no tags at all

    done = subprocess.run([sys.executable, "tools/api_fingerprint.py", "--write"],
                          cwd=tree, capture_output=True, text=True)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "no release tags at all" in done.stderr, done.stderr


def test_a_version_that_is_already_published_is_not_recorded_over(tmp_path):
    """Restoring the baseline from the previous tag is what this tool's own error
    messages tell you to do, and it walked a surface change into the live
    version: the release branch fires on "the recorded version differs", which is
    exactly the condition that made the same-version guard unreachable.

    This test used to run the tool not at all. It read `API.json`, called
    `_at_tag`, skipped when the tag was absent -- which it is for every
    unreleased version, so always -- and then asserted its own premise. Replacing
    the guard it names with `if False:` left the suite green.

    So: a baseline that *is* what its tag published, a compatible addition on
    top, and the version bumped to another tag that also exists. Everything the
    tool checks before this guard passes; the only thing wrong is that somebody
    already installed the number being written.
    """
    tree = tmp_path / "tree"
    shutil.copytree(ROOT / "packages", tree / "packages")
    (tree / "tools").mkdir()
    shutil.copy(TOOL, tree / "tools" / "api_fingerprint.py")
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)

    was = json.loads((tree / "packages" / "vdi2770" / "API.json").read_text(
        encoding="utf-8"))["version"]
    subprocess.run(["git", "add", "-A"], cwd=tree, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "x"], cwd=tree, check=True)
    # The baseline is genuinely the record of that tag, so `_at_tag` matches
    # it and the "restore it from the tag" branch above cannot fire instead.
    subprocess.run(["git", "tag", tag_for(was)], cwd=tree, check=True)

    major, minor, _patch = (int(x) for x in was.split("."))
    # The *minor*: the addition below changes a dataclass's signature, and the
    # pin is `~=`, so a patch bump is refused one guard earlier and this test
    # would pass on the wrong sentence.
    now = f"{major}.{minor + 1}.0"
    subprocess.run(["git", "tag", tag_for(now)], cwd=tree, check=True)
    # `__init__.py` and nothing else: the reader had a `pyproject.toml` of its
    # own while it was published separately, and the number lives in one place
    # now.
    f = tree / "packages" / "vdi2770" / "src" / "vdi2770" / "__init__.py"
    f.write_text(f.read_text(encoding="utf-8").replace(was, now), encoding="utf-8")
    # An addition, so `compatible()` is happy with the patch bump and the only
    # thing left to object to is the number itself.
    zr = tree / "packages" / "vdi2770" / "src" / "vdi2770" / "zipread.py"
    text = zr.read_text(encoding="utf-8")
    anchor = "    member_name: Optional[str] = None"
    assert text.count(anchor) == 1
    zr.write_text(text.replace(anchor, anchor + "\n    sneak: Optional[str] = None"),
                  encoding="utf-8")

    done = subprocess.run([sys.executable, "tools/api_fingerprint.py", "--write"],
                          cwd=tree, capture_output=True, text=True)
    assert done.returncode == 1, done.stdout + done.stderr
    assert f"{tag_for(now)} is already published" in done.stderr, done.stderr
    kept = json.loads((tree / "packages" / "vdi2770" / "API.json").read_text(
        encoding="utf-8"))
    assert kept["version"] == was, "it refused and wrote the file anyway"


def test_a_version_going_backwards_is_not_a_release():
    """Additions are compatible with a patch bump, and `compatible()` returned
    None on the strength of that before it ever looked at the numbers — so
    0.6.1 -> 0.5.0 passed. A pin that admits the older one will never see it."""
    sys.path.insert(0, str(ROOT / "tools"))
    import api_fingerprint as fp

    was = json.loads(BASELINE.read_text(encoding="utf-8"))
    added = {"format": fp.FORMAT, "version": "0.0.1",
             "surface": dict(was["surface"], NEWNAME={"kind": "str", "value": "'x'"})}
    why = fp.compatible(was, added)
    assert why and "backwards" in why, why


def test_pointing_the_record_at_a_tag_that_does_not_exist_is_refused(tmp_path):
    """The authenticity check was guarded by `_published(recorded["version"])` —
    on a value the editor of that file chooses. Point `version` at a tag that
    does not exist and the branch never runs: `compatible()` is handed a version
    out of thin air and waves a removal through as a patch. `--write` then
    overwrites the field, so the committed diff shows an ordinary version bump
    and nothing else.
    """
    tree, _ = run(tmp_path)
    baseline = tree / "packages" / "vdi2770" / "API.json"
    body = json.loads(baseline.read_text(encoding="utf-8"))
    body["version"] = "0.0.5"                    # deliberately never tagged
    baseline.write_text(json.dumps(body, indent=2), encoding="utf-8")

    done = subprocess.run([sys.executable, "tools/api_fingerprint.py", "--write"],
                          cwd=tree, capture_output=True, text=True)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "no release tag ever named it" in done.stderr, done.stderr


def test_a_baseline_that_differs_from_its_tag_is_refused(tmp_path):
    """The comparison itself, on a tag that really carries a different baseline.
    The sibling above covers "no tag"; this covers "a tag, and it says something
    else" — the path nothing in this file used to reach."""
    tree, _ = run(tmp_path)
    baseline = tree / "packages" / "vdi2770" / "API.json"
    body = json.loads(baseline.read_text(encoding="utf-8"))
    version = body["version"]

    # The tag holds the real baseline; the tree's copy claims one more name.
    body["surface"]["SNEAK"] = {"kind": "str", "value": "'x'"}
    baseline.write_text(json.dumps(body, indent=2), encoding="utf-8")
    bumped = ".".join([*version.split(".")[:2], str(int(version.split(".")[2]) + 1)])
    p = tree / "packages" / "vdi2770" / "src" / "vdi2770" / "__init__.py"
    p.write_text(p.read_text(encoding="utf-8").replace(f'"{version}"', f'"{bumped}"'),
                 encoding="utf-8")

    done = subprocess.run([sys.executable, "tools/api_fingerprint.py", "--write"],
                          cwd=tree, capture_output=True, text=True)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "is not what v" in done.stderr, done.stderr
    assert "no baseline at all" not in done.stderr, (
        "this is the 'the tag says something else' path, not the 'no tag' one")


def test_an_unreleased_version_is_told_to_re_record_not_to_bump(tmp_path):
    """`--check` said the wrong thing, and its remedy would have cost a version.

    The message read *"Whoever installs 0.6.2 from PyPI does not get this. Bump
    the version…"* about a version that was never published — nobody can install
    it, so nobody is missing anything, and bumping would have burned a number to
    fix a problem that did not exist. `--write` gets this right and accepts the
    re-record; only the sentence explaining the refusal was untrue.

    The two cases need two sentences, because the repair is different: a
    published version cannot take back what it shipped, and an unpublished one
    has shipped nothing.
    """
    tree = tmp_path / "tree"
    shutil.copytree(ROOT / "packages", tree / "packages")
    (tree / "tools").mkdir()
    shutil.copy(TOOL, tree / "tools" / "api_fingerprint.py")
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tree, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "x"], cwd=tree, check=True)
    subprocess.run(["git", "tag", "v0.0.1"], cwd=tree, check=True)

    zr = tree / "packages" / "vdi2770" / "src" / "vdi2770" / "zipread.py"
    text = zr.read_text(encoding="utf-8")
    anchor = "    member_name: Optional[str] = None"
    assert text.count(anchor) == 1
    zr.write_text(text.replace(anchor, anchor + "\n    sneak: Optional[str] = None"),
                  encoding="utf-8")

    done = subprocess.run([sys.executable, "tools/api_fingerprint.py", "--check"],
                          cwd=tree, capture_output=True, text=True)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "from PyPI does not get this" not in done.stderr, done.stderr
    assert "--write" in done.stderr, (
        "an unpublished version is re-recorded, and the message has to say so")
