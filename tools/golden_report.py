#!/usr/bin/env python3
"""The whole report for one container, kept as a file a diff can be read from.

    python tools/golden_report.py            # write it
    python tools/golden_report.py --check    # it still says what the tool says

`docs/report-schema.md` states the contract and several tests pin parts of the
*shape*: which keys exist, that `schemaVersion` moves when a meaning does. None
of them reads a whole document at once, so a value quietly becoming a different
value -- a severity spelled differently, a rule dropping out, a finding losing
its `where` -- is a change no gate here would report.

So the whole document is a file. A change to it is a line in a diff, which is
what makes "the report is an interface" reviewable rather than asserted: a
consumer reading this repository sees exactly what their parser would see move.

`corpus/examples/container/missingdocuments.zip` because it is committed bytes
rather than a generated fixture, and because it exercises the widest slice of
the contract in one run: four findings over three rules at all three
severities, one of them (`Z8`) about the container and so carrying no member,
the others located. A generated fixture would do as well for content and worse
for provenance -- `tools/make_fixtures.py` writes entries at the current time,
so its bytes are not the same twice.

Two fields are replaced by a marker rather than pinned, because they are meant
to move and are held elsewhere:

* `toolVersion` -- every release moves it, and the version gates hold it against
  `pyproject.toml` and the changelog.
* `vdiSchema` -- the version the bundled schema stamps on itself. A property of
  the build rather than of the run, and `docs/report-schema.md` says so.

Everything else is exact. `path` included: it is the argument as typed, and a
report that stopped saying which input it was about would be a real change.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "docs" / "golden-report.json"
CONTAINER = "corpus/examples/container/missingdocuments.zip"

#: Replaced rather than pinned, with the reason a reader needs. Each is a fact
#: about the build that produced the report rather than about the report's
#: shape, and a golden that rewrites itself on every release is a file nobody
#: reads the diff of -- which is the one thing this file is for.
MOVING = {
    "toolVersion": "<the release that ran it; the version gates hold this>",
    "vdiSchema": "<the bundled schema's own stamp; a property of the build>",
}


def report() -> list:
    """What `check --json` says about the container, from this tree."""
    pythonpath = os.pathsep.join(
        [str(ROOT / "src"), str(ROOT / "packages" / "vdi2770" / "src")]
        + ([os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else []))
    done = subprocess.run(
        [sys.executable, "-m", "vdi2770.validate", "check", CONTAINER, "--json"],
        cwd=ROOT, capture_output=True, text=True,
        # Spelled out on the line rather than behind a helper: the gate that
        # checks for this reads the line, and it is right to -- a run that
        # leaves `__pycache__` beside the source makes the next gate's idea of
        # a clean tree wrong.
        env={**os.environ, "PYTHONPATH": pythonpath, "PYTHONDONTWRITEBYTECODE": "1"})
    # 0 is a clean container and 1 is one with findings; anything else and
    # whatever is on stdout is not a report. Said as a sentence, because a gate
    # that ends in a traceback is a gate whose failure nobody reads.
    if done.returncode not in (0, 1) or not done.stdout.strip():
        last = (done.stderr.strip().splitlines()[-1] if done.stderr.strip()
                else "nothing on stderr either")
        raise SystemExit(
            f"the checker gave no report for {CONTAINER} "
            f"(exit {done.returncode}): {last}")
    try:
        documents = json.loads(done.stdout)
    except ValueError as exc:
        raise SystemExit(
            f"the checker's output for {CONTAINER} is not JSON: {exc}") from exc
    for document in documents:
        for field, marker in MOVING.items():
            if field in document:
                document[field] = marker
    return documents


def main() -> int:
    parser = argparse.ArgumentParser(description="the whole report for one container")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    fresh = json.dumps(report(), indent=1, sort_keys=True) + "\n"
    if not args.check:
        GOLDEN.write_text(fresh, encoding="utf-8")
        print(f"{GOLDEN.relative_to(ROOT)}: written")
        return 0

    if not GOLDEN.exists():
        print(f"{GOLDEN.relative_to(ROOT)} does not exist; "
              f"run tools/golden_report.py", file=sys.stderr)
        return 1
    stored = GOLDEN.read_text(encoding="utf-8")
    if stored == fresh:
        print("the stored report is the one this tree produces")
        return 0

    import difflib
    diff = list(difflib.unified_diff(stored.splitlines(True), fresh.splitlines(True),
                                     fromfile="docs/golden-report.json",
                                     tofile="what this tree says", n=2))
    sys.stderr.writelines(diff[:60])
    if len(diff) > 60:
        print(f"... {len(diff) - 60} more lines", file=sys.stderr)
    print(f"the report for {CONTAINER} is not what is stored. If the change is "
          f"meant, `python tools/golden_report.py` writes it and the diff above "
          f"is what a consumer's parser sees move.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
