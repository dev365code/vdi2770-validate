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
sys.path.insert(0, str(ROOT / "src"))

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
}


def observe() -> Counter:
    fired: Counter = Counter()
    for z in sorted(list(CORPUS.rglob("*.zip")) + list(FIXTURES.rglob("*.zip"))):
        for f in check_file(str(z)).findings:
            fired[f.rule.id] += 1
    return fired


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
        want = json.loads(BASELINE.read_text(encoding="utf-8"))
        problems = []
        # The baseline records how many rules there were and which ones cannot
        # fire. Comparing only the fired set let both go stale in silence — a
        # rule could be added, excused, and never noticed by this check.
        if want.get("rules") != len(all_ids):
            problems.append(f"the catalogue has {len(all_ids)} rules, the baseline says "
                            f"{want.get('rules')}")
        if set(want.get("cannotFire", {})) != set(CANNOT_FIRE):
            problems.append(f"the excused set moved: baseline {sorted(want.get('cannotFire', {}))} "
                            f"-> now {sorted(CANNOT_FIRE)}")
        regressed = sorted(set(want["fired"]) - set(fired))
        if regressed:
            problems.append(f"rules that used to fire and no longer do: {regressed}")
        newly = sorted(set(fired) - set(want["fired"]))
        if newly:
            problems.append(f"rules now firing that the baseline does not list: {newly} "
                            f"(baseline is stale — rerun with --write and review the diff)")
        if problems:
            for p in problems:
                print(p, file=sys.stderr)
            return 1
        print(f"firing coverage ok: {len(fired)}/{len(all_ids)} rules fire, "
              f"{len(unexercised)} unexercised")
        return 0

    print(f"{len(fired)}/{len(all_ids)} rules fire")
    for rid in sorted(fired):
        print(f"  {rid:4} {fired[rid]:4}x")
    if unexercised:
        print(f"\nnever fired ({len(unexercised)}): {', '.join(unexercised)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
