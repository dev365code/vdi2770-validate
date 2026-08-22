"""Container-shape rules (Z). These are the ones that turn a reader's Defect
into something a person can act on."""
from __future__ import annotations

from typing import Iterator

from ..catalog import rule
from ..model import Finding

DEFECT_TO_RULE = {
    "not-a-zip": "Z1",
    "too-many-members": "Z5",
    "member-too-large": "Z5",
    "suspicious-compression": "Z5",
    "archive-too-large": "Z5",
    "unsafe-member-name": "Z4",
    "nesting-too-deep": "Z6",
    "metadata-unreadable": "Z3",
    "metadata-too-large": "Z5",
    "member-unreadable": "Z1",
}


def check(container) -> Iterator[Finding]:
    from ..readers.zipread import MAIN_PDF, Kind

    for d in container.defects:
        rid = DEFECT_TO_RULE.get(d.kind)
        if rid is None:
            continue
        r = rule(rid)
        yield Finding(r, r.title, d.where, detail=f"{d.kind}: {d.detail}" if d.detail else d.kind)

    if container.kind is Kind.UNREADABLE:
        return

    if not container.members:
        r = rule("Z2")
        yield Finding(r, r.title, container.where)
        return

    if container.kind is Kind.UNKNOWN:
        r = rule("Z3")
        detail = "; ".join(f"{k}: {v}" for k, v in sorted(container.near_misses.items())) or None
        yield Finding(r, r.title, container.where, detail=detail)

    dirs = [m.name for m in container.members if m.is_dir]
    if dirs:
        r = rule("Z9")
        yield Finding(r, r.title, container.where,
                      detail=f"{len(dirs)} folder entr{'y' if len(dirs) == 1 else 'ies'}: "
                             + ", ".join(sorted(dirs)[:5]))

    if container.duplicate_names:
        r = rule("Z10")
        for name in container.duplicate_names:
            yield Finding(r, r.title, container.where.child(member=name, subject=name))

    if container.kind is Kind.DOCUMENT:
        for m in container.members:
            if m.name.lower().endswith(".zip"):
                r = rule("Z11")
                yield Finding(r, r.title, container.where.child(member=m.name, subject=m.name))

    if container.kind is Kind.DOCUMENTATION:
        if MAIN_PDF not in container.file_names:
            r = rule("Z7")
            yield Finding(r, r.title, container.where)
        if not container.children:
            r = rule("Z8")
            yield Finding(r, r.title, container.where)
