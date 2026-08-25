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

from typing import Dict, List, Mapping, Optional, Sequence, Tuple

# Canonicalising a member name belongs to whoever reads archives. There were two
# copies of that one line, in two packages, which is precisely the failure this
# module was created to stop.
from vdi2770 import nfc
from vdi2770.model import Defect

__all__ = ["Members", "nfc"]


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
        self._by_nfc: Dict[str, List[str]] = {}
        for name in self.present:
            self._by_nfc.setdefault(nfc(name), []).append(name)
        self._rejected = dict(rejected or {})
        self._rejected_by_nfc: Dict[str, List[str]] = {}
        for name in self._rejected:
            self._rejected_by_nfc.setdefault(nfc(name), []).append(name)

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
        candidates = self._by_nfc.get(nfc(declared), ())
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

    def refused_by(self, declared: str) -> Optional[Defect]:
        """The `Defect` behind a refusal, for a caller that needs to know *which*
        refusal rather than how to say it.

        Whether a refusal is the sender's doing depends on the kind: a bad CRC is
        theirs, a budget of ours is not, and one rule reports both.
        """
        if declared in self._rejected:
            return self._rejected[declared]
        candidates = self._rejected_by_nfc.get(nfc(declared), ())
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
