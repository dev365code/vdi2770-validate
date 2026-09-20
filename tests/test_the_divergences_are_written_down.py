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
