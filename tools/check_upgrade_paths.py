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
import subprocess
import sys
import tempfile
from pathlib import Path

#: The command a user types, and what it must print. Read from the installed
#: package rather than hard-coded, so a release cannot pass by agreeing with a
#: number written here.
COMMAND = "vdi2770-validate"


def run(*args, **kw):
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


def both_halves_run(env: Env, why: str) -> None:
    """The assertion this file is for: the thing a person types works.

    Both import names, because the reader is published for use on its own and a
    caller that only ever imports `vdi2770` is a caller this project invites.
    And the console script, because an entry point is a file like any other and
    an uninstall can delete it while every import still resolves.
    """
    for name in ("vdi2770", "vdi2770_validate"):
        done = run(env.python, "-c", f"import {name}")
        expect(done.returncode == 0, f"{why}: import {name} failed\n{done.stderr}")
    code, said = env.command("--version")
    expect(code == 0, f"{why}: `{COMMAND} --version` gave {code}: {said}")
    expect(said.strip(), f"{why}: `{COMMAND} --version` printed nothing")


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
    expect(before.get("vdi2770") == "0.4.0",
           f"0.6.0 no longer drags 0.4.0 behind it; this case is about that: {before}")
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

    An exact pin is what makes the pair impossible to half-move, and it is also
    what makes a *mixed* install complain out loud instead of silently working
    until something is removed. That second property is why this is checked
    against the index rather than against `pyproject.toml`.
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
    done = env.install("-U", "--find-links", wheels, "vdi2770-validate")
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
