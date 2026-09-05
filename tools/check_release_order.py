"""Refuse to publish the old distribution name before the package it redirects to.

`vdi2770-validate` is what this project published from 0.1.0 to 0.6.0, and after
the rename it is metadata and one dependency: `vdi2770`. Publishing it first
puts a distribution on the index that `pip` cannot resolve, and on PyPI that is
permanent -- the version number cannot be reused.

Nothing in a build catches this. `python -m build` does not resolve runtime
dependencies at all, and `release.yml` installs the package from the working
tree, so the shim's dependency is satisfied everywhere except where it matters.

This gate ran in the other direction until the two distributions became one: the
validator pinned the reader, and the reader had to go first. The pin moved, the
hazard did not, and the sentence that describes the harm did not change either
-- it is still `pip install vdi2770-validate` that ends up unresolvable.

Two questions, cheapest first. The tag history is evidence and needs a checkout
with tags (`fetch-depth: 0`); not being able to see them is a refusal, not a
pass -- the same rule `api_fingerprint._tags()` learned. Then the index, because
a tag is not a publication: it exists the moment it is pushed, while publication
happens afterwards, in a job that can stop at an environment approval or a PyPI
5xx. In that window the tag check is green and the install is broken.
`--offline` says which half ran.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

from packaging.requirements import Requirement
from packaging.version import Version

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import check_version_is_new  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


#: The pin lives with the shim now. Read from the manifest rather than from
#: installed metadata: the question is what is about to be published, and what
#: is installed here is the working tree.
SHIM = ROOT / "packages" / "vdi2770-validate" / "pyproject.toml"


def version_being_released() -> str:
    """What this repository publishes as `vdi2770`."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    found = re.search(r'^version = "([^"]+)"', text, re.M)
    if found is None:
        raise SystemExit("pyproject.toml declares no version")
    return found.group(1)


def floor_of_the_pin() -> str:
    """The lowest `vdi2770` the shim admits."""
    if not SHIM.exists():
        raise SystemExit(f"{SHIM.relative_to(ROOT)} is gone, so nothing publishes "
                         f"the name people already have")
    deps = re.search(r"^dependencies = \[(.*?)\]",
                     SHIM.read_text(encoding="utf-8"), re.M | re.S)
    if deps is None:
        raise SystemExit("the shim declares no dependencies")
    pin = next((Requirement(m) for m in re.findall(r'"([^"]+)"', deps.group(1))
                if Requirement(m).name == "vdi2770"), None)
    if pin is None:
        raise SystemExit("the shim no longer depends on the package it redirects to")
    floors = [s.version for s in pin.specifier
              if s.operator in ("~=", ">=", "==")]
    if not floors:
        raise SystemExit(f"{pin} has no lower bound; any older release satisfies "
                         f"it, so the redirect can resolve to the tool it replaced")
    return max(floors, key=lambda v: tuple(int(x) for x in v.split(".")))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--offline", action="store_true",
                   help="check the tag history only, and say that is what happened")
    a = p.parse_args(argv)
    floor, version = floor_of_the_pin(), version_being_released()
    # Offline and free, and it answers a question the index cannot: a floor above
    # what this repository publishes is unresolvable on the day it is published,
    # however healthy the index looks.
    if Version(floor) > Version(version):
        print(f"the shim asks for vdi2770>={floor} and this repository publishes "
              f"{version}. Nothing on the index can satisfy that.", file=sys.stderr)
        return 1
    got = subprocess.run(["git", "tag", "--list", "v*"],
                         cwd=ROOT, capture_output=True, text=True)
    if got.returncode:
        print("cannot read the tag history, and the release order rests on it. "
              "Fetch tags (`fetch-depth: 0`) and try again.", file=sys.stderr)
        return 1
    tags = {t for t in got.stdout.split() if t}
    if not tags:
        print("this checkout has no `v*` tags at all, which is "
              "indistinguishable from the package never having been released.",
              file=sys.stderr)
        return 1
    if f"v{version}" not in tags:
        print(f"the shim redirects to vdi2770 {version} and v{version} is not "
              f"tagged. Release it first: published this way, "
              f"`pip install vdi2770-validate` cannot resolve, and the version "
              f"number cannot be reused to fix it.", file=sys.stderr)
        return 1
    if a.offline:
        print(f"v{version} is tagged. Not asking the index whether it was "
              f"published: --offline", file=sys.stderr)
        return 0
    try:
        have = check_version_is_new.published("vdi2770")
    except Exception as e:                       # noqa: BLE001 - the network is the risk
        print(f"v{version} is tagged, but the index could not be asked whether "
              f"it was published: {e}. Refusing rather than guessing -- a "
              f"redirect published against a package that is not there cannot "
              f"be fixed under this version number.", file=sys.stderr)
        return 1
    if not check_version_is_new.holds(have, version):
        print(f"v{version} is tagged but vdi2770 {version} is not on the index. "
              f"A tag is not a publication: the publish job may still be waiting "
              f"for an environment approval, or have failed. Publish it first -- "
              f"`pip install vdi2770-validate` cannot resolve until it is there, "
              f"and this version number does not come back.", file=sys.stderr)
        return 1
    print(f"v{version} is tagged and vdi2770 {version} is on the index.",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
