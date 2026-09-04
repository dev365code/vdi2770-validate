"""Three things that must be true of the read figure on every container here.

Each of the earlier tests builds one container and asserts one thing about it.
These sweep the corpus and the fixtures instead, so a change somewhere else —
a new `continue` in the walk, a rule that stops firing, a counter that learns to
double — fails without anyone remembering to come back and write a test for it.

They are also the three properties the figure is *for*. If any of them can be
false, the number stops being evidence and becomes decoration.
"""
from __future__ import annotations

import json

import pytest

from conftest import CORPUS, FIXTURES
from vdi2770_validate.model import Severity
from vdi2770_validate.report import as_json
from vdi2770_validate.runner import check_file

CONTAINERS = sorted(CORPUS.rglob("*.zip")) + sorted(FIXTURES.rglob("*.zip"))


def _short(read) -> bool:
    return (read.archives_opened < read.archives_found
            or read.metadata_read < read.metadata_found)


def test_there_are_containers_to_sweep():
    """A sweep over nothing passes every assertion it makes."""
    assert len(CONTAINERS) >= 40, len(CONTAINERS)


@pytest.mark.parametrize("path", CONTAINERS, ids=lambda p: p.name)
def test_the_figure_never_claims_more_than_the_archive_lists(path):
    """`opened` over `found` would be this tool counting work nobody gave it."""
    r = check_file(str(path)).read
    assert 0 <= r.archives_opened <= r.archives_found, r
    assert 0 <= r.metadata_read <= r.metadata_found, r


@pytest.mark.parametrize("path", CONTAINERS, ids=lambda p: p.name)
def test_a_read_that_fell_short_is_never_silent(path):
    """The figure says *how much*; a finding has to say *what about it*.

    A floor, and worth saying which: it catches a short read that says nothing,
    and it does not prove the finding it found is the one that explains the
    shortfall. Silencing `Z13` on the folders container leaves this green,
    because two unrelated errors are still there. Silencing `Z10` does not:
    that container's only finding is the one that explains its `0 of 1`, and the
    test goes red — which is how I know the assertion is load-bearing somewhere
    rather than everywhere.

    A page telling a reader the delivery is fine, with the one number that
    disagrees printed underneath as though it were furniture, is the thing this
    forbids."""
    report = check_file(str(path))
    if not _short(report.read):
        return
    assert report.count(Severity.ERROR) or report.count(Severity.WARNING), (
        f"{path.name} read {report.read} and said nothing louder than a note")


@pytest.mark.parametrize("path", CONTAINERS, ids=lambda p: p.name)
def test_complete_is_never_true_of_a_read_that_fell_short(path):
    """`complete` is the one field a CI job gates on."""
    report = check_file(str(path))
    said = json.loads(as_json(report))["read"]["complete"]
    assert not (said and _short(report.read)), report.read
