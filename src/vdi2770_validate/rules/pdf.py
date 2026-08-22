"""PDF rules (P). We report what a PDF claims. We never report a claim as a verdict."""
from __future__ import annotations

from typing import Iterator

from ..catalog import rule
from ..model import Finding

UNVERIFIED = "this tool cannot verify PDF/A conformance"


def check(container, document, facts_for) -> Iterator[Finding]:
    for f in document.all_files:
        fmt = f.file_format.split(";")[0].strip().lower()
        if fmt != "application/pdf" or not f.file_name:
            continue
        facts = facts_for(f.file_name)
        if facts is None:
            continue                      # F1 already reported it as missing
        where = container.where.child(member=f.file_name, subject=f.file_name)
        if not facts.is_pdf:
            r = rule("P1")
            yield Finding(r, r.title, where)
            continue
        if facts.encrypted:
            r = rule("P2")
            yield Finding(r, r.title, where)
        if facts.pdfa_claim is None:
            r = rule("P3")
            yield Finding(r, r.title, where,
                          detail="no pdfaid identification found in the XMP metadata")
        else:
            r = rule("P4")
            yield Finding(r, r.title, where,
                          detail=f"claims PDF/A-{facts.pdfa_claim} — {UNVERIFIED}")
