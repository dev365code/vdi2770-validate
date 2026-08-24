"""Schema rules (X): does the metadata match the schema VDI publishes?"""
from __future__ import annotations

from typing import Iterator

from ..catalog import rule
from ..model import Finding


def check(container, parse_error, schema_errors) -> Iterator[Finding]:
    if parse_error is not None:
        rid = "X3" if parse_error.__class__.__name__ == "UnsafeXml" else "X1"
        r = rule(rid)
        where = container.where.child(member=container.metadata_name,
                                      line=parse_error.line, column=parse_error.column)
        yield Finding(r, r.title, where, detail=parse_error.message)
        return

    for err in schema_errors:
        if err.get("broken"):
            r = rule("X0")
            yield Finding(r, r.title, container.where.child(member=container.metadata_name),
                          detail=err.get("reason"))
            continue
        r = rule("X2")
        where = container.where.child(member=container.metadata_name,
                                      line=err.get("line"), xpath=err.get("path"))
        yield Finding(r, r.title, where, detail=err.get("reason"))
