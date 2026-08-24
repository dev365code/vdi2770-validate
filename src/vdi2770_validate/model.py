"""Core value types: what a rule is, what a finding is, where it happened.

Nothing in this module knows about ZIP files, XML, or PDF. Rules are written
against the model; the readers are not reachable from here.

`Location` and `Defect` live in the `vdi2770` reader library and are re-exported
here on purpose: this module is meant to be the single vocabulary a rule imports,
so a rule never has to know which package a value type was defined in.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional, Tuple

from vdi2770.model import Defect, Location

__all__ = ["Defect", "Finding", "Location", "Obligation", "Report", "Rule",
           "Severity"]


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
