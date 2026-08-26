"""Container-shape rules (Z). These are the ones that turn a reader's Defect
into something a person can act on."""
from __future__ import annotations

from typing import Iterator

from ..catalog import rule
from ..model import MAIN_PDF, METADATA_XML, Finding, Kind
from ..names import folder_path, nfc


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
        r = rule(rid)
        yield Finding(r, r.title, d.where,
                      detail=f"{d.kind}: {d.detail}" if d.detail else d.kind,
                      fix=REMEDY_FOR_DEFECT.get(d.kind))

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

    if not container.members and not container.rejected and not opaque:
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
    if container.kind is Kind.UNKNOWN and is_declared_payload is False:
        r = rule("Z3")
        # The reader records what nearly matched; the sentence is ours to write,
        # because "it must sit at the root" is a claim about VDI 2770.
        said = {
            "in-a-subfolder": "{wanted} found at {found!r} — it must sit at the root of the archive",
            "path-prefixed": "{wanted} found at {found!r} — it is at the root, but the "
                             "name carries a path in front of it and readers match the "
                             "name exactly",
            "case-differs": "{wanted} found as {found!r} — the name is case-sensitive",
        }
        detail = "; ".join(
            said[kind].format(wanted=wanted, found=found)
            # (Removing this `sorted` is an equivalent mutant: `near_misses` is
            # filled by a loop over a fixed tuple of three names, so the dict's
            # insertion order is already fixed. Kept because the reader is free
            # to fill it some other way, and this is not where that should
            # become a report that differs between runs.)
            for wanted, (kind, found) in sorted(container.near_misses.items())
            if kind in said) or None
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
    if folders:
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
            yield Finding(r, r.title, container.where.child(member=name, subject=name))

    if container.kind is Kind.DOCUMENT:
        for m in container.members:
            # Z11 exists because an undeclared container is "a way to carry
            # something past a check that only looks at declared files". A
            # declared one is not past that check, so its own argument excuses it.
            if declared is None:
                continue        # we did not model this container's own metadata
            if m.name.lower().endswith(".zip") and nfc(m.name) not in declared:
                r = rule("Z11")
                yield Finding(r, r.title, container.where.child(member=m.name, subject=m.name))

    if container.kind is Kind.DOCUMENTATION:
        # `present`, not `file_names`. A main document with a bad CRC is in the
        # archive; Z12 says we could not read it. Telling the sender to add a
        # file they already sent is the report contradicting itself.
        if MAIN_PDF not in container.present:
            r = rule("Z7")
            yield Finding(r, r.title, container.where)
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
        as_folders = folders_holding_metadata(container)
        if as_folders:
            r = rule("Z13")
            # Named the way `Z9` names it. The two rules were spelling one
            # folder two ways in the same report -- `AB393/` and `./AB393/` --
            # and a reader then has to work out that the tool is not talking
            # about two places. The list itself keeps the archive's prefix,
            # because `files.py` matches it against member names to suppress
            # `F2`; it is the sentence that is rendered.
            named = [folder_path(f) + "/" for f in as_folders[:5]]
            yield Finding(r, r.title, container.where,
                          detail=f"{len(as_folders)} folder"
                                 f"{'' if len(as_folders) == 1 else 's'} "
                                 f"{'holds' if len(as_folders) == 1 else 'hold'} "
                                 f"{METADATA_XML}: " + ", ".join(named)
                                 + (", ..." if len(as_folders) > 5 else ""))

        # (`stopped` above already covers the unreadable child, so whether this
        # list admits one cannot change the answer. Both are kept: one says what
        # we count, the other says when we decline to answer.)
        delivered = [k for k in container.children
                     if k.kind in (Kind.DOCUMENT, Kind.DOCUMENTATION)]
        if not delivered and not stopped and not as_folders:
            r = rule("Z8")
            yield Finding(r, r.title, container.where)
