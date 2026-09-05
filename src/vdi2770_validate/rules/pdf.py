"""PDF rules (P). We report what a PDF claims. We never report a claim as a verdict."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from ..catalog import rule
from ..model import MAIN_PDF, About, Finding, Kind
from ..names import Members, as_written, folder_path

UNVERIFIED = "this tool cannot verify PDF/A conformance"

@dataclass(frozen=True)
class Stopped:
    """A declared PDF whose *claim search* this read stopped short of running.

    Not "a file nobody opened": the allowance bounds inflating streams, and the
    header, the indirect objects and the encryption flag are all read from bytes
    no stream has to be inflated for. Withholding those too made spending the
    budget delete `P1` from the reserved main document -- a worse answer than
    the `P3` this class was invented to prevent, which is "this scan found no
    PDF/A claim in the file" over a scan that did not happen.

    So the facts travel with it and every rule but `P3` is judged from them. It
    carries the ceiling rather than reading it, because a rule module may not
    import a parser: the layer that spends a budget knows what it was, and this
    one only says so.
    """

    #: What this read may inflate in total. Only the `"read"` reason spends it,
    #: and only `Z5` prints it; it is carried rather than read because a rule
    #: module may not import a parser.
    ceiling: int
    facts: object
    #: Which limit ended the search. `"read"` is the allowance across the whole
    #: read and is the only one `Z5` speaks for -- it says nothing about this
    #: file, so it belongs to the container. `"file"` and `"streams"` are this
    #: file being larger than a bounded scan reads, which is `P3` saying so.
    reason: str

# The most files one finding will name before it counts the rest, as everywhere
# else a finding lists members.
MAX_NAMED = 5

#: Why a member is scanned when no metadata declared it. Named rather than
#: spelled twice: the reason a file qualifies is also the obligation it is held
#: to, and one of the two rules that reads it is the one that decides whether an
#: unconfirmed PDF is a finding.
RESERVED = "the reserved main document"


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
        out.append((at_root, RESERVED))
    return out


def check(container, document, facts_for) -> Iterator[Finding]:
    unopened = []
    for name, why in _targets(container, document):
        facts = facts_for(name)
        if facts is None:
            continue          # the reader refused it, and said so as a Z finding
        cut_short = isinstance(facts, Stopped)
        if cut_short:
            # A claim sitting in bytes no stream had to be inflated for is found
            # whether or not the allowance is spent, so the budget took nothing
            # away from this file and counting it among the cut-short ones would
            # be a report saying it looked away from a file it read. The reader
            # already only reports a cut search when it found nothing, but it is
            # separately versioned and the pin admits releases nobody here has
            # run, so this stays.
            stopped, facts = facts, facts.facts
            cut_short = facts.pdfa_claim is None
            # Only the read's allowance is somebody else's doing. The other two
            # are this file against a bounded scan, and `Z5` is an error on the
            # tool axis -- an ordinary multi-page PDF reaches them.
            if cut_short and stopped.reason == "read":
                unopened.append((name, stopped))
        where = container.where.child(member=name, subject=name)
        if facts.is_pdf is False:
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
        if facts.is_pdf is None:
            # The reader looked at `MAX_OBJ_PROBES` places and did not find an
            # indirect object. That is not "no PDF document here" -- a
            # conforming file can carry a long comment, and the scan can end
            # inside one -- so nothing here says it is.
            #
            # What it is worth depends on where the file sits. Every declared
            # rendition owes something: `M6` reads "Other formats may accompany
            # it but cannot replace it", so a version has to have a PDF, and
            # `_targets` scans the declared renditions and the reserved name.
            # There is no member here with no duty at all, which is why silence
            # was wrong for both. The reserved name owes more: the recipient's
            # system opens it as a PDF whatever this scan could confirm, so that
            # one is an error and the rest are a warning `M6` does not cover.
            #
            # Same observation, two obligations, two strengths. The sentence
            # stays with the observation either way: it never says the file is
            # not a PDF, because that is exactly what was not established.
            #
            # `as_about` on both, because the limit that ended the scan is ours.
            # It is also what keeps `read.complete` honest -- a report saying it
            # stopped looking and `complete: true` in the same breath is the
            # contract `docs/scope.md` writes down.
            #
            # No number in either sentence: a rule module may not import a
            # parser, the same reason `Stopped` is handed its ceiling.
            reserved = (container.kind is Kind.DOCUMENTATION
                        and folder_path(name) == MAIN_PDF)
            r = rule("P1" if reserved else "P5")
            yield Finding(
                r,
                "This file could not be confirmed to be a PDF document" if reserved
                else r.title,
                where,
                detail=(f"{RESERVED}, so it has to be one; " if reserved else "")
                       + "the scan looked as far into it as it looks and found "
                         "no indirect object. Whether there is one beyond that "
                         "is not known",
                fix=("If this is a real PDF, re-export it: a file that fills its "
                     "own beginning with `obj` before its first indirect object "
                     "is not something a producer writes, and whatever wrote "
                     "this is worth looking at. If it is not a PDF, the name is "
                     "reserved and the recipient's system will open it as one, "
                     "so put the main document here. If you believe this is a "
                     "conforming file this tool cannot read, please report it "
                     "with the file.") if reserved else None,
                as_about=About.TOOL)
            # And then fall through. Whether the file is a PDF document says
            # nothing about the other three facts -- the header, the encryption
            # flag and the PDF/A claim are read from bytes no indirect object had
            # to be found for. Skipping them threw away what the scan did settle:
            # a declared rendition holding `/Encrypt` lost its `P2` outright, so
            # a container that came back with a warning came back clean.
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
            if cut_short and stopped.reason == "read":
                continue      # the search did not run at all; `Z5` says so
            r = rule("P3")
            if cut_short:
                # Same rule, same severity: this is still a warning about a
                # document in the container, and an ordinary multi-page PDF
                # reaches these limits. What changes is that the sentence says
                # the scan stopped, and that this one occurrence takes the tool
                # axis -- the limit is ours. The remedy already ends "if the
                # file does carry one, our scan did not reach it"; until now the
                # detail gave a reader no way to tell which had happened.
                #
                # No number: `MAX_STREAMS` counts stream *markers* and
                # `stream\n` matches `endstream\n` too, so any count printed
                # here would be about twice what a PDF parser sees in the file.
                yield Finding(
                    r, r.title, where,
                    detail="this scan stopped before the end of the file, "
                           "against a limit of this tool rather than anything "
                           "in the file; there is no pdfaid identification in "
                           "the part it read",
                    as_about=About.TOOL)
            else:
                yield Finding(
                    r, r.title, where,
                    detail="no pdfaid identification found in the XMP metadata")
        else:
            r = rule("P4")
            if facts.pdfa_claim.endswith("?"):
                # `?` is the reader saying "a part, and no level with it".
                # Printing it inside the claim quotes the file for a level it
                # does not name; parts 1 to 3 require one, so its absence is the
                # thing to say, and saying it is not "the claim is well-formed".
                yield Finding(
                    r, r.title, where,
                    detail=f"claims PDF/A part {facts.pdfa_claim[:-1]} and names "
                           f"no conformance level — {UNVERIFIED}, and this claim "
                           f"is incomplete besides",
                    fix="Parts 1, 2 and 3 of PDF/A each require a conformance "
                        "level beside the part. Re-export with a producer that "
                        "writes one into the XMP metadata, then run a PDF/A "
                        "validator such as veraPDF if you need the claim itself "
                        "verified.")
            else:
                yield Finding(
                    r, r.title, where,
                    detail=f"claims PDF/A-{facts.pdfa_claim} — {UNVERIFIED}. The "
                           f"claim is the first one in the file; PDF/A-3 files "
                           f"carry attachments with XMP packets of their own, and "
                           f"this tool cannot tell one from the other")

    if unopened:
        # `Z5`, the sentence this tool already uses for every limit it declines
        # to spend: same statement, same remedy -- split the delivery -- and
        # `about: tool`, because the ceiling is ours. Saying it once with a count
        # beats one line per file, and saying nothing was the defect.
        #
        # Only the allowance spent across the read reaches here. A ceiling one
        # file went over on its own is that file's `P3`, whose remedy already
        # ends "if the file does carry one, our scan did not reach it": an error
        # on the tool axis for an ordinary multi-page PDF is the shape
        # `test_tool_limits_are_not_verdicts.py` exists to keep out, and one
        # remedy cannot serve both -- "split the delivery" does nothing about a
        # limit that is per file.
        r = rule("Z5")
        gib = unopened[0][1].ceiling / (1024 ** 3)
        one = len(unopened) == 1
        yield Finding(
            r, r.title, container.where,
            detail=f"this read spent its {gib:g} GiB budget for inflating PDF "
                   f"streams, so the search for a PDF/A claim inside "
                   f"{len(unopened)} declared PDF "
                   f"file{'' if one else 's'} was cut short for: "
                   + ", ".join(as_written(n) for n, _ in unopened[:MAX_NAMED])
                   + (", ..." if len(unopened) > MAX_NAMED else "")
                   + f". Nothing is said about whether "
                     f"{'it carries' if one else 'they carry'} one",
            fix="Split the delivery into several containers, or produce the "
                "documents as PDF/A: the scan stops at the first PDF/A claim it "
                "finds, so a delivery of conforming files does not approach this "
                "budget. Every other check on these files still ran.")
