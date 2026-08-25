"""Core value types: what a rule is, what a finding is, where it happened.

Nothing in this module knows about ZIP files, XML, or PDF. Rules are written
against the model; the readers are not reachable from here.

`Location`, `Defect`, `Kind` and the three reserved filenames live in the
`vdi2770` reader library and are re-exported here on purpose: this module is the
single vocabulary a rule imports, so a rule never has to know which package a
value came from. It was three-quarters true for a while -- the rules reached past
it for `Kind` and the filenames, in function-local imports, and the layering test
had no opinion about that.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from vdi2770.model import Defect, Location
from vdi2770.xmlread import UnsafeXml, XmlTooLarge
from vdi2770.zipread import MAIN_PDF, MAIN_XML, METADATA_XML, Kind

__all__ = ["About", "Defect", "Finding", "Kind", "Location", "MAIN_PDF", "MAIN_XML", "METADATA_XML",
           "Obligation", "Report", "Rule", "Severity", "UnsafeXml", "XmlTooLarge"]


class Severity(enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def rank(self) -> int:
        return {"error": 0, "warning": 1, "info": 2}[self.value]


class About(enum.Enum):
    """Who the finding is about.

    Four rules fire because this tool stopped — a broken installation, a document
    the schema checker would not finish, an archive over a budget, a tree deeper
    than we open. Nothing in those is a statement about what the sender packed,
    and a consumer reading the JSON could not tell them from the rest.
    """

    CONTAINER = "container"
    TOOL = "tool"


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
    about: About
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
    as_about: Optional[About] = None

    @property
    def severity(self) -> Severity:
        return self.rule.severity

    @property
    def remedy(self) -> str:
        return self.fix or self.rule.remedy

    @property
    def about(self) -> About:
        """Whether *this finding* is a statement about the container or about
        this tool.

        Usually the rule's, and overridable for the same reason `fix` is: one
        rule can be reached two ways. `F1` reports a declared file that is not
        usable, and whether that is the sender's doing depends on why — a bad
        CRC is theirs, a budget of ours is not — and a CI job filtering on this
        field was handed the second as the first.
        """
        return self.as_about or self.rule.about

    def sort_key(self):
        w = self.where
        return (self.severity.rank, self.rule.id, w.container, w.member or "",
                w.line if w.line is not None else -1, w.subject or "", self.message)



# One rule can have as many findings as the document has elements. A metadata
# file of four hundred thousand empty DocumentIds produced four hundred thousand
# byte-identical M10 lines: 923 MB of memory and 107 MB of output from a 225 KB
# archive, and two such containers reached 3.98 GB. Nobody reads the four hundred
# thousandth line, and nothing downstream needs it either — the count does.
MAX_LISTED_PER_RULE = 100


@dataclass
class Report:
    target: str
    findings: list = field(default_factory=list)
    # (rule id, container) -> how many findings were counted but not kept.
    suppressed: Dict[Tuple[str, str], int] = field(default_factory=dict)
    _listed: Dict[Tuple[str, str], int] = field(default_factory=dict, repr=False)
    _suppressed_severity: Dict[Severity, int] = field(default_factory=dict, repr=False)
    _suppressed_rule: Dict[Tuple[str, str], Rule] = field(default_factory=dict, repr=False)

    def add(self, f: Finding) -> None:
        key = (f.rule.id, f.where.container)
        if self._listed.get(key, 0) >= MAX_LISTED_PER_RULE:
            # Counted, not kept. `count()` still reports every one of them, so
            # the summary and the exit code stay true; only the listing is bounded.
            self.suppressed[key] = self.suppressed.get(key, 0) + 1
            self._suppressed_rule[key] = f.rule
            self._suppressed_severity[f.severity] = (
                self._suppressed_severity.get(f.severity, 0) + 1)
            return
        self._listed[key] = self._listed.get(key, 0) + 1
        self.findings.append(f)

    def not_listed(self, show_info: bool = True) -> List[Tuple[str, str, int]]:
        """(rule id, container, how many) for findings counted but not kept.

        Honours the same INFO filter the listing does, so a quiet run does not
        announce notes it is not printing."""
        return [(rid, container, n)
                for (rid, container), n in sorted(self.suppressed.items())
                if show_info
                or self._suppressed_rule[(rid, container)].severity is not Severity.INFO]

    def sorted(self) -> list:
        return sorted(self.findings, key=lambda f: f.sort_key())

    def count(self, sev: Severity) -> int:
        return (sum(1 for f in self.findings if f.severity is sev)
                + self._suppressed_severity.get(sev, 0))

    @property
    def clean(self) -> bool:
        return self.count(Severity.ERROR) == 0
