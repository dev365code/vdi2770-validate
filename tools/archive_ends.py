"""The ways an archive can end, built field by field from a plain archive's own end.

APPNOTE 6.3.10 lays the end of an archive out as the central directory; then,
when a value is too large for the end record, a zip64 end of central directory
record (4.3.14) and a locator saying where it is (4.3.15); then the end of
central directory record (4.3.16), last in the file. Every builder here takes a
plain archive -- members, central directory, and a 22-byte end record with no
comment -- and rewrites its end: the same members and the same central
directory, under an end that says one particular thing about them.

`tools/make_fixtures.py` writes some of them as fixtures, and the tests hold
the reader to what each one says, on every Python they run on.
"""
from __future__ import annotations

import io
import struct
import zipfile

END = b"PK\x05\x06"            # end of central directory record (4.3.16)
LOCATOR = b"PK\x06\x07"        # zip64 end of central directory locator (4.3.15)
END64 = b"PK\x06\x06"          # zip64 end of central directory record (4.3.14)
END_FIELDS = "<4s4H2LH"        # 22 bytes, then the comment
LOCATOR_FIELDS = "<4sLQL"      # 20 bytes
END64_FIELDS = "<4sQ2H2L4Q"    # 56 bytes: version 1, with no extensible data

#: What a field holds when its value is in the zip64 end record instead (4.4.1.4).
P16, P32 = 0xFFFF, 0xFFFFFFFF

#: One block of zip64 extensible data: a Header ID, a Data Size and that many bytes (4.3.14.3).
EXTENSIBLE = struct.pack("<HL", 0x0099, 4) + b"\0" * 4


def plain(files: dict) -> bytes:
    """An archive of `files`, stored and dated 1980-01-01, so that every Python
    writes the same bytes for it."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for name, data in files.items():
            z.writestr(zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), data)
    return buf.getvalue()


def directory(data: bytes):
    """Everything before a plain archive's end record, and what that record says."""
    sig, disk, cd_disk, this, entries, size, offset, comment = struct.unpack(END_FIELDS, data[-22:])
    if sig != END or comment or disk or cd_disk or this != entries or offset + size != len(data) - 22:
        raise ValueError("not a plain archive: its end record is not the last 22 bytes, "
                         "on one disk, right after its central directory")
    return data[:-22], {"entries": entries, "size": size, "offset": offset}


def end(data: bytes, *, entries=None, this=None, size=None, offset=None, disk=0, cd_disk=0,
        comment=b"", comment_length=None, after=b"") -> bytes:
    """The archive under an end record of its own kind, with any field given
    replaced -- and a comment, and bytes after it, if given."""
    body, d = directory(data)
    entries = d["entries"] if entries is None else entries
    return body + struct.pack(
        END_FIELDS, END, disk, cd_disk, entries if this is None else this, entries,
        d["size"] if size is None else size, d["offset"] if offset is None else offset,
        len(comment) if comment_length is None else comment_length) + comment + after


def zip64(data: bytes, *, placeholders=True, gap=0, size=44, extensible=b"", signature=END64,
          points=0, disk=0, cd_disk=0, entries=None, this=None, locator_disk=0, disks=1,
          end_fields=None, moved=0) -> bytes:
    """The archive under a zip64 end record and its locator, then an end record
    holding placeholders -- or, with `placeholders=False`, the values themselves.
    `points` moves where the locator says the zip64 record is; `gap` puts bytes
    between the central directory and the record; `size` is what the record
    says its own size is, which a record of version 1 with nothing extensible
    gives as 44 (4.3.14.1); `moved` is how far past the central directory the
    record says the directory begins; `this` is the record's count of entries
    on this disk, and `end_fields` replaces fields of the end record after it."""
    body, d = directory(data)
    entries = d["entries"] if entries is None else entries
    out = body + b"\0" * gap
    at = len(out)
    out += struct.pack(END64_FIELDS, signature, size, 45, 45, disk, cd_disk,
                       entries if this is None else this, entries, d["size"],
                       d["offset"] + moved) + extensible
    out += struct.pack(LOCATOR_FIELDS, LOCATOR, locator_disk, at + points, disks)
    fields = ({"this": P16, "entries": P16, "size": P32, "offset": P32} if placeholders else
              {"this": d["entries"], "entries": d["entries"], "size": d["size"], "offset": d["offset"]})
    fields = {"disk": 0, "cd_disk": 0, **fields, **(end_fields or {})}
    return out + struct.pack(END_FIELDS, END, fields["disk"], fields["cd_disk"], fields["this"],
                             fields["entries"], fields["size"], fields["offset"], 0)


#: The cases written as fixtures: each end the library's releases read
#: differently -- in verdict, or only in the words -- and so the ones the
#: reader has to settle itself. The rest are held to by the tests alone.
FIXTURES = {
    "zip64-locator-past-its-record": "the locator points 8 bytes past the zip64 end record",
    "zip64-locator-before-its-record": "the locator points 8 bytes before the zip64 end record",
    "zip64-locator-before-its-record-values-in-the-end-record":
        "the locator points 8 bytes before the zip64 end record; the end record holds the values too",
    "zip64-record-of-the-wrong-size": "the zip64 end record gives its size as 60 bytes, not 56",
    "zip64-record-of-the-wrong-size-values-in-the-end-record":
        "the zip64 end record gives its size as 60 bytes, not 56; the end record holds the values too",
    "zip64-record-with-extensible-data": "the zip64 end record carries a 10-byte extensible data block",
    "zip64-record-with-extensible-data-values-in-the-end-record":
        "the zip64 end record carries a 10-byte extensible data block; the end record holds the values too",
    "end-record-placeholders-and-no-zip64": "the end record holds placeholders and there is no zip64 end record",
    "end-record-directory-larger-than-what-precedes-it":
        "the end record gives the central directory as long as the whole file",
    "zip64-locator-pointing-at-nothing": "the locator points where no zip64 end record begins",
    "zip64-locator-pointing-at-nothing-values-in-the-end-record":
        "the locator points where no zip64 end record begins; the end record holds the values too",
    "zip64-record-after-a-gap": "four bytes between the central directory and the zip64 end record",
    "zip64-with-bytes-in-front-located-from-the-file":
        "seven bytes in front of the archive, the locator counting from the start of the file",
    "zip64-record-placing-the-directory-past-where-it-is":
        "the zip64 end record places the central directory four bytes past where it is",
    "end-record-with-the-longest-comment-and-a-byte-after-it":
        "the end record carries the longest comment there is, and one byte follows it",
}


def cases(data: bytes) -> dict:
    """Every end the reader is held to, by name, from one plain archive."""
    real = {"placeholders": False}
    _, d = directory(data)
    more = d["entries"] + 1
    return {
        # Ends every release of the library reads alike.
        "plain": end(data),
        "zip64": zip64(data),
        "zip64-with-its-values-in-the-end-record": zip64(data, **real),
        "zip64-on-no-disks": zip64(data, disks=0),
        "zip64-locator-on-disk-1": zip64(data, locator_disk=1),
        "zip64-locator-of-two-disks": zip64(data, disks=2),
        "zip64-locator-of-two-disks-pointing-past-its-record": zip64(data, disks=2, points=8),
        "no-end-record": data[:-22],
        # A comment as long as one can be reaches back to where the search for
        # the record begins; the stored archive's own end record is in that
        # stretch, and is not the end of this one.
        "end-record-with-the-longest-comment": end(data, comment=b"\0" * 0xFFFF),
        "plain-holding-a-stored-archive": end(plain({"inner.zip": data})),
        "zip64-end-record-disks-as-placeholders": zip64(data, end_fields={"disk": P16, "cd_disk": P16}),
        "plain-with-bytes-in-front": b"\0" * 7 + end(data),
        "zip64-with-bytes-in-front": b"\0" * 7 + zip64(data),
        # Ends the library reads one way before CVE-2025-8291 was repaired and
        # another way after.
        "zip64-locator-past-its-record": zip64(data, points=8),
        "zip64-locator-before-its-record": zip64(data, points=-8),
        "zip64-locator-before-its-record-values-in-the-end-record": zip64(data, points=-8, **real),
        "zip64-record-of-the-wrong-size": zip64(data, size=48),
        "zip64-record-of-the-wrong-size-values-in-the-end-record": zip64(data, size=48, **real),
        "zip64-record-with-extensible-data": zip64(data, size=44 + len(EXTENSIBLE), extensible=EXTENSIBLE),
        "zip64-record-with-extensible-data-values-in-the-end-record":
            zip64(data, size=44 + len(EXTENSIBLE), extensible=EXTENSIBLE, **real),
        # Ends every release refuses, in words that differ between releases.
        "end-record-placeholders-and-no-zip64": end(data, entries=P16, size=P32, offset=P32),
        "end-record-directory-larger-than-what-precedes-it": end(data, size=len(data)),
        "zip64-locator-pointing-at-nothing": zip64(data, signature=b"PK\x06\x00"),
        "zip64-locator-pointing-at-nothing-values-in-the-end-record": zip64(data, signature=b"PK\x06\x00", **real),
        "zip64-record-after-a-gap": zip64(data, gap=4),
        "zip64-with-bytes-in-front-located-from-the-file": b"\0" * 7 + zip64(data, points=7),
        "zip64-record-placing-the-directory-past-where-it-is": zip64(data, moved=4),
        # Searched for one byte further back than the longest comment reaches
        # by the releases before 3.12.10, and not by those after.
        "end-record-with-the-longest-comment-and-a-byte-after-it":
            end(data, comment=b"\0" * 0xFFFF, after=b"\0"),
        # Ends every release reads, and reads alike, that contradict themselves.
        "end-record-with-bytes-after-it": end(data, after=b"\0" * 7),
        "end-record-comment-past-the-end": end(data, comment=b"abc", comment_length=9),
        "end-record-in-the-comment": end(data, comment=END + b"\0" * 18),
        # The record's two counts spell the record's own signature, so the last
        # time it occurs in the file is inside the record: the library takes the
        # last 22 bytes as the record when they are one, and so must the reader.
        "end-record-whose-counts-spell-its-signature": end(data, this=0x4B50, entries=0x0605),
        "end-record-on-disk-1": end(data, disk=1),
        "end-record-directory-on-disk-1": end(data, cd_disk=1),
        "end-record-entries-on-this-disk-differ": end(data, this=0),
        "end-record-entries-wrong": end(data, entries=more),
        "zip64-record-on-disk-1": zip64(data, disk=1),
        "zip64-record-directory-on-disk-1": zip64(data, cd_disk=1),
        "zip64-record-entries-on-this-disk-differ": zip64(data, this=0),
        "zip64-end-record-on-disk-1": zip64(data, end_fields={"disk": 1}),
        "zip64-end-record-offset-disagrees": zip64(data, end_fields={"offset": 1}, **real),
        "zip64-end-record-entries-disagree": zip64(data, end_fields={"this": more, "entries": more}, **real),
        "zip64-entries-wrong": zip64(data, entries=more),
    }
