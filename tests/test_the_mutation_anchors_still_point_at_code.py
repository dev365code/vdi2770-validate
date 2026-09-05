"""Every mutation row has to be able to find the line it breaks.

`make mutations` proves each row's edit makes a named test fail. It takes minutes
and it is not part of `make check`, so an anchor that stops matching -- because
the line it quotes was reworded in some other change -- sits unnoticed until
somebody runs the slow gate. That is what happened: `F2`'s emit line grew a
`- collides` term, `rules/f2-emits-in-a-fixed-order` went to zero matches, and
the row proved nothing in between.

Zero matches is a row that cannot run. More than one is worse: the runner would
edit every occurrence, so the test that goes red need not be red for the reason
the row claims. Neither needs the mutation itself to be applied to detect, which
is why this is seconds rather than minutes.
"""
import sys

from conftest import ROOT

sys.path.insert(0, str(ROOT / "tools"))
from mutation_table import TABLE  # noqa: E402


def test_every_anchor_appears_exactly_once_in_the_file_it_names():
    wrong = []
    for row in TABLE:
        name, path, anchor = row[0], row[1], row[2]
        target = ROOT / path
        if not target.exists():
            wrong.append(f"{name}: {path} is not in this tree")
            continue
        seen = target.read_text(encoding="utf-8").count(anchor)
        if seen != 1:
            wrong.append(f"{name}: the anchor appears {seen} times in {path}")
    assert not wrong, (
        "mutation rows whose anchor no longer pins one line — each proves "
        "nothing until it is re-pinned:\n  " + "\n  ".join(wrong))


def test_every_row_names_a_test_that_exists():
    """The other half of a row: the anchor points at code to break, and the
    `proves` list points at what has to go red. An anchor that stops matching is
    caught above. A *selection* that stops matching is not, and it fails in the
    opposite direction — pytest exits non-zero on a selection that matches
    nothing, so the row reads as proven while nothing ran.

    Not hypothetical. Editing this suite by replacing a span between two named
    tests deleted seven tests that sat between them, and the whole suite stayed
    green: a deleted test is not a failing test. Two of the rows here pointed at
    one of them. `make mutations` would have said so, in minutes, later.
    """
    missing = []
    for row in TABLE:
        name, proves = row[0], row[4]
        for selection in proves:
            if "::" not in selection:
                # A whole file, or a tool invocation like
                # `tools/rule_coverage.py --check`. The first word is the path.
                path = ROOT / selection.split()[0]
                if not path.exists():
                    missing.append(f"{name}: {selection} is not in this tree")
                continue
            path, _, target = selection.partition("::")
            here = ROOT / path
            if not here.exists():
                missing.append(f"{name}: {path} is not in this tree")
            elif f"def {target}(" not in here.read_text(encoding="utf-8"):
                missing.append(f"{name}: {path} has no {target}")
    assert not missing, (
        "mutation rows naming a test that is not there — pytest exits non-zero "
        "on a selection that matches nothing, so each of these reads as proven "
        "while nothing ran:\n  " + "\n  ".join(missing))
