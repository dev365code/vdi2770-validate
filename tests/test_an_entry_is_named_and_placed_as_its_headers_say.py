"""An entry is named and placed by what its headers say, the same way on every Python.

APPNOTE 6.3.10 names an entry in UTF-8 when general purpose bit 11 says so and
in IBM Code Page 437 when it does not (4.4.4, APPENDIX D), and lets an Info-ZIP
Unicode Path extra field carry the UTF-8 version of a name the header holds in
another character set (4.6.9). Python's `zipfile` reads that field from 3.12 on
and not before, so an archive whose names it gives was read one way on one
Python and another way on the next -- and one whose field is damaged was
refused by the newer releases alone. The repair for CVE-2024-0450, which
refuses an entry whose data runs on over the next one's, is in some releases
and not in others; of two entries sharing a local header, the releases that
have it refuse one before 3.12.10 and 3.13.3, and only warn from those on.

The reader now names every entry itself, the way APPNOTE says, and refuses an
entry that names two files, or whose bytes are another entry's too, before the
library is asked -- so the names, the verdict and the sentence are the same on
every Python. Each case below is the conforming document container with one
entry renamed or moved, field by field (`tools/archive_entries.py`), and every
sentence is asserted to the byte.
"""
import inspect
import io
import struct
import sys
import unicodedata
import warnings
import zipfile

import pytest

from conftest import CLEAN_DOCUMENT, ROOT

sys.path.insert(0, str(ROOT / "tools"))
from vdi2770_validate.runner import check_bytes  # noqa: E402

import archive_entries as ENTRIES  # noqa: E402 - after sys.path
from vdi2770 import zipread  # noqa: E402
from vdi2770.validate.rules.container import ONE_NAME, REBUILD  # noqa: E402
from vdi2770.zipread import Kind  # noqa: E402


def _members(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


#: The conforming document container's members, in its order; the PDF is the
#: entry each case renames or moves.
FILES = _members(CLEAN_DOCUMENT)
SUBJECT = "B.pdf"
CASES = ENTRIES.cases(FILES, SUBJECT)
OTHERS = sorted(n for n in FILES if n != SUBJECT)


def _layout():
    """Where each member's local header begins, as the builder stores them,
    and where the central directory begins after them."""
    at, starts = 0, {}
    for name, data in FILES.items():
        starts[name] = at
        at += 30 + len(name.encode("utf-8")) + len(data)
    return starts, at


STARTS, DIRECTORY = _layout()
LAST = list(FILES)[-1]
#: Where the last member's local header lies when it is written after the end
#: record, as its comment: past the other members, the central directory and
#: the end record's 22 bytes.
PAST = STARTS[LAST] + sum(46 + len(name.encode("utf-8")) for name in FILES) + 22
#: The entry one case adds after the last member, and where the last
#: member's local header and that entry's lie when both are written after
#: the end record, in that order: past the central directory, which lists
#: one entry more, and the end record's 22 bytes.
ADDED = "C.txt"
PAST_FIRST = STARTS[LAST] + sum(46 + len(name.encode("utf-8")) for name in [*FILES, ADDED]) + 22
PAST_SECOND = PAST_FIRST + 30 + len(LAST.encode("utf-8")) + len(FILES[LAST])

#: Read on every Python, with nothing refused: the name the PDF has.
NAMED = {
    "plain": "B.pdf",
    "a-flagged-utf-8-name": "B\u00fc.pdf",
    # Its bytes are UTF-8 and nothing says so, so the name is IBM 437's.
    "an-unflagged-utf-8-name": "B\u251c\u255d.pdf",
    "a-unicode-path-whose-crc-is-another-names": "X.pdf",
    "a-unicode-path-of-version-2": "B\u251c\u255d.pdf",
    "a-unicode-path-repeating-an-ascii-name": "B.pdf",
    # The Unicode Path field's name, where the field is one (4.6.9).
    "an-unflagged-utf-8-name-with-its-unicode-path": "B\u00fc.pdf",
    "a-name-in-another-code-page-with-its-unicode-path": "B\u00fc.pdf",
    # A header holding bytes other than printable ASCII: its field is taken at
    # its word, whatever IBM 437 makes of the header.
    "a-name-in-ibm-437-with-a-unicode-path-naming-another-file": "X.pdf",
    "a-header-with-a-control-byte-and-a-unicode-path": "B\u263a.pdf",
    # Compared as the library tidies a name: cut at its first NUL -- and a
    # field that leaves no name is none.
    "a-unicode-path-carrying-a-nul": "X.pdf",
    "a-unicode-path-cut-to-nothing": "B\u207f.pdf",
    "a-flagged-utf-8-name-with-its-unicode-path": "B\u00fc.pdf",
    # A field that is not one is passed over, and says nothing.
    "a-unicode-path-that-is-not-utf-8": "B.pdf",
    "an-empty-unicode-path": "B.pdf",
    "a-unicode-path-beside-a-zip64-field": "B\u00fc.pdf",
    "a-unicode-path-too-short-for-its-crc": "B.pdf",
}

_TWO = "one stretch of bytes would be read as two members"
_SHARED = f"its local header, at byte {STARTS[SUBJECT]:,}, is another entry's too: {_TWO}"
_AMBIGUOUS = ("2 entries in this archive carry this name; the reader cannot say which one is "
              "meant and read none of them")
#: Why two fields name nothing: not a sentence of APPNOTE's, which forbids
#: neither, but what the releases of Python's `zipfile` do with them -- 3.9.6
#: reads the header's name, 3.12.10, 3.13.2 and 3.13.15 the last field's, and
#: those refuse the archive when the first is not UTF-8.
_TWICE = ("its extra field carries 2 Info-ZIP Unicode Path fields (APPNOTE 4.6.9); Python's "
          "zipfile releases take the last of them as its name, or none of them, or refuse the "
          "archive, so this tool takes none of them and does not read the entry")


def _two_names(field):
    return (f"its header calls it 'X.pdf' and its Info-ZIP Unicode Path field (APPNOTE 4.6.9) "
            f"calls it {field}; that field is the UTF-8 version of the header's name, so the "
            f"entry names two files")


#: Read on every Python with an entry refused: the members still read, and
#: each refused name with the kind of refusal and its one sentence.
REFUSED = {
    # The library's own words, the same on every release.
    "a-local-name-other-than-the-directorys": (OTHERS, {
        "B.pdf": ("member-unreadable", "BadZipFile: File name in directory 'B.pdf' and header "
                                       "b'C.pdf' differ.")}),
    # The rules on names hold on the name the field gives.
    "a-local-name-shorter-than-the-directorys": (OTHERS, {
        "B.pdf": ("member-unreadable", "BadZipFile: File name in directory 'B.pdf' and header "
                                       "b'C' differ.")}),
    "a-unicode-path-naming-a-path-out": (OTHERS, {
        "../B.pdf": ("unsafe-member-name", "parent-directory segment")}),
    "a-unicode-path-repeating-another-members-name": (sorted(set(OTHERS) - {"B.docx"}), {
        "B.docx": ("ambiguous-name", _AMBIGUOUS)}),
    # An entry that names two files (4.6.9): neither name is taken for the other.
    "a-unicode-path-naming-another-file": (OTHERS, {"X.pdf": ("member-unreadable", _two_names("'B.pdf'"))}),
    # A header bit 11 says is UTF-8 is its own UTF-8 version.
    "a-flagged-utf-8-name-with-a-unicode-path-naming-another-file": (OTHERS, {
        "B\u00fc.pdf": ("member-unreadable",
                        "its header calls it 'B\u00fc.pdf' and its Info-ZIP Unicode Path field "
                        "(APPNOTE 4.6.9) calls it 'X.pdf'; that field is the UTF-8 version of the "
                        "header's name, so the entry names two files")}),
    "a-unicode-path-differing-in-case": (OTHERS, {"X.pdf": ("member-unreadable", _two_names("'x.pdf'"))}),
    # A byte order mark is not tidied away, and UTF-8 here carries none (4.6.9).
    "a-unicode-path-with-a-byte-order-mark": (OTHERS, {
        "X.pdf": ("member-unreadable", _two_names("'\\ufeffX.pdf'"))}),
    # Two fields name an entry twice, whether or not they agree, and whether
    # or not the first is one at all.
    "two-unicode-paths-agreeing": (OTHERS, {"B\u207f.pdf": ("member-unreadable", _TWICE)}),
    "two-unicode-paths-naming-two-files": (OTHERS, {"B\u207f.pdf": ("member-unreadable", _TWICE)}),
    "a-broken-unicode-path-and-a-whole-one": (OTHERS, {"B\u207f.pdf": ("member-unreadable", _TWICE)}),
    # Data that runs on past where the next entry, or the directory, begins.
    "data-running-into-the-next-entry": (OTHERS, {
        "B.pdf": ("member-unreadable",
                  f"its data runs to byte {DIRECTORY:,}, and the next entry's local header "
                  f"begins at byte {STARTS[LAST]:,}: {_TWO}")}),
    "data-running-one-byte-into-the-next-entry": (OTHERS, {
        "B.pdf": ("member-unreadable",
                  f"its data runs to byte {STARTS[LAST] + 1:,}, and the next entry's local header "
                  f"begins at byte {STARTS[LAST]:,}: {_TWO}")}),
    "data-running-into-the-central-directory": (sorted(set(FILES) - {LAST}), {
        LAST: ("member-unreadable",
               f"its data runs to byte {DIRECTORY + 8:,}, and the central directory begins at "
               f"byte {DIRECTORY:,}: the directory would be read as part of a member")}),
    # A local header past where the directory begins: its data does not run
    # into the directory, so the sentence says where the header is.
    "a-local-header-past-the-central-directory": (sorted(set(FILES) - {LAST}), {
        LAST: ("member-unreadable",
               f"its local header, at byte {PAST:,}, lies past where the central directory "
               f"begins, at byte {STARTS[LAST]:,}")}),
    # Two of them: the first one's data ends where the second's header begins,
    # so it does not run into anything, and it is not in the archive's body either.
    "two-local-headers-past-the-central-directory": (sorted(set(FILES) - {LAST}), {
        LAST: ("member-unreadable",
               f"its local header, at byte {PAST_FIRST:,}, lies past where the central "
               f"directory begins, at byte {STARTS[LAST]:,}"),
        ADDED: ("member-unreadable",
                f"its local header, at byte {PAST_SECOND:,}, lies past where the central "
                f"directory begins, at byte {STARTS[LAST]:,}")}),
    # Two entries and one local header: both are refused, whichever comes first.
    "two-entries-one-local-header": (OTHERS, {
        "C.pdf": ("member-unreadable", _SHARED), "B.pdf": ("member-unreadable", _SHARED)}),
    "two-entries-one-local-header-one-name": (OTHERS, {"B.pdf": ("ambiguous-name", _AMBIGUOUS)}),
}

#: Read on every Python, with an entry that has no name: the header's, which a
#: Unicode Path field does not give it (4.4.17).
NAMELESS = {
    "a-nameless-header-with-a-unicode-path": "1 entry in this archive has no name; nothing can "
                                             "extract it",
    "a-header-cut-to-nothing-with-a-unicode-path": "1 entry in this archive has no name; nothing "
                                                   "can extract it",
}

#: Not a readable archive, in the library's words, the same on every release.
UNREADABLE = {
    "a-name-flagged-utf-8-that-is-not": "'utf-8' codec can't decode byte 0xff in position 1: "
                                        "invalid start byte",
    # Left in place, so the library refuses it in the words it has for it.
    "a-unicode-path-running-past-its-extra-field": "Corrupt extra field 7075 (size=20)",
}


def _read(name):
    return zipread.read(CASES[name], name + ".zip")


def test_every_case_is_named_refused_or_unreadable():
    assert sorted(list(NAMED) + list(REFUSED) + list(NAMELESS) + list(UNREADABLE)) == sorted(CASES)
    assert set(ENTRIES.FIXTURES) <= set(REFUSED)


@pytest.mark.parametrize("name", sorted(NAMED))
def test_an_entry_is_named_the_same_way_on_every_python(name):
    """By bit 11, or IBM 437, or a Unicode Path field that is one -- and only
    one of those, whichever Python reads it."""
    c = _read(name)
    assert c.kind is Kind.DOCUMENT and c.defects == [], [(d.kind, d.detail) for d in c.defects]
    assert sorted(c.file_names) == sorted(OTHERS + [NAMED[name]])


@pytest.mark.parametrize("name", sorted(REFUSED))
def test_an_entry_is_refused_in_one_sentence_on_every_python(name):
    """The words are the reader's -- or, where every release already says the
    same thing, the library's -- so the report is one report whichever Python
    printed it."""
    c = _read(name)
    readable, refused = REFUSED[name]
    assert c.kind is Kind.DOCUMENT
    assert sorted(c.file_names) == readable
    assert {n: (d.kind, d.detail) for n, d in c.rejected.items()} == refused
    assert [d for d in c.defects if d.kind == "not-a-zip"] == []


@pytest.mark.parametrize("form", ["plain", "zip64", "behind-a-stub"])
def test_no_archive_the_library_writes_has_a_local_header_past_its_directory(form, monkeypatch):
    """The refusal of a local header past where the central directory begins
    reaches no archive written the ordinary way: the library's writer lays
    every one out as 4.3.6 does -- with ZIP64 fields and end records, and
    behind bytes put in front of the archive as a self-extracting one has.
    """
    if form == "zip64":
        monkeypatch.setattr(zipfile, "ZIP64_LIMIT", 1 << 6)
        monkeypatch.setattr(zipfile, "ZIP_FILECOUNT_LIMIT", 2)
    raw = io.BytesIO(b"#!stub\n" * 50 if form == "behind-a-stub" else b"")
    raw.seek(0, io.SEEK_END)
    with zipfile.ZipFile(raw, "a" if form == "behind-a-stub" else "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in FILES.items():
            z.writestr(name, data)
    data = raw.getvalue()
    assert (b"PK\x06\x06" in data) is (form == "zip64"), "the library wrote the end records it was asked to"
    found = zipread._directory(data)
    begins = found.follows - found.size
    infos = zipfile.ZipFile(io.BytesIO(data)).infolist()
    assert len(infos) == len(FILES) and all(i.header_offset < begins for i in infos)
    assert zipread._overlapping(data, infos, begins) == {}


@pytest.mark.parametrize("name", sorted(NAMELESS))
def test_an_entry_a_field_names_and_its_header_does_not_has_no_name(name):
    c = _read(name)
    assert c.kind is Kind.DOCUMENT and sorted(c.file_names) == OTHERS and c.rejected == {}
    assert [(d.kind, d.detail) for d in c.defects] == [("nameless-member", NAMELESS[name])]


@pytest.mark.parametrize("name", sorted(UNREADABLE))
def test_an_archive_whose_names_cannot_be_read_is_refused_alike(name):
    c = _read(name)
    assert c.kind is Kind.UNREADABLE
    assert [d.detail for d in c.defects if d.kind == "not-a-zip"] == [UNREADABLE[name]]


def test_no_case_makes_the_library_warn():
    """The library warns, on standard error, about an empty Unicode Path field
    from 3.12 on and about two entries sharing a local header from 3.12.10 and
    3.13.3 on, and goes on: one more line in one Python's report than in
    another's. Neither the first read nor a later one lets it."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for name in sorted(CASES):
            c = _read(name)
            for member in c.file_names:
                zipread.member_bytes(CASES[name], member, set(c.file_names))
    assert [str(w.message) for w in caught] == []


@pytest.mark.parametrize("name", sorted(set(NAMED) | set(REFUSED)))
def test_a_later_read_finds_each_member_by_the_name_the_first_one_gave_it(name):
    """The validator asks for a member's bytes by the name the first read gave
    it, among the names that read accepted. A name only this reader gives -- a
    Unicode Path field's, on a Python whose library does not read the field --
    reached nothing there, and its PDF went unchecked."""
    c = _read(name)
    names = set(c.file_names)
    expected = {NAMED[name]: FILES[SUBJECT]} if name in NAMED else {}
    for member in sorted(names):
        assert zipread.member_bytes(CASES[name], member, names) == expected.get(member, FILES.get(member)), member


def test_an_entry_naming_two_files_is_told_to_name_one():
    """Its bytes are readable. The remedy for a member that is not -- re-create
    the archive and send it again -- re-zips the same files into the same
    field, so the finding on the entry and the one on the file the metadata
    declares under its name both say to name it once."""
    files = dict(FILES)
    files[LAST] = files[LAST].replace(b"B.pdf", b"X.pdf")
    data = ENTRIES.cases(files, SUBJECT)["a-unicode-path-naming-another-file"]
    found = {f.rule.id: f for f in check_bytes(data, "two-names.zip").findings}
    assert found["F1"].message == ("A file named in the metadata is in the container under an "
                                   "entry that names itself more than once")
    assert found["F1"].fix == ONE_NAME and found["Z12"].fix == ONE_NAME


#: The cases whose entry is refused for where its bytes lie, with the findings
#: each draws: rule, severity and what it is about. `F1` comes with them where
#: the refused entry is a file the metadata declares.
LAID_OUT = {
    "data-running-into-the-next-entry": ["F1", "Z12"],
    "data-running-one-byte-into-the-next-entry": ["F1", "Z12"],
    "data-running-into-the-central-directory": ["Z12"],
    "a-local-header-past-the-central-directory": ["Z12"],
    "two-local-headers-past-the-central-directory": ["Z12", "Z12"],
    "two-entries-one-local-header": ["F1", "Z12", "Z12"],
}


@pytest.mark.parametrize("name", sorted(LAID_OUT))
def test_an_entry_laid_out_where_no_writer_puts_one_is_told_to_rebuild_the_archive(name):
    """Its bytes are read as another entry's too, or reach into or past the
    central directory, and sending the same file again sends the same layout --
    the remedy for a truncated transfer, or for a member that needs a password,
    is not the one that helps. Every finding on the entry says the same thing,
    and the verdict is the one it was."""
    report = check_bytes(CASES[name], "0")
    assert sorted((f.rule.id, f.severity.value, f.about.value) for f in report.findings) == [
        (rule, "error", "container") for rule in LAID_OUT[name]]
    assert {f.fix for f in report.findings} == {REBUILD}
    for finding in report.findings:
        if finding.rule.id == "F1":
            assert finding.message == (
                "A file named in the metadata is in the container under an entry "
                "laid out where no ordinary writer puts one")


@pytest.mark.parametrize("name", sorted(CASES))
def test_a_later_read_with_no_list_refuses_what_the_first_one_refused(name):
    """`member_bytes` and `member_reader` are public, and a caller need not
    pass the names the first read accepted. Asked for an entry the first read
    refused for naming two files, or for data another entry holds too, the
    library's releases answered differently: bytes on one, nothing on the
    next. Asked for one a name the field gives would put outside the folder it
    is extracted to, or that holds a backslash, every release gave its bytes --
    and for one set aside for having no name, which nothing can extract and the
    empty name still found."""
    c = _read(name)
    asked = sorted(c.rejected)
    if any(d.kind == "nameless-member" for d in c.defects):
        asked.append("")
    for member in asked:
        assert zipread.member_bytes(CASES[name], member) is None, member


@pytest.mark.parametrize("limit", ["count", "ratio", "total"])
def test_a_later_read_with_no_list_meets_the_limits_the_first_one_met(limit, monkeypatch):
    """Asked without the names `read` accepted, `member_bytes` refused what
    `read` refused for a name or a place, and not what it refused for size: a
    member said to expand past the ratio `read` allows came back -- sixteen
    megabytes from one of zeros -- and so did the members past the total an
    archive may declare, and every member of an archive listing more entries
    than `read` reads. The limits are made small here; what is held is that
    both reads meet the same ones."""
    data = CASES["plain"]
    if limit == "count":
        monkeypatch.setattr(zipread, "MAX_MEMBERS", len(FILES) - 1)
    elif limit == "ratio":
        monkeypatch.setattr(zipread, "MIN_SUSPICIOUS_BYTES", 0)
        monkeypatch.setattr(zipread, "MAX_RATIO", 0)
    else:
        monkeypatch.setattr(zipread, "MAX_TOTAL_BYTES", len(FILES[list(FILES)[0]]))
    c = zipread.read(data, "limits.zip")
    accepted = {m.name for m in c.members}
    assert accepted != set(FILES), "the limit stopped nothing; the case holds nothing"
    for member in FILES:
        assert (zipread.member_bytes(data, member) is not None) is (member in accepted), member


def test_a_later_read_with_no_list_counts_a_repeated_name_as_the_first_one_does(monkeypatch):
    """`read` sets aside a name repeated among file entries and adds up the
    declared size of every other entry, a directory entry's with a repeated
    name included. The later read without the list set aside a repeated
    directory name too, came to a smaller total, and gave a member `read` had
    refused for passing it."""
    data = ENTRIES.build([ENTRIES.entry(b"D/", b"abc"), ENTRIES.entry(b"D/", b"abc"),
                          ENTRIES.entry(b"E/", b"abc"), ENTRIES.entry(b"E/", b"abc"),
                          ENTRIES.entry(b"x.pdf", b"x")])
    monkeypatch.setattr(zipread, "MAX_TOTAL_BYTES", 12)
    c = zipread.read(data, "dirs.zip")
    assert c.rejected.get("x.pdf") is not None and c.rejected["x.pdf"].kind == "archive-too-large", c.rejected
    assert zipread.member_bytes(data, "x.pdf") is None


def test_an_archive_without_a_unicode_path_field_is_handed_over_as_it_is():
    """The copy costs a second archive's worth of memory for as long as the
    archive is open, so it is made only where there is a field to take out."""
    assert zipread._unread(CASES["plain"], []) is CASES["plain"]


def test_an_archive_with_a_unicode_path_field_is_held_twice_not_three_times():
    """The copy the library reads is the second time the archive is held while
    it is open, and making it is not to hold a third: a mutable copy turned
    into the one handed over held one more for as long as that took -- a
    hundred megabytes more for an archive of a hundred."""
    import tracemalloc

    data = ENTRIES.build([ENTRIES.entry(b"B.pdf", bytes(4 << 20),
                                        extra=ENTRIES.unicode_path(b"B.pdf", of=b"B.pdf"))])
    _, tags = zipread._headers(data, zipread._directory(data))
    assert tags
    # Measured from here, whether or not tracing was already on: an
    # interpreter started with `-X tracemalloc` has been tracing since it began,
    # and its peak is the whole process's.
    started = not tracemalloc.is_tracing()
    if started:
        tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        before, _ = tracemalloc.get_traced_memory()
        copy = zipread._unread(data, tags)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        if started:
            tracemalloc.stop()
    assert len(copy) == len(data) and copy != data
    assert peak - before < 1.5 * len(data), f"{peak - before:,} bytes held at once to copy {len(data):,}"


#: What the reader records of a name stored as UTF-8 bytes without general
#: purpose bit 11, read as IBM Code Page 437 as APPNOTE says (4.4.4, APPENDIX
#: D): by the name the entry is read under, the name its bytes spell in UTF-8.
#: An entry whose bytes are ASCII, or not UTF-8, or that bit 11 or a Unicode
#: Path field names, has nothing to record.
UNFLAGGED = {
    "an-unflagged-utf-8-name": {"B\u251c\u255d.pdf": "B\u00fc.pdf"},
    # A field of a version this reader does not know names nothing, so the
    # header's bytes are what the entry is read by.
    "a-unicode-path-of-version-2": {"B\u251c\u255d.pdf": "B\u00fc.pdf"},
}


@pytest.mark.parametrize("name", sorted(NAMED))
def test_a_name_stored_as_utf_8_without_its_flag_is_recorded_as_such(name):
    """The entry is read as APPNOTE reads it, and the reader keeps what its
    bytes would have spelled, so that a finding can say why a declaration of
    that spelling finds nothing."""
    assert _read(name).unflagged_utf8 == UNFLAGGED.get(name, {})


def _unflagged(raw: bytes) -> bytes:
    """The conforming container with its PDF stored under `raw`, without bit
    11, and its metadata declaring the PDF as `B\u00fc.pdf`."""
    files = dict(FILES)
    files[LAST] = files[LAST].replace(b"B.pdf", "B\u00fc.pdf".encode("utf-8"))
    entries = [ENTRIES.entry(n.encode("utf-8"), d) for n, d in files.items()]
    entries[list(files).index(SUBJECT)] = ENTRIES.entry(raw, files[SUBJECT])
    return ENTRIES.build(entries)


@pytest.mark.parametrize("form", ["NFC", "NFD"])
def test_a_declaration_of_a_name_stored_as_utf_8_without_its_flag_is_told_to_set_it(form):
    """The declaration still names a file the container does not hold under
    that name -- the reference implementation reads the entry as IBM Code Page
    437 too -- so the verdict stays: `F1`, and no `F2` for the member, which
    the declaration does mean. The sentence says why, and what to set. macOS's
    `zip` and `ditto` write names decomposed, and the metadata a sender types
    is composed; both are the spelling the declaration meant."""
    raw = unicodedata.normalize(form, "B\u00fc.pdf").encode("utf-8")
    found = {f.rule.id: f for f in check_bytes(_unflagged(raw), "unflagged.zip").findings}
    assert found["F1"].message == ("A file named in the metadata is in the container under a "
                                   "name read as IBM Code Page 437")
    member = raw.decode("cp437")
    assert found["F1"].fix == (
        f"The member {member!r} stores this name as UTF-8 bytes without general purpose bit 11 "
        "(APPNOTE 4.4.4), so it reads as IBM Code Page 437 (APPENDIX D). Set bit 11 on that "
        "entry -- or write the archive with a tool that sets it -- for the name to read as "
        "UTF-8.")
    assert "F2" not in found


def test_the_library_is_handed_no_unicode_path_field(monkeypatch):
    """What makes every release read an archive alike is that none of them is
    given a Unicode Path field to read. On a release that passes the field over
    anyway nothing outside shows whether it was taken out, so this looks at
    what each read hands the library -- the first read and a later one."""
    handed = []
    real = zipread.zipfile.ZipFile

    def recording(file, *args, **kwargs):
        handed.append(file.getvalue())
        return real(file, *args, **kwargs)

    monkeypatch.setattr(zipread.zipfile, "ZipFile", recording)
    data = CASES["an-unflagged-utf-8-name-with-its-unicode-path"]
    c = zipread.read(data, "unicode-path.zip")
    zipread.member_bytes(data, NAMED["an-unflagged-utf-8-name-with-its-unicode-path"], set(c.file_names))

    def fields(archive):
        """The Header IDs in the PDF's central directory extra field."""
        extra = real(io.BytesIO(archive)).infolist()[1].extra
        ids, q = [], 0
        while q + 4 <= len(extra):
            tag, size = struct.unpack_from("<2H", extra, q)
            ids.append(tag)
            q += 4 + size
        return ids

    assert fields(data) == [ENTRIES.UNICODE_PATH] and len(handed) == 2
    assert all(len(fields(copy)) == 1 and ENTRIES.UNICODE_PATH not in fields(copy) for copy in handed)


def test_an_entry_is_named_by_its_own_header_or_not_at_all(monkeypatch):
    """This reader's reading of the central directory and the library's are
    paired entry by entry, in the order both list them. Paired wrong, one
    entry would be named by another's field -- so a pairing that does not hold
    refuses the archive, rather than naming anything."""
    real = zipread._headers
    monkeypatch.setattr(zipread, "_headers",
                        lambda data, found: (lambda headers, tags: (headers[::-1], tags))(*real(data, found)))
    c = zipread.read(CASES["plain"], "plain.zip")
    assert c.kind is Kind.UNREADABLE
    assert [d.detail for d in c.defects] == [
        "the central directory lists its entries one way to this reader and another way to the "
        "library it reads them with"]


def test_the_reader_names_and_places_entries_without_the_librarys_private_parts():
    """Which name an entry has and where its data may run to were the library's
    to decide, through `ZipInfo._decodeExtra` and `ZipInfo._end_offset` -- which
    are not its to promise, and which its releases do not fill alike."""
    source = inspect.getsource(zipread)
    assert "_decodeExtra" not in source and "_end_offset" not in source and "NameToInfo" not in source


METHOD_CASES = [(0, "stored"), (8, "deflate"), (12, "bzip2"), (14, "lzma"),
                (93, "zstd"), (95, "method 95"), (98, "method 98"),
                (99, "method 99"), (1, "method 1"), (6, "method 6")]


def _method_case(method):
    """Generate the method in both headers (APPNOTE 4.4.5)."""
    buf = io.BytesIO()
    compression = zipfile.ZIP_DEFLATED if method == 8 else zipfile.ZIP_STORED
    with zipfile.ZipFile(buf, "w", compression=compression) as out:
        for name, data in FILES.items():
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            out.writestr(info, data, compress_type=compression)
    data = bytearray(buf.getvalue())
    with zipfile.ZipFile(io.BytesIO(data)) as src:
        struct.pack_into("<H", data, src.getinfo(SUBJECT).header_offset + 8, method)
        at = src.start_dir
        for info in src.infolist():
            if info.filename == SUBJECT:
                struct.pack_into("<H", data, at + 10, method)
            at += 46 + len(info.filename.encode()) + len(info.extra) + len(info.comment)
    return bytes(data)


@pytest.mark.parametrize("method,label", METHOD_CASES)
def test_a_method_has_its_name_or_an_explicit_method_number(method, label):
    """APPNOTE 4.4.5 identifies compression by a number, including unnamed methods."""
    raw = _method_case(method)
    container = zipread.read(raw, "0")
    report = check_bytes(raw, "0")
    if method in (0, 8):
        assert SUBJECT in container.file_names
        assert SUBJECT not in container.rejected
        assert not {"Z12", "F1"} & {f.rule.id for f in report.findings}
        return
    detail = f"member compressed with {label}; this reader accepts stored and deflate"
    assert container.rejected[SUBJECT].detail == detail
    for rule_id in ("Z12", "F1"):
        findings = [f for f in report.findings if f.rule.id == rule_id]
        assert len(findings) == 1
        assert findings[0].severity.value == "error"
        assert findings[0].about.value == "container"
        assert f"It is compressed with {label}, and this tool" in findings[0].fix


def _unicode_case(flag, form, ascii_header, version, crc_matches, equivalent):
    """Generate the header and its Unicode Path field (APPNOTE 4.6.9)."""
    stem, dot, ext = SUBJECT.rpartition(".")
    base = SUBJECT if ascii_header else f"{stem}\u00e9{dot}{ext}"
    header = unicodedata.normalize(form, base).encode("utf-8")
    other = "NFC" if form == "NFD" else "NFD"
    given = unicodedata.normalize(other, base) if equivalent else "X" + base
    extra = ENTRIES.unicode_path(given.encode("utf-8"), of=header, version=version,
                                 **({} if crc_matches else {"crc": 0}))
    valid_field = version == 1 and crc_matches
    refused = valid_field and not equivalent and (bool(flag) or ascii_header)
    expected = given if valid_field else header.decode("utf-8" if flag else "cp437")
    entries = []
    for name, data in FILES.items():
        if name == SUBJECT:
            entries.append(ENTRIES.entry(header, data, flags=flag, extra=extra))
        else:
            if name == zipread.METADATA_XML:
                data = data.replace(SUBJECT.encode(), expected.encode("utf-8"))
            entries.append(ENTRIES.entry(name.encode(), data))
    return ENTRIES.build(entries), expected, refused


@pytest.mark.parametrize("flag", [0, ENTRIES.UTF8])
@pytest.mark.parametrize("form", ["NFD", "NFC"])
@pytest.mark.parametrize("ascii_header", [False, True])
@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("crc_matches", [False, True])
@pytest.mark.parametrize("equivalent", [False, True])
def test_a_unicode_path_compares_canonical_spellings(
        flag, form, ascii_header, version, crc_matches, equivalent):
    """APPNOTE 4.6.9 makes the field the UTF-8 version of the header's name; this
    reader compares the two in NFC, as it matches names to declarations."""
    raw, expected, refused = _unicode_case(flag, form, ascii_header, version, crc_matches, equivalent)
    container = zipread.read(raw, "0")
    report = check_bytes(raw, "0")
    name_findings = [f for f in report.findings if f.rule.id == "Z12"]
    if refused:
        assert len(name_findings) == 1
        assert "names two files" in name_findings[0].detail
    else:
        assert not name_findings
        assert expected in container.file_names
        assert zipread.member_bytes(raw, expected, allowed=container.file_names) == FILES[SUBJECT]
        assert not {"F1", "F2"} & {f.rule.id for f in report.findings}


def _canonical_extra_case(form):
    """One extra entry whose two spellings are canonically equivalent."""
    base = "\u00e9.txt"
    header = unicodedata.normalize(form, base).encode("utf-8")
    given = unicodedata.normalize("NFC" if form == "NFD" else "NFD", base).encode("utf-8")
    entries = [ENTRIES.entry(n.encode(), data) for n, data in FILES.items()]
    entries.append(ENTRIES.entry(header, b"x", flags=ENTRIES.UTF8,
                                 extra=ENTRIES.unicode_path(given, of=header)))
    return ENTRIES.build(entries)


@pytest.mark.parametrize("form", ["NFD", "NFC"])
def test_canonical_equivalence_can_leave_only_a_warning(form):
    """Two canonically equivalent spellings alone, compared in NFC, must not fail
    the delivery."""
    report = check_bytes(_canonical_extra_case(form), "0")
    assert "Z12" not in {f.rule.id for f in report.findings}
    assert not any(f.severity.value == "error" for f in report.findings)
    assert "F2" in {f.rule.id for f in report.findings}


# Two spellings that put two combining marks in the other order are one name
# in NFC when the marks' classes tell them apart -- and the class is the running
# Python's Unicode's to give. U+0350 has one from Unicode 4.0 and U+1AC1 from
# 14.0: on Python 3.9, whose Unicode is 13.0, the second has none, NFC leaves it
# where it stands, and the two orders were two files there and one name on 3.13.
LATER_MARKS = {"unicode-4.0": "͐", "unicode-14.0": "᫁"}
BELOW = "̣"


def _spelled_twice(header, given):
    """The subject with `header` in its header, bit 11 set, and `given` in its
    Unicode Path field, declared as the field spells it."""
    raw = header.encode("utf-8")
    entries = []
    for name, data in FILES.items():
        if name == SUBJECT:
            entries.append(ENTRIES.entry(raw, data, flags=ENTRIES.UTF8,
                                         extra=ENTRIES.unicode_path(given.encode("utf-8"), of=raw)))
        else:
            if name == zipread.METADATA_XML:
                data = data.replace(SUBJECT.encode(), given.encode("utf-8"))
            entries.append(ENTRIES.entry(name.encode(), data))
    return ENTRIES.build(entries)


def _marked(first, second):
    stem, dot, ext = SUBJECT.rpartition(".")
    return f"{stem}{first}{second}{dot}{ext}"


@pytest.mark.parametrize("mark", sorted(LATER_MARKS))
@pytest.mark.parametrize("reverse", [False, True])
def test_spellings_differing_in_a_mark_unicode_3_2_lacked_are_two_names_on_every_python(mark, reverse):
    """Compared in NFC where Unicode 3.2 had every character of both, and as
    written where it did not -- the one comparison every Python makes alike, and
    for these two orders it is the one 1.0.0 made: `Z12`, and `F1` for the
    declaration of the file that entry holds."""
    later = LATER_MARKS[mark]
    header, given = _marked(BELOW, later), _marked(later, BELOW)
    if reverse:
        header, given = given, header
    report = check_bytes(_spelled_twice(header, given), "0")
    refusals = [f for f in report.findings if f.rule.id == "Z12"]
    assert len(refusals) == 1
    assert "names two files" in refusals[0].detail
    assert "F1" in {f.rule.id for f in report.findings}


@pytest.mark.parametrize("mark", sorted(LATER_MARKS))
def test_a_name_with_a_mark_unicode_3_2_lacked_spelled_alike_is_that_name(mark):
    """The same spelling twice is one name whatever its characters are."""
    name = _marked(BELOW, LATER_MARKS[mark])
    raw = _spelled_twice(name, name)
    report = check_bytes(raw, "0")
    assert "Z12" not in {f.rule.id for f in report.findings}
    assert not any(f.severity.value == "error" for f in report.findings)
    assert name in zipread.read(raw, "0").file_names


def test_spellings_differing_in_the_order_of_marks_unicode_3_2_had_are_one_name():
    """U+0301 above and U+0323 below: NFC orders the two by class on every Python."""
    raw = _spelled_twice(_marked(BELOW, "́"), _marked("́", BELOW))
    report = check_bytes(raw, "0")
    assert "Z12" not in {f.rule.id for f in report.findings}
    assert not any(f.severity.value == "error" for f in report.findings)


@pytest.mark.parametrize("reverse", [False, True])
def test_a_spelling_alike_only_in_compatibility_is_another_name(reverse):
    """NFC, not NFKC: a fullwidth letter is a character of its own, so a header
    and a field giving `B` and its fullwidth form name two files."""
    header, given = SUBJECT, "Ｂ" + SUBJECT[1:]
    if reverse:
        header, given = given, header
    report = check_bytes(_spelled_twice(header, given), "0")
    refusals = [f for f in report.findings if f.rule.id == "Z12"]
    assert len(refusals) == 1
    assert "names two files" in refusals[0].detail
