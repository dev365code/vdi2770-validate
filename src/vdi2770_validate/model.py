"""Core value types: what a rule is, what a finding is, where it happened.

Nothing in this module knows about ZIP files, XML, or PDF. Rules are written
against the model; the readers are not reachable from here.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field, replace
from typing import Optional, Tuple


class Severity(enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def rank(self) -> int:
        return {"error": 0, "warning": 1, "info": 2}[self.value]


class Obligation(enum.Enum):
    """Where the requirement comes from. Deliberately not called 'MUST/SHOULD':
    we have not read the guideline, so we never claim to quote its obligations."""

    SCHEMA = "schema"          # the published XSD says so, mechanically
    PUBLISHED_TABLE = "table"  # a freely published table says so (IDTA 02004)
    CONTAINER = "container"    # mechanics of ZIP and XML, true without VDI 2770
    REFERENCE = "reference"    # observed in the MIT reference implementation;
                               # NOT verified against the guideline, which is paywalled
    OURS = "ours"              # our own judgement; must carry `whyOurs`


@dataclass(frozen=True, order=True)
class Location:
    """Where a finding is. `container` uses the JAR convention so it stays
    greppable: outer.zip!/inner.zip!/VDI2770_Metadata.xml"""

    container: str = ""
    member: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    xpath: Optional[str] = None      # schema layer only
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
class Rule:
    id: str
    title: str
    severity: Severity
    obligation: Obligation
    layer: str
    remedy: str
    basis: str = ""
    ref_codes: Tuple[str, ...] = ()     # the reference implementation's displayed codes
    ref_keys: Tuple[str, ...] = ()      # module:key — the unambiguous unit (13 codes collide)
    why_ours: str = ""


@dataclass(frozen=True)
class Finding:
    rule: Rule
    message: str
    where: Location
    detail: Optional[str] = None
    fix: Optional[str] = None

    @property
    def severity(self) -> Severity:
        return self.rule.severity

    @property
    def remedy(self) -> str:
        return self.fix or self.rule.remedy

    def sort_key(self):
        w = self.where
        return (self.severity.rank, self.rule.id, w.container, w.member or "",
                w.line if w.line is not None else -1, w.subject or "", self.message)


@dataclass(frozen=True)
class Defect:
    """Something a reader could not do. Readers never invent rule ids; the
    container rules are the single place a Defect becomes a Finding."""

    kind: str
    where: Location
    detail: str = ""


@dataclass
class Report:
    target: str
    findings: list = field(default_factory=list)

    def add(self, f: Finding) -> None:
        self.findings.append(f)

    def sorted(self) -> list:
        return sorted(self.findings, key=lambda f: f.sort_key())

    def count(self, sev: Severity) -> int:
        return sum(1 for f in self.findings if f.severity is sev)

    @property
    def clean(self) -> bool:
        return self.count(Severity.ERROR) == 0
