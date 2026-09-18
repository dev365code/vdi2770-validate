#!/usr/bin/env python3
"""How much the whole corpus costs, measured in units of the machine it ran on.

The PDF scan was quadratic once. It stayed correct the whole time -- 28 seconds
on a delivery that now takes under a second -- so nothing here noticed, and what
caught it was a person waiting. This is the gate that would have.

**Seconds do not travel.** A ceiling recorded on a laptop is meaningless on a CI
runner, and a runner under load is slower than the same runner idle, so an
absolute budget is either loose enough to catch nothing or tight enough to go
red for reasons that are nobody's fault. What travels is a ratio: the corpus
timed against a **yardstick** measured in the same process, on the same machine,
in the same run.

The yardstick deliberately does not call this project. It is `zlib` and
`hashlib` over fixed bytes -- the two kinds of work the reader actually does --
so a slow machine moves both numbers and the ratio stays put, while a layer that
starts costing more moves the ratio alone. A yardstick that ran our own code
would slow down with the regression it is supposed to measure and say nothing.

    python tools/time_budget.py --check     # the gate
    python tools/time_budget.py --write     # record the budgets on this machine
"""
from __future__ import annotations

import argparse
import json
import pathlib
import platform
import sys
import time
import zipfile
from typing import Optional

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUDGET_FILE = ROOT / "docs" / "time-budget.json"

#: Half again as expensive is worth saying out loud; twice is a failure. Both
#: are generous on purpose: a gate that fires on runner noise is a gate people
#: learn to pass with a re-run, and then it is not a gate.
WARN_AT = 1.5
FAIL_AT = 2.0

#: Three passes, and the **fastest** one -- of the run and of the yardstick
#: alike. A median still carries whatever else the machine was doing: measured
#: three times in a row on an idle laptop, medians put the same tree between
#: 0.69x and 0.99x of its own budget, because the yardstick moved as much as the
#: work did. The fastest pass is the one least interrupted, and it is the figure
#: that repeats.
PASSES = 3
#: The yardstick is sized by the clock, not by a number: enough repetitions that
#: one measurement takes at least this long. Forty rounds took five milliseconds
#: on the machine this was written on, and five milliseconds is mostly scheduling
#: -- the tree's own timing repeated inside 2% while the yardstick moved 20%, so
#: the ratio was noisier than either number it is made of.
YARDSTICK_FLOOR_SECONDS = 0.05


class NoBaseline(Exception):
    """No budget to compare against. Not passing: a gate that did not look."""


class Verdict:
    def __init__(self, ratio: float, baseline: float):
        self.ratio = ratio
        self.baseline = baseline
        self.factor = ratio / baseline
        self.ok = self.factor < FAIL_AT
        self.warned = WARN_AT <= self.factor < FAIL_AT

    def __repr__(self) -> str:
        return (f"Verdict(ratio={self.ratio:.1f}, baseline={self.baseline:.1f}, "
                f"factor={self.factor:.2f}, ok={self.ok}, warned={self.warned})")


def judge(measured: float, baseline: Optional[float]) -> Verdict:
    """The whole arithmetic of this gate, in one place so it can be tested
    without waiting for a measurement."""
    if baseline is None:
        raise NoBaseline(
            "no budget recorded for comparison -- run `python tools/time_budget.py "
            "--write` on a machine that is behaving, and commit the file")
    return Verdict(measured, baseline)


def platform_key() -> str:
    """One budget per operating system.

    The ratio was supposed to travel, and it travels *some*: a Linux runner read
    0.56x of the budget recorded on the laptop, because `zlib` is three times
    slower there while this project's own work is only one and a half times
    slower. A single number across both is a weak gate exactly where it matters
    -- at 0.56x, a genuine doubling on that runner reads 1.12x and passes -- so
    each platform carries its own, measured on that platform.
    """
    return platform.system() or "unknown"


def load() -> dict:
    if not BUDGET_FILE.exists():
        raise NoBaseline(f"{BUDGET_FILE.relative_to(ROOT)} is not there")
    return json.loads(BUDGET_FILE.read_text(encoding="utf-8"))


def budgets_for(recorded: dict, key: str) -> dict:
    """The budgets recorded for this platform, or nothing -- never another
    platform's, which is the mistake the numbers above measured."""
    return recorded.get("budgets", {}).get(key, {})


def _yardstick() -> float:
    """One unit of this machine, in seconds. Not this project's code.

    **Pure Python on purpose.** The first version of this inflated a fixed blob
    with `zlib`, on the reasoning that inflating members is what the reader
    spends its time on. CI disagreed with that reasoning: on one Linux runner the
    same tree read 1412, 1650 and 950 units on Python 3.13, 3.12 and 3.9, because
    `zlib` is C and barely notices which interpreter called it while this
    project -- which is Python all the way down -- is half again faster on 3.13
    than on 3.9. A yardstick that ignores the interpreter cannot normalise work
    that is made of it.

    So the yardstick is the interpreter: dictionary, integer and string work in a
    loop, which is what the rules layer is when you look at it closely. No I/O,
    nothing random, nothing this project defines.
    """
    def work(rounds: int) -> int:
        counts: dict = {}
        total = 0
        for i in range(rounds):
            key = i & 1023
            counts[key] = counts.get(key, 0) + i
            total += len(str(key)) + (i % 7)
        return total

    rounds = 4096
    while True:
        t = time.perf_counter()
        work(rounds)
        spent = time.perf_counter() - t
        if spent >= YARDSTICK_FLOOR_SECONDS or rounds > 1 << 24:
            break
        rounds *= 2

    runs = []
    for _ in range(3):
        t = time.perf_counter()
        work(rounds)
        runs.append((time.perf_counter() - t) / rounds)
    # Per ten thousand rounds rather than per round, so the budgets read in the
    # hundreds instead of the millions. Nothing about the comparison changes;
    # a number a person can hold in their head is easier to argue with.
    return min(runs) * 10_000


def _containers() -> list:
    """Every container the oracle sweeps, which is the set this project already
    treats as its corpus. Read once, so the timing is the check and not the
    disk."""
    swept = json.loads((ROOT / "docs" / "oracle-sweep.json").read_text(encoding="utf-8"))["containers"]
    found = []
    for name in sorted(swept):
        hits = list((ROOT / "corpus").rglob(name)) or list((ROOT / "tests" / "fixtures").rglob(name))
        if hits:
            found.append((name, hits[0].read_bytes()))
    return found


def _pdfs(containers) -> list:
    out = []
    for _name, data in containers:
        try:
            with zipfile.ZipFile(__import__("io").BytesIO(data)) as z:
                for member in z.namelist():
                    if member.lower().endswith(".pdf"):
                        out.append(z.read(member))
        except Exception:                    # noqa: BLE001 - a fixture that is not a zip is not this gate's business
            continue
    return out


def measure() -> dict:
    sys.path.insert(0, str(ROOT / "packages" / "vdi2770" / "src"))
    from vdi2770 import pdfread  # noqa: E402  (the path above is what makes it importable)
    from vdi2770.validate.runner import check_bytes  # noqa: E402

    containers = _containers()
    if len(containers) < 40:
        raise SystemExit(f"only {len(containers)} containers found; the corpus is not here")
    pdfs = _pdfs(containers)

    # A warm-up, untimed. The yardstick is measured first, and on a machine that
    # has been idle it gets the boost clock while the tree that follows runs at
    # the sustained one -- which made the recording invocation read 15% higher
    # than every invocation after it, on the same tree. Running both once before
    # either is timed puts the recording and the checking on the same machine.
    for name, data in containers:
        check_bytes(data, name)
    _yardstick()

    unit = _yardstick()
    corpus = []
    for _ in range(PASSES):
        t = time.perf_counter()
        for name, data in containers:
            check_bytes(data, name)
        corpus.append(time.perf_counter() - t)
    pdf = []
    for _ in range(PASSES):
        t = time.perf_counter()
        for data in pdfs:
            pdfread.read(data)
        pdf.append(time.perf_counter() - t)

    corpus_s, pdf_s = min(corpus), min(pdf)
    return {
        "containers": len(containers),
        "pdfs": len(pdfs),
        "yardstick_seconds": unit,
        "absolute_seconds": {"corpus_pass": round(corpus_s, 4), "pdf_layer": round(pdf_s, 4)},
        "budgets": {"corpus_over_reference": round(corpus_s / unit, 1),
                    "pdf_layer_over_reference": round(pdf_s / unit, 1)},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help="record the budgets measured here")
    ap.add_argument("--check", action="store_true", help="compare this machine against the record")
    args = ap.parse_args(argv)
    if not (args.write or args.check):
        ap.error("say --check or --write")

    now = measure()
    key = platform_key()
    if args.write:
        existing = load() if BUDGET_FILE.exists() else {}
        budgets = dict(existing.get("budgets", {}))
        recorded_on = dict(existing.get("recorded_on", {}))
        budgets[key] = now["budgets"]
        recorded_on[key] = {
            "machine": platform.machine(), "python": platform.python_version(),
            "containers": now["containers"], "pdfs": now["pdfs"],
            "yardstick_seconds": round(now["yardstick_seconds"], 6),
            "absolute_seconds": now["absolute_seconds"],
        }
        BUDGET_FILE.write_text(json.dumps({
            "_about": "Budgets are ratios against a yardstick measured in the same run "
                      "(zlib over fixed bytes, never this project's code), because seconds "
                      "recorded on one machine cannot gate another. One entry per operating "
                      "system: the ratio travels only part of the way -- a Linux runner read "
                      "0.56x of the laptop's budget -- so each platform carries what was "
                      "measured on it. The seconds are for a reader, not what is compared.",
            "budgets": budgets,
            "recorded_on": recorded_on,
            "thresholds": {"warn_at": WARN_AT, "fail_at": FAIL_AT},
        }, indent=1) + "\n", encoding="utf-8")
        print(f"recorded {key} {now['budgets']} from {now['containers']} containers "
              f"({now['absolute_seconds']['corpus_pass']}s) and {now['pdfs']} PDFs "
              f"({now['absolute_seconds']['pdf_layer']}s)")
        return 0

    # What this machine measured, printed before anything is compared -- and the
    # seconds beside the ratios rather than instead of them: when a factor moves,
    # the first question is which half moved, and a reader holding only the ratio
    # cannot tell a slower tree from a faster yardstick. It also means a platform
    # with no budget yet still reports its numbers, which are exactly the numbers
    # somebody needs in order to record one.
    print(f"{key}: corpus {now['absolute_seconds']['corpus_pass']}s, "
          f"pdf layer {now['absolute_seconds']['pdf_layer']}s, "
          f"yardstick {now['yardstick_seconds'] * 1000:.3f}ms "
          f"({now['containers']} containers, {now['pdfs']} PDFs) -> {now['budgets']}")

    recorded = budgets_for(load(), key)
    if not recorded:
        raise NoBaseline(
            f"no budget recorded for {key}; measured {now['budgets']} here just now. "
            f"Run `python tools/time_budget.py --write` on this platform when the "
            f"machine is quiet and commit the file -- another platform's number "
            f"would not mean anything here")
    bad = False
    for key, measured in now["budgets"].items():
        verdict = judge(measured, recorded.get(key))
        where = key.replace("_over_reference", "")
        if not verdict.ok:
            print(f"{where}: {verdict.factor:.2f}x the recorded budget "
                  f"({measured} against {verdict.baseline}) -- something got slower, "
                  f"not the machine: the yardstick is measured in this same run", file=sys.stderr)
            bad = True
        elif verdict.warned:
            print(f"{where}: {verdict.factor:.2f}x the recorded budget "
                  f"({measured} against {verdict.baseline}) -- inside the budget, worth a look")
        else:
            print(f"{where}: {verdict.factor:.2f}x the recorded budget ({measured} against {verdict.baseline})")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
