#!/usr/bin/env python3
"""Install this project the way people actually have it, and then run it.

Not `make check`. This needs the network and a clean interpreter per case, and
it takes minutes rather than seconds -- so it runs where those are already true
and where being wrong is expensive: before a tag publishes anything, and by hand
whenever the packaging shape is touched.

    python3 tools/check_upgrade_paths.py            # every case
    python3 tools/check_upgrade_paths.py --case 2   # one of them

**The verdict is execution.** `pip check` is not a trust signal and this file
exists partly to keep that in front of whoever reads it: a distribution can be
uninstalled out from under another one, leaving an install whose metadata is
consistent and whose command is gone, and `pip check` reports that as fine. So
every case here ends by running the console script and reading what it printed.
What `pip check` said is recorded beside it, never instead of it.

The paths a person is actually on are the ones that get checked. A clean
install is the easy half; the half that has ever gone wrong here is upgrading
over what somebody already had.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

ROOT = Path(__file__).resolve().parent.parent

#: The command a user types, and what it must print. Read from the installed
#: package rather than hard-coded, so a release cannot pass by agreeing with a
#: number written here.
COMMAND = "vdi2770-validate"
RULES = "vdi2770-validate"

#: What a refusal to judge begins with. Spelled here rather than
#: imported: this file runs against installed copies of the tool, and
#: importing the tool it is testing would ask this interpreter what the
#: other one should have said.
MARKER = "vdi2770-validate: INSTALLATION"


#: Everything here starts a fresh interpreter to find out what an install can
#: do, and the parent's `PYTHONPATH` would let this tree answer for it -- the
#: imports would resolve against the source and the case would pass over a venv
#: holding nothing. `PIP_*` settings would steer the installs the same way.
_CLEAN = {k: v for k, v in os.environ.items()
          if not k.startswith(("PYTHON", "PIP_"))} | {"PYTHONDONTWRITEBYTECODE": "1"}


#: Where a virtual environment keeps its executables. `bin` everywhere except
#: Windows, which uses `Scripts` -- and this file spells the path itself rather
#: than asking the environment, so the assumption travelled unstated until a
#: Windows row ran the one test that builds a real directory.
SCRIPTS = "Scripts" if os.name == "nt" else "bin"


def run(*args, **kw):
    kw.setdefault("env", _CLEAN)
    return subprocess.run(args, capture_output=True, text=True, **kw)


def installed_command(directory: Path, command: str):
    """The file pip wrote for a console script, or `None`.

    Windows gets `vdi2770-validate.exe`, and asking whether
    `Scripts/vdi2770-validate` exists there answers no. `CreateProcess` appends
    the extension when running it, which is why `pip` and `python` in this class
    work unqualified -- so the mistake shows up only in the one place that asks
    a question instead of running something, and it answers "not installed at
    all" about an installation that has it. This gate has never run on Windows
    until now, and an assertion of absence that is right for the wrong reason is
    the shape this project keeps finding.

    Extensions rather than a glob: `vdi2770-validate.exe` is the command and
    `vdi2770-validate-script.py` beside it is not, and neither is a name that
    merely starts the same way.
    """
    for suffix in ("", ".exe", ".bat", ".cmd"):
        here = directory / (command + suffix)
        if here.exists():
            return here
    return None


class Env:
    """One throwaway interpreter, with the pip that people have."""

    def __init__(self, root: Path):
        self.root = root
        run(sys.executable, "-m", "venv", str(root), check=False)
        self.pip = str(root / SCRIPTS / "pip")
        self.python = str(root / SCRIPTS / "python")
        run(self.pip, "install", "-q", "--upgrade", "pip")

    def install(self, *spec):
        return run(self.pip, "install", "-q", *spec)

    def versions(self) -> dict:
        out = run(self.pip, "list", "--format=json").stdout
        return {p["name"].lower(): p["version"] for p in json.loads(out or "[]")}

    def check(self) -> str:
        done = run(self.pip, "check")
        return (done.stdout + done.stderr).strip() or "(silent)"

    def imports(self, name):
        """Whether a fresh interpreter in this environment can import it.

        A method on the environment rather than a call to `run` beside the
        other assertions: the harness that proves this gate can fail replaces
        `run` wholesale, so an assertion phrased through it is one no test can
        break -- deleting these lines left every gate test green.
        """
        done = run(self.python, "-c", f"import {name}")
        return done.returncode, (done.stdout + done.stderr).strip()

    def command(self, *args):
        exe = installed_command(self.root / SCRIPTS, COMMAND)
        if exe is None:
            return None, f"{COMMAND} is not installed at all"
        done = run(str(exe), *args)
        return done.returncode, (done.stdout + done.stderr).strip()


def expect(condition, said: str):
    if not condition:
        raise AssertionError(said)


#: The releases whose rules named the reader by *range* rather than exactly.
#: One of these has to be installable for the case below to have a mismatch to
#: upgrade out of. Several, because a version can be yanked or deleted, and a
#: release blocked by the disappearance of one number on an index this project
#: does not control is a release blocked for a reason that has nothing to do
#: with it -- which is what the hard-coded `0.6.0` here did.
RANGE_ERA = ("0.6.0", "0.5.1", "0.5.0", "0.4.0")

#: Readers old enough to have no `vdi2770.validate` at all — every release
#: before the merge. One of these has to be installable for the case that asks
#: what happens when the engine is older than the rules that alias it.
OLD_READERS = ("0.4.0", "0.5.0", "0.5.1", "0.6.0", "0.7.0")


#: Two containers that ship here, and what this tool has to say about them. A
#: verdict in both directions, because either one alone is satisfied by a
#: program that answers the same way to everything -- and a release that exits
#: 0 on every input is precisely the shape this gate stands in front of.
VERDICTS = (("corpus/examples/container/documentcontainer.zip", 0),
            ("corpus/examples/missingdocuments/folders.zip", 1))


def both_halves_run(env: Env, why: str) -> None:
    """The assertion this file is for: the thing a person types *works*.

    Working is three questions and the first version asked one of them. That it
    starts -- both import names, because the reader is published for use on its
    own, and the console script, because an entry point is a file like any
    other and an uninstall can delete it while every import still resolves.
    That it knows what it is -- `--version` has to print the version that is
    installed, not merely print something. And that it judges -- a container
    with an error in it has to come back as an error and a clean one as clean.

    The first version asked only whether the command exited 0 and printed a
    non-empty line. A build whose entry point printed "the rule catalogue could
    not be loaded; validating nothing", printed a version that was not
    installed, and exited 0 on every input passed all of it, and this gate is
    the last thing that runs before a release is published.
    """
    for name in ("vdi2770", "vdi2770_validate"):
        code, said = env.imports(name)
        expect(code == 0, f"{why}: import {name} failed\n{said}")

    code, said = env.command("--version")
    expect(code == 0, f"{why}: `{COMMAND} --version` gave {code}: {said}")
    installed = env.versions().get("vdi2770-validate")
    expect(installed, f"{why}: nothing named vdi2770-validate is installed")
    expect(installed in said.split(), (
        f"{why}: `{COMMAND} --version` says {said!r} and what is installed is "
        f"{installed}. A build that reports a version it is not is a build "
        f"whose reports name an engine nobody has. Compared as a whole word: "
        f"{installed} is a substring of {installed}.post1, and a build "
        f"reporting that passed the check written to catch it."))

    for path, wanted in VERDICTS:
        target = str(ROOT / path)
        code, said = env.command("check", target)
        expect(code == wanted, (
            f"{why}: `{COMMAND} check {path}` exited {code} and this container "
            f"is a {'clean' if wanted == 0 else 'failing'} one. A program that "
            f"answers the same way to everything answers nothing."))


def _floor_of(requirement: str):
    """The version this requirement cannot go below, or `None`.

    The same question `tools/check_release_order.py` asks of the manifest, put
    to the metadata of what is actually installed. One `==` or one `>=`;
    anything else -- a bare name, a ceiling, a compatible release -- lets a
    resolver walk down to an engine nobody ran this against.
    """
    try:
        only = list(Requirement(requirement).specifier)
    except Exception:                            # noqa: BLE001 - any spelling
        return None
    if len(only) != 1 or only[0].operator not in ("==", ">="):
        return None
    return None if only[0].version.endswith(".*") else only[0].version


def _the_one_before():
    """The newest published `vdi2770-validate` older than this tree's version.

    Asked of the index, because "what somebody already has" is a fact about the
    index and not about this repository. Falling back to a hard-coded number
    would be the defect this file removed from `case_2`: a version yanked from
    an index this project does not control would block a release for a reason
    that has nothing to do with it.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    import check_version_is_new

    ours = Version(_version_in_the_tree())
    older = sorted((Version(v) for v in check_version_is_new.published(RULES)
                    if Version(v) < ours), reverse=True)
    if not older:
        raise AssertionError(
            f"the index has no {RULES} older than {ours}, so there is no "
            f"installation for this case to upgrade from")
    return str(older[0])


def _version_in_the_tree() -> str:
    found = re.search(r'^version = "([^"]+)"',
                      (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    if found is None:
        raise AssertionError("pyproject.toml declares no version")
    return found.group(1)

def case_1_clean(env: Env) -> str:
    """Nothing installed, one command. What a first-time reader does."""
    env.install("vdi2770-validate")
    have = env.versions()
    expect("vdi2770" in have and "vdi2770-validate" in have,
           f"a clean install did not bring both halves: {have}")
    expect(have["vdi2770"] == have["vdi2770-validate"],
           f"the halves arrived at different versions: {have}")
    both_halves_run(env, "clean install")
    return f"both at {have['vdi2770']}; pip check: {env.check()}"


def case_2_upgrade_from_0_6_0(env: Env) -> str:
    """The upgrade that a version range would have got wrong.

    0.6.0 asked for `vdi2770~=0.4.0`, so this starts from a pair that is
    genuinely mismatched -- reader 0.4.0 under rules 0.6.0 -- and the question
    is whether one `-U` leaves a working tool rather than a half-moved one.
    """
    tried = []
    for spec in RANGE_ERA:
        done = env.install(f"vdi2770-validate=={spec}")
        if done.returncode:
            tried.append(f"{spec}: the index would not serve it")
            continue
        before = env.versions()
        if before.get("vdi2770") and before["vdi2770"] != before["vdi2770-validate"]:
            break
        tried.append(f"{spec}: arrived with a matching pair, so there is no "
                     f"mismatch here to upgrade out of")
    else:
        # Never a silent skip. A case that returns early and reports success is
        # the shape this whole file exists to refuse.
        expect(False, "no release from the range era could be installed, so the "
                      "upgrade this case is about cannot be started: "
                      + "; ".join(tried))
    before = env.versions()
    # Older, not `== "0.4.0"`. The exact number is a fact about an index this
    # repository does not control: a `vdi2770 0.4.1` upload satisfies `~=0.4.0`
    # and would turn this gate red -- blocking a release for a reason that has
    # nothing to do with the release. What the case is about is the mismatch,
    # and the mismatch is that the pair does not match.
    expect(before.get("vdi2770") and before["vdi2770"] != before["vdi2770-validate"],
           f"0.6.0 no longer arrives with a reader of its own vintage; this "
           f"case is about a pair that a range left mismatched: {before}")
    done = env.install("-U", "vdi2770-validate")
    expect(done.returncode == 0, f"the upgrade itself failed:\n{done.stderr}")
    after = env.versions()
    expect(after["vdi2770"] == after["vdi2770-validate"],
           f"the upgrade moved one half and not the other: {after}")
    both_halves_run(env, "upgrade from 0.6.0")
    return (f"{before['vdi2770-validate']}+{before['vdi2770']} -> "
            f"{after['vdi2770-validate']}+{after['vdi2770']}; pip check: {env.check()}")


def case_3_the_engine_cannot_be_older_than_the_alias(env: Env) -> str:
    """What the installed metadata asks for, not what the repository declares.

    Until 0.8.0 this was an exact pin, and an exact pin is what made the pair
    impossible to half-move. There is no pair now -- the alias is two lines and
    the rules live in the engine -- so the requirement is a floor at the alias's
    own version, which says the same thing that still needs saying: installing
    it can never leave an engine older than the release it stands for.

    Checked against the index rather than against `pyproject.toml` because what
    a release shipped and what this tree declares are different questions and
    only the first reaches anybody. This case went red the day 0.8.0 was
    published, which is the point of asking the index.

    It is *not* checked here that a mixed install is refused, because it is
    not: pip prints its conflict line and exits 0. `pip check` goes red, which
    is the one place in this whole area where it says something true — and a
    thing that has to be run separately is not a refusal.
    """
    env.install("vdi2770-validate")
    have = env.versions()
    done = run(env.python, "-c",
               "import importlib.metadata as m;"
               "print([r for r in m.requires('vdi2770-validate') or []"
               " if r.startswith('vdi2770')][0])")
    expect(done.returncode == 0, f"could not read the installed metadata: {done.stderr}")
    asked = done.stdout.strip()
    floor = _floor_of(asked)
    expect(floor is not None,
           f"the installed rules ask for {asked!r}, which lets a resolver "
           f"choose an engine the release was never run against")
    expect(Version(floor) >= Version(have["vdi2770-validate"]),
           f"the installed rules floor the engine at {floor} while standing "
           f"for {have['vdi2770-validate']}, so installing them can leave an "
           f"engine older than the release they are")
    # This case installs a whole working pair on its way to reading one field,
    # so it asks the same question the others do. A case that installs and
    # never runs anything is a case that would not notice the install being
    # broken in the way this file exists to notice.
    both_halves_run(env, "the pinned pair")
    return f"{asked}; pip check: {env.check()}"


def case_4_the_release_being_made(env: Env, wheels: str) -> str:
    """The artefacts about to be published, installed over what is published now.

    This is the only case that is about *this* release rather than about the
    index as it already stands, which is why it takes the built wheels rather
    than a name. A gate that runs before publishing and only reads the index
    checks a state nobody is changing.

    It upgrades rather than installing clean, because upgrading is where the
    failures have been: a range that could not reach its own fix, and a
    distribution uninstalled out from under the one that replaced it.
    """
    # The newest published release *older than the one being built*, named
    # rather than inferred. `pip install vdi2770-validate` gives whatever the
    # index holds, and the moment this release is published that is this
    # release: the upgrade then moves nothing and this case fails saying the
    # wheels are not newer than the index. It went red exactly that way once
    # 0.8.0 was published.
    env.install(f"vdi2770-validate=={_the_one_before()}")
    before = env.versions()
    # `--pre`, because the ordinary state of this tree is a `.devN` and pip
    # will not select one otherwise: without it this case fails on every
    # working tree and blames the wheels. `--no-index`, because `--find-links`
    # is additive and "the release being made" could otherwise be satisfied by
    # what is already published.
    done = env.install("-U", "--pre", "--no-index", "--find-links", wheels,
                       "vdi2770-validate")
    expect(done.returncode == 0, f"the upgrade to the built wheels failed:\n{done.stderr}")
    after = env.versions()
    expect(after["vdi2770"] != before["vdi2770"] or
           after["vdi2770-validate"] != before["vdi2770-validate"],
           f"nothing moved; the wheels in {wheels} are not newer than the index")
    expect(after["vdi2770"] == after["vdi2770-validate"],
           f"the release moves one half and not the other: {after}")
    both_halves_run(env, "upgrade to the release being made")
    return (f"{before['vdi2770-validate']}+{before['vdi2770']} -> "
            f"{after['vdi2770-validate']}+{after['vdi2770']}; pip check: {env.check()}")


def _from_the_wheels(env: Env, wheels: str, *spec):
    """Install from the built wheels and nowhere else.

    `--pre`, because the ordinary state of this tree is a `.devN` and pip will
    not select one otherwise. `--no-index`, because `--find-links` is additive
    and "the release being made" could otherwise be satisfied by what is already
    published.

    The parser first, from the index, because `--no-index` cuts off the ordinary
    dependency along with the published copies of what is being tested. It is
    the same wheel a user's `pip install` would fetch, and fetching it here
    keeps the two names under test coming from one place only.
    """
    if any("[validate]" in s or s.startswith("vdi2770-validate") for s in spec):
        env.install("xmlschema==4.2.0")
    return env.install("--pre", "--no-index", "--find-links", wheels, *spec)


def case_5_the_new_world_installs_the_old_name(env: Env, wheels: str) -> str:
    """Nothing here has ever seen the old arrangement, and somebody types the
    old name.

    The row this case replaces did not exist while the two distributions
    carried code that had to match, and it is the one that would have caught
    the failure: an old name that resolves to something older drags the engine
    back with it. What has to be true is that the reader's version does not go
    down.
    """
    done = _from_the_wheels(env, wheels, "vdi2770")
    expect(done.returncode == 0, f"the reader would not install:\n{done.stderr}")
    before = env.versions()
    done = _from_the_wheels(env, wheels, "vdi2770-validate")
    expect(done.returncode == 0, f"the old name would not install:\n{done.stderr}")
    after = env.versions()
    expect(after["vdi2770"] == before["vdi2770"], (
        f"installing the old name moved the reader from {before['vdi2770']} to "
        f"{after['vdi2770']}. An old engine signing verdicts is what this whole "
        f"arrangement exists to make unreachable."))
    both_halves_run(env, "the new world, then the old name")
    return f"reader stayed at {after['vdi2770']}; pip check: {env.check()}"


def case_6_both_names_at_once(env: Env, wheels: str) -> str:
    """The same question with the resolver given both names in one command,
    where backtracking has somewhere to go."""
    done = _from_the_wheels(env, wheels, "vdi2770")
    expect(done.returncode == 0, f"the reader would not install:\n{done.stderr}")
    before = env.versions()
    done = _from_the_wheels(env, wheels, "vdi2770-validate", "vdi2770")
    expect(done.returncode == 0, f"the pair would not install:\n{done.stderr}")
    after = env.versions()
    expect(after["vdi2770"] == before["vdi2770"], (
        f"asking for both moved the reader from {before['vdi2770']} to "
        f"{after['vdi2770']}"))
    both_halves_run(env, "both names in one command")
    return f"reader stayed at {after['vdi2770']}; pip check: {env.check()}"


def case_7_removing_the_old_name_leaves_the_tool(env: Env, wheels: str) -> str:
    """Uninstalling the alias must not take the tool with it.

    This is the failure the whole arrangement is built around, asked directly:
    two distributions that share a path do not conflict when installed and
    conflict when either is removed. The alias owns `vdi2770_validate/` and
    nothing else, so removing it leaves the engine untouched — and the way to
    know is to run the tool afterwards rather than to read a record.
    """
    done = _from_the_wheels(env, wheels, "vdi2770-validate")
    expect(done.returncode == 0, f"the install failed:\n{done.stderr}")
    done = run(env.pip, "uninstall", "-y", "vdi2770-validate")
    expect(done.returncode == 0, f"the uninstall failed:\n{done.stderr}")
    left = env.versions()
    expect("vdi2770" in left, "removing the alias took the reader with it")
    # The command goes with it -- that script belongs to the alias, and pip
    # removing what it installed is the correct behaviour rather than the
    # failure. What must survive is the engine, and the way to know is to run
    # it: the whole point of this arrangement is that removing one distribution
    # cannot reach into the other.
    for name in ("vdi2770", "vdi2770.validate"):
        code, said = env.imports(name)
        expect(code == 0, f"{name} no longer imports after the alias was removed: {said}")
    # Both directions. One of them alone is satisfied by a program that answers
    # the same way to everything, which is the shape this file refuses
    # everywhere else and had let through here.
    for path, wanted in VERDICTS:
        done = run(env.python, "-m", "vdi2770.validate", "check", str(ROOT / path))
        expect(done.returncode == wanted, (
            f"after the alias was removed, `check {path}` exited "
            f"{done.returncode} and this container is a "
            f"{'clean' if wanted == 0 else 'failing'} one\n{done.stderr[-400:]}"))
    return f"alias gone, reader {left['vdi2770']} still judges; pip check: {env.check()}"


def case_8_the_reader_alone_declines_by_name(env: Env, wheels: str) -> str:
    """`pip install vdi2770` and then ask for a schema check.

    The reader is published as a library with no dependencies, and the schema
    parser is an extra — so a machine that installs the reader alone and reaches
    for a schema check has done nothing wrong and must not be handed a
    traceback. What it gets is `X0`, which the report itself calls this tool
    declining to look rather than a verdict on the container.
    """
    done = _from_the_wheels(env, wheels, "vdi2770")
    expect(done.returncode == 0, f"the reader would not install:\n{done.stderr}")
    installed = env.versions()
    expect("xmlschema" not in installed, (
        f"`pip install vdi2770` brought {installed.get('xmlschema')} with it; the "
        f"page for that distribution says it has no dependencies"))
    done = run(env.python, "-c",
               "import sys, json;"
               "from vdi2770.validate.runner import check_file;"
               "r = check_file(sys.argv[1]);"
               "print(json.dumps([f.rule.id for f in r.findings]))",
               str(ROOT / "corpus" / "examples" / "container" / "documentcontainer.zip"))
    expect(done.returncode == 0, (
        f"a reader-only install raised instead of reporting:\n{done.stderr[-800:]}"))
    expect("X0" in done.stdout, (
        f"the schema check without its parser reported {done.stdout.strip()}; "
        f"`X0` is how this tool says it declined to look"))
    return f"reader {installed['vdi2770']} alone, schema check reports X0"


def case_9_the_extra_runs_without_the_alias(env: Env, wheels: str) -> str:
    """`pip install vdi2770[validate]` — the whole tool, under its own name."""
    done = _from_the_wheels(env, wheels, "vdi2770[validate]")
    expect(done.returncode == 0, f"the extra would not install:\n{done.stderr}")
    installed = env.versions()
    expect("xmlschema" in installed, "the extra did not bring the parser")
    expect("vdi2770-validate" not in installed, (
        "the extra pulled the alias in; the point of it is that the tool is one "
        "distribution"))
    # And therefore no command: the console script is declared by the alias.
    # Both pages say so and tell the reader to run this install as a module,
    # so if a command ever does appear here those sentences have gone stale --
    # which is the only reason this asserts an absence.
    code, said = env.command("--version")
    expect(code is None, (
        f"`vdi2770[validate]` installed a `{COMMAND}` command. That is not "
        f"wrong in itself, but both public pages tell the reader this install "
        f"has no command and to use `python -m vdi2770.validate`; they now say "
        f"something untrue. It answered: {said[:200]}"))
    for path, wanted in VERDICTS:
        done = run(env.python, "-m", "vdi2770.validate", "check", str(ROOT / path))
        expect(done.returncode == wanted, (
            f"`python -m vdi2770.validate check {path}` exited "
            f"{done.returncode}, wanted {wanted}"))
    return f"vdi2770[validate] {installed['vdi2770']} judges both ways, no alias"


def case_10_the_alias_brings_the_extra(env: Env, wheels: str) -> str:
    """And the old name gets you all of it, which is what makes it an upgrade
    path rather than a tombstone."""
    done = _from_the_wheels(env, wheels, "vdi2770-validate")
    expect(done.returncode == 0, f"the alias would not install:\n{done.stderr}")
    installed = env.versions()
    expect("xmlschema" in installed, (
        "the alias did not bring the parser, so the schema check would report "
        "X0 on a machine that typed the documented command"))
    both_halves_run(env, "the old name brings the whole tool")
    return (f"alias {installed['vdi2770-validate']} + reader {installed['vdi2770']} "
            f"+ parser {installed['xmlschema']}")


def case_11_an_old_reader_under_new_rules_refuses(env: Env, wheels: str) -> str:
    """The state the version check exists for, end to end.

    An engine older than the rules cannot even be imported by them — `model`
    reaches for names the old reader does not export — so the command used to
    die at import with a traceback and `rc=1`, which is this tool's code for *a
    container has findings*. The refusal has to come first and say what it is.
    """
    # Whichever of the old readers the index still serves. A single hard-coded
    # number here is the defect this file removed from `case_2` and then kept
    # one function further down: a version yanked from an index this project
    # does not control would block a release for a reason that has nothing to
    # do with it.
    tried = []
    for spec in OLD_READERS:
        done = env.install(f"vdi2770=={spec}")
        if done.returncode == 0:
            break
        tried.append(spec)
    else:
        expect(False, ("no reader old enough to lack `vdi2770.validate` could be "
                       f"installed, so the state this case is about cannot be "
                       f"built: tried {tried}"))
    done = _from_the_wheels(env, wheels, "--no-deps", "vdi2770-validate")
    expect(done.returncode == 0, f"the alias would not install:\n{done.stderr}")
    # `--no-deps` on the alias leaves the old reader in place, which is the
    # state; installed normally the resolver would fix it, and there would be
    # nothing here to see.
    code, said = env.command("--version")
    expect(code == 3, (
        f"`{COMMAND} --version` gave {code} on a split installation, and 3 is "
        f"the code that says this tool refused to judge. {said[:200]}"))
    expect(MARKER in said, (
        f"the refusal does not begin `{MARKER}`, so a log cannot tell it from a "
        f"container that failed: {said[:200]}"))
    expect("Traceback" not in said, f"it died instead of refusing: {said[:400]}")
    # And the other door. Nothing asked this until a review did, and the answer
    # was an exit of 1 with a `__spec__ is None` ValueError -- the code that
    # says a container has findings, from a state where nothing was read.
    done = run(env.python, "-m", "vdi2770_validate", "--version")
    both = (done.stdout + done.stderr).strip()
    expect(done.returncode == 3, (
        f"`python -m vdi2770_validate` gave {done.returncode} on a split "
        f"installation: {both[:300]}"))
    expect(MARKER in both, f"and did not say which kind of 3: {both[:300]}")
    expect("Traceback" not in both, f"it died instead of refusing: {both[:400]}")
    expect(not done.stdout.strip(), (
        f"it wrote to stdout while refusing: {done.stdout[:200]}"))
    return "an engine older than the rules is refused at both doors, not tracebacked"


#: Every `pip install` the documentation gives. Read from the page rather than
#: repeated here: a command that appears on the front door and not in this list
#: is one nobody tested, and the list going stale is the ordinary way that
#: happens.
def documented_installs():
    import re
    page = (ROOT / "README.md").read_text(encoding="utf-8")
    # Anywhere on the page, quoted or not, mid-sentence or in a block. The
    # first version anchored on end-of-line and missed
    # `pip install "vdi2770[validate]"` -- which is written inside a sentence,
    # in quotes, and is the only documented form that yields a tool able to
    # check a schema. A list that quietly omits the interesting command is
    # worse than no list.
    found = re.findall(r"""pip install (?:-U )?["']?(vdi2770[A-Za-z0-9_.\[\]-]*)["']?""", page)
    return sorted(set(found))


def case_12_the_window(env: Env, wheels: str) -> str:
    """The minutes between publishing the engine and publishing the alias.

    The order is forced: the alias asks for `vdi2770[validate]` at its own
    version, so it cannot resolve until the engine is on the index. Between the
    two uploads the index serves a new engine and an old alias, and this asks
    what the documented commands do in that gap.

    The bar is not "harmless". A machine that already had 0.7 has the old alias
    -- which was real code with rules of its own -- and moving the engine
    forward under it is exactly the state the version check exists for. What
    has to be true is that every documented command leaves either a tool that
    runs or a refusal that says so: never a wrong verdict, and never a
    traceback.

    Simulated by giving pip the built engine and letting the alias come from
    the index, which is the window as a resolver sees it.
    """
    env.install("vdi2770-validate==0.7.0")          # the machine as it was
    said = []
    for spec in documented_installs():
        done = env.install("--pre", "--find-links", wheels, "-U", spec)
        if done.returncode:
            said.append(f"`pip install -U {spec}` failed outright: "
                        f"{done.stderr.strip().splitlines()[-1][:120]}")
            continue
        refused = False
        for path, wanted in VERDICTS:
            code, out = env.command("check", str(ROOT / path))
            if code == 3:
                expect(MARKER in out, (
                    f"after `pip install -U {spec}`, the tool exited 3 without "
                    f"saying which kind of 3 it was: {out[:200]}"))
                refused = True
                continue
            expect("Traceback" not in out, (
                f"after `pip install -U {spec}`, `check {path}` died: {out[:300]}"))
            expect(code == wanted, (
                f"after `pip install -U {spec}`, `check {path}` exited {code} "
                f"and this container is a {'clean' if wanted == 0 else 'failing'} "
                f"one. A wrong verdict is the one outcome this window may not "
                f"produce."))
        if refused:
            said.append(f"{spec}: refuses by name")
        else:
            # And it says which release those verdicts came from. This is where
            # the window is actually safe, and not for the reason it looks:
            # `pip install -U vdi2770` moves the engine and leaves the 0.7 alias
            # -- which was real code with its own command and its own rules --
            # in place, with a conflict warning and an exit of 0. The 0.8 check
            # cannot fire there, because the code that runs is 0.7's and has no
            # such check. What saves it is that the old tool goes on working and
            # goes on saying it is old: the report is stamped with a version
            # that is installed, so the verdicts are old rather than wrong.
            code, version = env.command("--version")
            expect(code == 0, f"after `pip install -U {spec}`, --version gave {code}")
            have = set(env.versions().values())
            expect(version.strip() in have, (
                f"after `pip install -U {spec}` the tool reports {version!r} and "
                f"the versions installed are {sorted(have)}. A report naming a "
                f"release nobody has is the one thing worse than an old one."))
            said.append(f"{spec}: judges correctly as {version.strip()}")
    # At least one documented command has to leave a tool that judges. A window
    # in which every one of them refuses is a window in which the documentation
    # is wrong, and the first version of this case accepted it: the refusal arm
    # broke out of the container loop before anything else was asked, so a
    # build that exited 3 on every input -- which a version-comparison bug can
    # produce -- was recorded as `refuses by name` and passed.
    expect(any("judges correctly" in s for s in said), (
        f"every documented install left a tool that refuses: {said}. One of "
        f"them has to work, or the page is telling people to do something that "
        f"does not."))
    return "; ".join(said)


def case_13_every_door_on_a_working_install(env: Env, wheels: str) -> str:
    """Three ways in, on whatever machine this is running on.

    The other cases ask what an upgrade *leaves*, and they ask it through the
    console script. This one asks whether the thing pip actually wrote starts —
    and it asks on the platform, which is the half of the question a matrix
    that has only ever run on Linux cannot answer. The release this belongs to
    moves where the code is installed from and which distribution owns the
    executable, so "the file is there and it runs" stops being a formality.

    The file first, by name and in its directory, rather than inferred from an
    exit code: an install with no command and an install whose command exits
    non-zero are different failures, and a case that cannot tell them apart
    reports the wrong one. Windows writes `vdi2770-validate.exe`, which is the
    spelling that made this harness answer *not installed at all* about an
    installation that had it.

    Then both module doors. `python -m vdi2770_validate` is what code written
    against the old name runs, and until a review asked, nothing had run it in
    a state where it works — only in the refusal, where it was returning 1.
    """
    done = _from_the_wheels(env, wheels, COMMAND)
    expect(done.returncode == 0, f"the alias would not install:\n{done.stderr}")
    both_halves_run(env, "a plain install of the old name")

    # The file itself, by name and in its directory. `both_halves_run` reaches
    # the command through a lookup that answers `None` for an absent one, and
    # an install with no command then fails the same way as an install whose
    # command exits wrong -- two different repairs behind one message. On
    # Windows the file is `vdi2770-validate.exe`, which is the spelling that
    # made this harness say *not installed at all* about an installation that
    # had it.
    here = env.root / SCRIPTS
    exe = installed_command(here, COMMAND)
    expect(exe is not None, (
        f"pip installed no {COMMAND} in {here}. It holds: "
        f"{sorted(f.name for f in here.iterdir())}"))

    # And the two module doors, in the state where they are supposed to work.
    # Nothing ran `python -m vdi2770_validate` outside the refusal until a
    # review asked, and there it was returning 1.
    for path, wanted in VERDICTS:
        for door in ("vdi2770_validate", "vdi2770.validate"):
            done = run(env.python, "-m", door, "check", str(ROOT / path))
            said = (done.stdout + done.stderr).strip()
            expect(done.returncode == wanted, (
                f"`python -m {door} check {path}` exited {done.returncode} and "
                f"this container is a {'clean' if wanted == 0 else 'failing'} "
                f"one: {said[:300]}"))
    # The two sentences the old name's page makes, measured on the install the
    # page is about. It used to say a module imported through the old path
    # "still carries the old name" -- and none of them do: the object is the
    # same object, and it answers to the new name, which is what a traceback, a
    # log line and a pickle will say. The claim was on a public page and had
    # nothing behind it.
    done = run(env.python, "-c",
               "import vdi2770_validate.model as old, vdi2770.validate.model as new;"
               "print(old.Severity is new.Severity, old.__name__)")
    said = (done.stdout + done.stderr).strip()
    expect(done.returncode == 0, f"the old name would not import: {said[:300]}")
    expect(said.split()[0] == "True", (
        f"`vdi2770_validate.model.Severity` is not the same object as "
        f"`vdi2770.validate.model.Severity`, so the old name resolves to a copy: "
        f"{said[:200]}"))
    expect(said.split()[-1] == "vdi2770.validate.model", (
        f"a module imported through the old path reports __name__ as "
        f"{said.split()[-1]!r}; the page says it reports the new name, which is "
        f"what a traceback and a pickle will show"))
    return f"{exe.name if exe else '(no command)'} and two module doors, both verdicts"


#: Every case, in the order they run. `case_4` takes the directory of wheels
#: as well, so it is held here partially applied at call time rather than
#: listed apart -- kept out of this list, it was the one case no structural
#: test covered, and deleting its verdict left the suite green. It is also the
#: only case that installs the release being published.
CASES = [case_1_clean, case_2_upgrade_from_0_6_0, case_3_the_engine_cannot_be_older_than_the_alias,
         case_4_the_release_being_made,
         case_5_the_new_world_installs_the_old_name,
         case_6_both_names_at_once,
         case_7_removing_the_old_name_leaves_the_tool,
         case_8_the_reader_alone_declines_by_name,
         case_9_the_extra_runs_without_the_alias,
         case_10_the_alias_brings_the_extra,
         case_11_an_old_reader_under_new_rules_refuses,
         case_12_the_window,
         case_13_every_door_on_a_working_install]

#: The cases that need the artefacts being built rather than a name on an
#: index. Everything about the merged shape is one of these: 0.8 is not
#: published, so a case that asks the index for it is asking about a state
#: nobody is in yet.
NEEDS_WHEELS = frozenset(CASES[3:])


def cases_to_run(wheels=None, only=None):
    """The cases this invocation runs.

    `case_4` needs a directory of wheels and is skipped without one -- but
    skipped loudly, in the caller, never by returning early from inside a case
    that then reports success.
    """
    import functools
    chosen = []
    for case in ([CASES[n - 1] for n in only] if only else CASES):
        if case in NEEDS_WHEELS:
            if not wheels:
                continue
            case = functools.partial(case, wheels=wheels)
        chosen.append(case)
    return chosen


def name_of(case) -> str:
    return getattr(case, "__name__", None) or case.func.__name__


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    # Repeatable. One flag taking one number meant that asking for two cases
    # took two interpreters' worth of setup and two builds, and the platform
    # step that needs exactly two of them is the reason this exists.
    ap.add_argument("--case", type=int, action="append", metavar="N",
                    help="run this case by its number; repeat for several")
    ap.add_argument("--from", dest="wheels", metavar="DIR",
                    help="also upgrade to the wheels in DIR — the release being made")
    args = ap.parse_args()
    chosen = cases_to_run(wheels=args.wheels, only=args.case)

    failed = []
    numbers = args.case or list(range(1, len(CASES) + 1))
    # A selection that runs nothing is a broken invocation, not a pass. Every
    # case past the third needs the wheels being built and is skipped without
    # `--from` -- deliberately, so a local run is not a build -- but the skip
    # and the success printed the same thing and exited the same way. A CI step
    # whose build produced nothing, or whose directory name was wrong, would
    # then report that this platform runs the tool while starting no
    # interpreter at all.
    if not chosen:
        asked = ", ".join(str(n) for n in numbers)
        print(f"case {asked} needs the wheels being built and no --from was "
              f"given, so nothing ran. That is not a pass.", file=sys.stderr)
        return 2
    for n, case in zip(numbers, chosen):
        with tempfile.TemporaryDirectory() as tmp:
            env = Env(Path(tmp) / "venv")
            try:
                said = case(env)
            except AssertionError as e:
                failed.append(f"{n} {name_of(case)}: {e}")
                print(f"  FAIL  {n} {name_of(case)}\n        {e}", file=sys.stderr)
                continue
            print(f"  ok    {n} {name_of(case)}: {said}")
    if failed:
        print(f"\n{len(failed)} upgrade path(s) do not leave a working tool.",
              file=sys.stderr)
        return 1
    print(f"\n{len(chosen)} upgrade path(s) end in a tool that runs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
