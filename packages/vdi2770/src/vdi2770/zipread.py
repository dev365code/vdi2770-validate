"""The ZIP layer: open a container, look at it, never extract it.

Nothing is written to disk. A supplier archive is untrusted input: it does not
get to choose a path on our filesystem, and it does not get to decide how much
memory we spend. Everything it does wrong becomes a Defect, which the container
rules turn into a Finding with a remedy.
"""
from __future__ import annotations

import io
import unicodedata
import zipfile
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
    # `in-a-subfolder`, `path-prefixed`, `case-differs`.
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
            # Not a name the reader refused for what it is. A `../` member is
            # not a file that merely sits in the wrong folder -- those bytes were
            # never read, and the caller has its own finding for the name. The
            # folder walk one layer up learned this; this table did not, so one
            # report said the name was refused outright and, two lines on, that
            # it was *found at* a place and just needed moving.
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


def read(data: bytes, path: str, depth: int = 0, _budget: Optional[_Budget] = None) -> Container:
    budget = _budget if _budget is not None else _Budget()
    c = Container(path=path, depth=depth)
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
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
        if i.file_size > MAX_MEMBER_BYTES:
            c.rejected[i.filename] = _refuse(
                c, "member-too-large", c.where.child(member=i.filename),
                f"{i.file_size} bytes, over the {MAX_MEMBER_BYTES} byte limit")
            continue
        if (i.compress_size > 0 and i.file_size > MIN_SUSPICIOUS_BYTES
                and i.file_size // max(i.compress_size, 1) > MAX_RATIO):
            c.rejected[i.filename] = _refuse(
                c, "suspicious-compression", c.where.child(member=i.filename),
                f"expands {i.file_size // max(i.compress_size, 1)}x, over {MAX_RATIO}x")
            continue
        total += i.file_size
        if total > MAX_TOTAL_BYTES:
            c.defects.append(Defect("archive-too-large", c.where, f"over {MAX_TOTAL_BYTES} bytes"))
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
    c.kind, c.near_misses = _classify(c.present, set(c.rejected))

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
            c.metadata_bytes = zf.read(wanted)
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

    inner_zips = [m for m in c.members if m.name.lower().endswith(".zip")]
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
                inner = zf.read(m.name)
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
            child = read(inner, f"{path}!/{m.name}", depth + 1, budget)
            child.member_name = m.name
            child.parent = c
            c.children.append(child)
    else:
        for m in inner_zips:
            c.defects.append(Defect("nesting-too-deep", c.where.child(member=m.name),
                                    f"this tool opens {MAX_CONTAINER_LEVELS} container "
                                    f"levels; this one is deeper"))
    return c


def read_file(path: str) -> Container:
    with open(path, "rb") as fh:
        return read(fh.read(), path.rsplit("/", 1)[-1])


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
        archive = zipfile.ZipFile(io.BytesIO(data))
        # Counted once. `getinfo` and `open` resolve a duplicated name to the
        # *last* entry, while everything upstream -- the accepted `Member`, the
        # budget charge, the allow-list -- came from the first. A 505 KiB archive
        # whose second `d.zip` was 400 MB of zeros cost 1.25 GiB with the report
        # saying the member had been refused. A name that means two entries
        # identifies neither of them.
        counted: Dict[str, int] = {}
        for entry in archive.infolist():
            counted[entry.filename] = counted.get(entry.filename, 0) + 1
    except Exception:
        return lambda name: None

    def read_one(name: str) -> Optional[bytes]:
        try:
            if allowed is not None and name not in allowed:
                return None
            if counted.get(name) != 1:
                return None
            info = archive.getinfo(name)
            if info.file_size > MAX_MEMBER_BYTES:
                return None
            with archive.open(name) as fh:
                payload = fh.read(MAX_MEMBER_BYTES + 1)
            return None if len(payload) > MAX_MEMBER_BYTES else payload
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
