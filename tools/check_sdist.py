#!/usr/bin/env python3
"""Build the sdist, unpack it somewhere else, and run the tests from there.

Anything the suite needs but the sdist omits is invisible here and fatal there.
This is the same failure the licensing gate had: the gate existed, and it did
not run in anyone else's environment.
"""
from __future__ import annotations

import glob
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        build = subprocess.run([sys.executable, "-m", "build", "--sdist", "--outdir", tmp, str(ROOT)],
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
            tf.extractall(tmp)                                    # noqa: S202 - our own artifact
        unpacked = next(p for p in Path(tmp).iterdir() if p.is_dir())
        # Fixtures are generated, so the sdist carries the generator, not the
        # output — build them there exactly as `make check` does here.
        for step in (["tools/make_fixtures.py"], ["-m", "pytest", "-q"]):
            r = subprocess.run([sys.executable, *step], cwd=unpacked)
            if r.returncode:
                print(f"the sdist cannot run its own tests: {step}", file=sys.stderr)
                return 1
    print("sdist runs its own tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
