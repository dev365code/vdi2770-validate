#!/usr/bin/env python3
"""Something must have judged this commit before a tag turns it into a publish.

The release workflow runs `make check` on the tagged tree. That is one
interpreter on one Linux runner, and it is not the gate: the four-row matrix —
three Pythons and Windows — runs on push, and nothing connects the two. A tag
can be pushed at a moment when the branch run never finished, was cancelled, or
failed, and the release would neither know nor care.

**Cancelled is the case this exists for.** A cancelled run is not a failure and
not a pass. It is a commit nobody judged, and it renders as a grey dot rather
than a red one, so a person scrolling the runs sees nothing wrong. A sibling
project measured it: a commit on its default branch sat cancelled, and the
release gate standing between a tag and an upload could never have run on it.

Three refusals rather than one, because they are three different repairs:

  * **no run** — the tag arrived before CI, or the runs have been deleted.
    Absence is not consent.
  * **not `success`** — cancelled, failed, timed out, or still going. Each one
    is a commit whose verdict does not exist yet, and a publish cannot be taken
    back while waiting for one.
  * **no answer** — `gh` missing, a token without `actions: read`, a rate
    limit. Unable to tell is the state in which this must not authorise
    anything, and the shape that would otherwise turn every outage into a pass.

A re-run counts: one `success` among several attempts is how a commit
legitimately goes from red to green, and refusing on the presence of any
failure would make re-running useless.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

WORKFLOW = "ci.yml"
NO_BYTECODE = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def runs_for(commit: str, workflow: str = WORKFLOW):
    """What GitHub says about this commit, or `None` if it would not say.

    `--commit` is a server-side filter. The answer is checked against the
    commit anyway: a filter that is quietly ignored — by an older `gh`, by a
    typo in the flag — would let a run on some other commit stand in for this
    one, and this gate would be reading yesterday's green.
    """
    done = subprocess.run(
        ["gh", "run", "list", "--workflow", workflow, "--commit", commit,
         "--json", "databaseId,status,conclusion,headSha,workflowName"],
        capture_output=True, text=True, env=NO_BYTECODE)
    if done.returncode != 0:
        return None, (done.stderr or done.stdout).strip()
    try:
        return json.loads(done.stdout or "[]"), ""
    except json.JSONDecodeError as e:
        return None, f"{e}: {done.stdout[:200]}"


def verdict(commit: str, runs) -> str:
    """Empty when this commit has been judged and passed, else why not."""
    mine = [r for r in runs if (r.get("headSha") or "") == commit]
    if not mine:
        others = sorted({(r.get("headSha") or "")[:7] for r in runs})
        return (f"no completed CI run for {commit[:7]}"
                + (f"; the runs returned were for {', '.join(others)}, which is "
                   f"not this commit" if others else
                   ". Absence is not consent: nothing has judged this tree"))
    if any(r.get("status") == "completed" and r.get("conclusion") == "success"
           for r in mine):
        return ""
    states = sorted({f"{r.get('conclusion') or r.get('status')}" for r in mine})
    return (f"CI has not passed on {commit[:7]}: {', '.join(states)}. "
            f"A cancelled or unfinished run is a commit nobody judged, and it "
            f"looks like a grey dot rather than a red one.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commit", default=os.environ.get("GITHUB_SHA"),
                    help="the commit to ask about; defaults to $GITHUB_SHA")
    ap.add_argument("--workflow", default=WORKFLOW)
    args = ap.parse_args()
    if not args.commit:
        print("no commit to ask about: pass --commit or set GITHUB_SHA",
              file=sys.stderr)
        return 2
    runs, why = runs_for(args.commit, args.workflow)
    if runs is None:
        print(f"could not ask GitHub whether CI judged {args.commit[:7]}: {why}\n"
              f"Not knowing is not a pass. This needs `actions: read` and a "
              f"`gh` that can reach the API.", file=sys.stderr)
        return 1
    said = verdict(args.commit, runs)
    if said:
        print(said, file=sys.stderr)
        return 1
    print(f"{args.workflow} judged {args.commit[:7]} and it passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
