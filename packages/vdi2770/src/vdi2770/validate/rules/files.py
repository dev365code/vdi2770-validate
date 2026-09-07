"""File-set rules (F): does the metadata agree with what is actually in the ZIP?"""
from __future__ import annotations

from typing import Iterator

from ..catalog import rule
from ..model import MAIN_PDF, MAIN_XML, METADATA_XML, About, Finding, Kind
from ..names import Members, as_written, escaped, extracts_to, folder_path, nfc, without_edge_space
from .container import MAX_ALIKE, _inside

EXTENSION_FOR = {"application/pdf": ".pdf", "application/zip": ".zip"}


#: Refusals that are this tool's limit rather than a fault in the delivery.
#: The rest — an unsafe name, bytes that will not decompress — really are the
#: sender's, and the remedy differs accordingly.
BUDGET_REFUSALS = frozenset({
    "member-too-large", "suspicious-compression", "metadata-too-large",
    "archive-too-large", "container-budget-exhausted",
    "decompression-budget-exhausted", "member-budget-exhausted",
})


def _named_members(names) -> str:
    """Members as the archive spells them, with what draws nothing spelled out.

    Bounded like every other list a finding carries: nine thousand edge-space
    members put a 270,135-character line into one detail.
    """
    return (", ".join(f"'{escaped(n)}'" for n in names[:MAX_ALIKE])
            + (", ..." if len(names) > MAX_ALIKE else ""))


def check(container, document, foreign) -> Iterator[Finding]:
    """`foreign` is the namespace the metadata's names are in, when not ours.

    These rules read `document.all_files`, and a document whose names are in
    another vocabulary has none -- so every file in the container became "not
    named in the metadata", which is a flood of true sentences pointing at the
    wrong thing. `M1` says the one thing that is wrong; nothing here can add to it
    until the names are ours.
    """
    if foreign is not None:
        return

    # Names are reconciled in one place, for every comparison in this module and
    # the PDF one. See names.py for the two ways of getting this wrong that are
    # already behind it.
    members = Members(container.file_names, container.rejected)
    accounted_for = set()
    reached_ambiguously = set()
    # Built once: the missing-declaration branch asked, per declaration, whether
    # any member's name explains the miss because its edge whitespace cannot be
    # declared -- a scan of every member through `without_edge_space`, once per
    # missing declaration. Only names whose stripped form differs can explain
    # anything, and there are few of those in any honest archive.
    unreachable_as = {}
    for candidate in members.present:
        stripped = without_edge_space(candidate)
        if stripped != candidate:
            unreachable_as.setdefault(stripped, []).append(candidate)

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
            # Two different collisions arrive here and only one of them is about
            # spelling. `spelled_more_than_one_way` groups by `folder_path`,
            # which is `nfc` *and* dropping segments that name nothing — so
            # `.//B.pdf` and `./B.pdf` are one group, and the finding told a
            # reader they "print alike" about two names anybody can tell apart at
            # a glance, with a remedy about "different bytes that print the
            # same". Whether they print alike is a question with an answer:
            # canonically equivalent names do, and names that differ in a `.`
            # segment do not.
            look_alike = len({nfc(n) for n in spellings}) == 1
            if spellings and not twice:
                # Recorded here rather than above, because this is the branch
                # that lists them: in the `twice` case nothing names the
                # spellings, and keeping `F2` quiet about members no finding has
                # mentioned is silence, not a second opinion.
                reached_ambiguously.update(spellings)
                message = ("A file named in the metadata matches more than one "
                           "member of the container")
                fix = ("Store one spelling. The names below are different bytes "
                       "that print the same, so nothing can say which of them "
                       "this declaration meant — and a reader asking for the "
                       "name you wrote may get either.") if look_alike else (
                    "Store the file once, at one path. The names below are "
                    "different bytes that extract to the same place, so nothing "
                    "can say which of them this declaration meant — and which "
                    "one a recipient ends up with is their unzip tool's business.")
                whose = None
            elif twice:
                message = ("A file named in the metadata is in the container more "
                           "than once")
                fix = ("Remove the repeats. The name denotes more than one member, "
                       "and which one a reader extracts is its own business — so "
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
            elif because.kind == "unsafe-member-name":
                # The name, not the bytes. This fell into the generic branch and
                # came back as *could not be read* over a remedy saying "the
                # metadata is right" -- which `Z4`, two lines away, contradicts:
                # the metadata is what names `../evil.pdf`. And "send it again"
                # is the loop already removed for a locked member and a repeated
                # name; re-zipping the same tree produces the same name.
                message = ("A file named in the metadata has a name that would "
                           "escape the extraction directory")
                fix = ("Rename the member and the DigitalFile that names it, to "
                       "a plain relative path inside the container. This tool "
                       "never read those bytes: the name is what it refused, and "
                       "the finding beside this one says why. Re-creating the "
                       "archive from the same tree writes the same name.")
                whose = None
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
                # Bounded the way `Z10` bounds its partner list: rendering the
                # whole group put every spelling into every declaration's
                # detail, and the product ran to 69.71 seconds from a 290 KiB
                # archive. The count in the sentence stays exact.
                shown = (" and ".join(escaped(n) for n in spellings[:MAX_ALIKE])
                         + (", ..." if len(spellings) > MAX_ALIKE else ""))
                how = "print alike" if look_alike else "extract to the same path"
                detail = (f"{f.file_name!r} matches {len(spellings)} members "
                          f"that {how}: {shown}")
            elif twice:
                # The reader's sentence, which carries the true count. A count
                # taken from `container.present` could only ever be 1 here:
                # `present` is built over `rejected`, a dict keyed by name, so a
                # repeated name collapses to one entry -- and the finding said
                # *names 1 members* under a headline saying *more than once*,
                # beside a Z10 whose detail says four.
                detail = (f"{f.file_name!r}: {because.detail}" if because is not None
                          else f"{f.file_name!r} names more than one member of "
                               f"the archive")
            elif rejected:
                detail = f"{f.file_name!r} is in the archive but was refused: {rejected}"
            else:
                # A member no declaration can reach is a different thing from a
                # file nobody sent. The archive held `B.pdf ` and the metadata
                # declared `B.pdf `, and this said the file was not there while
                # `F2` said it was not named -- two findings about one file that
                # is both present and declared.
                unnameable = sorted(unreachable_as.get(f.file_name, ()))
                if unnameable:
                    message = ("A file named in the metadata is in the container "
                               "under a name no declaration can reach")
                    detail = (f"'{escaped(f.file_name)}' is declared; the archive "
                              f"holds {_named_members(unnameable)}, which no "
                              f"declaration can name — the metadata's text is "
                              f"read with the whitespace at its edge removed")
                    fix = ("Rename the member to the name you declared. Writing "
                           "the space into the metadata does not help: it is "
                           "read back without it, which is what lets an ordinary "
                           "indented declaration work at all.")
                else:
                    detail = f"{f.file_name!r} is declared but not in the archive"
            yield Finding(r, message, f.src.child(container=container.path,
                                                  member=container.metadata_name),
                          detail=detail, fix=fix, as_about=whose)

    # Reserved where it is reserved, and nowhere else. Exempting all three names
    # everywhere meant a stray VDI2770_Main.pdf inside a document container -- a
    # name that means nothing there -- was never reported as undeclared.
    reserved = ({MAIN_XML, MAIN_PDF} if container.kind is Kind.DOCUMENTATION
                else {METADATA_XML})
    # By what the name extracts to, so `./VDI2770_Main.pdf` is the reserved name
    # it is and not a file nobody declared. The set keeps the archive's own
    # spellings, because that is what the loop below subtracts from.
    structural = {n for n in members.present if folder_path(n) in reserved}
    # The archive's own spelling, not the canonical one: a name the user cannot
    # find in their ZIP listing is not a report they can act on.
    # A folder holding its own VDI2770_Metadata.xml is a document container that
    # was not zipped. Its files are declared in metadata this tool never opened,
    # so calling them undeclared is a statement about a file we did not read.
    # `Z13` says we did not read it.
    from .container import folders_holding_metadata
    unopened = frozenset(folder_path(f)
                         for f, _ in folders_holding_metadata(container)) - {""}
    # A member that shares its extracted path with one the metadata declared is
    # not undeclared -- the declaration reaches it too, and which of the two the
    # recipient ends up with is what `Z10` is reporting on the line above. Told
    # to "declare it or remove it", a sender would be declaring one path twice.
    # The declared paths, normalised once. This asked `any(extracts_to(n) ==
    # extracts_to(a) for a in accounted_for)` per colliding member, recomputing
    # the split-and-join on both sides at every pair: 0.82, 1.44 and 5.36 seconds
    # for 500, 1,000 and 2,000 declared files each also stored with a `./` in
    # front, from a 423 KiB archive.
    landed_on = {extracts_to(a) for a in accounted_for}
    collides = {n for n in container.duplicate_names if extracts_to(n) in landed_on}
    # And the members a declaration reached without resolving to one of them.
    # `F1` says that declaration matches these two; `F2` then said, of the same
    # two members on the next lines, that no declaration names them. One report,
    # one file, both claims — and the remedy it offered, *declare it or remove
    # it*, points away from the one `F1` had just given. Whichever spelling the
    # sender keeps, the declaration is already there.
    collides |= reached_ambiguously
    for name in sorted(set(members.present) - accounted_for - structural - collides):
        if name.lower().endswith(".zip"):
            continue
        if _inside(folder_path(name), unopened):
            continue
        r = rule("F2")
        # The other kind's classifying name at the root is not an undeclared
        # file. `VDI2770_Main.xml` beside `VDI2770_Metadata.xml` classifies as a
        # documentation container -- silently -- and the document metadata drew
        # this rule's bare title, whose remedy ("declare it") produced a fully
        # clean report for an archive whose kind depends on which name a reader
        # looks for first. `F2` still fires; the sentence says what the file is.
        if (container.kind is Kind.DOCUMENTATION
                and folder_path(name) == METADATA_XML):
            yield Finding(
                r, r.title, container.where.child(member=name, subject=name),
                detail=f"{as_written(name)} is the name that classifies a "
                       f"document container. This archive also holds "
                       f"{MAIN_XML}, so this tool read it as a documentation "
                       f"container — and a reader that looks for "
                       f"{METADATA_XML} first opens it as the other kind",
                fix="Remove or rename the classifying name you did not mean. "
                    "An archive that answers to both kinds is a different "
                    "delivery depending on who opens it, and declaring this "
                    "file would only make that silent.")
            continue
        # And "declare it" is not on offer for a member whose name carries a
        # space at its edge: the metadata's text is read with that removed, so
        # whatever the sender writes comes back without it. Half a remedy that
        # cannot be followed is worse than the half that can.
        yield Finding(r, r.title, container.where.child(member=name, subject=name),
                      fix=None if without_edge_space(name) == name else
                      ("Rename the member: whitespace at the edge of a name "
                       "cannot be declared, because the metadata's text is read "
                       "with it removed. Or remove the member from the "
                       "container."))

    for f in document.all_files:
        want = EXTENSION_FOR.get(f.file_format.split(";")[0].strip().lower())
        if want and f.file_name and not f.file_name.lower().endswith(want):
            r = rule("F3")
            yield Finding(r, r.title,
                          f.src.child(container=container.path, member=container.metadata_name),
                          detail=f"{f.file_name!r} is declared as {f.file_format!r}")
