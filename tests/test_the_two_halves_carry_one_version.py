"""Two distributions, one version, and an exact pin between them.

The reader is published as `vdi2770` and the rules as `vdi2770-validate`. The
second names the first exactly, both carry the same number, and they go out
under one tag. That is one release in two parts rather than two releases, and it
means a machine holding one of them holds the other it was tested against.

The pin used to be a range, and a range is a standing way to be wrong: `~=0.3.0`
let pip install a reader without the fix the release existed for, so the
correction never reached the people it was written for. An exact pin cannot do
that.

Folding the two into one distribution would remove the pin by removing the
second name, and it was built and then put down for a reason worth keeping
written down. A name on a package index cannot be vacated: whatever was
published under `vdi2770-validate` goes on resolving for anyone who types it.
Move the same import package from one distribution to the other and pip writes
those files and then deletes them -- it installs the new distribution first,
then uninstalls the old one from the old record, which lists the very same
paths. It reports success, satisfies `pip check`, and cannot run.

So the two names stay two distributions, and the last test here is the gate that
keeps them from ever claiming the same import name.
"""
import re

from conftest import ROOT

READER = ROOT / "packages" / "vdi2770" / "pyproject.toml"
RULES = ROOT / "pyproject.toml"


def manifest(path):
    assert path.exists(), (
        f"{path.relative_to(ROOT)} is not in this repository, so nothing here "
        f"builds that distribution")
    return path.read_text(encoding="utf-8")


def field(text, key):
    found = re.search(rf'^{key} = "([^"]+)"', text, re.M)
    assert found, f"the manifest declares no {key}"
    return found.group(1)


def requirements(text):
    """The runtime dependency list, and only that one. Anchored because
    `[project.optional-dependencies]` holds a list two lines away and a loose
    pattern reads that instead."""
    block = re.search(r"^dependencies = \[(.*?)\]", text, re.M | re.S)
    assert block, "the manifest declares no dependencies list"
    return re.findall(r'"([^"]+)"', block.group(1))


def asked_of(text, distribution):
    for spec in requirements(text):
        if re.split(r"[<>=!~\[; ]", spec, maxsplit=1)[0].strip() == distribution:
            return spec
    return None


def import_names(path):
    """What a distribution puts on `sys.path`, read from where it says its
    packages live rather than from its name -- the two are not the same, and
    this whole file is about the case where they diverge."""
    block = re.search(r"^where = \[(.*?)\]", manifest(path), re.M | re.S)
    assert block, f"{path.name} does not say where its packages are found"
    names = set()
    for where in re.findall(r'"([^"]+)"', block.group(1)):
        here = path.parent / where
        assert here.is_dir(), f"{path.name} looks for packages in {where}, which is not there"
        names |= {d.name for d in here.iterdir()
                  if d.is_dir() and (d / "__init__.py").exists()}
    return names


def test_the_reader_is_still_its_own_distribution():
    """It is published separately because it is useful separately: a container
    reader that costs nothing to depend on, for people who want the parsing and
    not the judgement."""
    assert field(manifest(READER), "name") == "vdi2770"


def test_the_rules_keep_the_name_people_already_typed():
    assert field(manifest(RULES), "name") == "vdi2770-validate"


def test_both_halves_carry_the_same_version():
    """The number is the pair. Two halves at different numbers cannot be named
    by one tag, and the pin below would have two answers to choose between."""
    reader, rules = field(manifest(READER), "version"), field(manifest(RULES), "version")
    assert reader == rules, (
        f"the reader is {reader} and the rules are {rules}; they are released "
        f"together under one tag and cannot disagree about which release it is")


def test_the_rules_name_the_reader_exactly_and_not_a_range():
    """A range says "some reader that ought to work". The release was tested
    against one, and that is the one it should install."""
    spec = asked_of(manifest(RULES), "vdi2770")
    assert spec, "the rules do not depend on the reader at all"
    assert re.fullmatch(r"vdi2770==\d+(\.\d+)*", spec), (
        f"the reader is pinned as {spec!r}. Anything but `==` lets pip choose a "
        f"reader this release was never run against, which is how a fix that "
        f"shipped failed to arrive once already.")


def test_the_pin_names_the_version_this_repository_is_publishing():
    """Otherwise the tag names one pair and the wheel installs another."""
    spec = asked_of(manifest(RULES), "vdi2770")
    here = field(manifest(RULES), "version")
    assert spec == f"vdi2770=={here}", (
        f"this repository publishes {here} and pins {spec!r}; the release would "
        f"install a reader it did not build")


def test_the_reader_depends_on_nothing():
    """The reason it is worth publishing on its own. Asserted rather than
    promised in prose."""
    assert requirements(manifest(READER)) == []


def test_the_command_is_not_named_after_the_other_distribution():
    """`pip install vdi2770` gets the reader, which is a library and ships no
    executable. A `vdi2770` command living in the *other* distribution would
    make the obvious install produce a name that is on the index, imports, and
    has nothing to run -- and the message the user gets is `command not found`,
    which points at their PATH rather than at the package they needed.
    """
    block = re.search(r"^\[project\.scripts\]\n(.*?)(?=^\[)",
                      manifest(RULES), re.M | re.S)
    assert block, "the rules declare no command"
    named = re.findall(r"^([\w.\-]+) = ", block.group(1), re.M)
    assert named == ["vdi2770-validate"], (
        f"the commands are {named}; `vdi2770` is the other distribution's name")


def test_neither_half_claims_the_others_import_name():
    """The gate on the failure described at the top of this file.

    Two distributions that both ship `vdi2770_validate/` do not conflict at
    install time -- pip writes whichever went last and says nothing. They
    conflict when one of them is removed, because the record it uninstalls by
    lists files the other one is still using. Keeping the sets disjoint is what
    makes that unreachable, and it is cheap to check and impossible to see by
    reading two manifests side by side.
    """
    reader, rules = import_names(READER), import_names(RULES)
    assert reader and rules, f"one of them ships no package at all: {reader}, {rules}"
    assert not (reader & rules), (
        f"both distributions ship {sorted(reader & rules)}. Installing one "
        f"overwrites the other's files and uninstalling either deletes them.")
