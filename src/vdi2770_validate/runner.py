"""Put the readers and the rules together. This is the only module that knows
both sides exist."""
from __future__ import annotations

from typing import Optional

from vdi2770 import pdfread, xmlread, zipread
from vdi2770.domain import build

from .model import Report, nfc
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
    raw_by_path = {root.path: data}

    # walk() is pre-order, so a container's parent has always been through this
    # loop before the container itself. That is what lets a rule ask "did my
    # parent's metadata declare me as a file?" without a second pass.
    declared_by_path = {}

    for c in root.walk():
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
        declared_by_path[c.path] = declared

        parent_path, _, member = c.path.rpartition("!/")
        is_payload = bool(parent_path) and nfc(member) in declared_by_path.get(
            parent_path, frozenset())

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

        raw = raw_by_path.get(c.path)
        if raw is None:
            parent_path, _, member = c.path.rpartition("!/")
            parent_raw = raw_by_path.get(parent_path)
            raw = zipread.member_bytes(parent_raw, member) if parent_raw else None
            raw_by_path[c.path] = raw
        if raw is not None:
            for f in r_pdf.check(c, document, _facts_for(raw, set(c.file_names))):
                report.add(f)

    return report


def check_file(path: str) -> Report:
    with open(path, "rb") as fh:
        data = fh.read()
    return check_bytes(data, path.rsplit("/", 1)[-1])
