#!/usr/bin/env python3
"""Firing coverage: a rule that never fires anywhere is a dead rule.

The point is not the number. The point is that a rule which has never been seen
to fire has never been tested, and nobody notices until a user hits it.

    python tools/rule_coverage.py            # report
    python tools/rule_coverage.py --check    # judge, against docs/rule-coverage.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
#: Both, and in this order. A tool that inserts only `src` measures whichever
#: `vdi2770` happens to be installed — on a machine with the reader from PyPI
#: that is a different library than the one in this commit, and the gate then
#: reports coverage for code nobody is changing.
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(1, str(ROOT / "packages" / "vdi2770" / "src"))

from vdi2770_validate.catalog import rules  # noqa: E402
from vdi2770_validate.runner import check_file  # noqa: E402

BASELINE = ROOT / "docs" / "rule-coverage.json"
CORPUS = ROOT / "corpus" / "examples"
FIXTURES = ROOT / "tests" / "fixtures"

# Rules that cannot fire on any container we can construct offline, with the reason.
# Kept separate from "not covered yet" on purpose: merging a settled question into
# an open list makes the open list unreadable.
CANNOT_FIRE: dict = {
    "X0": ("only fires when this tool's own installation is broken, which no container can "
           "cause. Exercised by tests/test_tool_limits_are_not_verdicts.py, which breaks the "
           "installation deliberately."),
    "X5": ("only fires when a step in this tool raises, which is a bug here rather than "
           "anything a container can ask for. Not only the rules: the steps that feed "
           "them -- the parse, the document build, the schema walk, and the two calls "
           "into the reader, which is a separately versioned package whose pin admits "
           "releases nobody in this repository has run. Exercised by "
           "tests/test_a_rule_that_crashes_does_not_kill_the_run.py, which makes each "
           "rule module and each of those steps raise in turn."),
}


def observe() -> Counter:
    fired: Counter = Counter()
    for z in sorted(list(CORPUS.rglob("*.zip")) + list(FIXTURES.rglob("*.zip"))):
        for f in check_file(str(z)).findings:
            fired[f.rule.id] += 1
    return fired


def _about_the_tool(rule_id: str) -> bool:
    from vdi2770_validate.catalog import rules
    from vdi2770_validate.model import About
    r = rules().get(rule_id)
    return r is not None and r.about is About.TOOL


def judge(all_ids, fired, baseline, cannot_fire=None, about_the_tool=None) -> list:
    """Every reason this coverage state should fail the build.

    Split out from `main` so the gate can be tested without a corpus. It used to
    live inline, `unexercised` was computed and never looked at, and README said
    "a rule that fires nowhere fails the build" while a rule that fired nowhere
    exited 0.
    """
    cannot_fire = CANNOT_FIRE if cannot_fire is None else cannot_fire
    all_ids, fired = set(all_ids), set(fired)
    problems = []
    # The baseline records how many rules there were and which ones cannot
    # fire. Comparing only the fired set let both go stale in silence — a
    # rule could be added, excused, and never noticed by this check.
    if baseline.get("rules") != len(all_ids):
        problems.append(f"the catalogue has {len(all_ids)} rules, the baseline says "
                        f"{baseline.get('rules')}")
    # The keys *and* the reasons. Comparing keys alone let an excuse be rewritten
    # from a genuine impossibility to "nobody got round to it" with a green
    # build, and the reason is the entire substance of an excuse.
    if dict(baseline.get("cannotFire", {})) != dict(cannot_fire):
        moved = sorted(set(baseline.get("cannotFire", {})) ^ set(cannot_fire))
        reworded = sorted(k for k in set(baseline.get("cannotFire", {})) & set(cannot_fire)
                          if baseline["cannotFire"][k] != cannot_fire[k])
        problems.append(f"the excused set moved: keys {moved or 'unchanged'}, "
                        f"reasons rewritten for {reworded or 'nothing'}")
    regressed = sorted(set(baseline.get("fired", ())) - fired)
    if regressed:
        problems.append(f"rules that used to fire and no longer do: {regressed}")
    newly = sorted(fired - set(baseline.get("fired", ())))
    if newly:
        problems.append(f"rules now firing that the baseline does not list: {newly} "
                        f"(baseline is stale — rerun with --write and review the diff)")
    # The whole point of the tool, and the one thing it did not check. Note that
    # the baseline cannot excuse this: recording a dead rule in a JSON file is
    # not the same as testing it. Either make it fire, or put it in CANNOT_FIRE
    # with the reason it cannot.
    # An excuse has to be the kind of thing an excuse can be. `CANNOT_FIRE` is
    # both the requirement and the exemption — one sentence in this file removes
    # a rule from the gate, and the only quality check was that the sentence was
    # long. Reproduced: deleting M9's fixture and adding "nobody has got round to
    # it" left the build green.
    #
    # The claim a row makes is "no container can cause this". That is only
    # coherent for a rule that is *about this tool* rather than about a
    # container, and `rules.json` already says which is which.
    # Injectable so a test can judge a synthetic catalogue; the real one is the
    # default, and a caller that passes nothing gets the real answer.
    is_tool = about_the_tool if about_the_tool is not None else _about_the_tool
    about_a_container = sorted(rid for rid in cannot_fire
                               if rid in all_ids and not is_tool(rid))
    if about_a_container:
        problems.append(
            f"excused rules that are about the container, not about this tool: "
            f"{about_a_container}. A container can cause those, so 'no container "
            f"can cause it' is not available — build the fixture.")
    unexercised = sorted(all_ids - fired - set(cannot_fire))
    if unexercised:
        problems.append(f"rules that fire nowhere in the corpus or the fixtures: "
                        f"{unexercised} — add a fixture that makes each one fire, or list "
                        f"it in CANNOT_FIRE with the reason it cannot")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    fired = observe()
    all_ids = set(rules())
    unexercised = sorted(all_ids - set(fired) - set(CANNOT_FIRE))
    payload = {
        "_note": "Not a target. A rule listed here has never been seen to fire; that is a gap, not an achievement.",
        "rules": len(all_ids),
        "fired": sorted(fired),
        "unexercised": unexercised,
        "cannotFire": CANNOT_FIRE,
    }

    if a.write:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {BASELINE.relative_to(ROOT)}")
        return 0

    if a.check:
        if not BASELINE.exists():
            print("docs/rule-coverage.json missing — run --write", file=sys.stderr)
            return 1
        problems = judge(all_ids, fired, json.loads(BASELINE.read_text(encoding="utf-8")))
        if problems:
            for p in problems:
                print(p, file=sys.stderr)
            return 1
        print(f"firing coverage ok: {len(fired)}/{len(all_ids)} rules fire, "
              f"{len(CANNOT_FIRE)} excused, none unexercised")
        return 0

    print(f"{len(fired)}/{len(all_ids)} rules fire")
    for rid in sorted(fired):
        print(f"  {rid:4} {fired[rid]:4}x")
    if unexercised:
        print(f"\nnever fired ({len(unexercised)}): {', '.join(unexercised)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
