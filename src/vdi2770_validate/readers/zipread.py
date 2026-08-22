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
from typing import Dict, List, Optional, Tuple

from ..model import Defect, Location

METADATA_XML = "VDI2770_Metadata.xml"
MAIN_XML = "VDI2770_Main.xml"
MAIN_PDF = "VDI2770_Main.pdf"

# Untrusted-input budget. Generous for real handover documentation, hostile to
# archives that are trying to be expensive.
MAX_MEMBERS = 10_000
MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_RATIO = 200
MAX_DEPTH = 2


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
    metadata_name: Optional[str] = None      # the member the metadata was read from
    metadata_bytes: Optional[bytes] = None
    children: List[Container] = field(default_factory=list)
    defects: List[Defect] = field(default_factory=list)
    near_misses: Dict[str, str] = field(default_factory=dict)
    depth: int = 0

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
    if name.startswith("/") or (len(name) > 1 and name[1] == ":"):
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


def read(data: bytes, path: str, depth: int = 0) -> Container:
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
            continue
        if i.file_size > MAX_MEMBER_BYTES:
            c.defects.append(Defect("member-too-large", c.where.child(member=i.filename),
                                    f"{i.file_size} bytes"))
            continue
        if i.compress_size > 0 and i.file_size // max(i.compress_size, 1) > MAX_RATIO:
            c.defects.append(Defect("suspicious-compression", c.where.child(member=i.filename),
                                    f"expands {i.file_size // max(i.compress_size, 1)}x"))
            continue
        total += i.file_size
        if total > MAX_TOTAL_BYTES:
            c.defects.append(Defect("archive-too-large", c.where, f"over {MAX_TOTAL_BYTES} bytes"))
            break
        members.append(Member(i.filename, i.file_size, i.compress_size, i.is_dir()))

    c.members = tuple(members)
    c.kind, c.near_misses = _classify(c.file_names)

    wanted = MAIN_XML if c.kind is Kind.DOCUMENTATION else METADATA_XML if c.kind is Kind.DOCUMENT else None
    if wanted:
        try:
            c.metadata_bytes = zf.read(wanted)
            c.metadata_name = wanted
        except (KeyError, zipfile.BadZipFile, RuntimeError) as e:
            c.defects.append(Defect("metadata-unreadable", c.where.child(member=wanted), str(e)))

    if depth < MAX_DEPTH:
        for m in c.members:
            if m.name.lower().endswith(".zip"):
                try:
                    inner = zf.read(m.name)
                except (RuntimeError, zipfile.BadZipFile) as e:
                    c.defects.append(Defect("member-unreadable", c.where.child(member=m.name), str(e)))
                    continue
                c.children.append(read(inner, f"{path}!/{m.name}", depth + 1))
    else:
        for m in c.members:
            if m.name.lower().endswith(".zip"):
                c.defects.append(Defect("nesting-too-deep", c.where.child(member=m.name),
                                        f"deeper than {MAX_DEPTH} levels"))
    return c


def read_file(path: str) -> Container:
    with open(path, "rb") as fh:
        return read(fh.read(), path.rsplit("/", 1)[-1])


def member_bytes(data: bytes, name: str) -> Optional[bytes]:
    try:
        return zipfile.ZipFile(io.BytesIO(data)).read(name)
    except Exception:
        return None
