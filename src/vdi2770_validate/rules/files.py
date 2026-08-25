"""File-set rules (F): does the metadata agree with what is actually in the ZIP?"""
from __future__ import annotations

from typing import Iterator

from ..catalog import rule
from ..model import MAIN_PDF, MAIN_XML, METADATA_XML, About, Finding, Kind
from ..names import Members, nfc

EXTENSION_FOR = {"application/pdf": ".pdf", "application/zip": ".zip"}


#: Refusals that are this tool's limit rather than a fault in the delivery.
#: The rest — an unsafe name, bytes that will not decompress — really are the
#: sender's, and the remedy differs accordingly.
BUDGET_REFUSALS = frozenset({
    "member-too-large", "suspicious-compression", "metadata-too-large",
    "archive-too-large", "container-budget-exhausted",
    "decompression-budget-exhausted", "member-budget-exhausted",
})


def check(container, document) -> Iterator[Finding]:
    # Names are reconciled in one place, for every comparison in this module and
    # the PDF one. See names.py for the two ways of getting this wrong that are
    # already behind it.
    members = Members(container.file_names, container.rejected)
    accounted_for = set()

    for f in document.all_files:
        if not f.file_name:
            r = rule("F4")
            yield Finding(r, r.title, f.src.child(container=container.path,
                                                  member=container.metadata_name),
                          detail=f"declared as {f.file_format!r} with no file name")
            continue
        found = members.resolve(f.file_name)
        if found is not None:
            accounted_for.add(found)
        else:
            r = rule("F1")
            rejected = members.refusal(f.file_name)
            because = members.refused_by(f.file_name)
            # The headline has to match the detail, and the detail has to match
            # *why*. A declared file that is in the archive is not missing, and
            # printing the rule's own title over that put a false sentence above
            # a true one. Then the replacement said "could not be read" for every
            # refusal — true of a bad CRC, false of a member this tool declined
            # to inflate, whose bytes are fine. It fires here rather than at the
            # member because this is the line in the metadata that named the file.
            ours = because is not None and because.kind in BUDGET_REFUSALS
            twice = f.file_name in members.ambiguous
            if twice:
                message = ("A file named in the metadata is in the container more "
                           "than once")
                fix = ("Remove the repeat. The name denotes two members with different "
                       "bytes, and which one a reader extracts is its own business — so "
                       "this tool will not say which of them you declared.")
                whose = None
            elif because is None:
                message, fix, whose = r.title, None, None
            elif ours:
                message = ("A file named in the metadata is in the container and this "
                           "tool declined to read it")
                fix = ("Nothing here is necessarily wrong with the file: it is inside a "
                       "limit this tool sets for untrusted input, and the finding beside "
                       "this one says which. Send it separately, or check it with "
                       "something that will read it.")
                whose = About.TOOL
            else:
                message = ("A file named in the metadata is in the container but could "
                           "not be read")
                fix = ("Re-create the archive and send it again. The file is listed, so "
                       "the metadata is right; the bytes behind the name are not readable.")
                whose = None
            if twice:
                detail = f"{f.file_name!r} names two members of the archive"
            elif rejected:
                detail = f"{f.file_name!r} is in the archive but was refused: {rejected}"
            else:
                detail = f"{f.file_name!r} is declared but not in the archive"
            yield Finding(r, message, f.src.child(container=container.path,
                                                  member=container.metadata_name),
                          detail=detail, fix=fix, as_about=whose)

    # Reserved where it is reserved, and nowhere else. Exempting all three names
    # everywhere meant a stray VDI2770_Main.pdf inside a document container -- a
    # name that means nothing there -- was never reported as undeclared.
    structural = ({MAIN_XML, MAIN_PDF} if container.kind is Kind.DOCUMENTATION
                  else {METADATA_XML})
    # The archive's own spelling, not the canonical one: a name the user cannot
    # find in their ZIP listing is not a report they can act on.
    # A folder holding its own VDI2770_Metadata.xml is a document container that
    # was not zipped. Its files are declared in metadata this tool never opened,
    # so calling them undeclared is a statement about a file we did not read.
    # `Z13` says we did not read it.
    from .container import folders_holding_metadata
    unopened = tuple(folders_holding_metadata(container))
    for name in sorted(set(members.present) - accounted_for - structural):
        if name.lower().endswith(".zip"):
            continue
        if any(nfc(name).startswith(f) for f in unopened):
            continue
        r = rule("F2")
        yield Finding(r, r.title, container.where.child(member=name, subject=name))

    for f in document.all_files:
        want = EXTENSION_FOR.get(f.file_format.split(";")[0].strip().lower())
        if want and f.file_name and not f.file_name.lower().endswith(want):
            r = rule("F3")
            yield Finding(r, r.title,
                          f.src.child(container=container.path, member=container.metadata_name),
                          detail=f"{f.file_name!r} is declared as {f.file_format!r}")
