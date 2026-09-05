#!/usr/bin/env python3
"""Build the sdist, unpack it somewhere else, and run the tests from there.

A file the sdist leaves out is invisible in the source tree and fatal in the
tarball. This is the same failure the licensing gate had: the gate existed, and
it did not run in anyone else's environment.

What it does not prove is that the tarball stands up with nothing installed. It
runs on `sys.executable`, and in this repository and in CI that interpreter
already has this repository installed -- so `tools/make_fixtures.py`, which the
sdist ships and which imports `vdi2770`, is satisfied from outside the tarball. A packager who installs the declared dependencies is in the
same position and the suite is green for them; a packager who unpacks and runs
`pytest` without installing anything is not, and this gate will not tell them.
That is a dependency being absent rather than a file being missing, which is the
half this checks.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

# Bytecode goes wherever this interpreter puts it, and `sys.pycache_prefix`
# can put it outside the tree entirely -- where nothing here cleans it and
# where a same-size restore inside one second leaves a stale `.pyc` that
# CPython still considers valid. Writing none is cheaper than chasing it.
NO_BYTECODE = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")


ROOT = Path(__file__).resolve().parent.parent

# One distribution carries the code. The reader was its own until 0.6.0 and was
# built here too -- if it could not stand up alone, the validator's green result
# would have been borrowed from a source tree that happened to be nearby. It
# ships inside this one now, and `packages/vdi2770/tests` runs from this sdist.
DISTRIBUTIONS = [
    (ROOT, ["tools/make_fixtures.py"]),
]

#: The other distribution this repository publishes: the name it used until
#: 0.6.0, kept resolving as metadata and a dependency. It has no tests to run —
#: what it has is a rule that cannot be relaxed by accident, checked below.
REDIRECT = ROOT / "packages" / "vdi2770-validate"


def _distribution(project: Path) -> str:
    """What the manifest calls it, not what the directory is called.

    The repository directory is `vdi2770-validate`, which is also the name of
    the other distribution built here — so `project.name` labelled the main
    sdist with the redirect's name and the two results read as one package
    checked twice.
    """
    import re

    text = (project / "pyproject.toml").read_text(encoding="utf-8")
    found = re.search(r'^name = "([^"]+)"', text, re.M)
    return found.group(1) if found else project.name


def _pristine(project: Path):
    """Remove what a previous build left where the next one will read it.

    setuptools falls back to a previous run's `SOURCES.txt` when no VCS plugin
    is present, so `*.egg-info` makes the next distribution assembled from the
    last one's file list rather than from `MANIFEST.in`. Measured: with
    `recursive-include corpus *` deleted, this gate passed with the egg-info
    present and failed without it — the two packaging gates could not fail on a
    packaging declaration at all on a machine that had built before.

    `build/lib` is the same trap one layer along and is cleared with it.
    """
    for stale in list(project.glob("**/*.egg-info")) + [project / "build"]:
        shutil.rmtree(stale, ignore_errors=True)


def check(project: Path, before: list) -> int:
    # setuptools writes `<project>/build/lib/...` on the way to an sdist and
    # leaves it there. It is gitignored, so what stays behind is a complete,
    # invisible copy of the source tree at the moment this gate last ran -- and
    # it outlives renames: four modules that moved into the `vdi2770` package
    # sat in `build/lib/vdi2770_validate/readers/` for weeks, findable by any
    # `grep -r` and safe to edit for nobody. A gate cleans up after itself.
    _pristine(project)
    try:
        return _build_and_run(project, before)
    finally:
        _pristine(project)


def _build_and_run(project: Path, before: list) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        build = subprocess.run([sys.executable, "-m", "build", "--sdist", "--outdir", tmp, str(project)],
                               env=NO_BYTECODE,
                               capture_output=True, text=True)
        if build.returncode:
            print(build.stdout[-2000:], build.stderr[-2000:], file=sys.stderr)
            print("could not build an sdist", file=sys.stderr)
            return 1
        archives = glob.glob(f"{tmp}/*.tar.gz")
        if len(archives) != 1:
            print(f"expected one sdist, found {archives}", file=sys.stderr)
            return 1
        with tarfile.open(archives[0]) as tf:
            # 3.14 makes `filter="data"` the default and 3.12/3.13 warn without
            # it, so the behaviour of this line would otherwise depend on which
            # interpreter ran the gate. This unpacks an artifact we built a
            # moment ago, so the restriction costs nothing. The keyword arrived
            # in 3.12 and in the later patch releases of 3.9-3.11; on an
            # interpreter without it the call raises before extracting anything.
            try:
                tf.extractall(tmp, filter="data")                 # noqa: S202 - our own artifact
            except TypeError:
                tf.extractall(tmp)                                # noqa: S202
        unpacked = next(p for p in Path(tmp).iterdir() if p.is_dir())
        # Fixtures are generated, so the sdist carries the generator, not the
        # output — build them there exactly as `make check` does here.
        for step in ([*before], ["-m", "pytest", "-q"]):
            if not step:
                continue
            r = subprocess.run([sys.executable, *step], cwd=unpacked, env=NO_BYTECODE)
            if r.returncode:
                print(f"{_distribution(project)}: the sdist cannot run its own "
                      f"tests: {step}",
                      file=sys.stderr)
                return 1
    print(f"{_distribution(project)}: sdist runs its own tests")
    return 0


def check_the_redirect_ships_no_code() -> int:
    """The redirect must be metadata and nothing else.

    Both distributions would otherwise install `vdi2770_validate/` over each
    other -- pip does not refuse it, it keeps whichever went last, and
    uninstalling the redirect afterwards deletes the real tool. `packages = []`
    in the manifest says so; this is whether the built artifact agrees, because
    a manifest is a claim and a tarball is what people receive.
    """
    _pristine(REDIRECT)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            build = subprocess.run(
                [sys.executable, "-m", "build", "--sdist", "--outdir", tmp,
                 str(REDIRECT)], env=NO_BYTECODE, capture_output=True, text=True)
            if build.returncode:
                print(build.stdout[-2000:], build.stderr[-2000:], file=sys.stderr)
                print("could not build the redirect's sdist", file=sys.stderr)
                return 1
            archives = glob.glob(f"{tmp}/*.tar.gz")
            if len(archives) != 1:
                print(f"expected one sdist, found {archives}", file=sys.stderr)
                return 1
            with tarfile.open(archives[0]) as tf:
                # `setup.py` is what setuptools may generate into an sdist; it is
                # not a module the install would place anywhere, so it does not
                # count. Anything else ending in `.py` does.
                carried = [n for n in tf.getnames()
                           if n.endswith(".py") and Path(n).name != "setup.py"]
            if carried:
                print(f"the redirect's sdist carries code: {carried}. Two "
                      f"distributions shipping the same module install over each "
                      f"other, and pip does not refuse it.", file=sys.stderr)
                return 1
    finally:
        _pristine(REDIRECT)
    print("vdi2770-validate: the redirect ships no code")
    return 0


def main() -> int:
    for project, before in DISTRIBUTIONS:
        rc = check(project, before)
        if rc:
            return rc
    return check_the_redirect_ships_no_code()


if __name__ == "__main__":
    raise SystemExit(main())
