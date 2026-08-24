"""Put the readers and the rules together.

The only module that *orchestrates* both sides. Two others touch the reader for
narrower reasons: `model.py` re-exports its vocabulary so the rules need not, and
`readers/xsdvalidate.py` walks its node tree to put a line number on a schema
complaint. Nothing else in this package imports it, and a test enforces that for
the rules."""
from __future__ import annotations

from typing import Optional

from vdi2770 import pdfread, xmlread, zipread
from vdi2770.domain import build

from .model import Report
from .names import nfc
from .readers import xsdvalidate
from .rules import container as r_container
from .rules import files as r_files
from .rules import metadata as r_metadata
from .rules import pdf as r_pdf
from .rules import schema as r_schema


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
    root = zipread.read(data, name)
    # One entry per level, not one per container. `walk()` is pre-order, so when
    # a container at depth d is reached the entry at d-1 is its parent -- nothing
    # at that depth is written between them. The previous version kept every
    # container's bytes in a dict keyed by path and never dropped any: a 2 MB
    # input with two hundred inner containers held 1.6 GB, which is the same
    # amplification the reader's tree budget was added to bound, reached through
    # a door the budget does not watch.
    # One entry per level, not one per container, and written for *every*
    # container before anything can skip it. `walk()` is pre-order, so the entry
    # at d-1 is this container's parent -- but only if nothing at that depth was
    # skipped in between. An earlier version published these after two `continue`
    # statements, so a container with no metadata never wrote its own bytes and
    # its children read whichever sibling subtree had been there before: the tool
    # printed a PDF/A claim for a text file, having read a different member of a
    # different archive. Publish first, decide later.
    raw_at_depth = {0: data}
    declared_at_depth = {}

    for c in root.walk():
        if c.depth == 0:
            raw = data
        else:
            parent_raw = raw_at_depth.get(c.depth - 1)
            # `member_name` comes from the reader. Reconstructing it by splitting
            # the path on the JAR separator got the wrong parent for a member
            # whose own name contains one, which was a way to have `Z3`
            # suppressed on an archive nobody declared.
            raw = (zipread.member_bytes(parent_raw, c.member_name)
                   if parent_raw is not None and c.member_name else None)
        raw_at_depth[c.depth] = raw

        parse_error = None
        tree = None
        document = None
        if c.metadata_bytes is not None:
            try:
                tree = xmlread.parse(c.metadata_bytes)
            except xmlread.XmlError as e:
                parse_error = e
            if tree is not None:
                document = build(tree, c.where.child(member=c.metadata_name))

        declared = frozenset(nfc(f.file_name) for f in document.all_files
                             if f.file_name) if document else frozenset()
        declared_at_depth[c.depth] = declared

        is_payload = bool(c.member_name) and nfc(c.member_name) in declared_at_depth.get(
            c.depth - 1, frozenset())

        for f in r_container.check(c, declared=declared, is_declared_payload=is_payload):
            report.add(f)

        if c.metadata_bytes is None:
            continue

        schema_errors = xsdvalidate.validate(c.metadata_bytes, tree) if tree is not None else []
        for f in r_schema.check(c, parse_error, schema_errors):
            report.add(f)
        if document is None:
            continue

        is_main = c.metadata_name == zipread.MAIN_XML

        for f in r_files.check(c, document):
            report.add(f)
        for f in r_metadata.check(c, document, is_main):
            report.add(f)

        if raw is not None:
            for f in r_pdf.check(c, document, _facts_for(raw, set(c.file_names))):
                report.add(f)

    return report


def check_file(path: str) -> Report:
    with open(path, "rb") as fh:
        data = fh.read()
    return check_bytes(data, path.rsplit("/", 1)[-1])
