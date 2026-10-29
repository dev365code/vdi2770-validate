"""Schema rules (X): does the metadata match the schema VDI publishes?"""
from __future__ import annotations

from typing import Iterator

from ..catalog import rule
from ..model import Finding, UnsafeXml, XmlTooLarge

CORRECT_LISTED = (
    "Correct the violations this report does list and run it again; the ones past the "
    "limit are reported once there is room for them. They are your document's, not this "
    "tool's — only the stopping is ours."
)


#: The remedy for a document in an encoding this reader does not read. Its first
#: bytes said what it is in (XML 1.0 Appendix F), so there is no position in it
#: to fix, which is what `X1`'s own remedy says to do.
RESAVE = "Save the metadata as UTF-8 (or UTF-16) and send it again."


def encoding_remedy(message):
    """`RESAVE` for a document the reader refused for the encoding its first
    bytes say it is in, read from the sentence it refused it in -- or None."""
    if ", as its first bytes say, and this reader does not read " in (message or ""):
        return RESAVE
    return None


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
        yield Finding(r, r.title, where, detail=parse_error.message,
                      fix=encoding_remedy(parse_error.message) if rid == "X1" else None)
        return

    for err in schema_errors:
        blame = err.get("broken")
        if blame:
            r = rule("X0" if blame == "install" else "X4")
            # `X4`'s remedy is written for a document the checker would not
            # follow to the end. It is the wrong instruction for one that simply
            # broke the schema more times than this tool will list: nothing here
            # needs simplifying, and every violation above belongs to the sender.
            yield Finding(r, r.title, container.where.child(member=container.metadata_name),
                          detail=err.get("reason"),
                          fix=None if blame != "listing" else
                          CORRECT_LISTED)
            continue
        r = rule("X2")
        where = container.where.child(member=container.metadata_name,
                                      line=err.get("line"), xpath=err.get("path"))
        yield Finding(r, r.title, where, detail=err.get("reason"))
