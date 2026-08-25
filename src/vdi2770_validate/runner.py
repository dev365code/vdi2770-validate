"""Put the readers and the rules together.

The only module that *orchestrates* both sides. Two others touch the reader for
narrower reasons: `model.py` re-exports its vocabulary so the rules need not, and
`xsdvalidate.py` walks its node tree to put a line number on a schema
complaint. Nothing else in this package imports it, and a test enforces that for
the rules."""
from __future__ import annotations

from typing import Optional

from vdi2770 import pdfread, xmlread, zipread
from vdi2770.domain import build

from . import xsdvalidate
from .catalog import rule
from .model import Finding, Location, Report
from .names import nfc
from .rules import container as r_container
from .rules import files as r_files
from .rules import metadata as r_metadata
from .rules import pdf as r_pdf
from .rules import schema as r_schema


def _into(report, findings, where, what: str) -> None:
    """Run one rule module's findings into the report, demoting a crash.

    CODE-CONVENTIONS §5: one rule's exception must not kill the run. It killed
    the run — a batch died on one archive with a traceback naming this tool's
    internals, and every container after it went unchecked. A rule that crashed
    has checked nothing, so this is an error: reporting the rest and exiting 0
    would tell the reader that check passed.

    The findings it managed to produce before crashing are kept. They are as true
    as they were going to be.
    """
    try:
        for f in findings:
            report.add(f)
    except Exception as e:                       # noqa: BLE001 - that is the point
        r = rule("X5")
        report.add(Finding(r, r.title, where,
                           detail=f"the {what} checks: {type(e).__name__}: {e}"))


_CRASHED = object()          # "this step raised"; distinct from a step that returned None



def _step(report, where, what: str, fn, *args, fix: Optional[str] = None):
    """Run one step that feeds the rules, demoting a crash the same way.

    `_into` wraps the rules. These run before them — parsing the metadata,
    building the document, walking the schema errors — and a crash in any of
    them killed the run just as dead. The guard was written for the rules and
    stopped at their door.

    Returns `_CRASHED` so the caller can tell "it raised" from "it legitimately
    produced nothing", which are different situations and used to look alike.

    `fix` overrides X5's remedy for a step whose failure means something the
    catalogue's sentence does not cover — see the container read in
    `check_bytes`, after which there is no rest of the report to still stand.
    """
    try:
        return fn(*args)
    except Exception as e:                       # noqa: BLE001 - that is the point
        r = rule("X5")
        report.add(Finding(r, r.title, where, detail=f"the {what} step: {type(e).__name__}: {e}",
                           fix=fix))
        return _CRASHED


def _facts_for(raw: bytes, accepted):
    cache = {}

    def get(name: str) -> Optional[pdfread.PdfFacts]:
        if name not in cache:
            member = zipread.member_bytes(raw, name, allowed=accepted)
            cache[name] = pdfread.read(member) if member is not None else None
        return cache[name]

    return get


def check_bytes(data: bytes, name: str) -> Report:
    report = Report(target=name)
    # The reader's contract is that it records a `Defect` rather than raising,
    # and its own suite holds it to that. It is also a separately versioned
    # package: the pin admits releases nobody in this repository has run, and a
    # crash there is the failure `_into` exists to prevent — a traceback naming
    # internals, with the rest of the batch unchecked. `_into` guarded the rules
    # and `_step` guarded what feeds them; the three calls into the reader sat
    # outside both.
    # X5's remedy ends "Every other finding in this report still stands; only the
    # named check did not run" -- written for one rule crashing among thirty that
    # did not. Every other check is downstream of this one, so here there is no
    # rest of the report, and the sentence would tell a user their archive was
    # checked when it was never opened.
    root = _step(report, Location(container=name), "container read", zipread.read, data, name,
                 fix="Nothing in the container needs changing for this one. This tool could "
                     "not open the archive at all, so nothing in it was checked — this "
                     "report is not a verdict on the container. Please report it with the "
                     "archive if you can share it.")
    if root is _CRASHED:
        return report
    # Keyed by the container each entry belongs to, and pruned as the walk
    # leaves a subtree, so at most one root-to-here chain is ever held. Two
    # earlier versions keyed this differently and both were wrong:
    #
    #   * by container path, dropping nothing -- a 2 MB input with two hundred
    #     inner containers held 1.6 GB, the same amplification the reader's tree
    #     budget was added to bound, reached through a door it does not watch;
    #   * by depth, trusting that `walk()` is pre-order so the entry at d-1 must
    #     be the parent. It is pre-order, but the entries were published after
    #     two `continue` statements, so a container with no metadata never wrote
    #     its own bytes and its children read whichever sibling subtree had been
    #     there before. The tool printed a PDF/A claim for a text file.
    #
    # Asking `c.parent` costs the same and cannot answer with somebody else's
    # archive: if an entry is missing the lookup misses, and a missing answer is
    # a rule that does not fire rather than a rule that fires about the wrong
    # file.
    # Keyed by `id()` and not by the container: `Container` is a dataclass with
    # `eq=True`, so `__hash__` is None and it cannot be a dict key. Every
    # container in this walk is reachable from `root`, so no id is reused while
    # the loop runs.
    raw_of = {}          # id(container) -> (depth, its own bytes or None)
    declared_of = {}     # id(container) -> the names its metadata declares

    for c in root.walk():
        # Leaving a subtree: everything at this depth or below is finished.
        for key in [k for k, (d, _) in raw_of.items() if d >= c.depth]:
            del raw_of[key]
            declared_of.pop(key, None)

        if c.parent is None:
            raw = data
        else:
            parent = raw_of.get(id(c.parent))
            # `member_name` comes from the reader. Reconstructing it by splitting
            # the path on the JAR separator got the wrong parent for a member
            # whose own name contains one, which was a way to have `Z3`
            # suppressed on an archive nobody declared.
            raw = None
            if parent is not None and parent[1] is not None and c.member_name:
                raw = _step(report, c.where, "member read",
                            zipread.member_bytes, parent[1], c.member_name)
                if raw is _CRASHED:
                    raw = None
        raw_of[id(c)] = (c.depth, raw)

        parse_error = None
        tree = None
        document = None
        if c.metadata_bytes is not None:
            try:
                tree = xmlread.parse(c.metadata_bytes)
            except xmlread.XmlError as e:
                # A malformed document is the container's problem and `X1`/`X3`
                # say so. Anything else out of expat is ours, and `_step` below
                # is what catches it -- this clause used to be the only guard,
                # so a surprise that was not an `XmlError` escaped the run.
                parse_error = e
            except Exception as e:               # noqa: BLE001
                r = rule("X5")
                report.add(Finding(r, r.title, c.where,
                                   detail=f"the parse step: {type(e).__name__}: {e}"))
                tree = None
            if tree is not None:
                document = _step(report, c.where, "document", build, tree,
                                 c.where.child(member=c.metadata_name))
                if document is _CRASHED:
                    document, tree = None, None

        declared = frozenset(nfc(f.file_name) for f in document.all_files
                             if f.file_name) if document else frozenset()
        declared_of[id(c)] = declared

        is_payload = bool(c.member_name) and nfc(c.member_name) in declared_of.get(
            id(c.parent), frozenset())

        _into(report, r_container.check(c, declared=declared, is_declared_payload=is_payload),
              c.where, "container")

        if c.metadata_bytes is None:
            continue

        schema_errors = (_step(report, c.where, "schema check", xsdvalidate.validate,
                               c.metadata_bytes, tree)
                         if tree is not None else [])
        if schema_errors is _CRASHED:
            schema_errors = []
        _into(report, r_schema.check(c, parse_error, schema_errors), c.where, "schema")
        if document is None:
            continue

        _into(report, r_files.check(c, document), c.where, "files")
        _into(report, r_metadata.check(c, document), c.where, "metadata")

        if raw is not None:
            _into(report, r_pdf.check(c, document, _facts_for(raw, set(c.file_names))),
                  c.where, "pdf")

    return report


def check_file(path: str) -> Report:
    with open(path, "rb") as fh:
        data = fh.read()
    return check_bytes(data, path.rsplit("/", 1)[-1])
