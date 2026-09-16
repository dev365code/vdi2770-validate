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
from packaging.version import Version

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
    stated = _declared_dependencies(_manifest())
    pin = next((r for r in stated if r.name == READER), None)
    if pin is None:
        raise SystemExit(f"this release no longer depends on {READER}, which is "
                         f"the half of it that does the reading. It declares "
                         f"{[str(r) for r in stated]}")
    floor = floor_of(str(pin))
    if floor is None:
        raise SystemExit(
            f"the reader is asked for as `{pin}`, which lets a resolver choose "
            f"an engine this release was never run against. One `==` or one "
            f"`>=`, and nothing else: a bare name, a ceiling, a compatible "
            f"release or an exclusion each leave pip free to install something "
            f"older than the release this stands for, which is the state the "
            f"version check refuses at run time and a release should never "
            f"create.")
    return floor


def floor_of(requirement: str):
    """The version below which this requirement cannot go, or `None`.

    Before the merge the rules named the reader with an exact `==`, because the
    two carried code that had to match. The alias is two lines now and there is
    no pair to hold together, so the requirement is a floor at its own version:
    installing it can never leave an engine older than the release it stands
    for. `==` still says that, more strongly, so both are read the same way.

    Everything else is refused, and each for the same reason: `>` excludes the
    release being made, a ceiling or a compatible-release operator lets a
    resolver walk down to an engine nobody ran this against, an exclusion says
    nothing about the bottom, and a wildcard is not a version.
    """
    try:
        parsed = Requirement(requirement)
    except Exception:                            # noqa: BLE001 - any malformed spelling
        return None
    only = list(parsed.specifier)
    if len(only) != 1 or only[0].operator not in ("==", ">="):
        return None
    if only[0].version.endswith(".*"):
        return None
    return only[0].version


def _declared_dependencies(text: str):
    r"""The `[project] dependencies` array, as requirements.

    Not `\[(.*?)\]`. A requirement carries its extras in brackets, so
    `"vdi2770[validate]>=0.8.0"` puts a `]` inside the array before the array
    ends -- measured, that pattern returned `'"vdi2770[validate'` and no
    requirements at all, and this gate then refused every release with *this
    release no longer depends on vdi2770*, about a manifest whose first
    dependency is that name. It stands between the engine's publish and the
    alias's, so the refusal would have landed with half a release on the index
    under a version number that does not come back.

    Nothing noticed because every test here rewrites the dependency into
    `vdi2770==0.7.0` first -- no extra, exact pin, the shape from before the
    merge -- so the manifest that ships was read by nothing.

    Scanned with the quoting rules applied rather than parsed as TOML: the
    release job installs `packaging` and not a TOML reader, and `tomllib` is
    3.11 and later while this gate is also run by a suite that answers on 3.9.
    """
    start = re.search(r"^dependencies = \[", text, re.M)
    if start is None:
        raise SystemExit("pyproject.toml declares no dependencies list")
    found, quote, current = [], None, []
    for ch in text[start.end():]:
        if quote:
            if ch == quote:
                found.append("".join(current))
                quote, current = None, []
            else:
                current.append(ch)
        elif ch in "\"\'":
            quote = ch
        elif ch == "]":
            break
    made = []
    for one in found:
        try:
            made.append(Requirement(one))
        except Exception:                        # noqa: BLE001 - not a requirement
            continue
    return made


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--offline", action="store_true",
                   help="check the tag history only, and say that is what happened")
    a = p.parse_args(argv)
    pinned, version = pinned_reader(), version_being_released()
    # Offline, free, and it answers a question the index cannot: whichever way
    # the two numbers differ, the pair named by the tag is not the pair the
    # wheel installs, and every version PyPI holds could be healthy.
    # Compared as versions, not as text. `>=0.7` and `0.7.0` are one release
    # under PEP 440, and refusing that pair would be refusing a spelling. What
    # must not pass is a floor at a *different* release: below this one, the
    # alias could resolve to an engine older than the release it stands for.
    if Version(pinned) != Version(version):
        print(f"the rules floor {READER} at {pinned} and this repository "
              f"publishes {version}. One tag names one pair; these are two, and "
              f"a floor below this release lets the alias resolve to an engine "
              f"older than the release it stands for.", file=sys.stderr)
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
        print(f"the rules floor {READER} at {pinned} and v{version} is not tagged. "
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
