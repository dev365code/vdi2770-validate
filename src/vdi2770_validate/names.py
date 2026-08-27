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

__all__ = ["Members", "as_written", "escaped", "extracts_to", "folder_path",
           "ignoring_case", "nfc", "told_apart", "without_edge_space"]


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


# Characters that take no room on the page. `isprintable` covers the format and
# control categories; the rest are marks and selectors Python calls printable and
# a terminal draws as nothing, so a name carrying one prints exactly like the same
# name without it. Python has no `Default_Ignorable_Code_Point` predicate, so the
# ranges are written out. `U+2800 BRAILLE PATTERN BLANK` is not one of them --
# it is `So`, printable, and not whitespace -- but it draws nothing, and it is
# the one character in that description that no property finds.
_INVISIBLE = ((0x034F, 0x034F),      # combining grapheme joiner
              (0x115F, 0x1160),      # Hangul choseong and jungseong fillers
              (0x17B4, 0x17B5),      # Khmer inherent vowels
              (0x180B, 0x180F),      # Mongolian free variation selectors
              (0x2800, 0x2800),      # braille pattern blank
              (0x3164, 0x3164),      # Hangul filler
              (0xFE00, 0xFE0F),      # variation selectors
              (0xFFA0, 0xFFA0),      # halfwidth Hangul filler
              (0xE0000, 0xE007F),    # tag characters
              (0xE0100, 0xE01EF))    # variation selectors supplement


def _draws_nothing(c: str) -> bool:
    return not c.isprintable() or any(lo <= ord(c) <= hi for lo, hi in _INVISIBLE)


def _spelled(c: str) -> str:
    """`c` as the escape a reader can type back.

    `\\U` above the BMP. `f"\\u{ord(c):04x}"` printed five and six hex digits for
    those, and `\\ue0067` reads as U+E006 followed by the digit 7 -- a different
    character, silently substituted, in the one line whose job is to be exact.
    """
    return f"\\U{ord(c):08x}" if ord(c) > 0xFFFF else f"\\u{ord(c):04x}"


def told_apart(observed: str, published: str):
    """`(observed, published)`, rendered so a reader can see what differs.

    `escaped` looks at one string. That is enough when the two are canonically
    equivalent -- exactly one of them is its own NFC, so exactly one is spelled
    out -- and it is not enough for anything else. One Cyrillic `е` among the
    Latin ones is its own NFC, printable and non-combining on both sides, so
    `escaped` left both alone and a finding read

        'Tеchnische Spezifikation' … published name is 'Technische Spezifikation'

    which asks its reader to find a difference nothing on the page shows.

    A caller holding *both* strings knows something `escaped` cannot: where they
    differ. The question this can answer is not *are these drawn alike* -- no
    rule over code points can answer that -- but **is this difference one a
    reader can miss**, and that has two shapes:

    * The same characters in the same places but for a few positions, at least
      one of which is not ASCII. A Cyrillic letter sitting among Latin ones is
      that, and so is a Greek question mark among semicolons. Those positions are
      spelled out on both sides and nothing else is. An all-ASCII difference is
      not spelled: `identification` against `Identification` needs no help, and
      hexing it buries the one character that matters.
    * A difference that changes the length and is made entirely of whitespace --
      a doubled space. Nothing else that changes the length qualifies: a name
      that is shorter, longer or wholly different is one nobody needs help
      seeing.

    The comparison runs over the characters `escaped` leaves alone, so a trailing
    space and a homoglyph in one name are both named rather than the first
    hiding the second. Longest common prefix and suffix rather than a diff:
    an alignment algorithm chooses between equally good answers, and a report
    that changes its mind about where a difference sits cannot be compared
    against yesterday's.
    """
    plain_o, plain_p = _plain_positions(observed), _plain_positions(published)

    if len(plain_o) == len(plain_p):
        differing = [k for k in range(len(plain_o))
                     if observed[plain_o[k]] != published[plain_p[k]]]
        easy_to_miss = any(not (observed[plain_o[k]].isascii()
                                and published[plain_p[k]].isascii())
                           for k in differing)
        if differing and easy_to_miss:
            return (_spelling_at(observed, {plain_o[k] for k in differing}),
                    _spelling_at(published, {plain_p[k] for k in differing}))
        return _as_text(observed), _as_text(published)

    head = 0
    while (head < len(observed) and head < len(published)
           and observed[head] == published[head]):
        head += 1
    tail = 0
    while (tail < len(observed) - head and tail < len(published) - head
           and observed[-1 - tail] == published[-1 - tail]):
        tail += 1
    runs = observed[head:len(observed) - tail] + published[head:len(published) - tail]
    if runs and all(c.isspace() for c in runs):
        return (_spelling_at(observed, set(range(head, len(observed) - tail))),
                _spelling_at(published, set(range(head, len(published) - tail))))
    return _as_text(observed), _as_text(published)


def _as_text(text: str) -> str:
    """`escaped` for something that is not a path."""
    return _spelling_at(text, ())


def _plain_positions(text: str) -> list:
    """The indices `escaped` leaves as they are — the visible skeleton.

    Comparing the raw strings let one difference hide another: a trailing space
    is spelled by `escaped`, and a name carrying both that and a homoglyph came
    back with the space explained and the homoglyph drawn as its look-alike. The
    supplier strips the space, resubmits, and fails again for a reason the report
    showed them once and never named.
    """
    edges = _at_an_edge(text, segments=False)
    return [i for i, c in enumerate(text)
            if not (c == "\\" or _draws_nothing(c) or i in edges)]


def _spelling_at(text: str, positions) -> str:
    """`escaped`'s per-character rule, plus everything in `positions`.

    Free text, so no segment edges: a `/` in a class name is a character, not a
    path separator.
    """
    edges = _at_an_edge(text, segments=False)
    return "".join(
        _spelled(c) if i in positions or c == "\\" or _draws_nothing(c) or i in edges
        else c
        for i, c in enumerate(text))


def as_written(name: str) -> str:
    """The archive's own spelling, with only what draws nothing spelled out.

    `escaped` spells out every non-ASCII character of a name that is not its own
    NFC, because that is what tells two canonically equivalent names apart. When
    the difference between two names is *not* a spelling difference -- two
    members that extract to one path and differ only in `.` segments -- that
    rule spends nothing and costs a great deal: two members written
    `설명서_Prüfbericht.pdf` and `./설명서_Prüfbericht.pdf` came back as four
    walls of hex in one finding, about names differing by two visible ASCII
    characters. macOS writes every filename decomposed, so this was the ordinary
    case for exactly the reader it hurt most.

    What is still spelled out is what draws nothing, a backslash, and whitespace
    at an edge -- because a name is not something a reader can act on while part
    of it is invisible, and that is as true here as it is one function down.
    """
    edges = _at_an_edge(name)
    return "".join(_spelled(c) if c == "\\" or _draws_nothing(c) or i in edges
                   else c
                   for i, c in enumerate(name))


def _at_an_edge(name: str, segments: bool = True) -> frozenset:
    """The indices of whitespace that begins or ends the name, or a segment of it.

    A space in the middle of `my report.pdf` is ordinary and visible. At an edge
    it draws nothing a reader can locate: `B.pdf ` and `B.pdf` are one line as
    far as the page is concerned, and a report could carry *`'B.pdf'` is declared
    and not in the archive* directly above *`B.pdf` is in the container and not
    named in the metadata*, which reads as a contradiction and is two names.
    Segment edges too, because `docs /B.pdf` hides it just as well -- but only
    when the string is a path. `escaped` also renders free text: a class name
    written `Technische / Spezifikation` had both of its ordinary spaces spelled
    out, because splitting on `/` had made each of them the edge of a "segment",
    and the difference that mattered -- a slash where nothing belongs -- was left
    for the reader to find among the escapes.
    """
    edges, start = set(), 0
    stops = ([i for i, c in enumerate(name) if c == "/"] if segments else []) + [len(name)]
    for stop in stops:
        front = start
        while front < stop and name[front].isspace():
            edges.add(front)
            front += 1
        back = stop - 1
        while back >= start and name[back].isspace():
            edges.add(back)
            back -= 1
        start = stop + 1
    return frozenset(edges)


def escaped(name: str) -> str:
    """A name a reader can tell apart from anything that prints like it.

    Two members can differ in bytes and print identically: a composed character
    against its decomposition, combining marks in a different order, a canonical
    singleton. Showing both as themselves gives a reader two lines they cannot
    tell apart, which is the whole reason the difference is worth reporting.

    The rule is one sentence, and it rests on one fact: **a canonical
    equivalence class holds exactly one NFC spelling.** So a name that is not its
    own NFC gets every non-ASCII character spelled out, and at most one member of
    any look-alike group is left printing as itself. Nothing here needs to guess
    which characters "combine" -- and every guess this had made was wrong in one
    direction or the other. Escaping by combining class missed Hangul conjoining
    jamo, which are `Lo`, printable, class 0, and compose with their neighbours:
    `도면.pdf` written the way a Mac writes it rendered exactly like `도면.pdf`
    written the way Windows does, in both halves of the same sentence. It missed
    canonical singletons for the same reason -- `Ångstrom` U+212B against U+00C5,
    `Ω` U+2126 against U+03A9. And it escaped Thai tone marks, Devanagari viramas
    and Arabic harakat, which are *visible letters*, so `परीक्षण.pdf` -- a name
    with nothing wrong with it -- printed as `परीक\\u094dषण.pdf`.

    The escapes are spelled so that reading them back gives the name: `\\` for a
    backslash, always. Without that, `A` and a combining ring above rendered
    identically to a member literally named `A\\u030angstrom.pdf`, and the report
    could not say which of the two it was looking at.

    A name carrying something that draws nothing is spelled out in full too. Not
    for the same reason -- there is nothing canonical about it -- but because
    escaping one character in the middle can leave a following mark attached to
    the escape's own letters, and a name with an invisible character in it is one
    a reader has to see whole in any case.
    """
    hidden = any(_draws_nothing(c) for c in name)
    all_of_it = hidden or nfc(name) != name
    edges = _at_an_edge(name)
    return "".join(
        _spelled(c) if c == "\\" or _draws_nothing(c) or i in edges
        or (all_of_it and not c.isascii())
        else c
        for i, c in enumerate(name))


def without_edge_space(name: str) -> str:
    """`name` with whitespace removed from the edge of every segment.

    What a declaration of this member would have to be, and cannot be. The
    metadata's text is read with the whitespace around it removed -- it has to
    be, because `<DigitalFile>\\n    B.pdf\\n  </DigitalFile>` is how a
    pretty-printer writes an ordinary declaration -- and the schema types that
    element `xs:string`, which preserves whitespace. So the stripping is a
    choice every implementation makes, and its consequence is that a member
    whose name carries a space at its edge cannot be declared by anybody:
    whatever the sender writes is read back without it.
    """
    return "/".join(segment.strip() for segment in name.split("/"))


def ignoring_case(name: str) -> str:
    """The one file a filesystem that folds case stores this member as.

    macOS as it ships and every Windows filesystem keep `B.pdf` and `b.pdf` as
    one file, so a container holding both delivers one of them and the other
    declaration names a path the recipient does not have.

    `casefold` before `nfc`, and both: measured against this machine's own
    volume, `str.lower` misses `ß`/`ss` and `ﬁ`/`fi`, which really do fold into
    one file; `str.upper` merges the Turkish dotless `ı` with `I`, which stay
    two; and NFKC-casefold merges a fullwidth `ａ` with `a`, which also stay two.
    Both of the last two are false alarms about a collision that does not happen.
    Folding first matters for the rare case where a fold exposes a composition
    that composing first would have hidden.

    Over `extracts_to`, not `folder_path`: `./B.PDF` beside `B.pdf` has to group,
    and so does a folder segment that differs only in case.

    The relation is the running interpreter's, which is not always the
    filesystem's: `casefold` reads Python's Unicode tables, and a volume built
    against a newer release folds pairs an older interpreter does not. Measured
    against this machine, the pairs it misses that way are all in scripts added
    after Unicode 13 -- Vithkuqi, Garay, Medefaidrin, Glagolitic supplement --
    and every miss is in that direction: it never claims a collision the
    filesystem does not make.
    """
    return nfc(extracts_to(name).casefold())


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
        # Sorted here, once. `spelled_more_than_one_way` sorted its group on
        # every call, and it is called once per declaration: four hundred
        # declarations of one name against two thousand spellings of it paid
        # four hundred sorts of a two-thousand-member list.
        for group in self._by_nfc.values():
            group.sort()
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
        # The archive's claim, not a measurement: the size comes from the
        # central directory and nothing inflated the member to check it.
        "member-too-large": "the archive declares it larger than this tool will read",
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
        return tuple(candidates) if len(candidates) > 1 else ()

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
