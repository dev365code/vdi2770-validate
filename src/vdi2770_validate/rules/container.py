"""Container-shape rules (Z). These are the ones that turn a reader's Defect
into something a person can act on."""
from __future__ import annotations

from typing import Iterator

from ..catalog import rule
from ..model import Finding
from ..names import nfc

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
    "container-budget-exhausted": "Z5",
    "member-unreadable": "Z12",
}


def check(container, declared=frozenset(), is_declared_payload=False) -> Iterator[Finding]:
    """`declared` is what this container's own metadata names as files.
    `is_declared_payload` says the parent's metadata names *this* archive as a
    file -- a parts list, a CAD bundle -- rather than expecting a container."""
    from vdi2770.zipread import MAIN_PDF, Kind

    for d in container.defects:
        rid = DEFECT_TO_RULE.get(d.kind)
        if rid is None:
            continue
        r = rule(rid)
        yield Finding(r, r.title, d.where, detail=f"{d.kind}: {d.detail}" if d.detail else d.kind)

    if container.kind is Kind.UNREADABLE:
        return

    # "Empty" has to mean empty. `members` is the survivors list -- the reader
    # drops anything that blew a budget or carried an unsafe name -- so an archive
    # whose only member we refused would otherwise be reported as having nothing
    # in it, with a remedy telling the user to add files they already sent.
    if not container.members and not container.rejected:
        r = rule("Z2")
        yield Finding(r, r.title, container.where)
        return

    # A `.zip` the parent declared as a DigitalFile never claimed to be a
    # container, and F3's own remedy blesses application/zip with .zip. The
    # reader opens every .zip because it has no metadata to know better; here we
    # do. If it turns out to be a real container it is still validated as one.
    if container.kind is Kind.UNKNOWN and not is_declared_payload:
        r = rule("Z3")
        detail = "; ".join(f"{k}: {v}" for k, v in sorted(container.near_misses.items())) or None
        yield Finding(r, r.title, container.where, detail=detail)

    # A directory entry is optional in the ZIP format, so testing for one made
    # this rule fire or not depending on which library wrote the archive rather
    # than on the archive's shape. A folder exists if a member sits in one.
    folders = set()
    for m in container.members:
        if m.is_dir:
            folders.add(m.name if m.name.endswith("/") else m.name + "/")
        stem = m.name.rstrip("/")
        if "/" in stem:
            folders.add(stem.rsplit("/", 1)[0] + "/")
    if folders:
        r = rule("Z9")
        named = sorted(folders)
        yield Finding(r, r.title, container.where,
                      detail=f"{len(named)} folder{'' if len(named) == 1 else 's'}: "
                             + ", ".join(named[:5])
                             + (", ..." if len(named) > 5 else ""))

    if container.duplicate_names:
        r = rule("Z10")
        for name in container.duplicate_names:
            yield Finding(r, r.title, container.where.child(member=name, subject=name))

    if container.kind is Kind.DOCUMENT:
        for m in container.members:
            # Z11 exists because an undeclared container is "a way to carry
            # something past a check that only looks at declared files". A
            # declared one is not past that check, so its own argument excuses it.
            if m.name.lower().endswith(".zip") and nfc(m.name) not in declared:
                r = rule("Z11")
                yield Finding(r, r.title, container.where.child(member=m.name, subject=m.name))

    if container.kind is Kind.DOCUMENTATION:
        if MAIN_PDF not in container.file_names:
            r = rule("Z7")
            yield Finding(r, r.title, container.where)
        # A refusal to look is not an absence. The reader stops descending at
        # MAX_CONTAINER_LEVELS and at the tree's container budget, and it drops a
        # `.zip` member it could not decompress -- in each case `children` is
        # short for reasons that have nothing to do with what the sender packed.
        # Z6 and Z12 already say what happened.
        stopped = any(
            d.kind == "container-budget-exhausted"
            or (d.kind in ("nesting-too-deep", "member-unreadable")
                and (d.where.member or "").lower().endswith(".zip"))
            for d in container.defects)
        if not container.children and not stopped:
            r = rule("Z8")
            yield Finding(r, r.title, container.where)
