"""`0 error(s)` is a statement about findings, not about reach.

A supplier reads the last line and decides whether to send the delivery. When
this tool cannot open the archive at all it prints `1 error(s)` — the same shape
as a container with one small thing wrong — and a reader has no way to tell "one
thing to fix" from "we could not start". Six of this repository's own fixtures
report a full stop that way.

So the report says what it read, counted from the archive's own directory rather
than from how far this tool got: `1 of 3 metadata files` is a number a sender can
check with `unzip -l`, and it cannot be improved by the tool doing less. That
last property is the whole point. A figure over this tool's own machinery scores
a file that is not a ZIP at one out of one — the worse the input, the better the
number — and a reader watching that number would be reassured by the one case
that deserves it least.
"""
from __future__ import annotations

import io
import zipfile

from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION, counts_line
from vdi2770_validate.report import as_text
from vdi2770_validate.runner import check_bytes


def _line(report) -> str:
    text = as_text(report, True)
    for line in text.splitlines():
        if line.strip().startswith("read "):
            return line.strip()
    raise AssertionError(f"no `read` line in:\n{text}")


def test_a_file_that_is_not_an_archive_says_it_read_nothing():
    report = check_bytes(b"not a zip at all\n", "junk.zip")
    said = _line(report)
    assert "0 of 1 archives" in said, said
    # And the counts line is untouched: coverage is not a finding.
    assert "1 error(s)" in counts_line(as_text(report, True))


def test_a_conforming_container_says_it_read_all_of_it():
    report = check_bytes(CLEAN_DOCUMENT.read_bytes(), "clean.zip")
    said = _line(report)
    assert "1 of 1 archives" in said, said
    assert "1 of 1 metadata files" in said, said


def test_a_folder_this_tool_will_not_open_is_a_metadata_file_it_did_not_read():
    """Every rule layer runs on the archive that was opened, so a figure counted
    over this tool's machinery reads complete here while two document folders go
    unread. The archive's own directory says three metadata files; one was read.
    """
    base = zipfile.ZipFile(CLEAN_DOCUMENTATION)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in base.namelist():
            z.writestr(name, base.read(name))
        for folder in ("456-29201", "AB393"):
            z.writestr(f"{folder}/VDI2770_Metadata.xml", b"<x/>")
    report = check_bytes(buf.getvalue(), "folders.zip")
    assert "Z13" in {f.rule.id for f in report.findings}, "the premise"
    r = report.read
    assert r.metadata_found - r.metadata_read >= 2, (
        f"the two folders hold a metadata file each and neither was read: "
        f"{r.metadata_read} of {r.metadata_found}")
    assert f"{r.metadata_read} of {r.metadata_found} metadata files" in _line(report)


def test_the_figure_does_not_improve_when_the_tool_does_less(monkeypatch):
    """The denominator comes from the archive, so giving up cannot flatter it."""
    from vdi2770 import zipread

    raw = CLEAN_DOCUMENT.read_bytes()
    before = _line(check_bytes(raw, "c.zip"))
    monkeypatch.setattr(zipread, "MAX_METADATA_BYTES", 8)
    after = _line(check_bytes(raw, "c.zip"))
    assert "1 of 1 metadata files" in before, before
    assert "0 of 1 metadata files" in after, after


def test_the_machine_shape_carries_it_too_and_quiet_does_not_hide_it():
    """`--quiet` hides notes. It must not hide a statement about how much of
    this tool ran — that is the one line a CI log most needs, and the tool's
    other self-limitation, the PDF/A refusal, is carried only by notes and does
    disappear with them."""
    import json

    from vdi2770_validate.report import as_json

    junk = check_bytes(b"not a zip at all\n", "junk.zip")
    clean = check_bytes(CLEAN_DOCUMENT.read_bytes(), "c.zip")
    # Both values of the flag, and on a container where every number is
    # non-zero — a case where the figure is already 0 cannot tell a flag that
    # zeroes it from one that does not.
    for show_info in (True, False):
        assert json.loads(as_json(junk, show_info))["read"] == {
            "archives": {"opened": 0, "found": 1},
            "metadataFiles": {"read": 0, "found": 0},
            "complete": False,
            "note": json.loads(as_json(junk, show_info))["read"]["note"],
        }
        got = json.loads(as_json(clean, show_info))["read"]
        assert got["archives"] == {"opened": 1, "found": 1}, got
        assert got["metadataFiles"] == {"read": 1, "found": 1}, got
        assert got["complete"] is True, got


def test_the_listing_cap_does_not_move_the_figure(monkeypatch):
    """The cap bounds what is printed, not what was read."""
    from vdi2770_validate import model

    monkeypatch.setattr(model, "MAX_LISTED_PER_RULE", 1)
    report = check_bytes(CLEAN_DOCUMENT.read_bytes(), "c.zip")
    assert "1 of 1 archives" in _line(report), _line(report)
