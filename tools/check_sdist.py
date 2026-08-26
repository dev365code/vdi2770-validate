#!/usr/bin/env python3
"""Build the sdist, unpack it somewhere else, and run the tests from there.

Anything the suite needs but the sdist omits is invisible here and fatal there.
This is the same failure the licensing gate had: the gate existed, and it did
not run in anyone else's environment.
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

# Two distributions come out of this repository, and a packager may build either.
# The SDK is checked first: if it cannot stand up alone, the validator's own
# green result would be borrowed from a source tree that happens to be nearby.
DISTRIBUTIONS = [
    (ROOT / "packages" / "vdi2770", []),
    (ROOT, ["tools/make_fixtures.py"]),
]


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
                print(f"{project.name}: the sdist cannot run its own tests: {step}",
                      file=sys.stderr)
                return 1
    print(f"{project.name}: sdist runs its own tests")
    return 0


def main() -> int:
    for project, before in DISTRIBUTIONS:
        rc = check(project, before)
        if rc:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
