"""Schema rules (X): does the metadata match the schema VDI publishes?"""
from __future__ import annotations

from typing import Iterator

from ..catalog import rule
from ..model import Finding, UnsafeXml, XmlTooLarge


def check(container, parse_error, schema_errors) -> Iterator[Finding]:
    if parse_error is not None:
        # Three different statements, and only two of them are about the sender.
        # `X1` says their file is malformed; `X3` says it tried something a data
        # file may not; `X6` says we declined to model it, which is ours. Mapping
        # every non-`UnsafeXml` error onto `X1` told the sender of a perfectly
        # well-formed document that it was not well-formed.
        # By class, not by the class's name. The name compare was not a choice:
        # `XmlTooLarge` was raised at the reader's boundary and not exported, so
        # this could not write `isinstance` even though that is what it meant.
        rid = ("X3" if isinstance(parse_error, UnsafeXml)
               else "X6" if isinstance(parse_error, XmlTooLarge) else "X1")
        r = rule(rid)
        where = container.where.child(member=container.metadata_name,
                                      line=parse_error.line, column=parse_error.column)
        yield Finding(r, r.title, where, detail=parse_error.message)
        return

    for err in schema_errors:
        blame = err.get("broken")
        if blame:
            r = rule("X0" if blame == "install" else "X4")
            yield Finding(r, r.title, container.where.child(member=container.metadata_name),
                          detail=err.get("reason"))
            continue
        r = rule("X2")
        where = container.where.child(member=container.metadata_name,
                                      line=err.get("line"), xpath=err.get("path"))
        yield Finding(r, r.title, where, detail=err.get("reason"))
