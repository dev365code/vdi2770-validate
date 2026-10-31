"""What `docs/divergences.md` says Python's own ZIP reading does with a zip64 end
record whose size field does not match where its locator follows, held on the
Python running this suite.

The page names the patch releases that sentence was measured on: one list that
refuses such an end and one that reads it. A sentence about what another piece
of software does is a claim this repository can only make where it measured, so
the sentence lists releases rather than a range, and this file holds it wherever
the suite runs on one of them: the archive is built here, from the conforming
container, by the end-record builder the fixtures use, and opened with `zipfile`
alone. On a release the page does not name there is nothing to hold, and the
skip says which release it was. The sentence's last clause is this tool's own
behaviour, and holds everywhere.
"""
import io
import platform
import re
import sys
import zipfile

import pytest
from vdi2770_validate.runner import check_bytes

from conftest import CLEAN_DOCUMENT, ROOT

sys.path.insert(0, str(ROOT / "tools"))
import archive_ends as ENDS  # noqa: E402 - after sys.path

SENTENCE = re.compile(
    r"Python's own ZIP reading refuses a zip64 end record whose size field does "
    r"not match where its locator follows in the patch releases measured here "
    r"\u2014 (?P<refuses>[0-9., and]+) \u2014 and reads one in "
    r"(?P<reads>[0-9., and]+); this tool refuses it on every Python\.")


def _releases(listed: str):
    return [v for v in re.split(r",\s*|\s+and\s+", listed.strip()) if v]


def _lists():
    text = " ".join((ROOT / "docs" / "divergences.md").read_text(encoding="utf-8").split())
    found = SENTENCE.search(text)
    assert found, "the sentence this file holds is no longer on the page"
    return _releases(found.group("refuses")), _releases(found.group("reads"))


def _size_that_counts_the_leading_twelve():
    """The conforming container under a zip64 end whose record is 56 bytes and
    says 68: the size field counts the twelve bytes APPNOTE 4.3.14.1 says it
    should not."""
    with zipfile.ZipFile(CLEAN_DOCUMENT) as z:
        files = {i.filename: z.read(i) for i in z.infolist()}
    return files, ENDS.zip64(ENDS.plain(files), size=56)


def test_the_two_lists_name_releases_and_share_none():
    refuses, reads = _lists()
    assert refuses and reads and not set(refuses) & set(reads)
    assert all(re.fullmatch(r"3\.\d+\.\d+", v) for v in refuses + reads)


def test_pythons_own_zip_reading_does_what_the_page_says_on_this_release():
    refuses, reads = _lists()
    here = platform.python_version()
    if here not in refuses + reads:
        pytest.skip(f"Python {here} is not a release the page names")
    files, data = _size_that_counts_the_leading_twelve()
    if here in refuses:
        with pytest.raises(zipfile.BadZipFile):
            zipfile.ZipFile(io.BytesIO(data))
    else:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            assert sorted(z.namelist()) == sorted(files)
            assert all(z.read(n) == files[n] for n in files)


def test_this_tool_refuses_it_on_every_python():
    _, data = _size_that_counts_the_leading_twelve()
    found = [(f.rule.id, f.severity.value) for f in check_bytes(data, "end.zip").findings]
    assert ("Z1", "error") in found
