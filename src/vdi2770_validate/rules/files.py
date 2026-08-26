"""File-set rules (F): does the metadata agree with what is actually in the ZIP?"""
from __future__ import annotations

from typing import Iterator

from ..catalog import rule
from ..model import MAIN_PDF, MAIN_XML, METADATA_XML, About, Finding, Kind
from ..names import Members, escaped, extracts_to
from .container import MAX_FOLDER_DEPTH

EXTENSION_FOR = {"application/pdf": ".pdf", "application/zip": ".zip"}


#: Refusals that are this tool's limit rather than a fault in the delivery.
#: The rest — an unsafe name, bytes that will not decompress — really are the
#: sender's, and the remedy differs accordingly.
BUDGET_REFUSALS = frozenset({
    "member-too-large", "suspicious-compression", "metadata-too-large",
    "archive-too-large", "container-budget-exhausted",
    "decompression-budget-exhausted", "member-budget-exhausted",
})


def _inside(here: str, unopened) -> bool:
    """Whether the normalised member path `here` sits in one of `unopened`.

    By asking about *this path's* ancestors rather than scanning every folder.
    The scan was `any(here == f or here.startswith(f + "/") for f in unopened)`,
    run once per undeclared member, with `unopened` bounded only by
    `MAX_MEMBERS` -- so cost was members times folders and a 900 KB archive of
    four thousand each cost 24 seconds, past every budget the reader has,
    because none of them measures this.

    A path has at most `MAX_FOLDER_DEPTH` ancestors, which is the bound `Z9`
    already puts on the same walk one file away. Both sides go through
    `folder_path` first: `startswith` on raw names made `docdirX/B.pdf` look like
    it was inside `docdir/`, and a `./` on either side made a file inside one
    look like it was outside.
    """
    if here in unopened:
        return True
    prefix = ""
    for segment in here.split("/")[:-1][:MAX_FOLDER_DEPTH]:
        prefix = f"{prefix}/{segment}" if prefix else segment
        if prefix in unopened:
            return True
    return False


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
            # Read from the refusal, not from `members.ambiguous`. That set is
            # computed over `container.file_names`, and the reader refuses *both*
            # entries of a repeated name and leaves neither there -- so it is
            # always empty from real reader output, and this branch, which has
            # had the right words in it all along, had never once run. The
            # archive that stores `B.pdf` twice fell through to the bad-CRC
            # wording and was told to re-create the archive and send it again,
            # which reproduces the same archive and the same finding.
            twice = (f.file_name in members.ambiguous
                     or (because is not None and because.kind == "ambiguous-name"))
            # And the other way a name can reach more than one member: two
            # spellings the archive keeps as separate entries, both of which
            # canonicalise to what the metadata declared. `resolve` answers
            # `None` for that exactly as it does for "no such file", and every
            # branch here read the second as the first -- so a file the archive
            # holds twice was reported absent, with a remedy that said to add it
            # or to delete a declaration that was right.
            spellings = members.spelled_more_than_one_way(f.file_name)
            if spellings and not twice:
                message = ("A file named in the metadata matches more than one "
                           "member of the container")
                fix = ("Store one spelling. The names below are different bytes "
                       "that print the same, so nothing can say which of them "
                       "this declaration meant — and a reader asking for the "
                       "name you wrote may get either.")
                whose = None
            elif twice:
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
            elif "encrypted" in (because.detail or "").lower():
                # A member the sender locked is not a truncated transfer. The
                # bytes are intact and re-zipping the same directory produces the
                # same member and the same finding, so "send it again" is the one
                # remedy that cannot work. The detail already knew -- it prints
                # "password required" -- and the remedy ignored it.
                message = ("A file named in the metadata is in the container and "
                           "needs a password")
                fix = ("Remove the password from this member before handing the "
                       "container over. A recipient who cannot open a file has "
                       "not been given it, and nothing here can check what it "
                       "cannot read.")
                whose = None
            else:
                message = ("A file named in the metadata is in the container but could "
                           "not be read")
                fix = ("Re-create the archive and send it again. The file is listed, so "
                       "the metadata is right; the bytes behind the name are not readable.")
                whose = None
            if spellings and not twice:
                shown = " and ".join(escaped(n) for n in spellings)
                detail = (f"{f.file_name!r} matches {len(spellings)} members "
                          f"that print alike: {shown}")
            elif twice:
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
    from ..names import folder_path
    from .container import folders_holding_metadata
    unopened = frozenset(folder_path(f) for f in folders_holding_metadata(container)) - {""}
    # A member that shares its extracted path with one the metadata declared is
    # not undeclared -- the declaration reaches it too, and which of the two the
    # recipient ends up with is what `Z10` is reporting on the line above. Told
    # to "declare it or remove it", a sender would be declaring one path twice.
    collides = {n for n in container.duplicate_names
                if any(extracts_to(n) == extracts_to(a) for a in accounted_for)}
    for name in sorted(set(members.present) - accounted_for - structural - collides):
        if name.lower().endswith(".zip"):
            continue
        if _inside(folder_path(name), unopened):
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
