"""Refuse to publish the rules before the reader they pin.

`vdi2770-validate` is this project's rule set and `vdi2770` is the reader it is
built on. They are one release in two parts -- same version, one tag, an exact
pin between them -- and the pin decides the order: publishing the rules first
puts a distribution on the index `pip` cannot resolve, and on PyPI that is
permanent, because the version number cannot be reused.

Nothing in a build catches this. `python -m build` does not resolve runtime
dependencies at all, and `release.yml` installs the package from the working
tree, so the pin is satisfied everywhere except where it matters.

Three questions, cheapest first.

The pin is exact, and that gives this gate a question it could not ask while the
pin was a range: not *is the pinned version old enough to exist* but *is it this
release*. A range could only be wrong in one direction -- ask for more than
exists -- and the stale half was invisible, because `>=0.6.2` is satisfied by
0.7.0 and by 0.6.2 alike. An exact pin naming any other version means the tag
and the wheel disagree about which pair went out, and no index can report that.

Then the tag history, which is evidence and needs a checkout with tags
(`fetch-depth: 0`); not being able to see them is a refusal, not a pass -- the
same rule `api_fingerprint._tags()` learned. Then the index, because a tag is
not a publication: it exists the moment it is pushed, while publication happens
afterwards, in a job that can stop at an environment approval or a PyPI 5xx. In
that window the tag check is green and the install is broken. `--offline` says
which half ran.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

from packaging.requirements import Requirement

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import check_version_is_new  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The distribution whose publication this gate holds back, and the one whose
#: absence would make it unresolvable.
RULES = "vdi2770-validate"
READER = "vdi2770"


def _manifest() -> str:
    """Read from the manifest rather than from installed metadata: the question
    is what is about to be published, and what is installed here is the working
    tree."""
    return (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def version_being_released() -> str:
    """What this repository publishes as `vdi2770-validate`."""
    found = re.search(r'^version = "([^"]+)"', _manifest(), re.M)
    if found is None:
        raise SystemExit("pyproject.toml declares no version")
    return found.group(1)


def pinned_reader() -> str:
    """The one `vdi2770` this release installs -- and it has to be one.

    Anchored to the `dependencies = [...]` list. `name = "vdi2770-validate"` is
    declared above it and starts with the same characters, so a pattern that
    merely looks for the reader's name finds the distribution's own name first.
    """
    deps = re.search(r"^dependencies = \[(.*?)\]", _manifest(), re.M | re.S)
    if deps is None:
        raise SystemExit("pyproject.toml declares no dependencies list")
    pin = next((Requirement(m) for m in re.findall(r'"([^"]+)"', deps.group(1))
                if Requirement(m).name == READER), None)
    if pin is None:
        raise SystemExit(f"this release no longer depends on {READER}, which is "
                         f"the half of it that does the reading")
    wanted = [s.version for s in pin.specifier if s.operator == "=="]
    if len(list(pin.specifier)) != 1 or len(wanted) != 1 or wanted[0].endswith(".*"):
        raise SystemExit(
            f"the reader is asked for as `{pin}`, which is not pinned exactly. "
            f"Anything else lets pip choose a reader this release was never run "
            f"against, and leaves this gate no single version to check the "
            f"order of.")
    return wanted[0]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--offline", action="store_true",
                   help="check the tag history only, and say that is what happened")
    a = p.parse_args(argv)
    pinned, version = pinned_reader(), version_being_released()
    # Offline, free, and it answers a question the index cannot: whichever way
    # the two numbers differ, the pair named by the tag is not the pair the
    # wheel installs, and every version PyPI holds could be healthy.
    if pinned != version:
        print(f"the rules pin {READER}=={pinned} and this repository publishes "
              f"{version}. One tag names one pair; these are two.", file=sys.stderr)
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
              "indistinguishable from the reader never having been released.",
              file=sys.stderr)
        return 1
    if f"v{version}" not in tags:
        print(f"the rules pin {READER}=={pinned} and v{version} is not tagged. "
              f"The reader goes first: published this way, "
              f"`pip install {RULES}` cannot resolve, and the version "
              f"number cannot be reused to fix it.", file=sys.stderr)
        return 1
    if a.offline:
        print(f"v{version} is tagged. Not asking the index whether it was "
              f"published: --offline", file=sys.stderr)
        return 0
    try:
        have = check_version_is_new.published(READER)
    except Exception as e:                       # noqa: BLE001 - the network is the risk
        print(f"v{version} is tagged, but the index could not be asked whether "
              f"{READER} {version} was published: {e}. Refusing rather than "
              f"guessing -- rules published against a reader that is not there "
              f"cannot be fixed under this version number.", file=sys.stderr)
        return 1
    if not check_version_is_new.holds(have, version):
        print(f"v{version} is tagged but {READER} {version} is not on the index. "
              f"A tag is not a publication: the publish job may still be waiting "
              f"for an environment approval, or have failed. Publish it first -- "
              f"`pip install {RULES}` cannot resolve until it is there, "
              f"and this version number does not come back.", file=sys.stderr)
        return 1
    print(f"v{version} is tagged and {READER} {version} is on the index.",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
