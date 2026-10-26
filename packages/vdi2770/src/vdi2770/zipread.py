"""The ZIP layer: open a container, look at it, never extract it.

Nothing is written to disk. A supplier archive is untrusted input: it does not
get to choose a path on our filesystem, and it does not get to decide how much
memory we spend. Everything it does wrong becomes a Defect, which the container
rules turn into a Finding with a remedy.
"""
from __future__ import annotations

import contextlib
import io
import struct
import unicodedata
import zipfile
import zlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from .model import Defect, Location

METADATA_XML = "VDI2770_Metadata.xml"
MAIN_XML = "VDI2770_Main.xml"
MAIN_PDF = "VDI2770_Main.pdf"

def nfc(name: str) -> str:
    """One canonical spelling for a member name.

    macOS stores names decomposed and writes them that way into a ZIP; metadata
    authored anywhere else is composed. Canonicalising archive names belongs to
    whoever reads archives, and there was a second copy of this line in the
    validator until it did.
    """
    return unicodedata.normalize("NFC", name)


# Untrusted-input budget. Generous for real handover documentation, hostile to
# archives that are trying to be expensive.
MAX_MEMBERS = 10_000
MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_RATIO = 200
# ...but only once the expansion is big enough to matter. An uncompressed TIFF
# scan of a line drawing expands 200x and lands at one megabyte; refusing that
# protects nothing and leaves the sender with no remedy. The absolute ceilings
# below are what actually bound the damage.
MIN_SUSPICIOUS_BYTES = 8 * 1024 * 1024
# The metadata is parsed into a tree and then handed to a schema validator, both
# of which cost several times the text. The per-member cap is sized for PDFs and
# is far too generous for something we are going to expand twice.
MAX_METADATA_BYTES = 16 * 1024 * 1024
# How many container levels we will open. This is a budget for untrusted input,
# not a statement about VDI 2770 — the reference project's own vdi2770_excel.zip
# is a documentation container holding documentation containers holding document
# containers, so three levels occur in practice. Anything below the budget is
# reported rather than opened.
MAX_CONTAINER_LEVELS = 3

# Every limit above bounds one archive or one member. None of them bounds the
# *tree*, and the tree is where the amplification lives: a documentation container
# may hold ten thousand inner containers, and each inner container's metadata is
# held for as long as the caller walks the tree. Measured, before these two
# existed: a 274 KB file produced 265 MB resident, and no per-archive cap came
# near engaging. At the permitted extreme it was about 156 GiB from a file small
# enough to email.
MAX_CONTAINERS = 1_000                            # opened across one read()
# And a ceiling on the work, not only on the holdings. Verifying that a member
# can be read decompresses it, and MAX_TOTAL_BYTES bounds that per archive: a
# thousand archives near their own ceiling is two terabytes of inflation that
# nothing was counting. Measured at the permitted extreme: a 6.4 MB file cost
# 380 seconds of CPU and returned a clean verdict.
MAX_TOTAL_DECOMPRESSED = 4 * 1024 * 1024 * 1024   # inflated across one read()
#: Directory entries listed across one read(). The other tree budgets bound
#: bytes and archives; this one bounds the *records* built out of them. One
#: `Member`, and often one `Defect`, exists per entry for as long as the walk
#: does — at MAX_MEMBERS x MAX_CONTAINERS that is ten million of them, measured
#: at roughly 460 bytes each. The largest container in the vendored corpus lists
#: twenty entries, so this is four thousand times a real delivery.
MAX_TOTAL_MEMBERS = 100_000
MAX_TOTAL_METADATA_BYTES = 64 * 1024 * 1024       # held across one read()

#: The two methods this reader accepts. Everything else is refused rather
#: than handed to a decompressor: CPython bounds only zlib per `read(n)`, so
#: a bzip2 or lzma member -- which `read` decodes whole before it cuts to the
#: size the member declares -- would spend its real size no matter how small
#: it claims to be, on a read no budget here measures. A stored member does
#: not inflate, and a deflated one is bounded a megabyte at a time.
SUPPORTED_METHODS = (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
METHOD_NAMES = {zipfile.ZIP_STORED: "stored", zipfile.ZIP_DEFLATED: "deflate",
                12: "bzip2", 14: "lzma", 93: "zstd"}


class Kind(Enum):
    DOCUMENTATION = "documentation container"
    DOCUMENT = "document container"
    UNKNOWN = "unrecognised"
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class Member:
    name: str
    size: int
    compressed: int
    is_dir: bool


@dataclass
class Container:
    path: str
    kind: Kind = Kind.UNKNOWN
    members: Tuple[Member, ...] = ()
    duplicate_names: Tuple[str, ...] = ()
    metadata_name: Optional[str] = None      # the member the metadata was read from
    metadata_bytes: Optional[bytes] = None
    children: List[Container] = field(default_factory=list)
    defects: List[Defect] = field(default_factory=list)
    # reserved name -> (kind, the name that nearly matched). Kinds:
    # `in-a-subfolder`, `path-prefixed`, `case-differs`, and
    # `case-differs-elsewhere` for a name that is both wrongly cased and in a
    # subfolder. The matched name is the whole member name as the archive
    # spells it -- it used to be the basename, which named a member the
    # listing does not hold.
    near_misses: Dict[str, Tuple[str, str]] = field(default_factory=dict)
    # Members we refused, mapped to the `Defect` that refused them. Kept so the
    # report can say "present but rejected" rather than the untrue "not in the
    # archive" -- and holding the fact, not a second sentence about it. There
    # were two wordings per refusal, written a line apart, and prose telling the
    # caller what to conclude is what `near_misses` stopped doing.
    rejected: Dict[str, Defect] = field(default_factory=dict)
    depth: int = 0
    # Which member of the parent this was read from. The name is right here;
    # a caller reconstructing it by splitting `path` on the JAR separator gets
    # it wrong for a member whose own name contains one.
    member_name: Optional[str] = None
    # The container this one was read out of, or None at the root.
    #
    # Deliberately not the archive's bytes. A caller that wants a member's bytes
    # asks `member_bytes()` with the parent's, one level at a time; holding the
    # bytes here would mean the whole tree stays in memory at once, which is the
    # amplification `MAX_TOTAL_METADATA_BYTES` exists to bound. What this saves
    # is the *guessing*: a caller walking the tree had to work out which
    # container was whose parent, and got it wrong twice.
    #
    # repr and compare are off because this points back up: without that, a
    # `repr()` of any container walks the whole tree, and `==` recurses.
    parent: Optional[Container] = field(default=None, repr=False, compare=False)
    # For a container delivered as a folder: the members of the parent it was
    # made from, as the parent's archive spells them. The folder's own member
    # names are reduced -- `./AB393/B.pdf` and `AB393//B.pdf` are both `B.pdf` in
    # `AB393/` -- so they cannot be turned back into these, and a caller that
    # wants the same bytes again asks with these.
    folder_members: Tuple[str, ...] = ()
    #: For a member whose header stores its name as UTF-8 bytes without general
    #: purpose bit 11 -- read, as APPNOTE reads it, as IBM Code Page 437 (4.4.4,
    #: APPENDIX D) -- the name those bytes spell in UTF-8, by the name it is
    #: read under. Only for bytes that are not ASCII, and only where no Unicode
    #: Path field named the entry: there the two readings differ, and a
    #: declaration of the UTF-8 one can be told why it finds nothing.
    unflagged_utf8: Dict[str, str] = field(default_factory=dict)

    @property
    def where(self) -> Location:
        return Location(container=self.path)

    @property
    def file_names(self) -> Tuple[str, ...]:
        """Names we can open. Use this before reading a member's bytes."""
        return tuple(m.name for m in self.members if not m.is_dir)

    @property
    def present(self) -> Tuple[str, ...]:
        """Every file name the archive declares, including members we refused
        or could not read.

        Whether a name is *there* is a fact about the archive's directory; being
        unable to read the bytes behind it does not unsay it. Asking
        `file_names` instead is how a container with one corrupt member came to
        be reported as not being a VDI 2770 container at all.
        """
        readable = self.file_names
        seen = set(readable)
        # Directory entries are excluded, and not by accident: a refusal is
        # recorded before anything asks whether the entry is a directory, so an
        # unsafe directory reached `rejected` and from there this list -- which
        # promises file *names*. A directory called `VDI2770_Main.pdf/` would
        # otherwise answer for the file of that name.
        return readable + tuple(n for n in self.rejected
                                if n not in seen and not n.endswith("/"))

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


def _whole(zf: zipfile.ZipFile, name: str) -> bytes:
    """A member the sweep already accepted, read in the same megabyte steps.

    `zf.read(name)` is `read(-1)`, which inflates up to its whole cap before
    cutting to the declared size -- the amplification `read_one` was changed
    to avoid, on the two reads that do not go through it: the metadata and a
    nested container. A method that would not stop at a megabyte is refused
    before it reaches here. The steps bound a member that lies about its size;
    an honest large member is still held whole (its declared size, capped by
    `MAX_MEMBER_BYTES` for a nested container and `MAX_TOTAL_METADATA_BYTES` for
    the metadata), with a transient of about twice that at the final join.
    """
    parts = []
    with zf.open(name) as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            parts.append(chunk)
    return b"".join(parts)


def _refuse(c: Container, kind: str, where: Location, detail: str) -> Defect:
    """Record a refusal once: one `Defect` in `defects`, the same object in
    `rejected`. Appending to both by hand meant two English sentences per
    refusal, a line apart, free to disagree."""
    d = Defect(kind, where, detail)
    c.defects.append(d)
    return d


def _unsafe(name: str) -> Optional[str]:
    # A Windows drive is a single ASCII letter, a colon, then a separator.
    # Testing only for the colon condemned `5:1.pdf` -- a gear ratio -- as an
    # absolute path, with two errors and a security-flavoured accusation.
    drive = (len(name) > 2 and name[0].isascii() and name[0].isalpha()
             and name[1] == ":" and name[2] in "/\\")
    if name.startswith("/") or drive:
        return "absolute path"
    parts = name.replace("\\", "/").split("/")
    if ".." in parts:
        return "parent-directory segment"
    if "\\" in name:
        return "backslash path separator"
    return None


def _classify(names: Tuple[str, ...],
              refused: Optional[Set[str]] = None) -> Tuple[Kind, Dict[str, Tuple[str, str]]]:
    """The reference implementation matches these names exactly and
    case-sensitively, with no path component. We do the same, but we also record
    what *nearly* matched so a caller can say why it did not.

    A kind and the name that nearly matched, not a sentence. The sentence this
    used to hold -- "it must sit at the root of the archive" -- is a normative
    claim about VDI 2770, written inside the package whose first line is that it
    decides nothing.
    """
    near: Dict[str, Tuple[str, str]] = {}
    exact = set(names)
    for wanted in (MAIN_XML, METADATA_XML, MAIN_PDF):
        if wanted in exact:
            continue
        for n in names:
            # Not a name the reader refused *for what it is*. A `../` member is
            # not a file that merely sits in the wrong folder -- those bytes were
            # never read, and the caller has its own finding for the name.
            # Only that reason: a metadata file stored twice is refused as
            # `ambiguous-name`, which is about the archive holding it twice, and
            # "it must sit at the root" is as true and as useful for it as ever.
            # Skipping every refusal erased the one line that said the archive
            # nearly has a metadata file.
            if refused and n in refused:
                continue
            base = n.rsplit("/", 1)[-1]
            head = n[:-(len(base))].strip("/")
            # `./name` is at the root: some writers emit the prefix and it is
            # not a folder. Reporting it as a subfolder made the caller tell a
            # sender to move a file that had not gone anywhere, so the two are
            # different kinds and the caller writes each its own sentence.
            elsewhere = "/" in n and head not in (".", "")
            prefixed = "/" in n and head in (".", "")
            wrong_case = base.lower() == wanted.lower() and base != wanted
            # The whole member name, never the basename: an archive holding
            # `sub/vdi2770_main.pdf` was told the file was "found as
            # 'vdi2770_main.pdf'", which nothing in its listing is called. And
            # both differences at once get both, because fixing the case alone
            # left the next run saying the file must sit at the root.
            if wrong_case and elsewhere:
                near[wanted] = ("case-differs-elsewhere", n)
            elif wrong_case:
                near[wanted] = ("case-differs", n)
            elif base == wanted and elsewhere:
                near[wanted] = ("in-a-subfolder", n)
            elif base == wanted and prefixed:
                near[wanted] = ("path-prefixed", n)
    if MAIN_XML in exact:
        return Kind.DOCUMENTATION, near
    if METADATA_XML in exact:
        return Kind.DOCUMENT, near
    return Kind.UNKNOWN, near


@dataclass
class _Budget:
    """Shared across one read() and everything it descends into."""

    containers: int = 0
    metadata_bytes: int = 0
    decompressed: int = 0
    members: int = 0

    def take_container(self) -> bool:
        # Do not count what was refused: the counter appears in the message, and
        # incrementing past the cap made it climb on every archive that hit it.
        if self.containers >= MAX_CONTAINERS:
            return False
        self.containers += 1
        return True

    def take_members(self, n: int) -> bool:
        """Charge for listing one archive's directory. False once the read has
        listed enough — and it is charged before anything is built, because the
        records are the thing being bounded."""
        if self.members + n > MAX_TOTAL_MEMBERS:
            return False
        self.members += n
        return True

    def take_bytes(self, n: int) -> bool:
        """Charge for inflating one member. False once the read has spent enough."""
        if self.decompressed + n > MAX_TOTAL_DECOMPRESSED:
            return False
        self.decompressed += n
        return True

    def take_metadata(self, n: int) -> bool:
        if self.metadata_bytes + n > MAX_TOTAL_METADATA_BYTES:
            return False
        self.metadata_bytes += n
        return True


#: The records an archive ends with, by their signatures (APPNOTE 6.3.10): the
#: end of central directory record (4.3.16); the zip64 end of central directory
#: locator, the 20 bytes in front of it (4.3.15); and the zip64 end of central
#: directory record the locator points at (4.3.14).
_END, _LOCATOR, _END64, _CENTRAL = b"PK\x05\x06", b"PK\x06\x07", b"PK\x06\x06", b"PK\x01\x02"

#: What a field too small for its value holds when the value is in the zip64
#: end record instead (4.4.1.4, 4.4.23, 4.4.24).
_PLACEHOLDER = 0xFFFFFFFF


@dataclass(frozen=True)
class _Directory:
    """Where an archive's end records put its central directory: where they say
    it begins, how long it is, where the record after it begins, how many
    entries it holds, and which of the records said so."""
    offset: int
    size: int
    follows: int
    entries: int
    which: str


def _prefixed(skipped: int) -> str:
    return (f"the archive its end record describes begins {skipped:,} bytes into the "
            "file, and what comes before it is not part of it")


_SPLIT = "of a split archive; this reader reads an archive that is one file"

#: The fields of the end record a zip64 end record holds as well (4.4.21 to
#: 4.4.24), and what each holds when it leaves its value to the zip64 record.
_SHARED = (("number of entries on this disk", 0xFFFF), ("number of entries", 0xFFFF),
           ("size of the central directory", _PLACEHOLDER),
           ("offset of the central directory", _PLACEHOLDER))


def _one_disk(which: str, disk: int, cd_disk: int, this: int, total: int):
    """An archive that is one file is disk 0 of one, and every entry is on it
    (4.4.19 to 4.4.21) -- or the reason this one is not."""
    if disk:
        return f"the {which} places this archive on disk {disk:,} {_SPLIT}"
    if cd_disk:
        return f"the {which} places the central directory on disk {cd_disk:,} {_SPLIT}"
    if this != total:
        return f"the {which} counts {this:,} entries on this disk and {total:,} in all"
    return None


def _closing(data: bytes, start: int):
    """Where, from `start` on, an end record's signature begins and its comment
    runs to the end of the file: where an end record could be the last thing
    in it."""
    n = len(data)
    q = data.find(_END, start, n - 18)
    while q >= 0:
        if q + 22 + struct.unpack_from("<H", data, q + 20)[0] == n:
            yield q
        q = data.find(_END, q + 1, n - 18)


def _directory(data: bytes):
    """The end of the archive, read from its bytes the way APPNOTE 6.3.10 lays it
    out -- or the reason it is not a readable ZIP archive.

    The standard library reads these records two ways. Its releases from before
    the repair for CVE-2025-8291 take the 56 bytes in front of a zip64 locator
    to be the zip64 end record, whatever the locator says, and go on without one
    when they are not; the releases after it follow the locator and hold the
    record to its own size. An archive whose end those two would read
    differently is refused here, before the library is asked, and in this
    reader's words -- so the verdict and the sentence are the same on every
    Python. What reaches the library is an end every release of it reads alike.

    And an end every release reads, and reads alike, is refused when it says two
    things: one end record, and nothing after it and its comment (4.3.1,
    4.3.16); one disk (4.4.19 to 4.4.21); one value for each field, whichever
    record holds it (4.4.21 to 4.4.24). A reader that takes the other half of
    such an end at its word reads another archive.
    """
    n = len(data)
    # The end record the library takes: the last 22 bytes when they are one
    # with no comment, or else the last of its signature in the last 64 KiB of
    # comment and the record -- the longest comment and the record, to the
    # byte, as the releases from 3.12.8 and 3.13.1 on have it; those before looked one
    # byte further back, where no record the file ends with can begin. Without
    # one there is no archive, which the library says in these words on every
    # release.
    if n >= 22 and data[n - 22:n - 18] == _END and data[n - 2:] == b"\0\0":
        p = n - 22
    else:
        p = data.rfind(_END, max(0, n - 22 - 0xFFFF))
        if p < 0 or n - p < 22:
            return "File is not a zip file"
    found = _described(data, p)
    if isinstance(found, str):
        return found
    # One end record, and the file ends with it and its comment (4.3.1, 4.3.16).
    # A record comes after the central directory it describes (4.3.6), so what
    # lies in front of where that directory ends is the archive's own content --
    # a member's bytes may hold anything -- and only from there on is a second
    # signature a second record.
    closing = list(_closing(data, max(found.offset + found.size, n - 22 - 0xFFFF)))
    if closing != [p]:
        if closing:
            return (f"the signature of an end record occurs again at byte {p:,}, after the "
                    f"end record at byte {closing[0]:,}")
        comment, = struct.unpack_from("<H", data, p + 20)
        if p + 22 + comment < n:
            return (f"the archive's end record ends {n - p - 22 - comment:,} bytes before the "
                    "end of the file, and what comes after it is not part of it")
        if p + 22 + comment > n:
            return (f"the archive's end record gives its comment {comment:,} bytes, and the "
                    f"file ends {n - p - 22:,} bytes after the record")
    return found


def _described(data: bytes, p: int):
    """Where the end record at `p`, and the zip64 records in front of it, put
    the central directory -- or the reason they do not."""
    counts = struct.unpack_from("<4H", data, p + 4)
    size, offset = struct.unpack_from("<2L", data, p + 12)
    loc = p - 20
    if loc < 0 or data[loc:loc + 4] != _LOCATOR:
        # No zip64 end record, so a field holding the placeholder points at
        # nothing.
        for name, value in (("size of the central directory", size),
                            ("offset of the central directory", offset)):
            if value == _PLACEHOLDER:
                return (f"the end record gives the {name} as {value:,}, the value that says it is "
                        "in a zip64 end record, and the archive has none")
        return _one_disk("end record", *counts) or _placed("end record", offset, size, p, counts[3])
    disk, at, disks = struct.unpack_from("<LQL", data, loc + 4)
    if disk != 0 or disks > 1:
        return "zipfiles that span multiple disks are not supported"
    # A zip64 end record of version 1 with nothing extensible is 56 bytes, and
    # it is the record right in front of its locator (4.3.6, 4.3.14.1).
    rec = loc - 56
    if at == rec or (at < rec and data[at:at + 4] == _END64):
        if data[at:at + 4] != _END64:
            return f"the zip64 locator points at byte {at:,}, and no zip64 end record begins there"
        length, = struct.unpack_from("<Q", data, at + 4)
        if at + 12 + length != loc:
            return (f"the zip64 end record gives its size as {length + 12:,} bytes, and the "
                    f"locator follows it after {loc - at:,}")
        if at < rec:
            # An extensible data sector (4.3.14.3), or the fields of a later
            # version of the record (4.3.14.2): what the library's releases
            # disagree on reading, and nothing this reader reads.
            return (f"the zip64 end record carries {rec - at:,} bytes past its fixed fields, "
                    "which this reader does not read")
        size, offset = struct.unpack_from("<2Q", data, at + 40)
        if size <= at:
            gap = at - size - offset
            if gap > 0 and data[offset + gap:offset + gap + 4] == _CENTRAL:
                return _prefixed(gap)
            if gap > 0:
                return f"the central directory ends {gap:,} bytes before the zip64 end record begins"
            if gap < 0:
                return f"the zip64 end record places its central directory {-gap:,} bytes past where it is"
        disk, cd_disk, this, total = struct.unpack_from("<2L2Q", data, at + 16)
        refused = _one_disk("zip64 end record", disk, cd_disk, this, total)
        if refused:
            return refused
        # What the end record does not leave to the zip64 record with a
        # placeholder, it gives as the value (4.4.19 to 4.4.24): the same one.
        for name, value in (("this archive", counts[0]), ("the central directory", counts[1])):
            if value not in (0, 0xFFFF):
                return f"the end record places {name} on disk {value:,} {_SPLIT}"
        said = (*counts[2:], *struct.unpack_from("<2L", data, p + 12))
        for (name, mark), small, large in zip(_SHARED, said, (this, total, size, offset)):
            if small not in (mark, large):
                return f"the end record gives the {name} as {small:,} and the zip64 end record as {large:,}"
        return _placed("zip64 end record", offset, size, at, total)
    if rec >= 0 and data[rec:rec + 4] == _END64:
        # The record is where one of version 1 would be, and the locator points
        # somewhere else: at the record of an archive that has bytes in front
        # of it and counts its offsets from where it begins -- or nowhere true.
        size, offset = struct.unpack_from("<2Q", data, rec + 40)
        shift = rec - at
        if shift > 0 and offset + size + shift == rec and data[offset + shift:offset + shift + 4] == _CENTRAL:
            return _prefixed(shift)
        return (f"the zip64 locator places the zip64 end record {abs(shift):,} bytes "
                f"{'before' if shift > 0 else 'past'} where it is")
    return f"the zip64 locator points at byte {at:,}, and no zip64 end record begins there"


def _placed(which: str, offset: int, size: int, follows: int, entries: int):
    """The central directory comes before the record after it (4.3.6)."""
    if size > follows:
        return (f"the {which} gives the central directory {size:,} bytes, more than the "
                f"{follows:,} that come before it")
    return _Directory(offset, size, follows, entries, which)


#: A local file header's signature (4.3.7).
_LOCAL = b"PK\x03\x04"
#: General purpose bit 11: the entry's name is UTF-8 (4.4.4).
_UTF8_NAME = 0x800
#: The Info-ZIP Unicode Path extra field (4.6.9): the UTF-8 version of a name
#: its header holds in another character set.
_UNICODE_PATH = 0x7075
#: What the copy of an archive handed to the library carries where a Unicode
#: Path field's Header ID was: an ID no mapping assigns (4.5.2, 4.6.1), so one
#: no release of the library reads.
_UNASSIGNED = 0xFFFF


@dataclass(frozen=True)
class _Header:
    """What a central directory header (4.3.12) says of its entry's name: the
    bytes of its File Name field, whether bit 11 says they are UTF-8, how many
    Unicode Path fields its extra field carries, and the name each of those
    that is one gives."""
    raw: bytes
    utf8: bool
    fields: int
    unicode: Tuple[str, ...]


def _headers(data: bytes, found: _Directory):
    """The central directory's headers as the library lists them -- to the
    directory's size, each one's fields where APPNOTE puts them -- and where in
    `data` each Unicode Path field's Header ID is.

    A Unicode Path field gives a name when it is of version 1, holds the CRC-32
    of the header's File Name field, and its UnicodeName is UTF-8 and not empty
    (4.6.9). APPNOTE says to pass over one whose CRC-32 does not match, and one
    that is not a name says no more than that one does. Where the library stops
    -- a header cut short, or without its signature -- this stops too, and an
    extra field is walked by its Header IDs and lengths only as far as they fit
    it: past there the library refuses the archive, in the same words on every
    release.
    """
    start = found.follows - found.size
    directory = data[start:found.follows]
    headers, tags, pos = [], [], 0
    while pos < len(directory):
        head = directory[pos:pos + 46]
        if len(head) < 46 or head[:4] != _CENTRAL:
            break
        flags, = struct.unpack_from("<H", head, 8)
        n, m, k = struct.unpack_from("<3H", head, 28)
        raw = directory[pos + 46:pos + 46 + n]
        at = pos + 46 + n
        extra = directory[at:at + m]
        fields, names, q = 0, [], 0
        while q + 4 <= len(extra):
            tag, size = struct.unpack_from("<2H", extra, q)
            if q + 4 + size > len(extra):
                break
            if tag == _UNICODE_PATH:
                fields += 1
                tags.append(start + at + q)
                body = extra[q + 4:q + 4 + size]
                if len(body) > 5 and body[0] == 1 and struct.unpack_from("<L", body, 1)[0] == zlib.crc32(raw):
                    with contextlib.suppress(UnicodeDecodeError):
                        names.append(body[5:].decode("utf-8"))
            q += 4 + size
        headers.append(_Header(raw, bool(flags & _UTF8_NAME), fields, tuple(names)))
        pos += 46 + n + m + k
    return headers, tags


def _unread(data: bytes, tags) -> bytes:
    """`data` as the library is to read it: each Unicode Path field's Header ID
    replaced by one no mapping assigns.

    The library's releases from 3.12 take an entry's name from that field,
    refuse the whole archive when a field of version 1 whose CRC-32 matches the
    header's name is not UTF-8, or when a field is too short to hold its version
    and CRC-32, and warn when such a field's name is empty; the releases before
    pass it over. So the field is this reader's to
    read, and no release of the library sees one. An archive without one is
    handed over as it is: the copy is a second one of the archive, and is made
    only where it changes what the library reads -- in one piece, from views of
    the bytes around each Header ID, so that making it holds no third.
    """
    if not tags:
        return data
    view, pieces, start = memoryview(data), [], 0
    for at in sorted(tags):
        pieces += [view[start:at], struct.pack("<H", _UNASSIGNED)]
        start = at + 2
    pieces.append(view[start:])
    return b"".join(pieces)


def _as_written(name: str) -> str:
    """A name as the archive writes it, cut at its first NUL as the library
    cuts it on every platform -- and not with its backslashes made `/`, which
    the library does on Windows only. There a member named `a\\b.pdf` was read
    as a path into a folder, where every other platform refuses it.
    """
    return name.split("\0", 1)[0]


def _name(info: zipfile.ZipInfo, header: _Header) -> Optional[str]:
    """Name the entry `info` stands for as APPNOTE names it -- or say why it has
    more than one name.

    The library has read the header's name by bit 11, or as IBM Code Page 437
    without it (4.4.4, APPENDIX D), and that stands unless a Unicode Path field
    gives the UTF-8 version of it (4.6.9). A header without bit 11 holding bytes
    other than printable ASCII is in a character set nothing here can know,
    which is what the field is for, and the field is taken at its word. But a
    header bit 11 says is UTF-8 already is the UTF-8 version, and printable
    ASCII reads the same in both character sets APPNOTE gives a name, IBM Code
    Page 437 and UTF-8 -- so a field giving either of those another name is not
    its UTF-8 version: the entry names two files, and a reader that ignores the
    field reads the other one. So does an extra field carrying two of them.
    Compared as this reader names an entry -- composed (NFC), cut at its first NUL, its
    separators as written -- so that only a difference the name keeps is one,
    and a field the cut leaves no name in is no name at all.
    """
    if not info.filename:
        return None
    if header.fields > 1:
        # Not a sentence of APPNOTE's, which forbids neither: what the library's
        # releases do with them. Before 3.12 they read the header's name; from
        # 3.12 they read the last field's, and refuse the archive when a field
        # before it is not UTF-8.
        return (f"its extra field carries {header.fields} Info-ZIP Unicode Path fields (APPNOTE "
                "4.6.9); Python's zipfile releases take the last of them as its name, or none "
                "of them, or refuse the archive, so this tool takes none of them and does not "
                "read the entry")
    if not header.unicode:
        return None
    given = _as_written(header.unicode[0])
    if not given:
        return None
    if nfc(given) != nfc(info.filename) and (header.utf8 or all(0x20 <= b <= 0x7E for b in header.raw)):
        return (f"its header calls it {info.filename!r} and its Info-ZIP Unicode Path field "
                f"(APPNOTE 4.6.9) calls it {given!r}; that field is the UTF-8 version of the "
                "header's name, so the entry names two files")
    info.filename = given
    return None


def _library(data: bytes, found: _Directory):
    """The archive opened by the library, as this reader has it read: from the
    copy without Unicode Path fields, each entry it lists named by this reader,
    and why any entry has more than one name, by `id` of its `ZipInfo`, and
    what each name stored as UTF-8 without bit 11 spells in UTF-8 -- or the
    reason the two did not list the same entries. Raises what the library
    raises.

    The entries are paired in the order both list them, which is the central
    directory's, and each pair has to agree on the header's name as the
    library decodes it: a reader naming one entry by another's field would be
    the silent version of exactly the failure this is here to prevent.
    """
    headers, tags = _headers(data, found)
    zf = zipfile.ZipFile(io.BytesIO(_unread(data, tags)))
    infos = zf.infolist()
    if len(headers) != len(infos) or any(
            i.orig_filename != h.raw.decode("utf-8" if h.utf8 else "cp437")
            for i, h in zip(infos, headers)):
        return ("the central directory lists its entries one way to this reader and another "
                "way to the library it reads them with")
    named, unflagged = {}, {}
    for info, header in zip(infos, headers):
        info.filename = _as_written(info.orig_filename)
        before = info.filename
        why = _name(info, header)
        if why:
            named[id(info)] = why
        elif info.filename == before and not header.utf8 and not header.raw.isascii():
            with contextlib.suppress(UnicodeDecodeError):
                unflagged[info.filename] = header.raw.decode("utf-8")
    return zf, named, unflagged


class _Named:
    """The library's archive, asked for its entries by the names this reader
    gave them. The library's own table is keyed by the header's name, which is
    not the name of an entry a Unicode Path field names: asked for that one, it
    found nothing, and the metadata, a nested container or a folder behind such
    a name was reported unreadable."""

    def __init__(self, zf: zipfile.ZipFile, infos) -> None:
        self._zf = zf
        self._by_name = {i.filename: i for i in infos}

    def getinfo(self, name: str) -> zipfile.ZipInfo:
        return self._by_name[name]

    def open(self, name: str):
        return self._zf.open(self._by_name[name])


def _overlapping(data: bytes, infos, directory_at: int) -> Dict[int, str]:
    """The entries whose data would be read as another entry's too, or that
    are not in the archive's body at all, by `id` of their `ZipInfo`, each with
    the reason: two entries pointing at one local header, an entry whose local
    header lies past where the central directory begins, and an entry whose
    data runs past where the next local header -- or, after the last one, the
    central directory -- begins (4.3.6).

    The first and the last of those are what the repair for CVE-2024-0450
    refuses, and only some of the library's releases carry it; of two entries
    sharing a header, the releases that do refuse one or the other, or only
    warn. The data ends where the library starts reading it, plus its
    compressed size: after the local header and its name and extra field, as
    that header gives their lengths. An entry whose local header cannot be read
    is left to the library, which refuses it in the same words on every
    release.

    A local header past where the central directory begins is outside the
    layout 4.3.6 gives an archive -- headers and data, then the directory, then
    the end record -- and a file entry is refused for lying there, whether or
    not its data would run into anything; `read` lets a directory entry
    through, which has no data to read. The repair asks only whether it would: of two such
    headers it reads the first, whose data ends where the second's begins --
    and a reader that walks local headers from the start stops at the directory
    and finds neither.
    """
    shared: Dict[int, int] = {}
    for i in infos:
        shared[i.header_offset] = shared.get(i.header_offset, 0) + 1
    bounds = sorted(set(shared) | {directory_at})
    after = dict(zip(bounds, bounds[1:]))
    out = {}
    for i in infos:
        if shared[i.header_offset] > 1:
            out[id(i)] = (f"its local header, at byte {i.header_offset:,}, is another entry's too: "
                          "one stretch of bytes would be read as two members")
            continue
        head = data[i.header_offset:i.header_offset + 30]
        if len(head) < 30 or head[:4] != _LOCAL:
            continue
        if i.header_offset >= directory_at:
            out[id(i)] = (f"its local header, at byte {i.header_offset:,}, lies past where the "
                          f"central directory begins, at byte {directory_at:,}")
            continue
        name_length, extra_length = struct.unpack_from("<2H", head, 26)
        ends = i.header_offset + 30 + name_length + extra_length + i.compress_size
        limit = after.get(i.header_offset, directory_at)
        if ends <= limit:
            continue
        out[id(i)] = (f"its data runs to byte {ends:,}, and the next entry's local header begins "
                      f"at byte {limit:,}: one stretch of bytes would be read as two members"
                      if limit < directory_at else
                      f"its data runs to byte {ends:,}, and the central directory begins at byte "
                      f"{limit:,}: the directory would be read as part of a member")
    return out


def _not_the_file(data: bytes, found: _Directory, zf: zipfile.ZipFile) -> Optional[str]:
    """Why the archive the library opened is not the file it was given, or
    None. `read` refuses the whole archive for these, and `member_reader`
    every member of it: asked without the names `read` accepted, it read
    such an archive anyway, and handed over a member of one a container
    cut short in transit ended in -- a file nobody delivered.
    """
    # As many entries as the end records count (4.4.22). The library lists the
    # central directory to its size and never asks the count; a reader that
    # lists it to its count lists other entries. Before a nameless one is set
    # aside below, because it is an entry all the same.
    if len(zf.infolist()) != found.entries:
        return (f"the {found.which} counts {found.entries:,} entries and the central directory "
                f"holds {len(zf.infolist()):,}")

    # From the start of the file. The library finds an archive by its end
    # record, searching back from the end of the file, and counts whatever comes
    # before that archive as a prefix to skip, the way a self-extracting archive
    # is read. A container that stores a document container without compressing
    # it, cut short in transit, can end in that document container -- and was
    # read, and passed, as that one: a verdict on a file nobody delivered.
    #
    # How far in the library went to reach it: where the central directory
    # ends -- the record after it -- less where the end records say it ends,
    # which is zero for an archive that is the file. Worked out from the end
    # records this reader read itself, because the library's own account of a
    # zip64 end differs between its patch releases.
    skipped = found.follows - found.size - found.offset
    # And the file begins with the archive. A split archive small enough to be
    # one file begins with a marker (APPNOTE 8.5.3 and 8.5.4; `zip -s` writes
    # one) whose four bytes its offsets count as its own; an archive with
    # nothing in it may begin with its zip64 end record.
    lead = 4 if data[:4] in (b"PK\x07\x08", b"PK00") else 0
    starts = min((i.header_offset for i in zf.infolist()), default=lead)
    begins = data[lead:lead + 4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x06\x06")
    if skipped or starts != lead or not begins:
        return (_prefixed(skipped) if skipped > 0 else
                f"the archive's end record places its central directory {-skipped:,} "
                "bytes past where it is" if skipped < 0 else
                f"the archive's first entry begins {starts:,} bytes into the file, and "
                "the file does not begin with it" if starts != lead else
                "the file does not begin with a ZIP record")
    return None


def read(data: bytes, path: str, depth: int = 0, _budget: Optional[_Budget] = None) -> Container:
    return _read(data, path, depth, _budget, None)


def _read(data: bytes, path: str, depth: int, _budget: Optional[_Budget],
          _inherited: Optional[Dict[str, Defect]]) -> Container:
    """`read`, with what the archive holding this one refused under it -- for a
    container delivered as a folder, handed over before it reads itself. Not
    on `read`, which is the reader's public door and has no use for it."""
    budget = _budget if _budget is not None else _Budget()
    c = Container(path=path, depth=depth)
    found = _directory(data)
    if not isinstance(found, _Directory):
        c.kind = Kind.UNREADABLE
        c.defects.append(Defect("not-a-zip", c.where, found))
        return c
    try:
        opened = _library(data, found)
    except Exception as e:                       # noqa: BLE001
        # Not just BadZipFile. `_RealGetContents` raises UnicodeDecodeError when
        # a name is flagged UTF-8 and is not — an ordinary mislabelling by older
        # Windows writers — and NotImplementedError for a "version needed to
        # extract" it does not know. Both escaped as a stack trace naming CPython
        # internals, from a hand-written 119-byte file, and took the rest of a
        # sweep with them. "Not a readable ZIP archive" is exactly what this is.
        c.kind = Kind.UNREADABLE
        c.defects.append(Defect("not-a-zip", c.where, str(e)))
        return c
    if isinstance(opened, str):
        c.kind = Kind.UNREADABLE
        c.defects.append(Defect("not-a-zip", c.where, opened))
        return c
    zf, contradicted, unflagged = opened
    reason = _not_the_file(data, found, zf)
    if reason:
        c.kind = Kind.UNREADABLE
        c.defects.append(Defect("not-a-zip", c.where, reason))
        return c

    infos = zf.infolist()
    # An entry whose name is the empty string, before anything asks it a
    # question. `ZipInfo.is_dir()` on Python 3.9 is `filename[-1] == "/"`, which
    # raises `IndexError` on it -- out of the public `read`, naming CPython
    # internals, taking the rest of a sweep with it; on 3.13 the same archive is
    # accepted and the entry becomes a member called `""`. Two supported
    # interpreters, two answers, and neither of them a fact about the archive.
    #
    # Filtered here rather than guarded at each of the four places that ask,
    # because the next place to ask would not have the guard.
    nameless = [i for i in infos if not i.filename]
    if nameless:
        infos = [i for i in infos if i.filename]
        c.defects.append(Defect(
            "nameless-member", c.where,
            f"{len(nameless)} entr{'y' if len(nameless) == 1 else 'ies'} in "
            f"this archive {'has' if len(nameless) == 1 else 'have'} no name; "
            f"nothing can extract {'it' if len(nameless) == 1 else 'them'}"))
    if not budget.take_members(len(infos)):
        # The same answer `too-many-members` gives, for the same reason: we did
        # not read it, so we say nothing about what is in it. `kind` is what
        # tells a caller that, and `present` is empty rather than short.
        c.kind = Kind.UNREADABLE
        c.defects.append(Defect(
            "member-budget-exhausted", c.where,
            # `budget.members`, not the cap. The charge fails on `members + n >
            # MAX`, so at the moment it fails fewer than the cap have been
            # listed -- and printing the cap made the sentence a constant that
            # was wrong by however many the archive had left to spend. The
            # element budget one module along had the same false claim about the
            # same kind of counter, and was repaired the same way.
            f"this read has listed {budget.members} entries and this archive "
            f"lists {len(infos)} more, past its limit of {MAX_TOTAL_MEMBERS}"))
        return c
    overlapping = _overlapping(data, zf.infolist(), found.follows - found.size)
    zf = _Named(zf, infos)
    if len(infos) > MAX_MEMBERS:
        c.kind = Kind.UNREADABLE
        c.defects.append(Defect("too-many-members", c.where,
                                f"{len(infos)} entries, limit is {MAX_MEMBERS}"))
        return c

    # A name that appears twice identifies neither entry. Every refusal below is
    # recorded against a *name*, and `zipfile` resolves a duplicated one to the
    # last entry -- so the accepted member, the budget charge and the allow-list
    # came from the first while the bytes came from the second. Measured: a
    # 505 KiB archive whose second `d.zip` was 400 MB of zeros cost 1.25 GiB,
    # with the report saying that member had been refused for its ratio.
    #
    # Both entries are refused, not one: keeping either would mean choosing, and
    # nothing here knows which the sender meant. `duplicate_names` below still
    # reports the pair, so the archive is not merely quietly emptied.
    counted: Dict[str, int] = {}
    for i in infos:
        if not i.is_dir():
            counted[i.filename] = counted.get(i.filename, 0) + 1
    repeated = {n for n, k in counted.items() if k > 1}

    # Once per name, not once per entry. Both entries are refused -- keeping
    # either would mean choosing, and nothing here knows which the sender meant
    # -- but two entries with one name is one problem, and the report says it
    # once. Recording it inside the loop below said it twice, on top of the
    # duplicate the archive already reports.
    for name in sorted(repeated):
        c.rejected[name] = _refuse(
            c, "ambiguous-name", c.where.child(member=name),
            f"{counted[name]} entries in this archive carry this name; the reader "
            f"cannot say which one is meant and read none of them")

    members, total = [], 0
    for i in infos:
        if i.filename in repeated:
            continue
        reason = _unsafe(i.filename)
        if reason:
            c.rejected[i.filename] = _refuse(
                c, "unsafe-member-name", c.where.child(member=i.filename), reason)
            continue
        # An entry that names two files is neither of them. Its bytes are fine;
        # which file they are is what the entry does not say.
        reason = contradicted.get(id(i))
        if reason:
            c.rejected[i.filename] = _refuse(
                c, "member-unreadable", c.where.child(member=i.filename), reason)
            continue
        # Whose number this is. Every size here comes from the central
        # directory, which is whatever the writer put there -- `member_bytes`
        # re-checks the declared size against the bytes it inflates and says so
        # in its own docstring, and this cannot: checking would mean inflating
        # the member, which is the work the budget exists to avoid. A 120 KiB
        # archive said one of its members was 629,145,600 bytes, and a recipient
        # comparing that against the file in their hand finds a contradiction
        # and no way to tell which half is wrong.
        if i.file_size > MAX_MEMBER_BYTES:
            c.rejected[i.filename] = _refuse(
                c, "member-too-large", c.where.child(member=i.filename),
                f"the archive says {i.file_size} bytes, over the "
                f"{MAX_MEMBER_BYTES} byte limit; nothing here inflated it to "
                f"find out")
            continue
        if (i.compress_size > 0 and i.file_size > MIN_SUSPICIOUS_BYTES
                and i.file_size // max(i.compress_size, 1) > MAX_RATIO):
            c.rejected[i.filename] = _refuse(
                c, "suspicious-compression", c.where.child(member=i.filename),
                f"the archive says it expands "
                f"{i.file_size // max(i.compress_size, 1)}x, over {MAX_RATIO}x")
            continue
        total += i.file_size
        if total > MAX_TOTAL_BYTES:
            c.defects.append(Defect("archive-too-large", c.where,
                                    f"the sizes this archive declares add up to "
                                    f"over {MAX_TOTAL_BYTES} bytes"))
            # The names past here are still in the archive's directory. Dropping
            # them made `present` -- whose whole promise is "every name the
            # archive declares" -- omit them, and a caller then had no way to
            # tell "this archive does not contain a reserved name" from "we
            # stopped reading the directory before we got to it". Three rules
            # in the validator said the first when the second was true.
            for rest in infos[infos.index(i):]:
                if not rest.is_dir():
                    c.rejected.setdefault(rest.filename, Defect(
                        "archive-too-large", c.where.child(member=rest.filename),
                        f"the archive passed {MAX_TOTAL_BYTES} bytes before this member"))
            break
        members.append(Member(i.filename, i.file_size, i.compress_size, i.is_dir()))
    method_of = {i.filename: i.compress_type for i in infos}

    # A member that is listed but cannot be decompressed -- a bad CRC from a
    # truncated transfer, a password on one file -- used to pass silently: the
    # bytes came back as None and every later layer read that as "not declared".
    # `unzip -t` refuses these archives; so do we.
    readable = []
    exhausted = False
    for m in members:
        if m.is_dir:
            readable.append(m)
            continue
        method = method_of.get(m.name)
        if method not in SUPPORTED_METHODS:
            # Before the budget, because it is not a cost we are measuring: this
            # reader does not inflate this method at all, and letting it reach a
            # decompressor is the amplification the caps do not bound.
            c.rejected[m.name] = _refuse(
                c, "member-unreadable", c.where.child(member=m.name),
                f"member compressed with {METHOD_NAMES.get(method, f'method {method}')}; this "
                f"reader accepts stored and deflate")
            continue
        # Before the budget too, for the same reason: data that is another
        # entry's as well is not read twice, whatever is left to spend.
        reason = overlapping.get(id(zf.getinfo(m.name)))
        if reason:
            c.rejected[m.name] = _refuse(
                c, "member-unreadable", c.where.child(member=m.name), reason)
            continue
        if not exhausted and not budget.take_bytes(m.size):
            # Stop verifying rather than stop reading: the members are still
            # listed, they are simply no longer known to be readable, and saying
            # so is the honest answer. Silence here would be the same lie as
            # passing an archive we never opened.
            exhausted = True
            c.defects.append(Defect(
                "decompression-budget-exhausted", c.where.child(member=m.name),
                f"this read has inflated {budget.decompressed} bytes and this "
                f"member would take it past its limit of "
                f"{MAX_TOTAL_DECOMPRESSED}; members from here on were not "
                f"checked for readability"))
        if exhausted:
            readable.append(m)
            continue
        try:
            with zf.open(m.name) as fh:
                while fh.read(1 << 20):
                    pass
        except Exception as e:                     # zlib, RuntimeError, BadZipFile
            c.rejected[m.name] = _refuse(
                c, "member-unreadable", c.where.child(member=m.name), f"{type(e).__name__}: {e}")
            continue
        readable.append(m)
    members = readable

    c.members = tuple(members)
    c.unflagged_utf8 = {m.name: unflagged[m.name] for m in c.members if m.name in unflagged}
    # Two members whose names differ only by Unicode normalisation are two
    # different files that print identically, and on a composing filesystem one
    # overwrites the other on extraction. That is the situation this rule is
    # about, so it is found the same way an exactly repeated name is -- and both
    # spellings are named, because the reader cannot know which was meant.
    # Over the archive's own directory, not the surviving members: refusing one
    # copy used to make the pair disappear, so an archive could hide a duplicate
    # name by making one of them oversized -- and the recipient's tool might
    # extract the copy this one never looked at, which is the entire reason this
    # is reported.
    first_seen, dupes = {}, []
    for m in [i for i in infos if not i.is_dir()]:
        # The path, not just the composition. `B.pdf` and `./B.pdf` are two
        # entries that `unzip` writes to one file, so which bytes the recipient
        # ends up with depends on the order they were stored in -- the same
        # argument this pairing already makes for a composed name against its
        # decomposition, and stronger, because a `.` segment collides on every
        # filesystem rather than only on a composing one.
        key = "/".join(seg for seg in nfc(m.filename).split("/")
                       if seg not in ("", "."))
        earlier = first_seen.get(key)
        if earlier is None:
            first_seen[key] = m.filename
            continue
        for name in (earlier, m.filename):
            if name not in dupes:
                dupes.append(name)
    c.duplicate_names = tuple(dupes)
    # `present`, not `file_names`: what kind of container this is follows from
    # the names the archive declares, not from which of them we could inflate.
    # A container delivered as a folder is handed what the archive holding it
    # refused under the folder, before it decides what it is or opens the
    # folders inside it: zipped, its own read would have refused those members
    # here, and a refusal handed over only after this read was over never
    # reached a folder inside it. Known, not reported again -- the refusal is
    # the holding archive's finding.
    for name, defect in (_inherited or {}).items():
        c.rejected.setdefault(name, defect)
    c.kind, c.near_misses = _classify(
        c.present,
        {name for name, defect in c.rejected.items()
         if defect.kind == "unsafe-member-name"})

    wanted = MAIN_XML if c.kind is Kind.DOCUMENTATION else METADATA_XML if c.kind is Kind.DOCUMENT else None
    # `_classify` reads `present`, so a member we refused can decide the kind --
    # which is the point: an unreadable VDI2770_Main.xml still makes this a
    # documentation container. It must not also make us read the thing we
    # refused. Without this line the refusal chose the classification and then
    # the refused bytes were inflated anyway: a 9.5 KB archive whose metadata
    # was rejected as a bomb still produced 9.4 MB of it.
    if wanted and wanted in c.rejected:
        wanted = None
    if wanted:
        try:
            declared = zf.getinfo(wanted).file_size
            if declared > MAX_METADATA_BYTES:
                c.rejected[wanted] = _refuse(
                    c, "metadata-too-large", c.where.child(member=wanted),
                    f"{declared} bytes; this tool parses at most {MAX_METADATA_BYTES}")
                raise KeyError(wanted)
            if not budget.take_metadata(declared):
                c.rejected[wanted] = _refuse(
                    c, "container-budget-exhausted", c.where.child(member=wanted),
                    f"reading it would take this read past {MAX_TOTAL_METADATA_BYTES} "
                    f"bytes of metadata, held across {budget.containers} containers")
                raise KeyError(wanted)
            # The decompression budget covers this read too. It was wired into
            # the readability sweep and nowhere else, so tripping it with one
            # small member made every later inflation in the tree free.
            if not budget.take_bytes(declared):
                c.rejected[wanted] = _refuse(
                    c, "decompression-budget-exhausted", c.where.child(member=wanted),
                    f"this read has inflated {budget.decompressed} bytes and "
                    f"reading it would take that past {MAX_TOTAL_DECOMPRESSED}")
                raise KeyError(wanted)
            c.metadata_bytes = _whole(zf, wanted)
            c.metadata_name = wanted
        # zlib.error is an OSError subclass and was in none of these: a damaged
        # deflate stream took the whole container down with an exception naming
        # zlib internals. 140 of 300 single-bit flips inside one metadata stream
        # did it. The readability sweep catches most of them first, but not when
        # the decompression budget ran out and members stopped being verified --
        # which is exactly when the bytes are least trustworthy.
        except (KeyError, zipfile.BadZipFile, RuntimeError, OSError, EOFError) as e:
            # Only when nothing has explained it yet. Every branch above records
            # its own reason in `rejected` first -- too large, over the tree's
            # budget -- and the readability sweep records a bad CRC before we get
            # here. Appending a second defect for the same member made the report
            # say two things about one file, and one of them was that the archive
            # is not a VDI 2770 container at all.
            if wanted not in c.rejected:
                c.defects.append(Defect("metadata-unreadable",
                                        c.where.child(member=wanted), str(e)))

    # A container delivered unzipped: a folder with a reserved name at its top.
    # Its members are read as the container they are -- taken from this archive
    # within the same budgets, written into an archive of their own and read by
    # this same function -- so every guard on names, sizes and depth holds
    # inside it too. A `.zip` inside such a folder is that container's to open,
    # not this one's, or it would be opened twice.
    # (`not in c.rejected` is an equivalent mutant today: every refusal above
    # skips the member before it reaches `members`. Kept because a refused
    # member must not be read a second time into a folder's archive, whatever
    # the order of the checks above becomes.)
    accepted = [m for m in c.members if not m.is_dir and m.name not in c.rejected]
    folders = folders_holding_containers([m.name for m in accepted])
    inner_zips = [m for m in c.members if m.name.lower().endswith(".zip")
                  and not any(placed(m.name).startswith(f) for f in folders)]
    if depth + 1 < MAX_CONTAINER_LEVELS:
        for i, m in enumerate(inner_zips):
            if not budget.take_bytes(m.size):
                c.rejected[m.name] = _refuse(
                    c, "decompression-budget-exhausted", c.where.child(member=m.name),
                    f"this read has inflated {budget.decompressed} bytes and "
                    f"reading it would take that past {MAX_TOTAL_DECOMPRESSED}; "
                    f"{len(inner_zips) - i} more containers here were not opened")
                break
            if sum(1 for i in infos if i.filename == m.name) != 1:
                _refuse(c, "ambiguous-name", c.where.child(member=m.name),
                        "two entries in this archive carry this name; the reader "
                        "cannot say which one is meant and opened neither")
                continue
            try:
                inner = _whole(zf, m.name)
            except Exception as e:               # noqa: BLE001 - see read()
                # `_refuse`, not a bare defect. `rejected` is where a caller
                # looks to ask whether a `.zip` went unopened, and this was the
                # one site that recorded the defect without recording the
                # refusal -- so the report could say a member was unreadable and,
                # a line later, that the container held no inner containers.
                c.rejected[m.name] = _refuse(
                    c, "member-unreadable", c.where.child(member=m.name),
                    f"{type(e).__name__}: {e}")
                continue
            if not budget.take_container():
                # Say how many, not just where it stopped. Breaking with one
                # defect read as "this single archive was skipped" while the rest
                # of the siblings went unmentioned.
                skipped = len(inner_zips) - i
                c.defects.append(Defect(
                    "container-budget-exhausted", c.where.child(member=m.name),
                    f"this read has opened {MAX_CONTAINERS} containers, its limit; "
                    f"{skipped} more in this archive were not opened"))
                break
            child = _read(inner, nested_path(path, m.name), depth + 1, budget, None)
            child.member_name = m.name
            child.parent = c
            c.children.append(child)
        for j, folder in enumerate(folders):
            inside = [m.name for m in accepted if placed(m.name).startswith(folder)]
            size = sum(m.size for m in accepted if m.name in inside)
            # The folder is read as one nested container, held whole, and a
            # nested container is held to this cap: a `.zip` over it is refused
            # before it is read. The same content unpacked was held to nothing
            # but the read's total.
            if size > MAX_MEMBER_BYTES:
                c.rejected[folder] = _refuse(
                    c, "member-too-large", c.where.child(member=folder),
                    f"the folder's members come to {size} bytes, over the "
                    f"{MAX_MEMBER_BYTES} byte limit a nested container is read "
                    f"within")
                continue
            if not budget.take_bytes(size):
                c.rejected[folder] = _refuse(
                    c, "decompression-budget-exhausted", c.where.child(member=folder),
                    f"this read has inflated {budget.decompressed} bytes and "
                    f"reading it would take that past {MAX_TOTAL_DECOMPRESSED}; "
                    f"{len(folders) - j} more containers here were not opened")
                break
            if not budget.take_container():
                c.defects.append(Defect(
                    "container-budget-exhausted", c.where.child(member=folder),
                    f"this read has opened {MAX_CONTAINERS} containers, its limit; "
                    f"{len(folders) - j} more in this archive were not opened"))
                break
            try:
                archive = folder_archive(lambda n: _whole(zf, n), folder, inside)
            except Exception as e:               # noqa: BLE001 - see read()
                c.rejected[folder] = _refuse(
                    c, "member-unreadable", c.where.child(member=folder),
                    f"{type(e).__name__}: {e}")
                continue
            # What this read refused under the folder is in the folder all the
            # same, and the container it is has to know: zipped, its own read
            # refuses the member and its report says "in the archive but was
            # refused"; unpacked, the member was missing from what it was handed
            # and the report told the sender to add a file they had sent.
            refused = {within(name, folder): defect for name, defect in c.rejected.items()
                       if not name.endswith("/") and placed(name).startswith(folder)}
            child = _read(archive, nested_path(path, folder), depth + 1, budget, refused)
            child.member_name = folder
            child.folder_members = tuple(inside)
            child.parent = c
            # And a pair this archive holds as one path spelled twice is the
            # folder's to report where the folder holds both spellings -- a name
            # composed and decomposed, `./B.pdf` beside `B.pdf` inside it -- as
            # the inner archive does zipped. Where the two are one name to the
            # folder, it holds one of them and the pair stays this archive's.
            spelled = {}
            for name in c.duplicate_names:
                if placed(name).startswith(folder):
                    spelled.setdefault(placed(name), []).append(within(name, folder))
            handed = {key for key, names in spelled.items() if len(set(names)) == len(names)}
            if handed:
                c.duplicate_names = tuple(n for n in c.duplicate_names if placed(n) not in handed)
            c.children.append(child)
    else:
        for m in inner_zips:
            c.defects.append(Defect("nesting-too-deep", c.where.child(member=m.name),
                                    f"this tool opens {MAX_CONTAINER_LEVELS} container "
                                    f"levels; this one is deeper"))
        for folder in folders:
            c.defects.append(Defect("nesting-too-deep", c.where.child(member=folder),
                                    f"this tool opens {MAX_CONTAINER_LEVELS} container "
                                    f"levels; this one is deeper"))
    return c


def placed(name: str) -> str:
    """Where a member is, however the archive spells it: `nfc`, then `.` and
    empty segments dropped, so `./AB393/B.pdf` and `AB393//B.pdf` are both
    `AB393/B.pdf`. The same reduction as `validate.names.folder_path`, which the
    rules use to agree about folders; `..` is left alone, as there."""
    return "/".join(seg for seg in nfc(name).split("/") if seg not in ("", "."))


def folders_holding_containers(names) -> List[str]:
    """Folders at whose top a reserved name sits, each ending in `/` and
    reduced by `placed`: a container delivered unzipped. Only the outermost of
    nested ones -- reading that one finds the others inside it."""
    held = set()
    for name in names:
        where = placed(name)
        for reserved in (METADATA_XML, MAIN_XML):
            if where.endswith("/" + reserved) and len(where) > len(reserved) + 1:
                held.add(where[: -len(reserved)])
    return sorted(f for f in held if not any(f != g and f.startswith(g) for g in held))


def nested_path(path: str, name: str) -> str:
    """The path of a container read out of the one at `path`: a member of an
    archive is after its `!/`, and a member of a folder is in the folder."""
    return path + name if path.endswith("/") else f"{path}!/{name}"


def within(name: str, folder: str) -> str:
    """`name`, a member under `folder`, as the folder's own archive spells it:
    what follows the folder, as written. `./AB393/./B.pdf` is `./B.pdf` in
    `AB393/`, as it would be in `AB393.zip` -- the folder's segments are matched
    the way `placed` reduces them, and what is left keeps its own spelling,
    save the empty segments a doubled slash leaves: `AB393//B.pdf` is `B.pdf`,
    not `/B.pdf`, which a read refuses as a path from the root."""
    want = [seg for seg in folder.split("/") if seg]
    parts = name.split("/")
    matched = position = 0
    while matched < len(want) and position < len(parts):
        segment = parts[position]
        position += 1
        if segment in ("", "."):
            continue
        matched += 1
    return "/".join(seg for seg in parts[position:] if seg)


def folder_entries(folder: str, names):
    """`(name in the folder, member)` for what a folder's archive holds: each
    member as `within` spells it, and of members that spell one name in the
    folder identically -- `./AB393/B.pdf` beside `AB393/B.pdf` -- the first.
    Those are one name to the folder, and written in twice the container they
    make refused both as a name stored twice and never read the document."""
    kept, seen = [], set()
    for name in names:
        relative = within(name, folder)
        if relative not in seen:
            seen.add(relative)
            kept.append((relative, name))
    return kept


def folder_archive(read_member, folder: str, names) -> bytes:
    """The members under `folder` as an archive of their own, as
    `folder_entries` names them: stored as they are, in the order given, and
    nothing from the clock -- the same bytes every time, so a later layer can
    ask for them again."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as out:
        for relative, name in folder_entries(folder, names):
            out.writestr(zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0)),
                         read_member(name))
    return buf.getvalue()


def folder_bytes(data: bytes, folder: str, names) -> Optional[bytes]:
    """A folder container's bytes again, for a caller holding its parent's: the
    members the first read put in it, and nothing it refused."""
    read_one = member_reader(data, set(names))
    got = {}
    for name in names:
        one = read_one(name)
        if one is None:
            return None
        got[name] = one
    return folder_archive(got.__getitem__, folder, names)


def _basename(path: str) -> str:
    """The last segment of a filesystem path, whichever separator wrote it.

    `os.path.basename` uses only the separator of the platform it runs on, so on
    POSIX it returns a Windows path unchanged -- the container would then be
    reported by its whole absolute path rather than by its own file name. Both
    separators are stripped so the name is the same on either platform.
    """
    return path.replace('\\', "/").rsplit("/", 1)[-1]


def read_file(path: str) -> Container:
    with open(path, "rb") as fh:
        return read(fh.read(), _basename(path))


def member_reader(data: bytes, allowed: Optional[Set[str]] = None):
    """Read several members of one archive, with its directory parsed once.

    `member_bytes` opens the archive on every call, which is right for one
    member and quadratic for a caller that wants many: the validator asks for
    every declared PDF, so a 210 KiB container of 2,000 of them cost 20.6
    seconds, 18.5 of those inside CPython's central-directory parse, called once
    per file. Nothing measured it -- the bytes are tiny, the members are under
    the cap, and nothing inflates. A plant handover with a few thousand drawings
    is that shape, and it is the ordinary one.

    Every guard `member_bytes` applies is applied here, because this is where
    they now live and that function is the one-member case of this one. A caller
    that could reach past them would make the budget in `read()` worthless.
    """
    try:
        # Opened and named the way `read` opens and names them: the library's
        # releases name an entry with a Unicode Path field two ways, and a
        # second read that asked the library would find the PDF the first read
        # named under one name on one Python and nothing on another.
        found = _directory(data)
        opened = _library(data, found) if isinstance(found, _Directory) else None
        if not isinstance(opened, tuple) or _not_the_file(data, found, opened[0]):
            return lambda name: None
        archive = _Named(opened[0], opened[0].infolist())
        # And refused where the first read refuses: an entry naming two files,
        # or whose data another entry holds too. A caller that passes no list
        # of accepted names asked the library for those, and its releases did
        # not answer alike -- and for a name that would land outside the folder
        # it is extracted to or that holds a backslash, which every release
        # gave.
        found_at = found.follows - found.size
        refused = set(opened[1]) | set(_overlapping(data, opened[0].infolist(), found_at))
        # Counted once. `getinfo` and `open` resolve a duplicated name to the
        # *last* entry, while everything upstream -- the accepted `Member`, the
        # budget charge, the allow-list -- came from the first. A 505 KiB archive
        # whose second `d.zip` was 400 MB of zeros cost 1.25 GiB with the report
        # saying the member had been refused. A name that means two entries
        # identifies neither of them.
        counted: Dict[str, int] = {}
        for entry in opened[0].infolist():
            counted[entry.filename] = counted.get(entry.filename, 0) + 1
        # And the limits `read` sets by the archive's own sizes, met the way it
        # meets them: no member of an archive listing more than `MAX_MEMBERS`
        # entries, none said to expand past `MAX_RATIO`, and none from where the
        # sizes it declares pass `MAX_TOTAL_BYTES`. A caller with the list of
        # accepted names cannot ask for those; one without it was handed sixteen
        # megabytes from a member of zeros `read` had refused for its ratio.
        listed = [i for i in opened[0].infolist() if i.filename]
        if len(listed) > MAX_MEMBERS:
            return lambda name: None
        # A name repeated among file entries, counted as `read` counts it: it
        # sets aside no directory entry for its name, and adds up its size.
        files: Dict[str, int] = {}
        for i in listed:
            if not i.is_dir():
                files[i.filename] = files.get(i.filename, 0) + 1
        oversized, total = set(), 0
        for at, i in enumerate(listed):
            if (files.get(i.filename, 0) > 1 or _unsafe(i.filename) or id(i) in opened[1]
                    or i.file_size > MAX_MEMBER_BYTES):
                continue
            if (i.compress_size > 0 and i.file_size > MIN_SUSPICIOUS_BYTES
                    and i.file_size // max(i.compress_size, 1) > MAX_RATIO):
                oversized.add(i.filename)
                continue
            total += i.file_size
            if total > MAX_TOTAL_BYTES:
                oversized.update(rest.filename for rest in listed[at:] if not rest.is_dir())
                break
    except Exception:
        return lambda name: None

    def read_one(name: str) -> Optional[bytes]:
        try:
            # An entry with no name is one `read` sets aside -- nothing can
            # extract it -- and the empty name still found it here.
            if not name:
                return None
            if allowed is not None and name not in allowed:
                return None
            if counted.get(name) != 1:
                return None
            if _unsafe(name):
                return None
            info = archive.getinfo(name)
            if id(info) in refused:
                return None
            if name in oversized:
                return None
            if info.compress_type not in SUPPORTED_METHODS:
                return None            # not one this reader inflates; see the sweep
            if info.file_size > MAX_MEMBER_BYTES:
                return None
            # In steps, as the first read does. `read(n)` inflates up to n bytes
            # before it cuts the result to the size the member declares, so one
            # call for the whole cap made a member that declares a kilobyte and
            # inflates to hundreds of megabytes cost all of them here -- outside
            # every budget, on the second read of a member the first had
            # accepted at a megabyte's cost.
            parts, got = [], 0
            with archive.open(name) as fh:
                while True:
                    chunk = fh.read(1 << 20)
                    if not chunk:
                        break
                    got += len(chunk)
                    if got > MAX_MEMBER_BYTES:
                        return None
                    parts.append(chunk)
            return b"".join(parts)
        except Exception:
            return None

    return read_one


def member_bytes(data: bytes, name: str, allowed: Optional[Set[str]] = None) -> Optional[bytes]:
    """Read one member — but only one the reader already accepted.

    The budget in `read()` is worthless if some later layer can reach past it
    and decompress whatever it likes. `allowed` is the set of members that
    survived those checks; anything else is refused here too, and the declared
    size is re-checked because a ZIP header can lie about it.

    One member, one archive parse. `member_reader` is the same guards for a
    caller that wants several, and this is its one-member case, so there is one
    place that decides which members may be read.
    """
    return member_reader(data, allowed)(name)
