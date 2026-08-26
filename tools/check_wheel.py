#!/usr/bin/env python3
"""Build each wheel, look inside it, then install it and run it.

The sdist gate proves a source distribution can run its own tests. Nobody
installs a source distribution. The wheel is what `pip install` fetches, and
nothing in this repository built one — so "the licences travel with the package"
and "the bundled schema ships" were claims about strings in a `pyproject.toml`,
which is not the same as a claim about the artifact.

What it checks, and what each check has been shown to catch:

  * **Licence files.** Every LICENSE / NOTICE / THIRD_PARTY.md the project has
    must be in the wheel. Killed by removing them from `license-files`.
  * **The wheel matches the source.** Every file under `src/<package>/` must
    ship. This is also why the build directory is removed *before* building:
    setuptools assembles the wheel from `<project>/build/lib`, and leaves files
    there that the source no longer has. Measured: with `data/rules.json` moved
    out of the tree, the wheel still contained it.
  * **It installs and runs.** The built wheels are installed into a temporary
    directory and the command line is run out of them, on a container that
    produces findings. Killed by removing `data/rules.json` (import-time) and by
    removing the bundled schema, which does not crash — it reports `X0`, so the
    smoke test asks about `X0` rather than only about the exit code.

Two mutations do *not* kill this gate and are recorded rather than hidden:
dropping `py.typed` from the reader's `package-data`, and excluding
`vdi2770_validate.rules*` from `packages.find`. setuptools ships both anyway, so
the artifact stays correct and the declaration is inert. They are equivalent
mutants for this backend, not holes.

The first version of this gate derived its requirements from the project's own
`pyproject.toml` and was circular: deleting a declaration deleted the
requirement, and all four ways of breaking the packaging passed. The
declaration is the thing that breaks. The filesystem is not.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DISTRIBUTIONS = [
    (ROOT / "packages" / "vdi2770", "vdi2770"),
    (ROOT, "vdi2770_validate"),
]
# A container that produces findings, used to prove the installed wheel runs.
SMOKE = ROOT / "corpus" / "examples" / "missingdocuments" / "folders.zip"

# Bytecode goes wherever this interpreter puts it, and `sys.pycache_prefix`
# can put it outside the tree entirely -- where nothing here cleans it and
# where a same-size restore inside one second leaves a stale `.pyc` that
# CPython still considers valid. Writing none is cheaper than chasing it.
NO_BYTECODE = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")



def contents(project: Path, out: Path) -> tuple:
    # Before, not just after, and `*.egg-info` as well as `build`. `python -m
    # build` assembles the wheel out of
    # `<project>/build/lib`, and setuptools does not remove files there that the
    # source no longer has -- so a deleted module or data file keeps shipping,
    # and a stale copy ships in place of the current one. Measured: with
    # `data/rules.json` moved out of the source tree, the wheel still contained
    # it. Any gate that builds on a workspace someone has built in before is
    # measuring that workspace, not this commit.
    for stale in list(project.glob("**/*.egg-info")) + [project / "build"]:
        shutil.rmtree(stale, ignore_errors=True)
    build = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(out), str(project)],
        env=NO_BYTECODE,
        capture_output=True, text=True)
    if build.returncode:
        print(build.stdout[-2000:], build.stderr[-2000:], file=sys.stderr)
        raise SystemExit(f"{project.name}: could not build a wheel")
    wheels = sorted(out.glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"{project.name}: expected one wheel, found {wheels}")
    return wheels[0], zipfile.ZipFile(wheels[0]).namelist()


def check(project: Path, package: str, wheel: Path, names: list) -> list:
    """What the source tree has, the wheel must carry.

    Deriving the requirement from the project's own `pyproject.toml` was the
    first attempt and it was circular: deleting `license-files` deleted the
    requirement, and all four ways of breaking the packaging passed. The
    declaration is the thing that breaks. The filesystem is not.
    """
    problems = []
    src = project / "src" / package

    for name in ("LICENSE", "NOTICE", "THIRD_PARTY.md"):
        if not (project / name).exists():
            continue
        if not any(n.endswith(f"/licenses/{name}") or n.endswith(f".dist-info/{name}")
                   for n in names):
            problems.append(f"{wheel.name}: {name} is in the project and not in the wheel")

    for f in sorted(src.rglob("*")):
        if not f.is_file() or "__pycache__" in f.parts or f.suffix == ".pyc":
            continue
        rel = f"{package}/{f.relative_to(src).as_posix()}"
        if rel not in names:
            kind = "module" if f.suffix == ".py" else "file"
            problems.append(
                f"{wheel.name}: {rel} is a {kind} inside the package and did not ship. "
                f"Anything under src/{package}/ is there to be installed.")

    # And the other direction. NOTICE and THIRD_PARTY.md tell readers which
    # MIT-derived material this project carries and where; the sentence that
    # matters to anyone installing it is that none of it is in what they
    # install. `corpus/`, `docs/oracle-sweep.json`, `tests/data/` and
    # `tools/oracle/` are all in the sdist and none belong here, and no gate
    # could tell if a `package-data` glob started sweeping them in.
    for n in names:
        # No `endswith(".dist-info")`: setuptools writes no directory entries
        # into a wheel, so nothing can end with it -- and the unreachable clause
        # was a hole, waving through any path that happened to end that way.
        if n.startswith(f"{package}/") or ".dist-info/" in n:
            continue
        problems.append(
            f"{wheel.name}: {n} shipped from outside src/{package}/. The wheel is "
            f"the package and nothing else; repository material — corpus, oracle "
            f"evidence, tools — stays in the sdist, which is what NOTICE says.")
    return problems


def smoke(wheels: list) -> list:
    """Install what was built and run the command line out of it.

    Offline: the wheels are installed from the directory they were built into,
    with `--no-deps`, and everything else resolves from the environment running
    this. What is being tested is that the artifact carries what it needs, not
    that pip can reach the internet.
    """
    with tempfile.TemporaryDirectory() as tmp:
        install = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "--no-index", "--no-deps",
             "--target", tmp, *[str(w) for w in wheels]],
            capture_output=True, text=True)
        if install.returncode:
            return [f"the wheels do not install: {install.stderr[-800:]}"]
        found = []

        env = dict(NO_BYTECODE, PYTHONPATH=tmp)
        env.pop("PYTHONHASHSEED", None)
        script = ("import sys, vdi2770_validate, vdi2770;"
                  "print(vdi2770_validate.__file__);"
                  "from vdi2770_validate.cli import main;"
                  "sys.exit(main(['check', sys.argv[1]]))")
        run = subprocess.run([sys.executable, "-c", script, str(SMOKE)],
                             capture_output=True, text=True, cwd=tmp, env=env)
        if tmp not in run.stdout:
            found.append(f"the smoke test ran a copy that was not the wheel: {run.stdout[:200]}")
        if run.returncode != 1:
            found.append(f"the installed tool exited {run.returncode} on a container with errors: "
                         f"{run.stderr[-800:]}")
        for rule in ("F1", "Z7", "Z9"):
            if f"  {rule}  " not in run.stdout:
                found.append(f"the installed tool did not report {rule}: {run.stdout[:400]}")
        # X0 is what this tool says when its own installation is broken. It is a
        # finding rather than a crash, on purpose -- which means a wheel missing
        # the bundled schema installs, runs, exits 1, and looks fine here unless
        # somebody asks. A packager who ships that has shipped a validator that
        # validates nothing against the XSD and says so in a line nobody reads.
        if "  X0  " in run.stdout:
            found.append("the installed wheel reports X0: something it needs did not ship")
    # Every smoke problem, not the first: returning early meant one run
    # reported at most one thing wrong with the artifact people install.
    return found


def main() -> int:
    problems, built = [], []
    with tempfile.TemporaryDirectory() as out:
        for project, package in DISTRIBUTIONS:
            # One directory per distribution: they land in the same place
            # otherwise and "expected one wheel" finds the neighbour's.
            here = Path(out) / package
            here.mkdir()
            # Unconditionally, both sides. `contents` has already destroyed
            # whatever was there, so "put back what we found" is not on offer --
            # and leaving a fresh one behind recreates the fossil that made a
            # deleted file keep shipping in the first place.
            try:
                wheel, names = contents(project, here)
            finally:
                for stale in (list(project.glob("**/*.egg-info"))
                              + [project / "build"]):
                    shutil.rmtree(stale, ignore_errors=True)
            found = check(project, package, wheel, names)
            problems += found
            built.append(wheel)
            # Only when it does. Printing the good news unconditionally after a
            # function that returns problems meant the run said both things.
            if not found:
                print(f"{package}: wheel carries its licences and its data")
        problems += smoke(built)
    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        return 1
    print("the built wheels install and run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
