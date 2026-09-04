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

    assert silent, ("the premise: the sweep holds at least one container the "
                    "reference is louder about than we are")
    unrecorded = {name: keys for name, keys in silent.items()
                  if name not in PAGE and not any(k in PAGE for k in keys)}
    assert not unrecorded, (
        "the reference reports a warning or worse and this tool reports nothing "
        "louder than a note, and the page does not say so:\n"
        + "\n".join(f"    {n}: {k}" for n, k in sorted(unrecorded.items())))
