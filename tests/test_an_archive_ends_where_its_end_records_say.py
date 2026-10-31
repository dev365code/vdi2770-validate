"""Where an archive ends is read here, not asked of the library.

APPNOTE 6.3.10 keeps the central directory's place at the end of the archive:
the end of central directory record (4.3.16) and, when a value does not fit
it, a zip64 end of central directory record (4.3.14) with a locator in front of
the end record saying where that is (4.3.15). Python's `zipfile` reads those
records two ways. Before the repair for CVE-2025-8291 it took the 56 bytes in
front of the locator to be the zip64 record, whatever the locator said, and
went on without one when they were not; after it, it follows the locator and
holds the record to its own size. So one archive was read on one Python and
refused on another -- and the browser page carries a release from before.

The reader now reads the end itself first, the way APPNOTE lays it out, and
asks the library about an archive only when every release would read that end
alike. And an end that contradicts itself is refused even where every release
reads it: one end record, and nothing after it (4.3.1, 4.3.16); one disk
(4.4.19 to 4.4.21); and fields that say one thing, whichever record holds them
(4.4.21 to 4.4.24) -- because a reader that takes the other half of a
contradiction at its word reads a different archive. Each case below is a
plain archive whose end has been rewritten field by field
(`tools/archive_ends.py`), and the reason one is refused is asserted to the
byte -- which is what makes the assertion mean the same thing on a Python whose
library would refuse it too, in other words.
"""
import inspect
import os
import sys
import zipfile

import pytest

from conftest import CLEAN_DOCUMENT, ROOT

sys.path.insert(0, str(ROOT / "tools"))
import archive_ends as ENDS  # noqa: E402 - after sys.path
from vdi2770 import zipread  # noqa: E402
from vdi2770.zipread import Kind  # noqa: E402


def _members(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


#: The conforming document container, stored and dated so that every Python
#: builds these same bytes from it.
PLAIN = ENDS.plain(_members(CLEAN_DOCUMENT))
CASES = ENDS.cases(PLAIN)
#: Where the zip64 end record is put: right after the central directory.
AT = len(PLAIN) - 22
#: What the plain archive's end record says: three entries, and where they are listed.
_, SAID = ENDS.directory(PLAIN)

#: The ends every release reads alike, and that are read.
READ = ["plain", "zip64", "zip64-with-its-values-in-the-end-record", "zip64-on-no-disks",
        "end-record-with-the-longest-comment", "plain-holding-a-stored-archive",
        "plain-with-a-closing-record-in-a-member", "zip64-end-record-disks-as-placeholders"]

#: How far into the file the archive begins, in the cases that put bytes in front of it.
_PREFIX = ("the archive its end record describes begins 7 bytes into the file, and what "
           "comes before it is not part of it")

#: How a split archive is refused, wherever its end says it is split.
_ONE_FILE = "of a split archive; this reader reads an archive that is one file"

#: The rest, each with the one reason it is not a readable ZIP archive.
REFUSED = {
    # A zip64 locator naming another disk, or more than one (4.3.15): a split
    # archive, in this reader's words as the end records' disk fields are.
    "zip64-locator-on-disk-1": f"the zip64 locator places the zip64 end record on disk 1 {_ONE_FILE}",
    "zip64-locator-of-two-disks": f"the zip64 locator counts 2 disks {_ONE_FILE}",
    "zip64-locator-of-two-disks-pointing-past-its-record": f"the zip64 locator counts 2 disks {_ONE_FILE}",
    # The library's own words, the same on every release.
    "no-end-record": "File is not a zip file",
    # Bytes in front of the archive, its offsets counted from where it begins.
    "plain-with-bytes-in-front": _PREFIX,
    "zip64-with-bytes-in-front": _PREFIX,
    # Read before the repair, refused after it (4.3.15, 4.3.14.1).
    "zip64-locator-past-its-record": "the zip64 locator places the zip64 end record 8 bytes past where it is",
    "zip64-locator-before-its-record": "the zip64 locator places the zip64 end record 8 bytes before where it is",
    "zip64-locator-before-its-record-values-in-the-end-record":
        "the zip64 locator places the zip64 end record 8 bytes before where it is",
    "zip64-record-of-the-wrong-size":
        "the zip64 end record gives its size as 60 bytes, and the locator follows it after 56",
    "zip64-record-of-the-wrong-size-values-in-the-end-record":
        "the zip64 end record gives its size as 60 bytes, and the locator follows it after 56",
    # Refused before the repair, read after it (4.3.14.2, 4.3.14.3, 4.4.27).
    "zip64-record-with-extensible-data":
        "the zip64 end record carries 10 bytes past its fixed fields, which this reader does not read",
    "zip64-record-with-extensible-data-values-in-the-end-record":
        "the zip64 end record carries 10 bytes past its fixed fields, which this reader does not read",
    # Refused by every release, in words that differ between them.
    "end-record-placeholders-and-no-zip64":
        "the end record gives the size of the central directory as 4,294,967,295, the value that "
        "says it is in a zip64 end record, and the archive has none",
    "end-record-directory-larger-than-what-precedes-it":
        f"the end record gives the central directory {len(PLAIN):,} bytes, more than the {AT:,} "
        f"that come before it",
    "zip64-locator-pointing-at-nothing":
        f"the zip64 locator points at byte {AT:,}, and no zip64 end record begins there",
    "zip64-locator-pointing-at-nothing-values-in-the-end-record":
        f"the zip64 locator points at byte {AT:,}, and no zip64 end record begins there",
    "zip64-record-after-a-gap": "the central directory ends 4 bytes before the zip64 end record begins",
    "zip64-with-bytes-in-front-located-from-the-file": _PREFIX,
    "zip64-record-placing-the-directory-past-where-it-is":
        "the zip64 end record places its central directory 4 bytes past where it is",
    # Read by the releases before 3.12.8 and 3.13.1, which look for the record one
    # byte further back than the longest comment reaches, and refused after.
    "end-record-with-the-longest-comment-and-a-byte-after-it": "File is not a zip file",
}

#: Read by every release, and alike, and each a contradiction: refused here.
CONTRADICTORY = {
    # One end record, and the file ends with it and its comment (4.3.1, 4.3.16).
    "end-record-with-bytes-after-it":
        "the archive's end record ends 7 bytes before the end of the file, and what comes "
        "after it is not part of it",
    "end-record-comment-past-the-end":
        "the archive's end record gives its comment 9 bytes, and the file ends 3 bytes after "
        "the record",
    "end-record-in-the-comment":
        f"the signature of an end record occurs again at byte {AT + 22:,}, after the end "
        f"record at byte {AT:,}",
    # One disk, holding every entry (4.4.19 to 4.4.21; 4.3.14 for the zip64 record).
    "end-record-on-disk-1": f"the end record places this archive on disk 1 {_ONE_FILE}",
    "end-record-directory-on-disk-1": f"the end record places the central directory on disk 1 {_ONE_FILE}",
    "end-record-entries-on-this-disk-differ": "the end record counts 0 entries on this disk and 3 in all",
    "end-record-whose-counts-spell-its-signature":
        "the end record counts 19,280 entries on this disk and 1,541 in all",
    "zip64-record-on-disk-1": f"the zip64 end record places this archive on disk 1 {_ONE_FILE}",
    "zip64-record-directory-on-disk-1":
        f"the zip64 end record places the central directory on disk 1 {_ONE_FILE}",
    "zip64-record-entries-on-this-disk-differ":
        "the zip64 end record counts 0 entries on this disk and 3 in all",
    "zip64-end-record-on-disk-1": f"the end record places this archive on disk 1 {_ONE_FILE}",
    # A field the end record does not leave to the zip64 record is the value
    # (4.4.21 to 4.4.24), so it is the zip64 record's value.
    "zip64-end-record-offset-disagrees":
        f"the end record gives the offset of the central directory as 1 and the zip64 end "
        f"record as {SAID['offset']:,}",
    "zip64-end-record-entries-disagree":
        "the end record gives the number of entries on this disk as 4 and the zip64 end "
        "record as 3",
    # As many entries as the central directory holds (4.4.22).
    "end-record-entries-wrong": "the end record counts 4 entries and the central directory holds 3",
    "zip64-entries-wrong": "the zip64 end record counts 4 entries and the central directory holds 3",
}


def _refusals(name):
    c = zipread.read(CASES[name], name + ".zip")
    return c, [d.detail for d in c.defects if d.kind == "not-a-zip"]


def test_every_case_is_either_read_or_refused_for_a_reason():
    assert sorted(READ + list(REFUSED) + list(CONTRADICTORY)) == sorted(CASES)
    assert SAID["entries"] == 3


@pytest.mark.parametrize("name", READ)
def test_an_end_every_release_reads_alike_is_read(name):
    """A zip64 end that is what APPNOTE lays out, with its values in the zip64
    record or in the end record too, and the plain end it stands for."""
    c, refused = _refusals(name)
    assert refused == [] and c.kind is not Kind.UNREADABLE, refused


@pytest.mark.parametrize("name", sorted(REFUSED))
def test_an_end_the_releases_disagree_on_is_refused_for_the_same_reason_on_each(name):
    """The words are the reader's -- or, where every release of the library
    already says the same thing, the library's -- so the report is one report
    whichever Python printed it."""
    c, refused = _refusals(name)
    assert c.kind is Kind.UNREADABLE and refused == [REFUSED[name]], refused


@pytest.mark.parametrize("name", sorted(CONTRADICTORY))
def test_an_end_that_contradicts_itself_is_refused_though_every_release_reads_it(name):
    """No release of the library refuses these, and each says two things about
    one archive: the reader takes neither."""
    c, refused = _refusals(name)
    assert c.kind is Kind.UNREADABLE and refused == [CONTRADICTORY[name]], refused


@pytest.mark.parametrize("name", sorted(REFUSED) + sorted(CONTRADICTORY))
def test_a_later_read_with_no_list_refuses_an_archive_the_first_one_refused(name):
    """`read` refuses each of these whole, and `member_bytes` asked without the
    names `read` accepted read some of them anyway: an archive with bytes in
    front of it, or whose end records count other entries than its central
    directory lists, gave the library an archive to open, and the later read
    took it."""
    c, _ = _refusals(name)
    assert c.kind is Kind.UNREADABLE
    for member in _members(CLEAN_DOCUMENT):
        assert zipread.member_bytes(CASES[name], member) is None, member


def test_a_later_read_with_no_list_refuses_a_container_cut_short_in_one_it_stores():
    """A container that stores a document container without compressing it,
    cut short in transit, can end in that document container. `read` refuses
    the file: the archive its end record describes does not begin it. Asked
    without the list, `member_bytes` handed over the metadata of the document
    container inside -- a file nobody delivered."""
    inner = PLAIN
    outer = ENDS.plain({"inner.zip": inner, "VDI2770_Metadata.xml": b"<x/>"})
    cut = outer[:outer.index(inner) + len(inner)]
    assert zipread.read(cut, "cut.zip").kind is Kind.UNREADABLE
    for member in _members(CLEAN_DOCUMENT):
        assert zipread.member_bytes(cut, member) is None, member


def test_the_reader_asks_the_library_nothing_private_about_where_an_archive_ends():
    """Where the central directory is was worked out from `zipfile._EndRecData`
    and `zipfile._ECD_OFFSET`, which are not the library's to promise and which
    report a zip64 end differently from one release to the next."""
    source = inspect.getsource(zipread)
    assert "_EndRecData" not in source and "_ECD_" not in source and "start_dir" not in source


def _generation() -> str:
    """Which way this Python's `zipfile` reads a zip64 end: "G1", as releases did
    before the repair for CVE-2025-8291, or "G2", as they do after it -- told by
    the repair's own words. The one private name a test here reads: the words
    are in that function, and a Python without it is one whose way of reading
    cannot be told -- which is said, rather than raised as an AttributeError."""
    reads = getattr(zipfile, "_EndRecData64", None)
    if reads is None:
        pytest.fail("this Python's zipfile has no _EndRecData64, so which way it reads a zip64 end cannot be told")
    repaired = "Corrupt zip64 end of central directory record" in inspect.getsource(reads)
    return "G2" if repaired else "G1"


def test_a_job_that_holds_these_on_one_kind_of_release_runs_on_that_kind():
    """The cases above prove nothing about the two kinds of release unless they
    run on both. The page's job runs them on its own pinned release from before
    the repair and the 3.13 check row on one from after it, and each says so
    here -- so a job moved to another release is a red job, not a quiet loss of
    one of the two ways of reading."""
    want = os.environ.get("VDI2770_ZIPFILE_GENERATION")
    if not want:
        pytest.skip("this run names no kind of release")
    assert _generation() == want, f"this Python reads zip64 ends as {_generation()}, the job says {want}"



# Each end below sits on the other side of one condition from a case above: the
# case above holds the reader to the condition, and these to its edge, which a
# reader testing the condition the wrong way round reads differently.


def test_the_last_record_the_library_takes_is_the_one_the_reader_takes():
    """The library takes the last 22 bytes as the end record only when they are
    one with no comment, and otherwise the last signature in the file. Here the
    record's own offset and comment length spell a second signature four bytes
    from the end, with no room for a record after it: no archive, in the
    library's words on every release. A reader that took the last 22 bytes for
    the record whatever its comment length says took another record, and
    refused the file in other words."""
    data = ENDS.end(PLAIN, offset=int.from_bytes(b"\0\0PK", "little"),
                    comment_length=int.from_bytes(b"\x05\x06", "little"))
    assert data[-4:] == ENDS.END
    c = zipread.read(data, "spelled.zip")
    assert c.kind is Kind.UNREADABLE
    assert [d.detail for d in c.defects if d.kind == "not-a-zip"] == ["File is not a zip file"]


@pytest.mark.parametrize("length", [6, 256])
def test_either_byte_of_the_comment_length_keeps_the_last_22_bytes_from_being_the_record(length):
    """The comment length is two bytes, and the last 22 bytes are the end record
    only when both are zero. A length of 6 sets the first of them and one of 256
    the second; with the record's own offset spelling a signature six bytes from
    the end, either is no archive, in the library's words on every release. A
    reader that read one byte of the two took the last 22 bytes for a record
    whose comment the file does not hold, and refused the file in other words."""
    data = ENDS.end(PLAIN, offset=int.from_bytes(ENDS.END, "little"), comment_length=length)
    assert data[-6:-2] == ENDS.END
    c = zipread.read(data, "comment.zip")
    assert c.kind is Kind.UNREADABLE
    assert [d.detail for d in c.defects if d.kind == "not-a-zip"] == ["File is not a zip file"]


@pytest.mark.parametrize("placeholders", [True, False])
def test_a_zip64_record_smaller_than_its_fixed_fields_is_refused(placeholders):
    """A record of version 1 with nothing extensible gives its size as 44
    (4.3.14.1), and one giving 43 says it ends a byte before its locator begins.
    Refused, as one giving more is, in this reader's words -- where a reader
    holding the size only against records too large handed it to the library."""
    data = ENDS.zip64(PLAIN, size=43, placeholders=placeholders)
    c = zipread.read(data, "smaller.zip")
    assert c.kind is Kind.UNREADABLE
    assert [d.detail for d in c.defects if d.kind == "not-a-zip"] == [
        "the zip64 end record gives its size as 55 bytes, and the locator follows it after 56"]


def test_the_empty_archive_the_library_writes_is_read():
    """Twenty-two bytes: an end record counting no entries in a central directory
    of no bytes, at the start of the file. The directory fits in front of the
    record with nothing to spare, and the archive is read."""
    data = ENDS.plain({})
    assert len(data) == 22
    c = zipread.read(data, "empty.zip")
    assert c.kind is not Kind.UNREADABLE
    assert [d.detail for d in c.defects if d.kind == "not-a-zip"] == []


def test_a_central_directory_one_byte_larger_than_what_precedes_it_is_refused():
    """The other side of that edge: an end record giving its central directory
    one byte more than comes before the record. Refused, in this reader's words
    -- where a reader that let the one byte through handed the archive to the
    library, whose words for it differ from one release to the next."""
    data = ENDS.end(PLAIN, size=AT + 1)
    c = zipread.read(data, "larger.zip")
    assert c.kind is Kind.UNREADABLE
    assert [d.detail for d in c.defects if d.kind == "not-a-zip"] == [
        f"the end record gives the central directory {AT + 1:,} bytes, more than the {AT:,} "
        f"that come before it"]


@pytest.mark.parametrize("form", ["end", "zip64"])
def test_an_end_counting_fewer_entries_than_its_directory_holds_is_refused(form):
    """As many entries as the end records count (4.4.22) -- fewer, as well as
    more: a reader comparing in one direction only read the third entry of an
    archive that says it has two."""
    data = ENDS.end(PLAIN, entries=2) if form == "end" else ENDS.zip64(PLAIN, entries=2)
    which = "end record" if form == "end" else "zip64 end record"
    c = zipread.read(data, "fewer.zip")
    assert c.kind is Kind.UNREADABLE
    assert [d.detail for d in c.defects if d.kind == "not-a-zip"] == [
        f"the {which} counts 2 entries and the central directory holds 3"]
