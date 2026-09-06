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
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: The command a user types, and what it must print. Read from the installed
#: package rather than hard-coded, so a release cannot pass by agreeing with a
#: number written here.
COMMAND = "vdi2770-validate"


#: Everything here starts a fresh interpreter to find out what an install can
#: do, and the parent's `PYTHONPATH` would let this tree answer for it -- the
#: imports would resolve against the source and the case would pass over a venv
#: holding nothing. `PIP_*` settings would steer the installs the same way.
_CLEAN = {k: v for k, v in os.environ.items()
          if not k.startswith(("PYTHON", "PIP_"))} | {"PYTHONDONTWRITEBYTECODE": "1"}


def run(*args, **kw):
    kw.setdefault("env", _CLEAN)
    return subprocess.run(args, capture_output=True, text=True, **kw)


class Env:
    """One throwaway interpreter, with the pip that people have."""

    def __init__(self, root: Path):
        self.root = root
        run(sys.executable, "-m", "venv", str(root), check=False)
        self.pip = str(root / "bin" / "pip")
        self.python = str(root / "bin" / "python")
        run(self.pip, "install", "-q", "--upgrade", "pip")

    def install(self, *spec):
        return run(self.pip, "install", "-q", *spec)

    def versions(self) -> dict:
        out = run(self.pip, "list", "--format=json").stdout
        return {p["name"].lower(): p["version"] for p in json.loads(out or "[]")}

    def check(self) -> str:
        done = run(self.pip, "check")
        return (done.stdout + done.stderr).strip() or "(silent)"

    def command(self, *args):
        exe = self.root / "bin" / COMMAND
        if not exe.exists():
            return None, f"{COMMAND} is not installed at all"
        done = run(str(exe), *args)
        return done.returncode, (done.stdout + done.stderr).strip()


def expect(condition, said: str):
    if not condition:
        raise AssertionError(said)


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
        done = run(env.python, "-c", f"import {name}")
        expect(done.returncode == 0, f"{why}: import {name} failed\n{done.stderr}")

    code, said = env.command("--version")
    expect(code == 0, f"{why}: `{COMMAND} --version` gave {code}: {said}")
    installed = env.versions().get("vdi2770-validate")
    expect(installed, f"{why}: nothing named vdi2770-validate is installed")
    expect(installed in said, (
        f"{why}: `{COMMAND} --version` says {said!r} and what is installed is "
        f"{installed}. A build that reports a version it is not is a build "
        f"whose reports name an engine nobody has."))

    for path, wanted in VERDICTS:
        target = str(ROOT / path)
        code, said = env.command("check", target)
        expect(code == wanted, (
            f"{why}: `{COMMAND} check {path}` exited {code} and this container "
            f"is a {'clean' if wanted == 0 else 'failing'} one. A program that "
            f"answers the same way to everything answers nothing."))


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
    env.install("vdi2770-validate==0.6.0")
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


def case_3_the_pin_is_exact(env: Env) -> str:
    """What the installed metadata asks for, not what the repository declares.

    An exact pin is what makes the pair impossible to half-move: there is no
    version of one that can be paired with a different version of the other, so
    a release cannot arrive half-applied. Checked against the index rather than
    against `pyproject.toml` because what a release shipped and what this tree
    declares are different questions and only the first reaches anybody.

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
    expect(asked == f"vdi2770=={have['vdi2770']}",
           f"the installed rules ask for {asked!r}, not an exact pin on "
           f"{have['vdi2770']}")
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
    env.install("vdi2770-validate")
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


CASES = [case_1_clean, case_2_upgrade_from_0_6_0, case_3_the_pin_is_exact]


def name_of(case) -> str:
    return getattr(case, "__name__", None) or case.func.__name__


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", type=int, help="run one case by its number")
    ap.add_argument("--from", dest="wheels", metavar="DIR",
                    help="also upgrade to the wheels in DIR — the release being made")
    args = ap.parse_args()
    chosen = ([CASES[args.case - 1]] if args.case else list(CASES))
    if args.wheels and not args.case:
        import functools
        chosen.append(functools.partial(case_4_the_release_being_made,
                                        wheels=args.wheels))

    failed = []
    for n, case in enumerate(chosen, start=args.case or 1):
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
