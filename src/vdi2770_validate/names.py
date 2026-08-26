"""Reconciling the name in the metadata with the name in the archive.

macOS stores filenames decomposed and its Finder writes them that way into a
ZIP; metadata authored anywhere else is composed. The two print identically and
are canonically equivalent, so they have to be reconciled — and every place that
compares a name has to reconcile them the *same* way, which is why this is one
module rather than a helper called from wherever somebody remembered.

Two mistakes are already behind it. Applying the normalisation to two of three
comparisons made the report call one file both missing and accounted for. And
mapping every member onto its canonical spelling loses a file when an archive
holds both spellings: they are two members with different bytes, and picking one
made the verdict depend on which came last in the archive.
"""
from __future__ import annotations

import unicodedata
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

# Canonicalising a member name belongs to whoever reads archives. There were two
# copies of that one line, in two packages, which is precisely the failure this
# module was created to stop.
from vdi2770 import nfc
from vdi2770.model import Defect

__all__ = ["Members", "escaped", "extracts_to", "folder_path", "nfc"]


def extracts_to(name: str) -> str:
    """The path an extractor writes this member to, without normalising letters.

    `folder_path` also applies `nfc`, which is right for *matching a declaration
    to a member* -- the two are written by different hands and may compose
    differently. It is wrong for asking whether two members land on the same
    file: `B.pdf` and its decomposed twin are two files on most filesystems and
    the metadata declares only one of them, so the other really is undeclared.
    `./B.pdf` and `B.pdf` are one file everywhere.
    """
    return "/".join(seg for seg in name.split("/") if seg not in ("", "."))


def escaped(name: str) -> str:
    """A name with anything invisible spelled out.

    Two members can differ in bytes and print identically -- combining marks in
    a different order, a composed character against its decomposition. Showing
    both as themselves gives a reader two lines they cannot tell apart, which is
    the whole reason the difference is worth reporting.
    """
    return "".join(c if c.isprintable() and not unicodedata.combining(c)
                   else f"\\u{ord(c):04x}" for c in name)


def folder_path(name: str) -> str:
    """`name` with `.` and empty segments dropped, after `nfc`.

    The other half of reconciliation, and it lived somewhere else for a while --
    in `rules/container.py`, where two rules used it to agree about folders while
    `Members`, one layer down, still compared member names by `nfc` alone. So a
    member stored as `./B.pdf` was `F1` *declared but not in the archive* and
    `F2` *in the container but not named in the metadata*, in one report, about
    one file: exactly what the module docstring above says this module exists to
    prevent, arriving through the door the docstring was not watching.

    Only segments that denote nothing are dropped -- `.` and empty. `..` is left
    alone: it denotes a different directory, the reader refuses names carrying it
    (`unsafe-member-name`), and quietly resolving one here would undo that.
    """
    return "/".join(seg for seg in nfc(name).split("/") if seg not in ("", "."))


class Members:
    """The archive's names, answering questions asked in the metadata's spelling."""

    def __init__(self, present: Sequence[str],
                 rejected: Optional[Mapping[str, Defect]] = None):
        self.present: Tuple[str, ...] = tuple(present)
        self._exact = set(self.present)
        # A name the archive stores twice denotes two files, and which one a ZIP
        # reader hands back is its own business. Exactly the ambiguity the
        # canonical-spelling branch below already declines to guess at, arriving
        # through the door an exact match walks straight past.
        seen: Dict[str, int] = {}
        for name in self.present:
            seen[name] = seen.get(name, 0) + 1
        # Empty for anything the reader produces: `read` refuses both entries
        # of a repeated name, so neither reaches `file_names`. Kept because this
        # class reconciles whatever names it is handed and a duplicate in that
        # input is a real ambiguity it must decline to guess at -- but a rule
        # that wants to know whether *the archive* repeated a name has to read
        # the refusal, which is where the reader put the answer.
        self.ambiguous = frozenset(n for n, k in seen.items() if k > 1)
        # Keyed on the path, not merely the composition. `./B.pdf` and `B.pdf`
        # are one path -- `unzip` writes both to `B.pdf` -- and keying on `nfc`
        # alone made the second of them unfindable.
        self._by_nfc: Dict[str, List[str]] = {}
        for name in self.present:
            self._by_nfc.setdefault(folder_path(name), []).append(name)
        self._rejected = dict(rejected or {})
        self._rejected_by_nfc: Dict[str, List[str]] = {}
        for name in self._rejected:
            self._rejected_by_nfc.setdefault(folder_path(name), []).append(name)

    def resolve(self, declared: str) -> Optional[str]:
        """The member a declared name refers to, in the archive's own spelling.

        An exact match wins outright *unless the archive holds that name twice*.
        Failing that the canonical spelling has to identify exactly one member: if
        the archive holds both spellings they are two different files, and
        answering with either is a guess. `Z10` reports either ambiguity, so
        returning None here loses nothing.

        The exact-duplicate case was the hole: one archive with two members
        called `B.pdf`, one a real PDF/A-3a and one sixteen bytes of text, gave
        opposite verdicts depending on which the archive stored last.
        """
        if declared in self.ambiguous:
            return None
        if declared in self._exact:
            return declared
        candidates = self._by_nfc.get(folder_path(declared), ())
        return candidates[0] if len(candidates) == 1 else None

    #: A refusal, said in a sentence. The reader hands back the `Defect` that
    #: refused the member and writes no prose about it -- deciding how to phrase
    #: a refusal to a user is a report's job, not a reader's.
    SAID = {
        "unsafe-member-name": "its name would escape the extraction directory",
        "member-too-large": "it is larger than this tool will read",
        "suspicious-compression": "it expands further than this tool will allow",
        "member-unreadable": "it is in the archive but could not be read",
        "metadata-too-large": "it is larger than this tool will parse",
        "container-budget-exhausted": "this read had no metadata budget left for it",
        "archive-too-large": "the archive passed this tool's size limit before "
                             "reaching it",
        "decompression-budget-exhausted": "this read had no decompression budget "
                                          "left for it",
        "member-budget-exhausted": "this read had already listed as many entries "
                                   "as it will hold",
        "ambiguous-name": "two entries in the archive carry this name, so it "
                          "identifies neither of them",
    }

    def spelled_more_than_one_way(self, declared: str) -> tuple:
        """The members a declared name reaches, when it reaches more than one.

        `resolve` returns `None` for two unrelated reasons — nothing matched, and
        too much matched — and every caller read the second as the first. So a
        file the archive holds *twice*, under two spellings that both canonicalise
        to the declared name, was reported as not being there, with a remedy that
        said to add it or to delete a correct declaration.

        Empty when the name is absent or resolves cleanly, so a caller can tell
        "no such file" from "which one did you mean" without guessing.
        """
        if declared in self._exact:
            return ()
        candidates = self._by_nfc.get(folder_path(declared), ())
        return tuple(sorted(candidates)) if len(candidates) > 1 else ()

    def refused_by(self, declared: str) -> Optional[Defect]:
        """The `Defect` behind a refusal, for a caller that needs to know *which*
        refusal rather than how to say it.

        Whether a refusal is the sender's doing depends on the kind: a bad CRC is
        theirs, a budget of ours is not, and one rule reports both.
        """
        if declared in self._rejected:
            return self._rejected[declared]
        candidates = self._rejected_by_nfc.get(folder_path(declared), ())
        return self._rejected[candidates[0]] if len(candidates) == 1 else None

    def refusal(self, declared: str) -> Optional[str]:
        """Why the reader refused this member, in a sentence, if it did.

        Keyed by the archive's spelling and asked in the metadata's, which is how
        a file that was present and declined came to be reported as absent.
        """
        d = self.refused_by(declared)
        if d is None:
            return None
        said = self.SAID.get(d.kind)
        # An unmapped kind still has to say something true. A gate keeps the
        # table complete; this is what a future kind reads like until it does.
        head = said or f"the reader refused it ({d.kind})"
        return f"{head} ({d.detail})" if d.detail else head
