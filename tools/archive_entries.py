"""The ways an archive can name and place its entries, built field by field.

APPNOTE 6.3.10 names an entry twice -- in its local file header (4.3.7) and in
its central directory header (4.3.12) -- in UTF-8 when general purpose bit 11
says so (4.4.4) and in IBM Code Page 437 when it does not (APPENDIX D); and an
Info-ZIP Unicode Path extra field (4.6.9) may carry the UTF-8 version of a name
the header holds in another character set. It places each entry's data after
its local header, before the next one and before the central directory (4.3.6).
Every builder here writes stored members dated 1980-01-01 with each of those
fields given, so that every Python reads the same bytes, and each case says one
particular thing about an entry's names or its place.

`tools/make_fixtures.py` writes some of them as fixtures, and the tests hold
the reader to what each one says, on every Python they run on.
"""
from __future__ import annotations

import struct
import zlib

LOCAL = b"PK\x03\x04"            # local file header (4.3.7)
CENTRAL = b"PK\x01\x02"          # central directory header (4.3.12)
END = b"PK\x05\x06"              # end of central directory record (4.3.16)
LOCAL_FIELDS = "<4s5H3L2H"       # 30 bytes, then the name and the extra field
CENTRAL_FIELDS = "<4s6H3L5H2L"   # 46 bytes, then the name, the extra field and the comment
END_FIELDS = "<4s4H2LH"          # 22 bytes, then the comment

#: The ZIP64 extended information extra field's Header ID (4.5.3).
ZIP64 = 0x0001
#: General purpose bit 11, the language encoding flag: the name is UTF-8 (4.4.4).
UTF8 = 0x800
#: The Info-ZIP Unicode Path extra field's Header ID (4.6.9).
UNICODE_PATH = 0x7075


def unicode_path(name: bytes, *, of: bytes, version: int = 1, crc=None) -> bytes:
    """An Info-ZIP Unicode Path extra field carrying `name` for a header whose
    File Name field is `of`: its version, and the CRC-32 of that field (4.6.9)."""
    body = struct.pack("<BL", version, zlib.crc32(of) if crc is None else crc) + name
    return struct.pack("<2H", UNICODE_PATH, len(body)) + body


def entry(name: bytes, data: bytes, *, flags=0, extra=b"", local_name=None, at=None,
          zip64=False) -> dict:
    """One central directory header: its name, flags and extra field -- and,
    unless `at` gives the index of the entry whose local header it points at,
    a local header and data of its own, under `local_name` if that differs.
    With `zip64`, the header gives its uncompressed size as 0xFFFFFFFF and a
    ZIP64 extended information field after its extra field gives the size
    (4.5.3)."""
    return {"name": name, "data": data, "flags": flags, "extra": extra,
            "local_name": name if local_name is None else local_name, "at": at, "zip64": zip64}


def _extra(e: dict, size: int) -> bytes:
    """The extra field an entry's central directory header carries."""
    return e["extra"] + (struct.pack("<2HQ", ZIP64, 8, size) if e["zip64"] else b"")


def build(entries, *, runs_on=None, past_directory=None) -> bytes:
    """The entries' local headers and data, in order; then the central
    directory, in order; then an end record (4.3.16), one disk, no comment --
    unless `past_directory` gives the index of an entry, or a tuple of them,
    whose local header and data come after the end record instead, as its
    comment and in that order, past where 4.3.6 lays every local header out:
    before the central directory.

    `runs_on` gives, by index, how many bytes past its own data an entry's
    sizes say its data runs: over what follows it, and at most into the fields
    of the central directory that come before its first CRC-32. The CRC-32 is
    that of all those bytes, so a reader that does not ask where the next entry
    begins reads them as this entry's.
    """
    runs_on = runs_on or {}
    past = (past_directory if isinstance(past_directory, tuple)
            else () if past_directory is None else (past_directory,))
    body, where = b"", {}
    for i, e in enumerate(entries):
        if e["at"] is None and i not in past:
            where[i] = len(body)
            body += struct.pack(LOCAL_FIELDS, LOCAL, 20, e["flags"], 0, 0, 33, zlib.crc32(e["data"]),
                                len(e["data"]), len(e["data"]), len(e["local_name"]), 0)
            body += e["local_name"] + e["data"]
    # The first sixteen bytes of the central directory do not depend on any
    # entry's sizes or CRC-32: a signature, two versions, the first entry's flags,
    # the method and the time and date.
    ahead = struct.pack("<4s6H", CENTRAL, 20, 20, entries[0]["flags"], 0, 0, 33)
    crcs, sizes = {}, {}
    for i, e in enumerate(entries):
        if e["at"] is not None or i in past:
            continue
        begins = where[i] + 30 + len(e["local_name"])
        sizes[i] = len(e["data"]) + runs_on.get(i, 0)
        covered = (body + ahead)[begins:begins + sizes[i]]
        if len(covered) != sizes[i]:
            raise ValueError("an entry's data may run on only as far as the first CRC-32 "
                             "of the central directory")
        crcs[i] = zlib.crc32(covered)
        if i in runs_on:
            # The local header says what the central directory says.
            body = (body[:where[i]] + struct.pack(LOCAL_FIELDS, LOCAL, 20, e["flags"], 0, 0, 33,
                                                  crcs[i], sizes[i], sizes[i], len(e["local_name"]), 0)
                    + body[where[i] + 30:])
    comment = b""
    after_end = len(body) + sum(46 + len(x["name"]) + len(_extra(x, 0)) for x in entries) + 22
    for i in past:
        e = entries[i]
        crcs[i], sizes[i] = zlib.crc32(e["data"]), len(e["data"])
        where[i] = after_end + len(comment)
        comment += struct.pack(LOCAL_FIELDS, LOCAL, 20, e["flags"], 0, 0, 33, crcs[i],
                               sizes[i], sizes[i], len(e["local_name"]), 0)
        comment += e["local_name"] + e["data"]
    directory = b""
    for i, e in enumerate(entries):
        j = i if e["at"] is None else e["at"]
        extra = _extra(e, sizes[j])
        directory += struct.pack(CENTRAL_FIELDS, CENTRAL, 20, 20, e["flags"], 0, 0, 33, crcs[j],
                                 sizes[j], 0xFFFFFFFF if e["zip64"] else sizes[j], len(e["name"]),
                                 len(extra), 0, 0, 0, 0, where[j])
        directory += e["name"] + extra
    return body + directory + struct.pack(END_FIELDS, END, 0, 0, len(entries), len(entries),
                                          len(directory), len(body), len(comment)) + comment


#: The cases written as fixtures: each an entry the library's releases read
#: differently -- in verdict, or only in the words -- that the reader refuses,
#: and so where it has to refuse in one sentence on every Python. The rest are
#: held to by the tests alone.
FIXTURES = {
    "a-unicode-path-naming-another-file":
        "the PDF's header names it X.pdf, and an Info-ZIP Unicode Path field whose CRC-32 is "
        "that name's names it B.pdf",
    "data-running-into-the-next-entry":
        "the PDF's sizes run its data on over the next entry's local header and data",
    "two-entries-one-local-header":
        "a second central directory entry, C.pdf, listed before the PDF, points at the PDF's "
        "local header",
}


def cases(files: dict, subject: str) -> dict:
    """Every way of naming or placing an entry the reader is held to, by name,
    from the members `files` in their order: each case changes how `subject` is
    named or where its data lies, and leaves the rest as they are."""
    stem, dot, ext = subject.rpartition(".")
    accented = f"{stem}\u00fc{dot}{ext}"
    utf8 = accented.encode("utf-8")
    # The same name in a code page other than IBM 437: a byte that code page
    # reads as another letter, which is what the Unicode Path field is for.
    latin = accented.encode("latin-1")
    other = f"X{dot}{ext}".encode("ascii")
    plain = subject.encode("ascii")
    # The same name in IBM Code Page 437 itself, and one with a control byte in it.
    ibm437 = accented.encode("cp437")
    control = plain[:1] + b"\x01" + plain[1:]
    names = list(files)
    k = names.index(subject)

    def renamed(*replacement):
        out = [entry(n.encode("utf-8"), files[n], flags=UTF8 if not n.isascii() else 0) for n in names]
        out[k:k + 1] = replacement
        return out

    data = files[subject]
    up = unicode_path
    return {
        # Names every release of the library reads alike.
        "plain": build(renamed(entry(plain, data))),
        "a-flagged-utf-8-name": build(renamed(entry(utf8, data, flags=UTF8))),
        "an-unflagged-utf-8-name": build(renamed(entry(utf8, data))),
        "a-name-flagged-utf-8-that-is-not": build(renamed(entry(plain[:1] + b"\xff" + plain[1:], data,
                                                                flags=UTF8))),
        "a-local-name-other-than-the-directorys": build(renamed(entry(plain, data, local_name=b"C" + plain[1:]))),
        # Shorter, so that where its data begins is the local header's to say.
        "a-local-name-shorter-than-the-directorys": build(renamed(entry(plain, data, local_name=b"C"))),
        "a-unicode-path-whose-crc-is-another-names": build(renamed(entry(other, data, extra=up(
            plain, of=other, crc=zlib.crc32(b"Y" + plain[1:]))))),
        "a-unicode-path-of-version-2": build(renamed(entry(utf8, data, extra=up(utf8, of=utf8, version=2)))),
        "a-unicode-path-repeating-an-ascii-name": build(renamed(entry(plain, data, extra=up(plain, of=plain)))),
        # Names the releases from 3.12 read by the Unicode Path field, and
        # those before by the header.
        "an-unflagged-utf-8-name-with-its-unicode-path": build(renamed(entry(utf8, data, extra=up(utf8, of=utf8)))),
        "a-name-in-another-code-page-with-its-unicode-path":
            build(renamed(entry(latin, data, extra=up(utf8, of=latin)))),
        # A header holding bytes other than printable ASCII is in a character
        # set nothing here can know, and its field is taken at its word.
        "a-name-in-ibm-437-with-a-unicode-path-naming-another-file":
            build(renamed(entry(ibm437, data, extra=up(other, of=ibm437)))),
        "a-header-with-a-control-byte-and-a-unicode-path":
            build(renamed(entry(control, data, extra=up(f"{stem}\u263a{dot}{ext}".encode(), of=control)))),
        # A field the library would tidy into the header's own name, or into
        # no name at all.
        "a-unicode-path-carrying-a-nul": build(renamed(entry(other, data, extra=up(other + b"\0junk", of=other)))),
        "a-unicode-path-cut-to-nothing": build(renamed(entry(latin, data, extra=up(b"\0junk", of=latin)))),
        # A header bit 11 says is UTF-8, and a field that agrees with it.
        "a-flagged-utf-8-name-with-its-unicode-path": build(renamed(entry(utf8, data, flags=UTF8,
                                                                          extra=up(utf8, of=utf8)))),
        "a-unicode-path-naming-a-path-out": build(renamed(entry(latin, data, extra=up(
            b"../" + plain, of=latin)))),
        "a-unicode-path-repeating-another-members-name": build(renamed(entry(latin, data, extra=up(
            next(n for n in names if n != subject).encode("utf-8"), of=latin)))),
        # Unicode Path fields the releases from 3.12 refuse the archive for, or
        # warn about, and those before pass over.
        "a-unicode-path-that-is-not-utf-8": build(renamed(entry(plain, data, extra=up(b"\xff\xfe", of=plain)))),
        "an-empty-unicode-path": build(renamed(entry(plain, data, extra=up(b"", of=plain)))),
        # A field beside the one that gives the size the header leaves to it.
        "a-unicode-path-beside-a-zip64-field": build(renamed(entry(latin, data, extra=up(utf8, of=latin),
                                                                   zip64=True))),
        "a-unicode-path-too-short-for-its-crc": build(renamed(entry(plain, data, extra=struct.pack(
            "<2H3B", UNICODE_PATH, 3, 1, 0, 0)))),
        # Entries that say two things about their own name.
        "a-unicode-path-naming-another-file": build(renamed(entry(other, data, extra=up(plain, of=other)))),
        "a-flagged-utf-8-name-with-a-unicode-path-naming-another-file":
            build(renamed(entry(utf8, data, flags=UTF8, extra=up(other, of=utf8)))),
        "a-unicode-path-with-a-byte-order-mark": build(renamed(entry(other, data, extra=up(
            b"\xef\xbb\xbf" + other, of=other)))),
        "a-unicode-path-differing-in-case": build(renamed(entry(other, data, extra=up(other.lower(), of=other)))),
        "two-unicode-paths-agreeing": build(renamed(entry(latin, data, extra=up(utf8, of=latin) + up(utf8, of=latin)))),
        "a-broken-unicode-path-and-a-whole-one": build(renamed(entry(latin, data, extra=up(b"\xff", of=latin)
                                                                     + up(utf8, of=latin)))),
        # A field giving a name to a header that has none (4.4.17), or none
        # once the library has cut it at its first NUL.
        "a-nameless-header-with-a-unicode-path": build(renamed(entry(b"", data, extra=up(plain, of=b"")))),
        "a-header-cut-to-nothing-with-a-unicode-path": build(renamed(entry(
            b"\0" + plain, data, extra=up(plain, of=b"\0" + plain)))),
        # A field whose length runs past the extra field holding it.
        "a-unicode-path-running-past-its-extra-field": build(renamed(entry(plain, data, extra=struct.pack(
            "<2HBL", UNICODE_PATH, 20, 1, zlib.crc32(plain))))),
        "two-unicode-paths-naming-two-files": build(renamed(entry(latin, data, extra=up(utf8, of=latin)
                                                                  + up(f"{stem}\u00f6{dot}{ext}".encode(),
                                                                       of=latin)))),
        # Data the repair for CVE-2024-0450 refuses to read twice, and the
        # releases without it read.
        "data-running-into-the-next-entry": build(renamed(entry(plain, data)),
                                                  runs_on={k: _rest(files, names, k)}),
        "data-running-one-byte-into-the-next-entry": build(renamed(entry(plain, data)), runs_on={k: 1}),
        "data-running-into-the-central-directory": build(renamed(entry(plain, data)), runs_on={len(names) - 1: 8}),
        # A local header past where the central directory begins: in the end
        # record's comment, which only the last entry's small data fits.
        "a-local-header-past-the-central-directory": build(renamed(entry(plain, data)),
                                                            past_directory=len(names) - 1),
        # Two of them, the last entry and one more after it: the first one's
        # data ends where the second's header begins, so where they lie is all
        # that says neither is in the archive's body.
        "two-local-headers-past-the-central-directory": build(
            renamed(entry(plain, data)) + [entry(b"C.txt", b"c\n")],
            past_directory=(len(names) - 1, len(names))),
        # Two central directory entries and one local header between them.
        "two-entries-one-local-header": build(_aliased(renamed(entry(plain, data)), k, b"C" + plain[1:])),
        "two-entries-one-local-header-one-name": build(_aliased(renamed(entry(plain, data)), k, plain)),
    }


def _rest(files: dict, names: list, k: int) -> int:
    """How many bytes the entry after entry `k` takes: its local header, its
    name and its data."""
    after = names[k + 1]
    return 30 + len(after.encode("utf-8")) + len(files[after])


def _aliased(entries: list, k: int, name: bytes) -> list:
    """`entries` with one more central directory entry, `name`, listed in front
    of entry `k` and pointing at its local header."""
    alias = entry(name, entries[k]["data"], at=k + 1)
    return entries[:k] + [alias] + entries[k:]
