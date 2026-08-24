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

__all__ = ["Members", "nfc"]


class Members:
    """The archive's names, answering questions asked in the metadata's spelling."""

    def __init__(self, present: Sequence[str], rejected: Optional[Mapping[str, str]] = None):
        self.present: Tuple[str, ...] = tuple(present)
        self._exact = set(self.present)
        self._by_nfc: Dict[str, List[str]] = {}
        for name in self.present:
            self._by_nfc.setdefault(nfc(name), []).append(name)
        self._rejected = dict(rejected or {})
        self._rejected_by_nfc: Dict[str, List[str]] = {}
        for name in self._rejected:
            self._rejected_by_nfc.setdefault(nfc(name), []).append(name)

    def resolve(self, declared: str) -> Optional[str]:
        """The member a declared name refers to, in the archive's own spelling.

        An exact match wins outright. Failing that the canonical spelling has to
        identify exactly one member: if the archive holds both spellings they are
        two different files, and answering with either is a guess. `Z10` reports
        that ambiguity, so returning None here loses nothing.
        """
        if declared in self._exact:
            return declared
        candidates = self._by_nfc.get(nfc(declared), ())
        return candidates[0] if len(candidates) == 1 else None

    def refusal(self, declared: str) -> Optional[str]:
        """Why the reader refused this member, if it did.

        Keyed by the archive's spelling and asked in the metadata's, which is how
        a file that was present and declined came to be reported as absent.
        """
        if declared in self._rejected:
            return self._rejected[declared]
        candidates = self._rejected_by_nfc.get(nfc(declared), ())
        return self._rejected[candidates[0]] if len(candidates) == 1 else None
