"""The ZIP layer: open a container, look at it, never extract it.

Nothing is written to disk. A supplier archive is untrusted input: it does not
get to choose a path on our filesystem, and it does not get to decide how much
memory we spend. Everything it does wrong becomes a Defect, which the container
rules turn into a Finding with a remedy.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from .model import Defect, Location

METADATA_XML = "VDI2770_Metadata.xml"
MAIN_XML = "VDI2770_Main.xml"
MAIN_PDF = "VDI2770_Main.pdf"

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
    near_misses: Dict[str, str] = field(default_factory=dict)
    # Members we refused, and why. Kept so the report can say "present but
    # rejected" rather than the untrue "not in the archive".
    rejected: Dict[str, str] = field(default_factory=dict)
    depth: int = 0
    # Which member of the parent this was read from. The name is right here;
    # a caller reconstructing it by splitting `path` on the JAR separator gets
    # it wrong for a member whose own name contains one.
    member_name: Optional[str] = None

    @property
    def where(self) -> Location:
        return Location(container=self.path)

    @property
    def file_names(self) -> Tuple[str, ...]:
        return tuple(m.name for m in self.members if not m.is_dir)

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


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


def _classify(names: Tuple[str, ...]) -> Tuple[Kind, Dict[str, str]]:
    """The reference implementation matches these names exactly and
    case-sensitively, with no path component. We do the same, but we also
    record what *nearly* matched so the report can say why it did not."""
    near: Dict[str, str] = {}
    exact = set(names)
    for wanted in (MAIN_XML, METADATA_XML, MAIN_PDF):
        if wanted in exact:
            continue
        for n in names:
            base = n.rsplit("/", 1)[-1]
            if base == wanted and "/" in n:
                near[wanted] = f"found at {n!r} — it must sit at the root of the archive"
            elif base.lower() == wanted.lower() and base != wanted:
                near[wanted] = f"found as {base!r} — the name is case-sensitive"
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

    def take_container(self) -> bool:
        self.containers += 1
        return self.containers <= MAX_CONTAINERS

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
    except zipfile.BadZipFile as e:
        c.kind = Kind.UNREADABLE
        c.defects.append(Defect("not-a-zip", c.where, str(e)))
        return c

    infos = zf.infolist()
    if len(infos) > MAX_MEMBERS:
        c.kind = Kind.UNREADABLE
        c.defects.append(Defect("too-many-members", c.where,
                                f"{len(infos)} entries, limit is {MAX_MEMBERS}"))
        return c

    members, total = [], 0
    for i in infos:
        reason = _unsafe(i.filename)
        if reason:
            c.defects.append(Defect("unsafe-member-name", c.where.child(member=i.filename), reason))
            c.rejected[i.filename] = reason
            continue
        if i.file_size > MAX_MEMBER_BYTES:
            c.defects.append(Defect("member-too-large", c.where.child(member=i.filename),
                                    f"{i.file_size} bytes"))
            c.rejected[i.filename] = f"larger than this tool will read ({i.file_size} bytes)"
            continue
        if (i.compress_size > 0 and i.file_size > MIN_SUSPICIOUS_BYTES
                and i.file_size // max(i.compress_size, 1) > MAX_RATIO):
            c.defects.append(Defect("suspicious-compression", c.where.child(member=i.filename),
                                    f"expands {i.file_size // max(i.compress_size, 1)}x"))
            c.rejected[i.filename] = (
                f"expands {i.file_size // max(i.compress_size, 1)}x, over this tool's limit")
            continue
        total += i.file_size
        if total > MAX_TOTAL_BYTES:
            c.defects.append(Defect("archive-too-large", c.where, f"over {MAX_TOTAL_BYTES} bytes"))
            break
        members.append(Member(i.filename, i.file_size, i.compress_size, i.is_dir()))

    # A member that is listed but cannot be decompressed -- a bad CRC from a
    # truncated transfer, a password on one file -- used to pass silently: the
    # bytes came back as None and every later layer read that as "not declared".
    # `unzip -t` refuses these archives; so do we.
    readable = []
    for m in members:
        if m.is_dir:
            readable.append(m)
            continue
        try:
            with zf.open(m.name) as fh:
                while fh.read(1 << 20):
                    pass
        except Exception as e:                     # zlib, RuntimeError, BadZipFile
            c.defects.append(Defect("member-unreadable", c.where.child(member=m.name),
                                    f"{type(e).__name__}: {e}"))
            c.rejected[m.name] = f"present in the archive but could not be read ({e})"
            continue
        readable.append(m)
    members = readable

    c.members = tuple(members)
    seen, dupes = set(), []
    for m in c.members:
        if m.name in seen and m.name not in dupes:
            dupes.append(m.name)
        seen.add(m.name)
    c.duplicate_names = tuple(dupes)
    c.kind, c.near_misses = _classify(c.file_names)

    wanted = MAIN_XML if c.kind is Kind.DOCUMENTATION else METADATA_XML if c.kind is Kind.DOCUMENT else None
    if wanted:
        try:
            declared = zf.getinfo(wanted).file_size
            if declared > MAX_METADATA_BYTES:
                c.defects.append(Defect("metadata-too-large", c.where.child(member=wanted),
                                        f"{declared} bytes; this tool parses at most "
                                        f"{MAX_METADATA_BYTES}"))
                c.rejected[wanted] = f"larger than this tool will parse ({declared} bytes)"
                raise KeyError(wanted)
            if not budget.take_metadata(declared):
                c.defects.append(Defect(
                    "container-budget-exhausted", c.where.child(member=wanted),
                    f"this read has already held {MAX_TOTAL_METADATA_BYTES} bytes of "
                    f"metadata across {budget.containers} containers"))
                c.rejected[wanted] = "not read: the tree's metadata budget was exhausted"
                raise KeyError(wanted)
            c.metadata_bytes = zf.read(wanted)
            c.metadata_name = wanted
        except (KeyError, zipfile.BadZipFile, RuntimeError) as e:
            c.defects.append(Defect("metadata-unreadable", c.where.child(member=wanted), str(e)))

    if depth + 1 < MAX_CONTAINER_LEVELS:
        for m in c.members:
            if m.name.lower().endswith(".zip"):
                try:
                    inner = zf.read(m.name)
                except (RuntimeError, zipfile.BadZipFile) as e:
                    c.defects.append(Defect("member-unreadable", c.where.child(member=m.name), str(e)))
                    continue
                if not budget.take_container():
                    c.defects.append(Defect(
                        "container-budget-exhausted", c.where.child(member=m.name),
                        f"this read has already opened {MAX_CONTAINERS} containers"))
                    break
                child = read(inner, f"{path}!/{m.name}", depth + 1, budget)
                child.member_name = m.name
                c.children.append(child)
    else:
        for m in c.members:
            if m.name.lower().endswith(".zip"):
                c.defects.append(Defect("nesting-too-deep", c.where.child(member=m.name),
                                        f"this tool opens {MAX_CONTAINER_LEVELS} container "
                                        f"levels; this one is deeper"))
    return c


def read_file(path: str) -> Container:
    with open(path, "rb") as fh:
        return read(fh.read(), path.rsplit("/", 1)[-1])


def member_bytes(data: bytes, name: str, allowed: Optional[Set[str]] = None) -> Optional[bytes]:
    """Read one member — but only one the reader already accepted.

    The budget in `read()` is worthless if some later layer can reach past it
    and decompress whatever it likes. `allowed` is the set of members that
    survived those checks; anything else is refused here too, and the declared
    size is re-checked because a ZIP header can lie about it.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        if allowed is not None and name not in allowed:
            return None
        info = zf.getinfo(name)
        if info.file_size > MAX_MEMBER_BYTES:
            return None
        with zf.open(name) as fh:
            payload = fh.read(MAX_MEMBER_BYTES + 1)
        return None if len(payload) > MAX_MEMBER_BYTES else payload
    except Exception:
        return None
