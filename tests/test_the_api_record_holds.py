"""`API.json` is evidence about a published library. Three edits to the JSON
itself used to make `--write` record a changed surface anyway: setting `format`
back a version disabled the refusal outright, a made-up `version` made it
compare against nothing, and `rm` plus `--first` claimed there had never been a
record.

All three are only a problem once `sdk-v<version>` exists — before that the
version is still being written and the record moves with it. That distinction is
the fix: the tool asks the tag history, not the file it is about to overwrite.
"""
import json
import shutil
import subprocess
import sys

import pytest

from conftest import ROOT

TOOL = ROOT / "tools" / "api_fingerprint.py"
BASELINE = ROOT / "packages" / "vdi2770" / "API.json"


def run(tmp_path, *args, published=True):
    """Run the tool against a copy whose `ROOT` is a throwaway git repo."""
    tree = tmp_path / "tree"
    shutil.copytree(ROOT / "packages", tree / "packages")
    (tree / "tools").mkdir()
    shutil.copy(TOOL, tree / "tools" / "api_fingerprint.py")
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
    version = json.loads((tree / "packages" / "vdi2770" / "API.json").read_text())["version"]
    if published:
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-q", "--allow-empty", "-m", "x"], cwd=tree, check=True)
        subprocess.run(["git", "tag", f"sdk-v{version}"], cwd=tree, check=True)
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
        subprocess.run(["git", "tag", f"sdk-v{value}"], cwd=tree, check=True)
    baseline.write_text(json.dumps(body, indent=2), encoding="utf-8")
    done = subprocess.run([sys.executable, "tools/api_fingerprint.py", "--write"],
                          cwd=tree, capture_output=True, text=True)
    assert done.returncode == 1, f"editing {field} let it record: {done.stdout}{done.stderr}"


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

    now = json.loads(json.dumps(was))
    now["version"] = "0.6.1"
    now["surface"]["__version__"] = {"kind": "str", "value": "'0.6.1'"}
    assert fp.compatible(was, now) is None, fp.compatible(was, now)

    # And the thing it is for still bites.
    now["surface"].pop("nfc")
    assert fp.compatible(was, now), "removing a name in a patch release is not compatible"
