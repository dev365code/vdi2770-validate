"""Put the readers and the rules together. This is the only module that knows
both sides exist."""
from __future__ import annotations

from typing import Optional

from .domain import build
from .model import Report
from .readers import pdfread, xmlread, xsdvalidate, zipread
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

    for c in root.walk():
        for f in r_container.check(c):
            report.add(f)

        if c.metadata_bytes is None:
            continue

        parse_error = None
        tree = None
        try:
            tree = xmlread.parse(c.metadata_bytes)
        except xmlread.XmlError as e:
            parse_error = e

        schema_errors = xsdvalidate.validate(c.metadata_bytes, tree) if tree is not None else []
        for f in r_schema.check(c, parse_error, schema_errors):
            report.add(f)
        if tree is None:
            continue

        base = c.where.child(member=c.metadata_name)
        document = build(tree, base)
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
