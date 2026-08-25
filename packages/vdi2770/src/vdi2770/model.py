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


#: The subset of `DEFECT_KINDS` that can name a member in `Container.rejected`.
#: A caller rendering a refusal needs a sentence for each of these, and working
#: the set out by scraping the reader's source is how two of them were missed:
#: one call site writes `rejected` in a shape a regex did not match, and the
#: gate that was supposed to keep the table complete only checked the kinds this
#: repository's own corpus happens to produce.
REFUSAL_KINDS = frozenset({
    "unsafe-member-name", "member-too-large", "suspicious-compression",
    "archive-too-large", "member-unreadable", "metadata-too-large",
    "container-budget-exhausted", "decompression-budget-exhausted",
    "member-budget-exhausted",
})

#: Every kind a reader in this package can emit. Part of the public surface --
#: callers switch on these strings -- and the single place they are written.
#: Two test suites used to find them by grepping `Defect("` out of the source,
#: which broke the third time a call site changed shape. A value cannot be
#: missed by a regex.
DEFECT_KINDS = frozenset({
    "not-a-zip", "too-many-members", "unsafe-member-name", "member-too-large",
    "suspicious-compression", "archive-too-large", "metadata-too-large",
    "metadata-unreadable", "member-unreadable", "nesting-too-deep",
    "container-budget-exhausted", "decompression-budget-exhausted",
    "member-budget-exhausted",
})


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

    def __post_init__(self) -> None:
        # A typo used to travel: the validator looks the kind up with `.get()`
        # and moves on, so a misspelling was a defect nobody ever reported.
        if self.kind not in DEFECT_KINDS:
            raise ValueError(f"unknown defect kind {self.kind!r}; add it to DEFECT_KINDS")
