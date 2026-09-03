"""PDF rules (P). We report what a PDF claims. We never report a claim as a verdict."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from ..catalog import rule
from ..model import MAIN_PDF, Finding, Kind
from ..names import Members, as_written, folder_path

UNVERIFIED = "this tool cannot verify PDF/A conformance"

@dataclass(frozen=True)
class Stopped:
    """The answer for a declared PDF this read stopped short of opening.

    Distinct from `None`, which means the archive reader refused the member and
    said so as a `Z` finding. Both were `None` once, and a file nobody opened
    drew `P3` -- "this scan found no PDF/A claim in the file" -- which is a fact
    about a scan that did not happen.

    It carries the ceiling rather than reading it, because a rule module may not
    import a parser: the layer that spends a budget is the layer that knows what
    it was, and this one only says so.
    """

    ceiling: int

# The most files one finding will name before it counts the rest, as everywhere
# else a finding lists members.
MAX_NAMED = 5


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

    # Found by what it extracts to, not by how it is spelled. Undeclared and
    # written `./VDI2770_Main.pdf`, the reserved main document matched nothing
    # here and was scanned by nobody -- which is the sentence in this function's
    # own docstring, arriving again through the `./` in front of the name.
    at_root = next((n for n in container.file_names
                    if folder_path(n) == MAIN_PDF), None)
    if (container.kind is Kind.DOCUMENTATION
            and at_root is not None and at_root not in seen):
        out.append((at_root, "the reserved main document"))
    return out


def check(container, document, facts_for) -> Iterator[Finding]:
    unopened = []
    for name, why in _targets(container, document):
        facts = facts_for(name)
        if facts is None:
            continue          # the reader refused it, and said so as a Z finding
        if isinstance(facts, Stopped):
            unopened.append((name, facts))
            continue
        where = container.where.child(member=name, subject=name)
        if not facts.is_pdf:
            r = rule("P1")
            # A file that never claimed to be a PDF and one that begins with the
            # header and carries no document are both "not a PDF", and a sender
            # looking at the second reads the first sentence, sees `%PDF-` in
            # their own file, and stops believing the report.
            yield Finding(r, r.title, where,
                          detail=why if not facts.header else
                          f"{why}; it begins with the header {facts.header!r} and "
                          f"carries no indirect object, so there is no PDF "
                          f"document after it")
            continue
        if facts.encrypted:
            r = rule("P2")
            yield Finding(r, r.title, where)
        if facts.pdfa_claim is None and facts.encrypted:
            # P2, one branch above, already says the file cannot be read. Adding
            # "this scan found no PDF/A claim" would be true of the scan and
            # useless to the reader, and its detail and remedy both name XMP
            # metadata this tool never decrypted -- telling a producer to fix an
            # exporter that may be doing the right thing. If we could not look,
            # we do not get to say.
            pass
        elif facts.pdfa_claim is None:
            r = rule("P3")
            yield Finding(r, r.title, where,
                          detail="no pdfaid identification found in the XMP metadata")
        else:
            r = rule("P4")
            yield Finding(r, r.title, where,
                          detail=f"claims PDF/A-{facts.pdfa_claim} — {UNVERIFIED}. The claim is "
                   f"read from an XMP packet in the file; PDF/A-3 files carry "
                   f"attachments with packets of their own, and this tool cannot "
                   f"tell one from the other")

    if unopened:
        # `Z5`, the sentence this tool already uses for every limit it declines
        # to spend: same statement, same remedy -- split the delivery -- and
        # `about: tool`, because the ceiling is ours. Saying it once with a count
        # beats one line per file, and saying nothing was the defect.
        r = rule("Z5")
        yield Finding(
            r, r.title, container.where,
            detail=f"this read spent its {unopened[0][1].ceiling}-byte "
                   f"budget for inflating PDF streams, so "
                   f"{len(unopened)} declared PDF "
                   f"file{'' if len(unopened) == 1 else 's'} "
                   f"{'was' if len(unopened) == 1 else 'were'} not opened: "
                   + ", ".join(as_written(n) for n, _ in unopened[:MAX_NAMED])
                   + (", ..." if len(unopened) > MAX_NAMED else "")
                   + ". Nothing is claimed about them",
            fix=rule("Z5").remedy)
