"""`vdi2770-validate` is the name on the index, in people's requirements files
and in whatever CI they wired it into. This release renames the distribution to
`vdi2770`, and a rename on a package index is not a rename: the old name keeps
resolving to the last thing published under it, forever, and quietly.

So the old name keeps being published — as metadata and nothing else, depending
on the new one. `pip install vdi2770-validate` installs `vdi2770`, and every
command and import that worked before still works, because they come from the
package that was renamed rather than from a copy.

Metadata and nothing else is not a style choice. Two distributions that both
ship `vdi2770_validate/` would write over each other's files, and pip does not
refuse it -- it installs whichever went last. The only safe shim owns no import
name at all.
"""
import re

import pytest

from conftest import ROOT

SHIM = ROOT / "packages" / "vdi2770-validate" / "pyproject.toml"


@pytest.fixture(scope="module")
def shim():
    assert SHIM.exists(), (
        "the distribution people have installed is not built by this repository "
        "any more, so nothing publishes the name they typed")
    return SHIM.read_text(encoding="utf-8")


def field(text, key):
    m = re.search(rf'^{key} = "([^"]+)"', text, re.M)
    assert m, f"the manifest declares no {key}"
    return m.group(1)


def test_it_is_published_under_the_name_people_already_have(shim):
    assert field(shim, "name") == "vdi2770-validate"


def test_it_carries_the_version_this_release_carries(shim):
    """A shim behind the package it points at is a shim that resolves to an
    older tool for anyone who pins the old name loosely."""
    assert field(shim, "version") == field(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8"), "version")


def test_it_asks_for_the_package_it_redirects_to(shim):
    """And with a floor, not a bare name: `pip install vdi2770-validate` on a
    machine that already has 0.6.x of the reader would otherwise be satisfied by
    what is already there and install nothing."""
    deps = re.search(r"^dependencies = \[(.*?)\]", shim, re.M | re.S)
    assert deps, "the shim depends on nothing, so it redirects to nothing"
    named = re.findall(r'"([^"]+)"', deps.group(1))
    assert len(named) == 1, f"a redirect declares one dependency, not {named}"
    assert re.match(r"^vdi2770\s*>=\s*\d", named[0]), named[0]


def test_it_ships_no_module_of_its_own(shim):
    """The whole hazard. Both distributions shipping `vdi2770_validate/` means
    installing one silently overwrites the other's files, and uninstalling the
    shim then deletes the real tool."""
    m = re.search(r"^packages = \[(.*?)\]", shim, re.M | re.S)
    assert m, "the shim does not say which packages it ships, so setuptools guesses"
    assert not re.findall(r'"([^"]+)"', m.group(1)), (
        "the shim ships a module; it must ship only metadata")


def test_the_floor_it_asks_for_is_this_release_and_not_an_older_one():
    """A floor is what makes a redirect redirect, and `>= anything older` makes
    it a no-op.

    `pip install vdi2770-validate` on a machine that already holds `vdi2770`
    0.6.1 -- the reader, published under that name while it was its own
    distribution -- finds the dependency already satisfied and installs
    *nothing*: no rules, no `vdi2770-validate` command, exit 0. The manifest
    says this in a comment and nothing checked it: lowering the floor to
    `>=0.1` left the whole suite green.

    So the floor is pinned to this release's line rather than merely to
    something this release satisfies. That also keeps it honest at the next
    minor: leave it at `>=0.7` while publishing 0.8.0 and everyone already on
    0.7 gets "requirement already satisfied" instead of the release.
    """
    deps = re.search(r"^dependencies = \[(.*?)\]",
                     SHIM.read_text(encoding="utf-8"), re.M | re.S)
    floor = re.search(r">=\s*([\d.]+)",
                      re.findall(r'"([^"]+)"', deps.group(1))[0]).group(1)
    here = field((ROOT / "pyproject.toml").read_text(encoding="utf-8"), "version")

    def line(v):
        parts = [int(x) for x in re.findall(r"\d+", v)]
        return tuple((parts + [0, 0])[:2])

    assert line(floor) == line(here), (
        f"the redirect asks for vdi2770>={floor} and this release is {here}. "
        f"A floor below this line is satisfied by something already installed, "
        f"so installing the old name installs nothing at all; a floor above it "
        f"cannot be satisfied by anything on the index.")
