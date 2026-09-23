"""Core value types: what a rule is, what a finding is, where it happened.

Nothing in this module reads a ZIP file, an XML document or a PDF. Rules are written
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
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from vdi2770.model import Defect, Location
from vdi2770.xmlread import NS, UnsafeXml, XmlTooLarge
from vdi2770.zipread import MAIN_PDF, MAIN_XML, METADATA_XML, Kind

from .names import as_written, on_one_line

#: An exception that names an object names the address it happened to live at,
#: because that is what `repr` does. Rendered into a finding, that address makes
#: two runs of one container differ in bytes -- the tool's own promise, broken by
#: a detail line -- and shows a reader an internal that tells them nothing.
#:
#: Anchored on the angle brackets rather than on the text " at 0x": exception
#: messages quote the document, and a container whose metadata said
#: `Bogus at 0x41` had that value silently shortened to `Bogus` by the first
#: version of this -- a report naming something the document does not contain,
#: which is worse than a report carrying an address. Only the default `repr`
#: shape is touched, and what is left (`<_io.BytesIO object>`) still reads as an
#: object rather than pretending to be anything else.
#:
#: It does not catch every way an address can be written: `id()` rendered in
#: decimal is invisible to it. Nothing in this project renders one, and the
#: corpus sweep in `tests/test_determinism.py` is what would notice if that
#: changed.
_ADDRESS = re.compile(r"(<[^<>]*) at 0x[0-9a-fA-F]+>")


def without_addresses(text: str) -> str:
    """The exception's words, with addresses gone from the objects they name."""
    return _ADDRESS.sub(r"\1>", text)


__all__ = ["About", "Defect", "Finding", "Kind", "Location", "MAIN_PDF", "MAIN_XML", "METADATA_XML",
           "NS", "Obligation", "Report", "Rule", "Severity", "UnsafeXml", "XmlTooLarge"]


class Severity(enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def rank(self) -> int:
        return {"error": 0, "warning": 1, "info": 2}[self.value]


class About(enum.Enum):
    """Who the finding is about.

    Some rules fire because this tool stopped — a broken installation, a document
    the schema checker would not finish, an archive over a budget, a tree deeper
    than we open, a scan for an indirect object that ended without answering.
    Nothing in those is a statement about what the sender packed, and a consumer
    reading the JSON could not tell them from the rest.

    No count here. Which rules those are is the catalogue's to say and
    `tests/test_catalogue.py` holds the list against it; a number in this
    sentence is a second copy of that list with nothing checking it, which is
    how it came to read "four" while there were eight.
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
        # Natural order, not lexical: comparing the ids as strings printed `Z1`,
        # `Z10`, `Z11`, `Z12`, `Z2`. The `rules` subcommand was given this once
        # and the report was not, so the two disagreed about what order the
        # rules come in.
        w = self.where
        letters = self.rule.id.rstrip("0123456789")
        number = int(self.rule.id[len(letters):] or 0)
        return (self.severity.rank, letters, number, w.container, w.member or "",
                w.line if w.line is not None else -1, w.subject or "", self.message)



# One rule can have as many findings as the document has elements, which the
# element budget now caps at just under a hundred thousand per container: 99,000
# empty DocumentIds give 99,000 byte-identical M10 lines from a 116 KiB archive,
# 26.7 KB of text and 75.2 KB of JSON. (The figures once here — four hundred
# thousand lines, 923 MB, 3.98 GB across two containers — were measured before
# that cap existed and describe a document this reader will no longer build.)
# Nobody reads the ninety-nine thousandth line, and nothing downstream needs it
# either — the count does.
MAX_LISTED_PER_RULE = 100

# And a hundred is a count, not a size. Every finding carries the path of the
# container it is in, a member name may be 65,535 bytes long, and a container
# that holds others repeats its name in every one of their paths -- so a hundred
# findings per rule, in each of up to a thousand containers, each printing a
# name the sender chose, grew with the containers times the length of that name.
# Ten containers under a 65,531-character name printed 68 MB of JSON and as much
# again of text from a 144 KB archive; twice the containers printed twice that.
#
# So each rule's listing also stops at a size: about how many bytes its findings
# print, in whichever shape prints more, counted where they are collected --
# as printed, not as stored, because both shapes spell some characters out and
# a name made of them printed six to thirteen times what a count of characters
# let through. Counted where they are
# printed, it would bound the page and not the memory, because every finding
# would be held until then. Past it a finding is counted and not kept, as past
# the cap above, and both shapes of the report say where the listing stopped.
LISTING_BUDGET_PER_RULE = 1_000_000

#: What one finding prints besides its own strings -- keys and indentation, the
#: rule's fields, the basis line -- as a flat allowance, so that a rule firing
#: many times with short strings reaches the budget too. The most any rule in
#: the catalogue takes is about 550 bytes, in JSON, and a test holds every rule
#: to this figure.
LISTED_ALLOWANCE = 1_024


def _json_bytes(s: str) -> int:
    """Bytes `s` takes as a string in the JSON shape, its quotes left out, on
    any console. One that cannot print UTF-8 gets the JSON with every non-ASCII
    character escaped -- six bytes, twelve above the BMP -- which is the most
    `s` can take."""
    return len(json.dumps(s, ensure_ascii=True)) - 2


def _page_bytes(s: str) -> int:
    """Bytes `s` takes on the page, on any console. One that cannot print a
    character gets a backslash escape for it -- up to ten bytes -- which is the
    most `s` can take."""
    return len(s.encode("ascii", "backslashreplace"))


@lru_cache(maxsize=1024)
def _where_bytes(s: str) -> Tuple[int, int]:
    """(JSON, page) bytes of a location string. Cached, because every finding
    in a container carries that container's path: the same string each time."""
    return _json_bytes(s), _page_bytes(as_written(s))


def listed_size(f) -> int:
    """About how many bytes listing `f` prints, in whichever shape prints more.

    As printed rather than as stored. JSON writes a control character as six
    characters; the page writes one as six and an invisible symbol as ten, and
    spells out names on the `at` line only. A count of characters as stored let
    a name made of either print six to thirteen times what the listing held.

    And on whichever console prints more: the command writes the JSON escaped
    and the page with backslash escapes where the console cannot print UTF-8,
    and a charge counted in UTF-8 let that print three times the budget.
    """
    w = f.where
    said = (f.message, f.detail or "", f.remedy)
    located = [_where_bytes(s) for s in (w.container or "", w.member or "")]
    as_json = (sum(_json_bytes(s) for s in said) + sum(j for j, _t in located)
               + _json_bytes(w.xpath or "") + _json_bytes(w.subject or ""))
    as_page = (sum(_page_bytes(on_one_line(s)) for s in said)
               + sum(t for _j, t in located))
    return LISTED_ALLOWANCE + max(as_json, as_page)


@dataclass
class Read:
    """What this read opened, and what the archive says was there to open.

    Both halves come from the archive's own directory rather than from how far
    this tool got, which is the property that makes the pair worth printing:
    every number is over names the archive lists, so giving up cannot improve
    it. A sender can check the figures against a listing of the archive -- of
    each archive, where containers are nested, because these count the tree and
    a listing shows one level. A figure counted over this tool's own machinery has the
    opposite sign — a file that is not a ZIP calls for one check, that check
    runs, and the worst input this tool sees scores full marks.
    """

    archives_found: int = 0
    archives_opened: int = 0
    metadata_found: int = 0
    metadata_read: int = 0


@dataclass
class Report:
    target: str
    findings: list = field(default_factory=list)
    read: Read = field(default_factory=Read)
    # (rule id, container) -> how many findings were counted but not kept.
    suppressed: Dict[Tuple[str, str], int] = field(default_factory=dict)
    _listed: Dict[Tuple[str, str], int] = field(default_factory=dict, repr=False)
    _suppressed_severity: Dict[Severity, int] = field(default_factory=dict, repr=False)
    # And by axis, for the same reason the line above exists: the summary says
    # how many of the errors are this tool declining to look, and counting that
    # over `findings` counts only the ones the cap let through.
    _suppressed_about: Dict[Tuple[Severity, About], int] = field(
        default_factory=dict, repr=False)
    _suppressed_rule: Dict[Tuple[str, str], Rule] = field(default_factory=dict, repr=False)
    # rule id -> how many findings the size budget counted but did not keep.
    over_budget: Dict[str, int] = field(default_factory=dict)
    _over_budget_rule: Dict[str, Rule] = field(default_factory=dict, repr=False)
    # rule id -> characters its listing has spent, findings in all, findings kept.
    _spent: Dict[str, int] = field(default_factory=dict, repr=False)
    _in_all: Dict[str, int] = field(default_factory=dict, repr=False)
    _kept: Dict[str, int] = field(default_factory=dict, repr=False)

    def add(self, f: Finding) -> None:
        rid = f.rule.id
        self._in_all[rid] = self._in_all.get(rid, 0) + 1
        key = (rid, f.where.container)
        if self._listed.get(key, 0) >= MAX_LISTED_PER_RULE:
            # Counted, not kept. `count()` still reports every one of them, so
            # the summary and the exit code stay true; only the listing is bounded.
            self.suppressed[key] = self.suppressed.get(key, 0) + 1
            self._suppressed_rule[key] = f.rule
            self._count_unlisted(f)
            return
        # Not sized once the listing has stopped: nothing it would say is kept.
        size = 0 if rid in self.over_budget else listed_size(f)
        if rid in self.over_budget or self._spent.get(rid, 0) + size > LISTING_BUDGET_PER_RULE:
            # Counted, not kept, for the same reason. And once a rule's listing
            # has stopped it stays stopped: a smaller finding after a larger one
            # would fit, and "stopped" would then be true of neither.
            self.over_budget[rid] = self.over_budget.get(rid, 0) + 1
            self._over_budget_rule[rid] = f.rule
            self._count_unlisted(f)
            return
        self._spent[rid] = self._spent.get(rid, 0) + size
        self._kept[rid] = self._kept.get(rid, 0) + 1
        self._listed[key] = self._listed.get(key, 0) + 1
        self.findings.append(f)

    def _count_unlisted(self, f: Finding) -> None:
        self._suppressed_severity[f.severity] = (
            self._suppressed_severity.get(f.severity, 0) + 1)
        self._suppressed_about[(f.severity, f.about)] = (
            self._suppressed_about.get((f.severity, f.about), 0) + 1)

    def not_listed(self, show_info: bool = True) -> List[Tuple[str, str, int]]:
        """(rule id, container, how many) for findings counted but not kept.

        Honours the same INFO filter the listing does, so a quiet run does not
        announce notes it is not printing."""
        return [(rid, container, n)
                for (rid, container), n in sorted(self.suppressed.items())
                if show_info
                or self._suppressed_rule[(rid, container)].severity is not Severity.INFO]

    def stopped(self, show_info: bool = True) -> List[Tuple[str, int, int]]:
        """(rule id, how many in all, how many listed) for each rule whose
        listing stopped at its size budget, under the same INFO filter."""
        return [(rid, self._in_all[rid], self._kept.get(rid, 0))
                for rid in sorted(self.over_budget)
                if show_info
                or self._over_budget_rule[rid].severity is not Severity.INFO]

    def sorted(self) -> list:
        return sorted(self.findings, key=lambda f: f.sort_key())

    def count(self, sev: Severity) -> int:
        return (sum(1 for f in self.findings if f.severity is sev)
                + self._suppressed_severity.get(sev, 0))

    def count_about(self, sev: Severity, about: About) -> int:
        """How many of `sev` are on `about`'s axis, listed or not."""
        return (sum(1 for f in self.findings
                    if f.severity is sev and f.about is about)
                + self._suppressed_about.get((sev, about), 0))

    @property
    def clean(self) -> bool:
        return self.count(Severity.ERROR) == 0
