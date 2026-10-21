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
alike. Each case below is a plain archive whose end has been rewritten field
by field (`tools/archive_ends.py`), and the reason one is refused is asserted
to the byte -- which is what makes the assertion mean the same thing on a
Python whose library would refuse it too, in other words.
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

#: The ends every release reads alike, and that are read.
READ = ["plain", "zip64", "zip64-with-its-values-in-the-end-record", "zip64-on-no-disks",
        "end-record-whose-counts-spell-its-signature"]

#: How far into the file the archive begins, in the cases that put bytes in front of it.
_PREFIX = ("the archive its end record describes begins 7 bytes into the file, and what "
           "comes before it is not part of it")

#: The rest, each with the one reason it is not a readable ZIP archive.
REFUSED = {
    # The library's own words, the same on every release.
    "zip64-locator-on-disk-1": "zipfiles that span multiple disks are not supported",
    "zip64-locator-of-two-disks": "zipfiles that span multiple disks are not supported",
    "zip64-locator-of-two-disks-pointing-past-its-record": "zipfiles that span multiple disks are not supported",
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
}


def _refusals(name):
    c = zipread.read(CASES[name], name + ".zip")
    return c, [d.detail for d in c.defects if d.kind == "not-a-zip"]


def test_every_case_is_either_read_or_refused_for_a_reason():
    assert sorted(READ + list(REFUSED)) == sorted(CASES)


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


def test_the_reader_asks_the_library_nothing_private_about_where_an_archive_ends():
    """Where the central directory is was worked out from `zipfile._EndRecData`
    and `zipfile._ECD_OFFSET`, which are not the library's to promise and which
    report a zip64 end differently from one release to the next."""
    source = inspect.getsource(zipread)
    assert "_EndRecData" not in source and "_ECD_" not in source and "start_dir" not in source


def _generation() -> str:
    """Which way this Python's `zipfile` reads a zip64 end: "G1", as releases did
    before the repair for CVE-2025-8291, or "G2", as they do after it -- told by
    the repair's own words."""
    repaired = "Corrupt zip64 end of central directory record" in inspect.getsource(zipfile._EndRecData64)
    return "G2" if repaired else "G1"


def test_a_job_that_holds_these_on_one_kind_of_release_runs_on_that_kind():
    """The cases above prove nothing about the two kinds of release unless they
    run on both. The check jobs run them on whatever release each Python is at,
    which after the repair stays repaired; the page's job runs them on its own
    pinned release from before it, and says so here -- so a job moved to another
    release is a red job, not a quiet loss of the one that still reads the old way."""
    want = os.environ.get("VDI2770_ZIPFILE_GENERATION")
    if not want:
        pytest.skip("this run names no kind of release")
    assert _generation() == want, f"this Python reads zip64 ends as {_generation()}, the job says {want}"

