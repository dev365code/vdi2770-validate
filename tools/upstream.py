#!/usr/bin/env python3
"""Say whether the reference implementation has moved since this project pinned it.

    python tools/upstream.py    # asks the reference's repository

Exit 0 while the default branch is at the pin, 1 once it has moved, and 2 when
the repository could not be asked or did not answer -- which says nothing about
where the reference is, and is not reported as a move.

The corpus was copied from the reference repository at one commit, which
`corpus/MANIFEST.json` names, and the oracle workflow runs the reference at the
same commit. A pin does not move on its own, which is the point of it -- and it
also means nothing here notices when the reference does. This asks the
reference's repository where its default branch is and says whether that is the
pinned commit. Moving the pin is a decision; this is what says there is one to
make.

The deciding is a function of what `git ls-remote` prints, so the tests hold it
without a network: nothing in the suite opens a socket, and this tool is the one
place that asks, run by `.github/workflows/upstream.yml`.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "corpus" / "MANIFEST.json"


def pin() -> tuple[str, str]:
    """The reference's repository and the commit the corpus was copied at."""
    upstream = json.loads(MANIFEST.read_text(encoding="utf-8"))["_upstream"]
    return upstream["repo"], upstream["commit"]


def verdict(listing: str, pinned: str) -> str | None:
    """None when the default branch is at `pinned`; otherwise a sentence saying
    where it is.

    `listing` is what `git ls-remote --symref <url> HEAD` prints: a line naming
    the branch HEAD points at, then the commit. A listing with no commit for
    HEAD is refused rather than read as "not moved" -- an answer that did not
    come is not an answer that nothing changed.
    """
    branch, head = None, None
    for line in listing.splitlines():
        if line.startswith("ref: ") and line.endswith("\tHEAD"):
            branch = line[len("ref: "):-len("\tHEAD")]
        else:
            sha, _, ref = line.partition("\t")
            if ref == "HEAD":
                head = sha
    if head is None:
        raise SystemExit("the reference's repository answered with no HEAD; nothing "
                         "can be said about whether it moved")
    if head == pinned:
        return None
    return (f"the reference moved: {branch or 'its default branch'} is at {head}, "
            f"and the pin is {pinned}")


def main() -> int:
    repo, pinned = pin()
    try:
        asked = subprocess.run(
            ["git", "ls-remote", "--symref", f"https://github.com/{repo}.git", "HEAD"],
            capture_output=True, text=True, timeout=300)
    except (subprocess.TimeoutExpired, OSError) as why:
        print(f"could not ask {repo}: {why}", file=sys.stderr)
        return 2
    if asked.returncode != 0:
        print(f"could not ask {repo}: {asked.stderr.strip()}", file=sys.stderr)
        return 2
    try:
        said = verdict(asked.stdout, pinned)
    except SystemExit as unanswered:
        print(f"{repo}: {unanswered}", file=sys.stderr)
        return 2
    if said is None:
        print(f"{repo}: the default branch is at the pinned commit {pinned}")
        return 0
    print(said, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
