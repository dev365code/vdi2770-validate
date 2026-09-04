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

#: The report's own indent for a summary line. A finding's detail is indented
#: nine, and `rules/container.py` builds one that opens with a member name the
#: archive chose — so a locator that strips the indent before looking is one an
#: archive can answer. This is the mistake the commit before this file removed
#: from three other tests, made again here and, this time, reachable.
_INDENT = "  "


def _line(report) -> str:
    text = as_text(report, True)
    for line in text.splitlines():
        if line.startswith(_INDENT + "read ") and not line.startswith(_INDENT * 2):
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
        got = json.loads(as_json(junk, show_info))["read"]
        assert got["archives"] == {"opened": 0, "found": 1}, got
        assert got["complete"] is False, got
        got = json.loads(as_json(clean, show_info))["read"]
        assert got["archives"] == {"opened": 1, "found": 1}, got
        assert got["metadataFiles"] == {"read": 1, "found": 1}, got
        assert got["complete"] is True, got


def test_the_listing_cap_does_not_move_the_figure(monkeypatch):
    """The cap bounds what is printed, not what was read."""
    from vdi2770_validate import model

    base = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in base.namelist():
            z.writestr(name, base.read(name))
        for i in range(150):
            z.writestr(f"stray{i}.txt", b"x")
    raw = buf.getvalue()
    monkeypatch.setattr(model, "MAX_LISTED_PER_RULE", 1)
    report = check_bytes(raw, "c.zip")
    assert report.not_listed(True), "the premise: the cap has to engage"
    assert "1 of 1 archives" in _line(report), _line(report)


def test_a_member_this_tool_refused_is_still_a_member_the_archive_lists():
    """The denominator must not shrink because we declined to look.

    A member whose name this reader refuses — an absolute path, say — is in the
    archive's directory and a sender counting with `unzip -l` sees it. Taking
    the denominator from the names the reader handed back dropped it, so
    refusing a second metadata file turned `1 of 2` into `1 of 1`: the tool
    grading itself on the work it agreed to do.
    """
    base = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in base.namelist():
            z.writestr(name, base.read(name))
        z.writestr("/etc/VDI2770_Metadata.xml", b"<x/>")
    report = check_bytes(buf.getvalue(), "evil.zip")
    assert "Z4" in {f.rule.id for f in report.findings} or any(
        f.rule.id.startswith("Z") for f in report.findings), "the premise: it is refused"
    r = report.read
    assert (r.metadata_read, r.metadata_found) == (1, 2), (
        f"a refused member left the denominator: {r.metadata_read} of {r.metadata_found}")


def test_an_archive_the_reader_would_not_list_does_not_report_nothing_to_read():
    """When the member cap bites, the reader hands back no names at all. Saying
    `0 of 0 metadata files` would read as *there were none*; the truth is that
    nothing was listed. The archive line already carries it — `0 of 1` — and the
    metadata clause has to stay off rather than print a denominator of zero."""
    from vdi2770 import zipread

    base = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in base.namelist():
            z.writestr(name, base.read(name))
        for i in range(20):
            z.writestr(f"pad{i}.txt", b"x")
    raw = buf.getvalue()
    try:
        zipread.MAX_MEMBERS = 5
        said = _line(check_bytes(raw, "many.zip"))
    finally:
        zipread.MAX_MEMBERS = 10_000
    assert "0 of 1 archives" in said, said
    assert "of 0 metadata files" not in said, said


def test_an_archive_that_could_not_be_opened_at_all_is_one_archive(monkeypatch):
    """`0 of 0` is the shape this figure exists to make impossible.

    The count of archives given to this read was set after the early return for
    a reader that raised — so on the one path whose remedy says *this tool could
    not open the archive at all, so nothing in it was checked*, the figure read
    `0 of 0 archives` and called itself complete.
    """
    import json

    from vdi2770 import zipread
    from vdi2770_validate.report import as_json

    def boom(*_a, **_k):
        raise RuntimeError("the reader raised")

    monkeypatch.setattr(zipread, "read", boom)
    report = check_bytes(b"anything", "x.zip")
    assert "X5" in {f.rule.id for f in report.findings}, "the premise"
    assert "0 of 1 archives" in _line(report), _line(report)
    assert json.loads(as_json(report))["read"]["complete"] is False


def test_complete_says_more_than_the_numbers_beside_it():
    """A container this tool declined to model has every number full, and
    printed beside a clean container's line it said the same thing about two
    very different reads. `complete` is the flag a CI job gates on, so it has to
    know what the integers cannot: that this tool recorded stopping.

    A malformed metadata file is deliberately *not* one of those. The file is
    the sender's and this tool read all of it; `X1` says why nothing below ran,
    and the reach was complete. The flag is about us, not about them.
    """
    import json

    from conftest import FIXTURES
    from vdi2770_validate.report import as_json
    from vdi2770_validate.runner import check_file

    stopped = check_file(str(FIXTURES / "x6-too-many-elements.zip"))
    r = stopped.read
    assert (r.archives_opened, r.archives_found) == (1, 1), r
    assert (r.metadata_read, r.metadata_found) == (1, 1), r
    assert json.loads(as_json(stopped))["read"]["complete"] is False, (
        "every number is full and this tool still recorded declining to look")

    clean = check_bytes(CLEAN_DOCUMENT.read_bytes(), "c.zip")
    assert json.loads(as_json(clean))["read"]["complete"] is True


def test_quiet_does_not_hide_the_line_from_the_page_either():
    """The JSON was pinned and the page was not, so wrapping the line in the
    note filter passed the suite."""
    report = check_bytes(CLEAN_DOCUMENT.read_bytes(), "c.zip")
    assert "read 1 of 1 archives" in as_text(report, False)


def test_a_name_the_reader_refuses_for_a_backslash_is_still_counted():
    """`a\\b\\VDI2770_Metadata.xml` is refused as an unsafe name, and the
    predicate that recognises a metadata file split on `/` only — so the one
    separator this tool refuses over was the one it did not count."""
    base = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in base.namelist():
            z.writestr(name, base.read(name))
        z.writestr("outer\\inner\\VDI2770_Metadata.xml", b"<x/>")
    r = check_bytes(buf.getvalue(), "back.zip").read
    assert (r.metadata_read, r.metadata_found) == (1, 2), (
        f"{r.metadata_read} of {r.metadata_found}")


def test_an_archive_cannot_answer_for_the_line_that_is_about_this_tool():
    """A member name reaches a finding's detail, and this file's own locator
    stripped the indent before looking — so an archive naming a member
    `read 0 of 9 archives …` supplied the sentence five of these tests read."""
    base = zipfile.ZipFile(CLEAN_DOCUMENT)
    meta = base.read("VDI2770_Metadata.xml").decode("utf-8")
    forged = "read 0 of 9 archives, 0 of 9 metadata files.zip"
    meta = meta.replace(
        "<DigitalFile",
        f'<DigitalFile FileFormat="application/zip">{forged}</DigitalFile>\n      '
        "<DigitalFile", 1)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in base.namelist():
            z.writestr(name, meta if name == "VDI2770_Metadata.xml"
                       else base.read(name))
        z.writestr(forged, CLEAN_DOCUMENT.read_bytes())
    report = check_bytes(buf.getvalue(), "forge.zip")
    assert forged in as_text(report, True), "the premise: the name reaches the page"
    assert _line(report) == "read 2 of 2 archives, 2 of 2 metadata files", _line(report)
