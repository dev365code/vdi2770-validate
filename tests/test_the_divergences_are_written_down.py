"""Every disagreement written down rather than averaged away.

`docs/divergences.md` says that in its first paragraph, and nothing held it to
the sweep. Two containers drew a warning from the reference implementation and
nothing but a note from this tool, and neither the container nor the message key
appeared anywhere on the page — so the promise was kept by hand, which is to say
kept until somebody forgot.
"""
from __future__ import annotations

import json

from conftest import ROOT

SWEEP = json.loads((ROOT / "docs" / "oracle-sweep.json").read_text(encoding="utf-8"))
PAGE = (ROOT / "docs" / "divergences.md").read_text(encoding="utf-8")


def _louder_than_a_note(entry) -> set:
    return set(entry.get("ERROR", [])) | set(entry.get("WARN", []))


def test_a_verdict_we_do_not_make_is_named_on_the_page():
    silent = {}
    for name, e in SWEEP["containers"].items():
        theirs = _louder_than_a_note(e["reference"])
        ours = e["ours"].get("error", []) + e["ours"].get("warning", [])
        if theirs and not ours:
            silent[name] = sorted(theirs)

    # Not `assert silent`. That guard was here so the test could not pass
    # vacuously, and it read the day silence reaches zero as a broken premise
    # rather than as the day this gate finished its job. Two rules now in flight
    # -- one for a declared format, one for an identifier claimed two ways --
    # cover between them every container the reference is louder about, and
    # measured across both, the silent set is empty.
    #
    # What still has to hold is that the comparison ran at all: an empty sweep
    # would pass this test while establishing nothing, and that is the failure
    # the original guard was reaching for.
    # The premise, taken from the side our rules cannot change. "At least one
    # container is silent" reads the day this gate finishes its job as the day
    # its premise broke. "The sweep is not empty" is too weak the other way: a
    # capture that recorded no reference verdicts at all would pass it while
    # establishing nothing, which is the vacuity the original guard was reaching
    # for. What has to hold is that the reference said something louder than a
    # note *somewhere* -- if it did not, there was no comparison to make.
    assert any(_louder_than_a_note(e["reference"]) for e in SWEEP["containers"].values()), (
        "the sweep records no reference verdict louder than a note; there is "
        "nothing here to be silent about and nothing to derive")
    unrecorded = {name: keys for name, keys in silent.items()
                  if name not in PAGE and not any(k in PAGE for k in keys)}
    assert not unrecorded, (
        "the reference reports a warning or worse and this tool reports nothing "
        "louder than a note, and the page does not say so:\n"
        + "\n".join(f"    {n}: {k}" for n, k in sorted(unrecorded.items())))


#: As the page spells a count it writes as a word.
WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
         8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}


def test_the_counts_the_page_gives_are_the_sweeps():
    """Section 5 counted the sweep once, and the sweep grew past the count:
    it said 21 containers where the record holds 22, 50 fixtures warned
    `REP_044` where it holds 52, and six other containers carrying `REP_023`
    and `REP_039` where it holds eight. The counts the sweep decides are counted
    here from the record the page describes."""
    found = SWEEP["containers"]
    text = " ".join(PAGE.split())

    def ours(e, severity):
        return e["ours"].get(severity, [])

    quiet = [n for n, e in found.items()
             if _louder_than_a_note(e["reference"]) and not (ours(e, "error") or ours(e, "warning"))]
    assert f"**{len(quiet)} containers draw reference errors or warnings while we report only notes.**" in text

    rep017 = [n for n, e in found.items() if "REP_017" in e["reference"].get("ERROR", [])]
    assert f"`REP_017` is an error on {len(rep017)} of the generated fixtures" in text
    io = [n for n in rep017 if {"REP_042", "REP_045"} <= set(found[n]["reference"].get("ERROR", []))]
    capped = sum("P6" in ours(found[n], "warning") for n in io)
    assert f"{WORDS[len(io)].capitalize()} of those {len(rep017)} also draw `REP_042` and `REP_045` errors." in text
    assert f"Here {WORDS[capped]} of the {WORDS[len(io)]} draw a P6 tool-limit warning" in text

    rep044 = [n for n, e in found.items() if "REP_044" in e["reference"].get("WARN", [])]
    notes = sum(not (ours(found[n], "error") or ours(found[n], "warning")) for n in rep044)
    limited = sum("P6" in ours(found[n], "warning") and not ours(found[n], "error") for n in rep044)
    unconfirmed = sum("P5" in ours(found[n], "error") for n in rep044)
    assert f"On {len(rep044)} of the generated fixtures, the reference also warns `REP_044`." in text
    assert (f"Of these {len(rep044)}, {notes} draw only P4 here, {limited} also draw a P6 warning, "
            f"and {WORDS[unconfirmed]} draws a P5 error") in text

    pair = [n for n, e in found.items() if {"REP_023", "REP_039"} <= set(e["reference"].get("ERROR", []))]
    # The generated page-tree fixtures that declare an invalid NumberOfPages are
    # named for the value they hold: invalid-zero, invalid-negative, ...
    invalid = [n for n in pair if n.startswith("invalid-")]
    assert (f"{WORDS[len(invalid)].capitalize()} generated fixtures with invalid NumberOfPages values "
            f"draw both `REP_023` and `REP_039` errors; {WORDS[len(pair) - len(invalid)]} other "
            f"containers in the sweep carry the same pair.") in text
