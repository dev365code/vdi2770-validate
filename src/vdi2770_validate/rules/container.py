"""Container-shape rules (Z). These are the ones that turn a reader's Defect
into something a person can act on."""
from __future__ import annotations

from typing import Iterator

from ..catalog import rule
from ..model import MAIN_PDF, METADATA_XML, Finding, Kind
from ..names import as_written, escaped, extracts_to, folder_path, ignoring_case, nfc


def _partners(group, index):
    """The members `group[index]` collides with, bounded, starting after it.

    Sliced out of a list sorted once, not filtered and sorted per member: doing
    the latter left the cost inside a single group after the cost across many
    groups had been removed -- 0.57, 0.73, 2.27 and 7.08 seconds for one group
    of 256, 512, 1,024 and 2,048, from a 296 KiB archive.

    Rotating rather than always naming the first few is what keeps every member
    on the page. `MAX_LISTED_PER_RULE` keeps a hundred findings and this names
    five partners in each, and with both caps a group of a hundred and ten left
    ten members appearing neither as a subject nor in anybody's list: counted,
    and never said what they were called.
    """
    # Spread across the group, not the next few. `MAX_LISTED_PER_RULE` keeps a
    # hundred findings, so with a stride of one a group of a hundred and ten
    # still left its last five members named by nobody. A stride of
    # `len // MAX_ALIKE` walks the whole group from every starting point.
    stride = max(1, len(group) // MAX_ALIKE)
    return [group[(index + 1 + step * stride) % len(group)]
            for step in range(min(MAX_ALIKE, len(group) - 1))]


def _named(alike, spell, total) -> str:
    """The partners a finding names, in the voice `Z9` and `Z13` use."""
    return (", ".join(spell(n) for n in alike)
            + (", ..." if total - 1 > len(alike) else ""))


def folders_holding_metadata(container) -> list:
    """Folders that hold a reserved metadata name — a document container that was
    not zipped.

    The reader opens `.zip` members and nothing else, so nothing inside one of
    these was checked. Two rules used to speak about them anyway: `Z8` said the
    documentation container held no document containers, and `F2` called their
    files undeclared — both false, because the metadata that declares them is
    the file this tool did not open.
    """
    out = []
    for name in container.present:
        # Not a member whose *name* does not denote a place in this archive.
        # `../VDI2770_Metadata.xml` drew `Z4` calling it a path-traversal
        # attempt and, beside it, this rule counting it as a folder holding a
        # document, with a remedy opening "Nothing here is necessarily wrong
        # with the container".
        #
        # Refused for any other reason is a different thing, and skipping those
        # too undid the repair one door along: a folder whose own metadata has a
        # bad CRC is a document container that was not zipped, delivered, and
        # unopened -- the strongest case there is for this rule. Passing over it
        # left `F2` calling that folder's files undeclared, from a metadata file
        # the report says on the line above it could not read, and `Z8` telling
        # the sender to add the document containers it was looking at.
        refusal = container.rejected.get(name)
        if refusal is not None and refusal.kind == "unsafe-member-name":
            continue
        prefix, sep, leaf = nfc(name).rpartition("/")
        if not sep or leaf != METADATA_XML:
            continue
        # `./VDI2770_Metadata.xml` *is* at the root. Some writers spell it that
        # way and the file has not gone anywhere, so reporting it as delivered in
        # a folder said this tool had not looked inside something it had read.
        # `Z9` skips a `.` segment for the same reason, two rules below, and the
        # reader grew a `path-prefixed` near-miss kind for it; this was the third
        # place and it was missed.
        #
        # The decision drops `.` segments; the value returned keeps the archive's
        # spelling. `files.py` matches this against the archive's own member
        # names to suppress `F2` inside a folder we did not open, and normalising
        # the prefix made that match nothing — so the files in a folder the same
        # report calls unopened were accused of being undeclared. It is also what
        # a user has to find in their ZIP listing.
        if not folder_path(prefix + "/"):
            continue
        out.append(prefix + "/")
    return sorted(set(out))


MAX_FOLDER_DEPTH = 32     # levels derived from one member's path
MAX_FOLDERS = 256         # distinct folders named in one container

DEFECT_TO_RULE = {
    "not-a-zip": "Z1",
    "too-many-members": "Z5",
    "member-too-large": "Z5",
    "suspicious-compression": "Z5",
    "archive-too-large": "Z5",
    "unsafe-member-name": "Z4",
    "nesting-too-deep": "Z6",
    # Z12, not Z3: we know what kind of container this is -- the name is in the
    # archive's directory, which is what classifies it. What we do not have is
    # the bytes behind that name, and that is exactly what Z12 says.
    "metadata-unreadable": "Z12",
    "metadata-too-large": "Z5",
    "container-budget-exhausted": "Z5",
    "decompression-budget-exhausted": "Z5",
    "member-budget-exhausted": "Z5",
    "member-unreadable": "Z12",
    # A name is how a member is asked for. An entry with none cannot be
    # extracted by anything, which is what Z12 already says.
    "nameless-member": "Z12",
    # Z10, which already says exactly this: two members of the archive have the
    # same name. No new rule -- the reader learned to refuse both entries rather
    # than silently reading the last one, and the rule for that was already here.
    "ambiguous-name": "Z10",
}


# One rule, seven ways to reach it. Z5's own remedy has to fit them all and ends
# up fitting none: "split the delivery into several containers" does nothing for
# a single member that expands past the ratio floor, and the project's own tests
# say so. A Finding may carry its own remedy, so each kind carries the one that
# names what to do about *it*.
def _remedy_for(defect):
    """The remedy for a refusal, by what the refusal actually says.

    `member-unreadable` covers a truncated transfer and a member the sender
    locked, and the catalogue sentence -- *re-create the archive and send it
    again* -- is the one remedy that cannot work for the second: re-zipping the
    same directory produces the same member and the same finding. `F1` learned
    this and `Z12` did not, so one password-protected member drew two findings
    with two remedies, one of them a loop.
    """
    if (defect.kind == "member-unreadable"
            and "encrypted" in (defect.detail or "").lower()):
        return ("Remove the password from this member before handing the "
                "container over. A recipient who cannot open a file has not been "
                "given it, and nothing here can check what it cannot read.")
    return REMEDY_FOR_DEFECT.get(defect.kind)


# What the reader saw that nearly matched a reserved name. `Z3` has read these
# since they existed; `Z7` did not, and told a supplier to add `VDI2770_Main.pdf`
# to an archive holding `vdi2770_main.pdf` -- which on their own machine is not
# an action they can take, because the file already answers to that name.
# How many of a collision's partners one finding names. The count it reports is
# exact; this cuts the list, the way `Z9` and `Z13` already cut theirs. Naming
# every partner in every finding is quadratic in the group, and a group is one
# name spelled many ways with `MAX_MEMBERS` the only bound on how many: measured
# at 0.07, 0.28 and 1.00 seconds for 32, 64 and 128 members of one group, which
# at the permitted extreme is over an hour from about a megabyte.
# `MAX_LISTED_PER_RULE` caps how many findings are printed and does not stop each
# one being built.
MAX_ALIKE = 5

NEAR_MISS = {
    "in-a-subfolder": "{wanted} found at {found!r} — it must sit at the root of the archive",
    "path-prefixed": "{wanted} found at {found!r} — it is at the root, but the "
                     "name carries a path in front of it and readers match the "
                     "name exactly",
    "case-differs": "{wanted} found as {found!r} — the name is case-sensitive",
}

REMEDY_FOR_DEFECT = {
    "ambiguous-name":
        "Rebuild the archive with one entry per name. Two entries share this one, "
        "so nothing here can say which bytes you meant and neither was read — a "
        "reader that guessed would show you one file and your unpacker another.",
    "member-budget-exhausted":
        "Split the delivery. This tool holds a record for every file named across "
        "the whole tree of containers, and this one names more than it will hold.",
    "too-many-members":
        "Split the delivery: this archive lists more members than this tool will open "
        "in one container.",
    "member-too-large":
        "That one member is larger than this tool will read. Send it on its own, or "
        "check it with something that has no such limit — the rest of the container "
        "was read normally.",
    "suspicious-compression":
        "That member expands far more than its stored size suggests, which is the shape "
        "of an archive built to exhaust whoever opens it. If it is a genuine "
        "uncompressed scan, send it separately: this tool will not inflate it.",
    "archive-too-large":
        "Split the delivery into several containers. This one holds more than this tool "
        "will read in a single archive.",
    "metadata-too-large":
        "The metadata file is larger than this tool will parse. Split the documents "
        "across several containers so each one's metadata is smaller.",
    "container-budget-exhausted":
        "Split the delivery, or run this tool on the inner containers separately. It "
        "opens a bounded number of containers in one pass, and the ones named here were "
        "not opened at all.",
    "decompression-budget-exhausted":
        "Split the delivery, or run this tool on the inner containers separately. Past "
        "its inflation ceiling the remaining members are still listed, but nothing has "
        "checked that they can be read.",
}


def check(container, declared, is_declared_payload) -> Iterator[Finding]:
    """`declared` is what this container's own metadata names as files.
    `is_declared_payload` says the parent's metadata names *this* archive as a
    file -- a parts list, a CAD bundle -- rather than expecting a container."""
    for d in container.defects:
        rid = DEFECT_TO_RULE.get(d.kind)
        if rid is None:
            continue
        # The reader stops descending at its depth limit before anything has
        # read a word of metadata, so it cannot know that the archive it
        # declined to open is a *file* this container declared -- a parts
        # bundle, a CAD archive. Reported as `Z6` it says a container is nested
        # too deep, names a member that never claimed to be a container, and
        # asks the sender to check an inner container that does not exist. The
        # same argument that excuses `Z3` and `Z11` excuses this.
        if (rid == "Z6" and declared is not None and d.where.member
                and folder_path(d.where.member) in declared):
            continue
        r = rule(rid)
        yield Finding(r, r.title, d.where,
                      detail=f"{d.kind}: {d.detail}" if d.detail else d.kind,
                      fix=_remedy_for(d))

    if container.kind is Kind.UNREADABLE:
        return

    # "Empty" has to mean empty. `members` is the survivors list -- the reader
    # drops anything that blew a budget or carried an unsafe name -- so an archive
    # whose only member we refused would otherwise be reported as having nothing
    # in it, with a remedy telling the user to add files they already sent.
    # A `.zip` the parent declared as a `DigitalFile` is one of the document's
    # *files*. What is inside it is its own business, the way a PDF's is, so the
    # rules that judge how a *container* arranges itself have nothing to say
    # about it. `Z3` and `Z11` already knew that and `Z2` and `Z9` did not: a
    # conforming delivery carrying a parts bundle was told to store the bundle's
    # members at the root, which flattens it, and an empty payload was reported
    # as an empty container. One decision, made at one place, read by all four.
    #
    # `False` is the one value that does *not* make it opaque: it means the
    # parent modelled its metadata and did not declare this archive, which is
    # the undeclared inner container `Z3` exists to report. `True` is a declared
    # payload and `None` is a parent nobody could model -- neither is something
    # to judge the shape of.
    opaque = container.kind is Kind.UNKNOWN and is_declared_payload is not False

    # `defects` too, and this is the door the guard above was not watching:
    # `nameless-member` is the one refusal recorded as a bare defect and never in
    # `rejected`, so an archive whose only entry had no name was called empty
    # beside a `Z12` saying there was an entry in it, with a remedy telling the
    # sender to add the files they had sent.
    nameless = any(d.kind == "nameless-member" for d in container.defects)
    if (not container.members and not container.rejected
            and not nameless and not opaque):
        r = rule("Z2")
        yield Finding(r, r.title, container.where)
        return

    # A `.zip` the parent declared as a DigitalFile never claimed to be a
    # container, and F3's own remedy blesses application/zip with .zip. The
    # reader opens every .zip because it has no metadata to know better; here we
    # do. If it turns out to be a real container it is still validated as one.
    # `is_declared_payload is None` means the parent's metadata was never
    # modelled, so nobody can say whether it declared this archive. Unknown
    # suppresses the rule; False does not.
    # And not when the parent is a document container, because `Z11` reports
    # that member from the other side and this said the opposite thing about it:
    # *move it up into the documentation container* against *put a
    # VDI2770_Metadata.xml at its root*. Follow either and the other still fires.
    # `Z11`'s remedy now carries the answer this tool actually accepts -- declare
    # it as an `application/zip` payload -- and one member gets one finding.
    covered_by_z11 = container.parent is not None and container.parent.kind is Kind.DOCUMENT
    if (container.kind is Kind.UNKNOWN and is_declared_payload is False
            and not covered_by_z11):
        r = rule("Z3")
        # The reader records what nearly matched; the sentence is ours to write,
        # because "it must sit at the root" is a claim about VDI 2770.
        detail = "; ".join(
            NEAR_MISS[kind].format(wanted=wanted, found=found)
            # (Removing this `sorted` is an equivalent mutant: `near_misses` is
            # filled by a loop over a fixed tuple of three names, so the dict's
            # insertion order is already fixed. Kept because the reader is free
            # to fill it some other way, and this is not where that should
            # become a report that differs between runs.)
            for wanted, (kind, found) in sorted(container.near_misses.items())
            if kind in NEAR_MISS) or None
        yield Finding(r, r.title, container.where, detail=detail)

    # A directory entry is optional in the ZIP format, so testing for one made
    # this rule fire or not depending on which library wrote the archive rather
    # than on the archive's shape. A folder exists if a member sits in one.
    folders = set()
    for m in container.members if not opaque else ():
        if len(folders) >= MAX_FOLDERS:
            break
        if m.is_dir:
            # `./` is a directory entry that names the root, and many writers put
            # one at the front of an archive. Added verbatim it produced
            # "1 folder: ./" with a remedy the archive already obeys. The path
            # branch below drops `.` segments; this one is the same miss, one
            # line apart.
            segments = [seg for seg in nfc(m.name).split("/") if seg not in ("", ".")]
            if segments:
                folders.add("/".join(segments) + "/")
        # Every folder on the path, not just the last one: `a/b/x.pdf` puts the
        # file in `a/b/` and also in `a/`, and a rule that reports one of them
        # calls a two-level layout "1 folder".
        #
        # Built by growing one string, and bounded twice. Re-joining the prefix
        # from scratch at each depth is quadratic in the name's length, and a ZIP
        # filename field is sixteen bits: one member named `p0/` thirty-two
        # thousand times cost 1.2 GB. Neither cap changes what a real archive
        # reports -- a hundred distinct folders is already a strange delivery, and
        # the finding names five of them.
        prefix = ""
        for part in m.name.rstrip("/").split("/")[:-1][:MAX_FOLDER_DEPTH]:
            # `./name` is at the root. Some writers emit the prefix and it is not
            # a folder, so counting it invented one and told the sender to move a
            # file that had not gone anywhere.
            if part in (".", ""):
                continue
            prefix += part + "/"
            folders.add(prefix)
            if len(folders) >= MAX_FOLDERS:
                break
        if len(folders) >= MAX_FOLDERS:
            break
    # And nothing to say about folders in an archive that holds no files. A
    # directory entry is a folder somebody made, which is why one on its own is
    # still collected above -- but an archive whose *only* entry was `a/` was
    # told it "stores files in folders", naming one with no file in it, in a
    # report saying two lines up that the archive is not a container at all.
    if folders and container.file_names:
        r = rule("Z9")
        named = sorted(folders)
        # "at least" when the collection stopped: the list is truncated with an
        # ellipsis and the count was printed flat, so an archive with three
        # hundred folders was reported as having 256. `report.py` makes the same
        # argument about the listing cap.
        capped = len(named) >= MAX_FOLDERS
        yield Finding(r, r.title, container.where,
                      detail=f"{'at least ' if capped else ''}{len(named)} "
                             f"folder{'' if len(named) == 1 else 's'}: "
                             + ", ".join(named[:5])
                             + (", ..." if len(named) > 5 else ""))

    if container.duplicate_names:
        r = rule("Z10")
        # The groups, built once. This used to filter `duplicate_names` inside a
        # loop over `duplicate_names`, normalising both sides at every step, so
        # the cost was collisions times collisions with `MAX_MEMBERS` the only
        # bound: 0.51, 0.92, 3.31 and 12.86 seconds for 200, 400, 800 and 1,600
        # pairs, a clean 4x per doubling, from a 316 KiB archive. Past every
        # budget the reader has, because not one of them measures this. The third
        # time this shape has been found here.
        joined, place, relation = {}, {}, {}
        for member in sorted(container.duplicate_names):
            group = joined.setdefault(folder_path(member), [])
            # Where each member sits in its group, recorded as the groups are
            # built. `group.index(member)` is a walk of the group per member,
            # which is the same quadratic one level down: 0.71, 1.95, 6.53 and
            # 23.53 seconds for one group of 512, 1,024, 2,048 and 4,000.
            place[member] = len(group)
            group.append(member)
        for key, group in joined.items():
            relation[key] = (len({extracts_to(n) for n in group}) == 1,
                             len({nfc(n) for n in group}) == 1)
        for name in container.duplicate_names:
            # The reader refuses a repeated name outright now and says so with a
            # reason and a remedy; the loop at the top of this function already
            # turned that into Z10. Two findings for one name is the noise the
            # test above this rule was written to prevent.
            #
            # Not all of these are repeats: `duplicate_names` also catches two
            # *different* spellings that normalise to one name, and nothing
            # refuses those -- they are two real entries.
            refused = container.rejected.get(name)
            if refused is not None and refused.kind == "ambiguous-name":
                continue
            # The title is true of a repeated name and false of this one: these
            # are *different* names that print alike, which is the only reason
            # the pair is worth reporting. Said with the rule's own title, no
            # detail and no remedy, the reader got the same line twice with
            # nothing on it to tell the two members apart, and no hint that the
            # difference is in the encoding rather than in the letters.
            # `folder_path`, which is the key `duplicate_names` was built on in
            # the reader. Filtering by `nfc` alone was a narrower relation than
            # the grouping, so `B.pdf` beside `./B.pdf` found nothing here and
            # fell to the branch below -- the rule's bare title, no detail, no
            # remedy, twice, about two members the report never named. The branch
            # that says both was reached through a door it was not watching.
            group = joined[folder_path(name)]
            alike = _partners(group, place[name])
            if not alike:
                # A name in `duplicate_names` has a partner there: the reader
                # appends both spellings when a key collides. The one case that
                # leaves it alone is two entries carrying the *same* string, and
                # the `continue` above takes those. So this is the fallback for a
                # repeat that reached here unrefused, and the reader's own
                # sentence covers it. Nothing the reader produces today gets
                # here, which is worth knowing rather than worth deleting.
                yield Finding(r, r.title,
                              container.where.child(member=name, subject=name))
                continue
            group = tuple(joined[folder_path(name)])
            # Three relations reach this loop and only one sentence used to be
            # said about them. `duplicate_names` is grouped on `folder_path`,
            # which is `nfc` *and* dropping segments that name nothing -- so the
            # group can hold names that print alike, names that land on one path,
            # or names that do both at once, and each of those is a different
            # thing to tell a sender. Saying "extract to the same path" over the
            # whole group asserted it of `./Ä.pdf` written decomposed beside
            # `Ä.pdf` written composed, which land on two paths, in a report
            # whose `F2` on the next line correctly treats them as two files.
            # `extracts_to` is the relation for one path; `nfc` for one glyph.
            # Per group, not per member: these walk the whole group and were
            # recomputed for every member of it, which is the same quadratic the
            # partner list had. 0.90, 1.98, 6.74 and 22.02 seconds for one group
            # of 512, 1,024, 2,048 and 4,000, from a 575 KiB archive.
            one_path, one_name = relation[folder_path(name)]
            if one_path:
                # Spelled the archive's way: the difference here is `.` segments,
                # which are visible ASCII, and spelling out the rest turned two
                # ordinary decomposed filenames into four walls of hex.
                shown = _named(alike, as_written, len(group))
                yield Finding(
                    r,
                    "Two members of the archive extract to the same path",
                    container.where.child(member=name, subject=name),
                    detail=f"this is {as_written(name)}; the archive also holds "
                           f"{shown} — different names for one path, "
                           f"{as_written(extracts_to(name))}",
                    fix="Store the file once, at one path. Which of them a "
                        "recipient ends up with is their unzip tool's business, "
                        "and nothing here can say which one you meant.")
                continue

            shown = _named(alike, escaped, len(group))
            if not one_name:
                yield Finding(
                    r,
                    "Two members of the archive come to one name",
                    container.where.child(member=name, subject=name),
                    detail=f"this is {escaped(name)}; the archive also holds "
                           f"{shown} — these differ both in how the letters are "
                           f"spelled and in path segments that name nothing, so "
                           f"a filesystem that normalises names sees one file "
                           f"where this archive has {len(group)}",
                    fix="Store the file once, under one spelling and one path. "
                        "On a filesystem that composes names — macOS, Windows — "
                        "these are one file and the later member wins; on one "
                        "that does not, they are two. Nothing here can say which "
                        "your recipient has.")
                continue
            # "different bytes, the same glyphs" was true of the archive and
            # became false of the page: once `escaped` spells out the spelling
            # that is not canonical, the two lines a reader sees no longer show
            # the same glyphs, and a reader who takes the sentence literally
            # concludes the tool contradicted itself. It also never said what the
            # file is called -- and when neither spelling is the canonical one,
            # both lines are code points and nothing readable ties them to
            # anything. The canonical form is that anchor.
            yield Finding(
                r,
                "Two members of the archive have names that print alike",
                container.where.child(member=name, subject=name),
                detail=f"this is {escaped(name)}; the archive also holds {shown} — "
                       f"one name, {escaped(nfc(name))} in a listing, stored "
                       f"{len(group)} ways. A spelling that is not the "
                       f"canonical one is printed here as code points, because "
                       f"otherwise these lines would be identical",
                fix="Store one spelling. A reader asking for the name as you "
                    "wrote it may get either member, and nothing here can say "
                    "which one you meant.")

    # And the collision the reader does not group on, because it is not a fact
    # about the archive: `B.pdf` beside `b.pdf` is two entries here and one file
    # on macOS as it ships and on every Windows filesystem. The recipient keeps
    # whichever their unzip tool wrote last, and the other declaration names a
    # path they do not have. The tool said `F2` about the second member -- a
    # warning -- so a sender who followed `F2`'s remedy and declared both got a
    # report with nothing wrong in it, for a delivery that loses a file.
    #
    # `Z10`'s id, not a new one: the rule is already a family of sentences about
    # two members a recipient may receive as one, and its `whyOurs` -- "readers
    # disagree about which one wins, so the container can show one thing to this
    # tool and another to whoever unpacks it" -- is this case in as many words.
    # The reader's own key is left alone. Widening it would say something about
    # somebody else's filesystem in a layer whose job is facts about an archive,
    # and its `duplicate_names` drives the refusal of a repeated name, which is
    # about `zf.open` not knowing which entry is meant -- and `zf.open("b.pdf")`
    # knows perfectly well.
    folded = {}
    for member in container.present:
        folded.setdefault(ignoring_case(member), []).append(member)
    for _key, together in sorted(folded.items()):
        # One member per group `Z10` has already joined above, so a pair that
        # differs in case *and* in path gets one finding rather than two.
        distinct = sorted({folder_path(n): n for n in together}.values())
        if len(distinct) < 2:
            continue
        r = rule("Z10")
        for index, name in enumerate(distinct):
            alike = _partners(distinct, index)
            yield Finding(
                r,
                "Two members of the archive are one file where case is not kept apart",
                container.where.child(member=name, subject=name),
                detail=f"this is {as_written(name)}; the archive also holds "
                       f"{_named(alike, as_written, len(distinct))} — {len(distinct)} entries "
                       f"that fold to one name, so a recipient on Windows, or on "
                       f"macOS as it ships, unpacks them into one file and keeps "
                       f"whichever their unzip tool wrote last",
                fix="Rebuild the archive with one entry per name once case is "
                    "folded, and name each DigitalFile after the entry you kept. "
                    "Rename as you write the archive rather than on disk: a "
                    "filesystem that folds case cannot hold both of these side "
                    "by side, so there is nothing there to rename.")

    if container.kind is Kind.DOCUMENT:
        for m in container.members:
            # Z11 exists because an undeclared container is "a way to carry
            # something past a check that only looks at declared files". A
            # declared one is not past that check, so its own argument excuses it.
            if declared is None:
                continue        # we did not model this container's own metadata
            if (m.name.lower().endswith(".zip")
                    and folder_path(m.name) not in declared):
                r = rule("Z11")
                yield Finding(r, r.title, container.where.child(member=m.name, subject=m.name))

    # Whatever kind of container this is. `files.py` keeps `F2` quiet about every
    # file inside a folder that holds its own metadata, in any container, because
    # what declares those files is a metadata file this tool never opened. That
    # silence is only honest while something says we did not look -- and this
    # said it for documentation containers alone. Put such a folder inside a
    # *document* container and its files left the report with nothing said about
    # them, which is the outcome the suppression exists to prevent. The reason
    # this rule gives has never had anything to do with the parent's kind.
    # `not opaque`, like the folder walk above. Lifting this out of the
    # documentation branch took it past the guard as well: the decision that
    # keeps `Z2`, `Z3` and `Z9` quiet about a declared `application/zip` member
    # says what it is for -- what is inside it is its own business, the way a
    # PDF's is -- and a conforming document container carrying a declared CAD
    # bundle became exit 1, with a remedy asking its supplier to restructure the
    # inside of something that is not a VDI 2770 artefact.
    as_folders = [] if opaque else folders_holding_metadata(container)
    if as_folders:
        r = rule("Z13")
        # Named the way `Z9` names it. The two rules were spelling one folder two
        # ways in the same report -- `AB393/` and `./AB393/` -- and a reader then
        # has to work out that the tool is not talking about two places. The list
        # itself keeps the archive's prefix, because `files.py` matches it against
        # member names to suppress `F2`; it is the sentence that is rendered.
        named = [folder_path(f) + "/" for f in as_folders[:5]]
        yield Finding(r, r.title, container.where,
                      detail=f"{len(as_folders)} folder"
                             f"{'' if len(as_folders) == 1 else 's'} "
                             f"{'holds' if len(as_folders) == 1 else 'hold'} "
                             f"{METADATA_XML}: " + ", ".join(named)
                             + (", ..." if len(as_folders) > 5 else ""))

    if container.kind is Kind.DOCUMENTATION:
        # `present`, not `file_names`. A main document with a bad CRC is in the
        # archive; Z12 says we could not read it. Telling the sender to add a
        # file they already sent is the report contradicting itself.
        # `folder_path`, not the raw string. `./VDI2770_Main.pdf` is at the
        # root -- the reader records a `path-prefixed` near-miss saying so, and
        # `Members`, `Z9`, `Z3` and `Z13` all read it that way. Comparing the
        # spelling told a sender to add a file the same report was reading the
        # PDF/A claim out of, one line further down.
        if not any(folder_path(n) == MAIN_PDF for n in container.present):
            r = rule("Z7")
            near = container.near_misses.get(MAIN_PDF)
            yield Finding(r, r.title, container.where,
                          detail=(NEAR_MISS[near[0]].format(wanted=MAIN_PDF, found=near[1])
                                  if near and near[0] in NEAR_MISS else None))
        # A refusal to look is not an absence. The reader stops descending at
        # MAX_CONTAINER_LEVELS and at the tree's container budget, and it drops a
        # `.zip` member it could not decompress -- in each case `children` is
        # short for reasons that have nothing to do with what the sender packed.
        # Z6 and Z12 already say what happened.
        # Ask the reader what it dropped rather than listing the reasons: an
        # earlier version named three defect kinds and missed the three
        # rejections -- unsafe name, oversized member, suspicious ratio -- that
        # remove a `.zip` before the descent loop ever sees it. `rejected` holds
        # every member the reader refused, whatever the reason, including ones
        # added after this was written.
        stopped = (
            any(d.kind in ("nesting-too-deep", "container-budget-exhausted")
                for d in container.defects)
            or any(name.lower().endswith(".zip") for name in container.rejected)
            # A child we opened but could not read might have been a document
            # container. Z12 says we could not read it; saying there are none
            # would be a second, different, and false claim.
            or any(k.kind is Kind.UNREADABLE for k in container.children))
        # `children` is every archive we descended into, which is not the same
        # set as the document containers this rule is about: a declared `.zip`
        # payload is a child too, and one of those used to silence the rule
        # entirely. Count what the title says we are counting.
        # (`stopped` above already covers the unreadable child, so whether this
        # list admits one cannot change the answer. Both are kept: one says what
        # we count, the other says when we decline to answer.)
        delivered = [k for k in container.children
                     if k.kind in (Kind.DOCUMENT, Kind.DOCUMENTATION)]
        if not delivered and not stopped and not as_folders:
            r = rule("Z8")
            yield Finding(r, r.title, container.where)
