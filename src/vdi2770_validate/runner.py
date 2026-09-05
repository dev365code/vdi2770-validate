"""Put the readers and the rules together.

The only module that *orchestrates* both sides. Two others touch the reader for
narrower reasons: `model.py` re-exports its vocabulary so the rules need not, and
`xsdvalidate.py` walks its node tree to put a line number on a schema
complaint. Nothing else in this package imports it, and a test enforces that for
the rules."""
from __future__ import annotations

import errno
import os
import stat
from typing import Optional

from vdi2770 import pdfread, xmlread, zipread
from vdi2770.domain import build
from vdi2770.zipread import Kind

from . import xsdvalidate
from .catalog import rule
from .model import MAIN_XML, METADATA_XML, NS, Finding, Location, Report
from .names import folder_path
from .rules import container as r_container
from .rules import files as r_files
from .rules import metadata as r_metadata
from .rules import pdf as r_pdf
from .rules import schema as r_schema
from .rules.container import _inside, folders_holding_metadata
from .rules.pdf import Stopped


def _into(report, findings, where, what: str) -> None:
    """Run one rule module's findings into the report, demoting a crash.

    One rule's exception must not kill the run. It killed
    the run — a batch died on one archive with a traceback naming this tool's
    internals, and every container after it went unchecked. A rule that crashed
    has checked nothing, so this is an error: reporting the rest and exiting 0
    would tell the reader that check passed.

    The findings it managed to produce before crashing are kept. They are as true
    as they were going to be.
    """
    try:
        for f in findings:
            report.add(f)
    except Exception as e:                       # noqa: BLE001 - that is the point
        r = rule("X5")
        report.add(Finding(r, r.title, where,
                           detail=f"the {what} checks: {type(e).__name__}: {e}"))


# The reader bounds one document; this bounds the sum of them.
#
# `xmlread.MAX_ELEMENTS` caps the tree built out of one metadata file. Nothing
# capped the tree of containers: a documentation container holding forty
# document containers, each with metadata just under that cap, is **12 KiB** on
# disk and cost **74 seconds** of CPU, measured. Every reader budget lets it
# through, because none of them is watching this axis -- the bytes are tiny, the
# members are few, nothing inflates, and the trees are built and dropped one at
# a time so memory stays flat.
#
# Sized against a real delivery rather than against the attack. The largest
# metadata file in this repository's corpus has 53 elements; nine hundred
# document containers of it -- a plant handover, and 1 MB of archive -- come to
# about 48,000. This is ten times that, and it bounds the element-driven cost at
# roughly eight seconds. The per-document cost that remains is real work
# proportional to real content, and `MAX_CONTAINERS` bounds that.
MAX_TOTAL_ELEMENTS = 500_000                 # parsed across one check_bytes()


def _count(node) -> int:
    """Elements in a parsed tree, iteratively -- the reader promises nothing
    about depth, so this must not recurse."""
    n, stack = 0, [node]
    while stack:
        n += 1
        stack.extend(stack.pop().children)
    return n


_CRASHED = object()          # "this step raised"; distinct from a step that returned None



def _step(report, where, what: str, fn, *args, fix: Optional[str] = None):
    """Run one step that feeds the rules, demoting a crash the same way.

    `_into` wraps the rules. These run before them — parsing the metadata,
    building the document, walking the schema errors — and a crash in any of
    them killed the run just as dead. The guard was written for the rules and
    stopped at their door.

    Returns `_CRASHED` so the caller can tell "it raised" from "it legitimately
    produced nothing", which are different situations and used to look alike.

    `fix` overrides X5's remedy for a step whose failure means something the
    catalogue's sentence does not cover — see the container read in
    `check_bytes`, after which there is no rest of the report to still stand.
    """
    try:
        return fn(*args)
    except Exception as e:                       # noqa: BLE001 - that is the point
        r = rule("X5")
        report.add(Finding(r, r.title, where, detail=f"the {what} step: {type(e).__name__}: {e}",
                           fix=fix))
        return _CRASHED


def _facts_for(raw: bytes, accepted, read_pdf):
    """A PDF fact cache for one container, over one parse of its directory.

    `member_bytes` opens the archive on every call, and this asks it for every
    declared PDF — so the cost was declared files times members, with no budget
    measuring it: the bytes are tiny, the members are under the cap and nothing
    inflates. 0.78, 1.29, 5.42 and 20.60 seconds for 250, 500, 1,000 and 2,000
    declared PDFs from a 210 KiB archive, and a profile put 18.5 of those 20
    seconds in CPython's central-directory parse, called once per file. A plant
    handover with a few thousand drawings is that shape.
    """
    read_member = zipread.member_reader(raw, allowed=accepted)
    cache = {}

    def get(name: str):
        if name not in cache:
            member = read_member(name)
            if member is None:
                cache[name] = None            # refused; a Z finding already says so
            else:
                # The budget bounds inflating a file, not reading one, so the
                # facts come back either way and only the claim search is lost.
                facts, cut_short = read_pdf(member)
                # Only the allowance spent across the read. A ceiling this file
                # reached on its own is `P3` -- the rule written for exactly
                # that, whose remedy already ends "if the file does carry one,
                # our scan did not reach it". Treating the two alike made `Z5`,
                # an error on the tool axis, fire on an ordinary multi-page PDF:
                # a 2 KB archive went from exit 0 to exit 1.
                #
                # The difference is whose limit it was. An allowance spent
                # across the read says nothing about this file -- it was not
                # looked at because of the files before it -- and that is what
                # `Z5` reports, once, for the container.
                cache[name] = (Stopped(pdfread.MAX_INFLATED_PER_READ, facts)
                               if cut_short == "read" else facts)
        return cache[name]

    return get


def check_bytes(data: bytes, name: str) -> Report:
    report = Report(target=name)
    # The reader's contract is that it records a `Defect` rather than raising,
    # and its own suite holds it to that. It is also a separately versioned
    # package: the pin admits releases nobody in this repository has run, and a
    # crash there is the failure `_into` exists to prevent — a traceback naming
    # internals, with the rest of the batch unchecked. `_into` guarded the rules
    # and `_step` guarded what feeds them; the two calls into the reader that can
    # fail sat outside both. `nfc` is left alone deliberately -- it is
    # `unicodedata.normalize` on a `str` and cannot raise, and wrapping two of
    # its nine call sites would be an inconsistency dressed as a guard.
    # X5's remedy ends "Every other finding in this report still stands; only the
    # named check did not run" -- written for one rule crashing among thirty that
    # did not. Every other check is downstream of this one, so here there is no
    # rest of the report, and the sentence would tell a user their archive was
    # checked when it was never opened.
    root = _step(report, Location(container=name), "container read", zipread.read, data, name,
                 fix="Nothing in the container needs changing for this one. This tool could "
                     "not open the archive at all, so nothing in it was checked — this "
                     "report is not a verdict on the container. Please report it with the "
                     "archive if you can share it.")
    # Before the early return: this is the archive this read was given, and it
    # is one whether or not the reader could open it. Counted after, the one
    # path whose remedy says "this tool could not open the archive at all" read
    # `0 of 0 archives` and called itself complete — the shape this figure
    # exists to make impossible.
    report.read.archives_found = 1
    if root is _CRASHED:
        return report

    # What the archive says was there to open, counted from its own directory,
    # and what this read actually opened. Both halves are the sender's material:
    # a name ending in one of the two reserved metadata names is one a reader can
    # count with `unzip -l`, so the pair cannot be flattered by this tool giving
    # up. Counting instead over this tool's own machinery has the opposite sign —
    # a file that is not a ZIP calls for one check, that check runs, and the
    # worst input this tool ever sees would score full marks.
    # Keyed by the container each entry belongs to, and pruned as the walk
    # leaves a subtree, so at most one root-to-here chain is ever held. Two
    # earlier versions keyed this differently and both were wrong:
    #
    #   * by container path, dropping nothing -- a 2 MB input with two hundred
    #     inner containers held 1.6 GB, the same amplification the reader's tree
    #     budget was added to bound, reached through a door it does not watch;
    #   * by depth, trusting that `walk()` is pre-order so the entry at d-1 must
    #     be the parent. It is pre-order, but the entries were published after
    #     two `continue` statements, so a container with no metadata never wrote
    #     its own bytes and its children read whichever sibling subtree had been
    #     there before. The tool printed a PDF/A claim for a text file.
    #
    # Asking `c.parent` costs the same and cannot answer with somebody else's
    # archive: if an entry is missing the lookup misses, and a missing answer is
    # a rule that does not fire rather than a rule that fires about the wrong
    # file.
    # Keyed by `id()` and not by the container: `Container` is a dataclass with
    # `eq=True`, so `__hash__` is None and it cannot be a dict key. Every
    # container in this walk is reachable from `root`, so no id is reused while
    # the loop runs.
    elements = 0         # parsed across this read; see MAX_TOTAL_ELEMENTS
    # One allowance for the whole walk, not one per container: "this read" is
    # what `MAX_INFLATED_PER_READ` bounds, and a tree of containers each paying
    # its own ceiling is the same unbounded product one level up.
    read_pdf = pdfread.reader(pdfread.MAX_INFLATED_PER_READ)
    raw_of = {}          # id(container) -> (depth, its own bytes or None)
    declared_of = {}     # id(container) -> the names its metadata declares

    for c in root.walk():
        # Every container the walk reaches was opened, and every `.zip` member
        # inside one is an archive that was there to open whether or not this
        # read reached it. `UNREADABLE` is the one the walk still visits and
        # nobody opened: the reader hands back a container so the refusal has
        # somewhere to live, and counting it as opened would say this tool read
        # a file it could not read.
        if c.kind is not Kind.UNREADABLE:
            report.read.archives_opened += 1
        # `present`, not `file_names`: the second is what the reader agreed to
        # hand over, and a member it refused -- an absolute path, say -- is in
        # the archive's directory all the same. A sender counting with a listing
        # tool sees it. Counting the reader's answer instead let refusing a
        # second metadata file turn `1 of 2` into `1 of 1`, which is this tool
        # grading itself on the work it agreed to do.
        listed = c.present or c.file_names
        report.read.archives_found += sum(
            1 for n in listed if n.lower().endswith(".zip"))
        report.read.metadata_found += sum(
            1 for n in listed
            if folder_path(n).replace("\\", "/").rsplit("/", 1)[-1]
            in (METADATA_XML, MAIN_XML))
        if c.metadata_bytes is not None:
            report.read.metadata_read += 1
        # Leaving a subtree: everything at this depth or below is finished.
        for key in [k for k, (d, _) in raw_of.items() if d >= c.depth]:
            del raw_of[key]
            declared_of.pop(key, None)

        if c.parent is None:
            raw = data
        else:
            parent = raw_of.get(id(c.parent))
            # `member_name` comes from the reader. Reconstructing it by splitting
            # the path on the JAR separator got the wrong parent for a member
            # whose own name contains one, which was a way to have `Z3`
            # suppressed on an archive nobody declared.
            raw = None
            if parent is not None and parent[1] is not None and c.member_name:
                raw = _step(report, c.where, "member read",
                            zipread.member_bytes, parent[1], c.member_name)
                if raw is _CRASHED:
                    raw = None
        raw_of[id(c)] = (c.depth, raw)

        parse_error = None
        tree = None
        document = None
        modelled = True
        if c.metadata_bytes is not None and elements >= MAX_TOTAL_ELEMENTS:
            # Not parsed at all, and the report says so rather than reporting
            # nothing -- a container whose metadata went unread has not passed
            # the checks that read it.
            r = rule("X6")
            report.add(Finding(r, r.title, c.where.child(member=c.metadata_name),
                               # "has already built {n} elements" was false, and
                               # off by five orders of magnitude in the case that
                               # trips this: the charge is taken from the markup
                               # *before* the parse, so a 1 KB archive whose read
                               # built about six elements reported 520,007. The
                               # number is real -- it is what bounds the cost --
                               # but it is a charge, not a count, and a finding
                               # that names the wrong thing sends its reader to
                               # look for a document that does not exist.
                               detail=f"this read has already been charged "
                                      f"{elements} elements' worth of markup, its "
                                      f"budget of {MAX_TOTAL_ELEMENTS}; the "
                                      f"metadata here was not parsed"))
            modelled = False
        elif c.metadata_bytes is not None:
            # Charged before the parse, not after it. Counting the tree that came
            # back charged nothing for a document the parser refused -- and
            # refusing is the expensive path, because it builds to the
            # per-document cap first. A thousand of those was a 280 KiB archive
            # that cost 51 seconds with the counter reading 2.
            #
            # From the bytes, because they are the only thing known before the
            # work: every element the parser can build has an opening `<` in
            # them, so this bounds what the parse can cost whether it succeeds,
            # refuses, or dies on a malformed token. `bytes.count` is a memchr.
            elements += (c.metadata_bytes.count(b"<") - c.metadata_bytes.count(b"</"))
            try:
                tree = xmlread.parse(c.metadata_bytes)
            except xmlread.XmlError as e:
                # A malformed document is the container's problem and `X1`/`X3`
                # say so. Anything else out of expat is ours, and `_step` below
                # is what catches it -- this clause used to be the only guard,
                # so a surprise that was not an `XmlError` escaped the run.
                parse_error = e
            except Exception as e:               # noqa: BLE001
                r = rule("X5")
                report.add(Finding(r, r.title, c.where,
                                   detail=f"the parse step: {type(e).__name__}: {e}"))
                tree = None
            if tree is not None:
                document = _step(report, c.where, "document", build, tree,
                                 c.where.child(member=c.metadata_name))
                if document is _CRASHED:
                    document, tree = None, None

        # A container whose kind names a metadata member and has no model of it,
        # however that came about. Keying this on `metadata_bytes is not None`
        # covered the parse we attempted and missed the read we never got to
        # make: when the *reader* refuses the member -- a bad CRC, over the
        # metadata budget, out of container budget -- there are no bytes, the
        # flag stayed true, and `declared` was an empty `frozenset`. *This
        # container declares no files*, asserted about a file nobody read. A
        # document container declaring an `inner.zip` payload, with its metadata
        # member corrupted, drew `Z12` (we could not read it) and then `Z11`,
        # `Z3` and `Z9` about that payload, all three derived from the emptiness
        # the same report says came from not looking.
        #
        # The kind is the right question because it is what decides whether a
        # metadata member is read at all: `UNKNOWN` never had one to model, so
        # nothing here widens to the ordinary archive that simply is not a
        # container. The comment below has said "unknown" and "declares nothing"
        # are different things since the budget path was repaired; these were the
        # other two ways in.
        # Whether this document's names are ours at all, decided from the model
        # rather than from the root's namespace. The root's own is not the
        # question: `<Document>` in no namespace with `xmlns` on its children
        # builds the whole model, because the builder reads the root's children
        # -- and a first version, which asked the root and then its children,
        # said "nothing in it is a VDI 2770 element" beside findings drawn from
        # those elements. What the layers below cannot work with is an *empty*
        # model, and the namespace is the reason for it exactly when the root
        # has children in some other vocabulary.
        foreign = None
        if document is not None:
            elsewhere = sorted({k.ns for k in tree.children if k.ns != NS})
            if elsewhere and not (document.identifiers or document.classifications
                                  or document.versions):
                foreign = elsewhere[0]

        # And an empty model is not "this container declares nothing" -- it is
        # the fourth way into the collapse the comment above is about. A payload
        # declared three lines from `B.pdf` drew `Z11`, telling its sender to
        # declare it.
        if c.kind in (Kind.DOCUMENT, Kind.DOCUMENTATION) and (document is None
                                                              or foreign is not None):
            modelled = False

        # `folder_path`, not `nfc`. A declared name and a member name are the
        # same kind of thing and have to be compared the one way -- the repair
        # that put path normalisation into `names.py` reached `Members.resolve`
        # and did not reach here, so `F1` matched `./cad.zip` to its declaration
        # while `Z11` and the payload exemption, reading this set, did not.
        declared = frozenset(folder_path(f.file_name) for f in document.all_files
                             if f.file_name) if document else frozenset()
        declared_of[id(c)] = declared if modelled else None

        # `None` and "declares nothing" are different, and collapsing them is how
        # a budget in the parent invented a finding about the child: `Z3` fires
        # on an inner archive that is neither kind of container *and* was not
        # declared as a file, and a parent we declined to model cannot say
        # whether it declared this one. Unknown suppresses the rule; empty does
        # not.
        parent_declared = declared_of.get(id(c.parent))
        # A member of a folder that holds its own metadata is governed by that
        # metadata -- the file this tool did not open -- and not by the parent's.
        # Judged against the parent's declarations, `AB393/cad.zip` drew `Z3`
        # ("the parent modelled its metadata and did not declare this") beside
        # the `Z13` saying `AB393/` was never read. Unknown, not undeclared.
        governed_elsewhere = (
            bool(c.member_name) and c.parent is not None
            # By name, not through the module attribute: the crash-guard test
            # replaces `r_container` wholesale with a stub that has only
            # `check`, and reaching through the attribute made the runner
            # itself fall over inside that test.
            and _inside(
                folder_path(c.member_name),
                {folder_path(f)
                 for f, _ in folders_holding_metadata(c.parent)} - {""}))
        unknown_parent = (c.parent is not None
                          and (parent_declared is None or governed_elsewhere))
        is_payload = (bool(c.member_name) and parent_declared is not None
                      and folder_path(c.member_name) in parent_declared)

        # A container whose metadata we declined to model has an empty `declared`,
        # and the rules that read it then said things about the sender: a
        # conforming document container declaring a `.zip` payload was reported
        # with `Z11` and `Z3`, both errors, both `about: container`, beside the
        # `X6` saying this tool had not looked. Checked on its own it is clean, so
        # the verdict depended on what else was in the sweep. `X6` is the true
        # statement and it is already in the report.
        # Not the whole call. `r_container.check` opens by turning the reader's
        # own defects into findings -- `Z1`, `Z2`, `Z4`, `Z5`, `Z6`, `Z10`,
        # `Z12` -- and none of those reads the model. Gating all of it meant a
        # path-traversal member reported `Z4` on its own and *nothing* behind a
        # sibling that spent the budget, with `X6` (`about: tool`) the only
        # substitute -- so a CI gate filtering the tool axis saw no container
        # finding for the subtree at all. `None` says "unknown" to the two rules
        # that actually read the model.
        _into(report, r_container.check(
            c, declared=declared if modelled else None,
            is_declared_payload=None if unknown_parent else is_payload),
              c.where, "container")

        if c.metadata_bytes is None:
            continue

        # `tree is not None` is the decision, and it used to be made twice: the
        # line above also read `or not modelled`, which is the same condition
        # said a second way -- a container we declined to model has no tree.
        # Removing it changed nothing, which is how it was found. Two spellings
        # of one decision are two things to keep in step, and this file has
        # already paid for that once.
        schema_errors = (_step(report, c.where, "schema check", xsdvalidate.validate,
                               c.metadata_bytes, tree)
                         if tree is not None else [])
        if schema_errors is _CRASHED:
            schema_errors = []
        _into(report, r_schema.check(c, parse_error, schema_errors), c.where, "schema")
        if document is None:
            continue

        _into(report, r_files.check(c, document, foreign), c.where, "files")
        _into(report, r_metadata.check(c, document, foreign), c.where, "metadata")

        if raw is not None:
            _into(report,
                  r_pdf.check(c, document, _facts_for(raw, set(c.file_names), read_pdf)),
                  c.where, "pdf")

    return report


def check_file(path: str) -> Report:
    # Opened without blocking, because one kind of unreadable path does not fail
    # -- it waits. A FIFO with no writer blocks in `open` forever, and `cli`
    # catches exceptions so one bad path cannot stop a sweep; a hang is not an
    # exception, so a single named pipe in a supplier drop folder meant the run
    # produced a verdict on nothing.
    #
    # The first repair refused anything `S_ISREG` said no to, which refused the
    # hang and also refused `check <(unzip -p ...)` and `... | check /dev/stdin`
    # -- both of which worked, and neither of which is a FIFO without a writer.
    # That was a fix for the shape that had been found rather than for the thing
    # that was wrong. `O_NONBLOCK` distinguishes the two: it returns at once
    # whether or not a writer is there, so the pipe that has one is read and the
    # one that does not reaches end-of-file instead of waiting.
    #
    # Cleared straight after, so a writer that is merely slow is waited for.
    # `fcntl` is Unix-only, and importing it at module scope made the whole
    # package fail to import on Windows -- in the release whose headline fix is
    # the Windows console. The platform that has no `O_NONBLOCK` also has no
    # FIFO to hang on, so it keeps the earlier refusal.
    if not hasattr(os, "O_NONBLOCK"):
        if not stat.S_ISREG(os.stat(path).st_mode):
            raise OSError(errno.EINVAL, "not a regular file", path)
        with open(path, "rb") as fh:
            data = fh.read()
    else:
        import fcntl

        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        try:
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)
        except BaseException:
            os.close(fd)
            raise
        # No second close: `fdopen` takes ownership, and closing again after the
        # `with` had already closed it turned a read error into `EBADF` -- the
        # true diagnosis destroyed, and in a long-lived process a chance of
        # closing an unrelated file that had reused the number.
        with os.fdopen(fd, "rb") as fh:
            data = fh.read()
    return check_bytes(data, path.rsplit("/", 1)[-1])
