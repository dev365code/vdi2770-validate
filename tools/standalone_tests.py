#!/usr/bin/env python3
"""Every test file, run on its own.

    python tools/standalone_tests.py

A suite is a shared process. Import a module in one file and every later file
gets it for free, including the ones whose subject is that it should not be
there. `tests/test_offline.py` failed on its own for weeks: it patches
`socket.socket` to a function and then imports `urllib.request`, which breaks
`class SSLSocket(socket)` inside the standard library — and the whole suite
passed because some earlier file had already imported ssl.

A test whose result depends on what ran before it is not a test, and the only way
to find one is to run each file alone. Not part of `make check`: one interpreter
start per file is a minute rather than a second, and this only tells you
something new when a file gains an import.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUITES = [
    (ROOT, sorted((ROOT / "tests").glob("test_*.py")), []),
    (ROOT / "packages" / "vdi2770",
     sorted((ROOT / "packages" / "vdi2770" / "tests").glob("test_*.py")),
     ["-c", "pyproject.toml"]),
]


def main() -> int:
    failed, ran = [], 0
    for cwd, files, extra in SUITES:
        if not files:
            print(f"no test files under {cwd}; this is looking in the wrong place",
                  file=sys.stderr)
            return 1
        for f in files:
            rel = f.relative_to(cwd)
            done = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                 *extra, str(rel)],
                cwd=cwd, capture_output=True, text=True)
            ran += 1
            # 5 is "collected nothing", which is a file that has stopped being a
            # test rather than a file that passes.
            if done.returncode != 0:
                failed.append((rel, done.returncode, (done.stdout or done.stderr)[-500:]))
                print(f"  alone: FAILED  {rel}")
            else:
                print(f"  alone: ok      {rel}")

    if failed:
        for rel, code, tail in failed:
            print(f"\n{rel} exits {code} when run by itself:\n{tail}", file=sys.stderr)
        return 1
    print(f"\n{ran} test files, each green on its own.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
