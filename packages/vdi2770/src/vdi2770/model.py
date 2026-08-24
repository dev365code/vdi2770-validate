"""Where something is, and what a reader could not do.

Two value types, and deliberately nothing else. A reader's job is to say what
it found and where; deciding whether that is *wrong* belongs to whoever is
holding the rules, which is not this library.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional


@dataclass(frozen=True, order=True)
class Location:
    """Where something is. `container` uses the JAR convention so it stays
    greppable: outer.zip!/inner.zip!/VDI2770_Metadata.xml"""

    container: str = ""
    member: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    xpath: Optional[str] = None
    subject: Optional[str] = None    # model identity: document id, file name, class id

    def child(self, **kw) -> Location:
        return replace(self, **kw)

    def __str__(self) -> str:
        parts = [self.container or "<input>"]
        if self.member:
            parts.append(self.member)
        s = "!/".join(parts)
        if self.line is not None:
            s += f":{self.line}"
            if self.column is not None:
                s += f":{self.column}"
        return s


@dataclass(frozen=True)
class Defect:
    """Something a reader could not do -- a member that blew a budget, a
    container it refused to descend into, a file it could not open.

    A Defect is a fact, not a verdict. It carries no severity and no rule id,
    because a reader that invented those would be deciding policy on your
    behalf. Read `kind` and decide for yourself; the vocabulary is listed in
    the README and is part of this package's public surface.
    """

    kind: str
    where: Location
    detail: str = ""
