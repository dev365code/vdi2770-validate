"""PDF rules (P). We report what a PDF claims. We never report a claim as a verdict."""
from __future__ import annotations

from typing import Iterator

from ..catalog import rule
from ..model import MAIN_PDF, Finding, Kind
from ..names import Members

UNVERIFIED = "this tool cannot verify PDF/A conformance"


def _targets(container, document):
    """Which members to scan, in report order, each with the reason it qualifies.

    Two things are easy to get wrong here and both were. A file may be declared
    by several document versions, and printing one identical note per declaration
    drowns the report; and `VDI2770_Main.pdf` is a PDF because its name is
    reserved, whether or not any metadata says so -- an undeclared one used to be
    scanned by nobody, so an eighteen-byte text file passed with exit 0.
    """
    # Same reconciliation as the F rules, from the same place. Keeping a private
    # copy here is how the two came to disagree: this one answered a name that
    # matched two members by taking whichever came last, so a valid declared PDF
    # was judged by reading its junk twin.
    members = Members(container.file_names)

    out, seen = [], set()
    for f in document.all_files:
        fmt = f.file_format.split(";")[0].strip().lower()
        if fmt != "application/pdf" or not f.file_name:
            continue
        member = members.resolve(f.file_name)
        if member is None or member in seen:
            continue
        seen.add(member)
        out.append((member, "declared as application/pdf"))

    if (container.kind is Kind.DOCUMENTATION
            and MAIN_PDF in container.file_names and MAIN_PDF not in seen):
        out.append((MAIN_PDF, "the reserved main document"))
    return out


def check(container, document, facts_for) -> Iterator[Finding]:
    for name, why in _targets(container, document):
        facts = facts_for(name)
        if facts is None:
            continue          # the reader refused it, and said so as a Z finding
        where = container.where.child(member=name, subject=name)
        if not facts.is_pdf:
            r = rule("P1")
            yield Finding(r, r.title, where, detail=why)
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
