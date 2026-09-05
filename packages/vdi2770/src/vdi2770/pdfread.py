"""Four facts about a PDF, read by scanning bytes.

We deliberately do not use a PDF parsing library. We need whether the file is a
PDF at all, its header, whether it is encrypted, and what PDF/A level it
*claims* in its XMP packet — the four the summary line names, and the four
`PdfFacts` carries; this paragraph used to say three and forget `is_pdf`.
Pulling a full parser for untrusted supplier files, to read four facts, is a
poor trade in both dependency weight and attack surface.

What this cannot do: verify a PDF/A claim. Only a PDF/A validator can. The
report says so every time it prints a claim.
"""
from __future__ import annotations

import re
import zlib
from dataclasses import dataclass
from typing import Callable, List, Optional

# A PDF/A identification is identified by its namespace URI. The prefix bound to
# that URI is a local choice -- `pa:part` says exactly what `pdfaid:part` says --
# so the prefix is read out of the packet rather than assumed.
_PDFA_NS = re.compile(
    rb"""xmlns:([A-Za-z_][\w.\-]{0,63})\s*=\s*["']http://www\.aiim\.org/pdfa/ns/id/["']""",
    re.I)
MAX_PDFA_PREFIXES = 4     # one is normal; a packet listing hundreds gets four tries
_STREAM = re.compile(rb"stream\r?\n")

# A PDF/A identification lives in the XMP metadata. Matching the words anywhere
# in the file means a comment could suppress a caller's PDF/A finding, so the
# search is scoped to XMP packets. (This package names no caller's rule ids: it
# reports what it found and lets whoever holds the rules decide.)
# Found by scanning, not by a backtracking regex. What was here before was
# `START.*?END` with re.S, and when END is absent every START rescans to the end
# of the input: 128 KiB of `<?xpacket begin` took 2.6 seconds, quadratic, so a
# member sized just under the compression-ratio floor would have taken hours.
# None of the budgets caught it -- they bound inflation, and this is the raw pass.
_PACKET_KINDS = (
    (re.compile(rb"<\?xpacket\s+begin", re.I), b"<?xpacket end", b"?>"),
    (re.compile(rb"<x:xmpmeta[\s>]", re.I), b"</x:xmpmeta>", None),
    (re.compile(rb"<rdf:RDF[\s>]", re.I), b"</rdf:rdf>", None),
)
MAX_XMP_PACKETS = 64      # per haystack; a file needs one

# The trailer references the encryption dictionary indirectly — that is what the
# format requires. `/Encrypt` on its own appears in comments, content streams and
# field names, and used to be reported as an error.
#
# Matching that indirect form anywhere in the file was not enough: the same token
# inside a string in a content stream — `(see /Encrypt 3 0 R for details)` — read
# as an encrypted document, which is an error raised against a file that opens
# fine. It is read from the trailer, which is where the format puts it.
_ENCRYPT_REF = re.compile(rb"/Encrypt\s+\d+\s+\d+\s+R")
_TRAILER = re.compile(rb"\btrailer\b")
MAX_TRAILER_SCAN = 65536  # the most of ONE trailer dictionary that is read
# And how many of them are read at all. Two bounds, because they answer different
# questions and one of them was doing both jobs badly: a single file-wide total
# stopped the multiplication attack and then let an ordinary earlier trailer -- a
# long `/ID`, a long `/Info` -- spend the whole budget, so the authoritative
# trailer of an incrementally updated file was never looked at and an encrypted
# document read as clean. Per-dictionary keeps every trailer readable; this keeps
# their number finite. The last ones are read, because an incremental update
# appends and the newest trailer is the one that counts.
MAX_TRAILERS = 64
# How far back a keyword looks for the start of its own line, which is also what
# examining one costs. Unbounded, this was the quadratic: the look-back decides
# whether a `%` on the same line commented the keyword out, and a file with no
# newline made every one of those walks run to the start of the file. A cap on
# *where* to look was not a cap on *how much* looking costs.
#
# The size is a balance between two attacks that pull opposite ways, and it is
# the only thing holding both off. Decoy tokens that cost nothing let a small
# file be scanned once per token -- 512 KB took eleven seconds. Decoy tokens that
# cost a lot let a supplier bury the real trailer behind enough of them to spend
# the budget before it is reached, which hides an encrypted document. So the
# charge is small and the number of tokens it admits is large:
# `MAX_TRAILER_BYTES` over this is sixteen thousand tokens examined, while the
# bytes they may scan between them stays fixed. Beyond the window a `%` is not
# seen, so a commented-out `trailer` in a very long line is read rather than
# skipped -- which costs one bounded dictionary scan and cannot cost more.
MAX_LINE_LOOKBACK = 256
# Not a number of trailers any more, but the bytes all of them together may cost.
# Sixty-four was a bound on *where* to look, and every bound on where is pushable
# by whoever appends: sixty-four `%trailer` decoys and one `startxref` of their
# own -- 658 bytes, ignored by every conformant reader -- pushed the real trailer
# out of the window and an encrypted PDF came back clean.
#
# A bound on *how much* is read cannot be pushed the same way, because a decoy
# that is not a dictionary is rejected in the two bytes it takes to see there is
# no `<<`. Thousands of them buy nothing. What an attacker now has to spend is
# real dictionaries, byte for byte, and this says how many bytes that is.
#
# Read from the end backwards, which is the half of the old reasoning that was
# right: an incremental update appends and the newest trailer is the one that
# counts. That order is also why one budget across the file is safe here, where
# spending it in file order was not -- a long `/ID` in an ordinary earlier
# trailer is now read *after* the authoritative one, not in front of it.
MAX_TRAILER_BYTES = MAX_TRAILERS * MAX_TRAILER_SCAN

# `\d{1,19}`, not `\d+`. CPython 3.11 refuses `int()` above 4,300 digits, so a
# few kilobytes of nines after `startxref` came back as `ValueError` out of
# `read_pdf` -- from a library whose contract is that it records a defect
# rather than raising, on the two interpreters CI runs. Through the validator it
# took the whole PDF layer down with it, so it was also a cheaper way to make an
# encrypted file look unencrypted. No offset into a real file has twenty digits;
# nothing that could have been an answer is lost by declining to read one.
_STARTXREF = re.compile(rb"startxref\s+(\d{1,19})")
_NEWLINE = re.compile(rb"[\r\n]")
_OBJ_HEADER = re.compile(rb"\d+\s+\d+\s+obj\b")


def _is_encrypted(data: bytes) -> bool:
    """Whether a trailer dictionary has an `/Encrypt` key whose value is an
    indirect reference, which is the only form the format permits: ISO 32000-1
    requires the encryption dictionary to be an indirect object. So
    `<< /Encrypt << /Filter /Standard >> >>` reads as not encrypted, and that
    is right rather than a gap -- but the one-line summary said `key`, which
    claims more than this delivers. `docs/scope.md` has always said which.

    Repaired three times before this, and each repair fixed the shape that had
    been found: a whole-file token search reported any PDF whose *content*
    mentioned `/Encrypt`; a fixed window missed an `/Encrypt` that a long `/ID`
    pushed past it; a brace walk counted `<<` inside a string; a brace walk that
    skipped strings still ran the token search over raw bytes, so `/Encrypt` in a
    *comment* counted. Each fix was to an instance of one class -- ad-hoc byte
    scanning of a format that has structure -- and the class kept a shape in
    reserve.

    So: one pass that knows the structure, and finds the key in the same pass
    that decides where the dictionary is. Nothing downstream can disagree with
    it, because there is no downstream.

    And two budgets, because the cost has two axes and one bound cannot hold
    both. A per-keyword bound multiplied: 16,000 bare `trailer` keywords cost 135
    seconds, and 8,000 that *open* a dictionary cost 28 seconds from a 20 KB
    archive. Replacing it with one file-wide total stopped that and started
    something worse -- an ordinary earlier trailer with a long `/ID` spent the
    budget, so the authoritative trailer of an incrementally updated file was
    never read and an encrypted document came back clean. Each dictionary gets
    its own scan; their number is capped separately, from the end, because an
    incremental update appends and the newest trailer is the one that counts.

    A PDF whose trailer lives in a cross-reference stream (1.5 and later) has no
    `trailer` keyword at all. Its dictionary belongs to an object, and the
    declared offset names that object's header rather than the `<<` -- which this
    said it read and did not, so every such file came back unencrypted while the
    docstring one function down said it would. Stepping over the header is what
    makes the claim true.
    """
    # Where the format says the answer is, before anywhere we might guess it is.
    #
    # The previous repair read the *last* `MAX_TRAILERS` dictionaries, on the
    # reasoning that an incremental update appends. True of a file nobody is
    # attacking; sixty-four occurrences of the token `%trailer` appended after
    # `%%EOF` -- 640 bytes, ignored by every conformant reader -- pushed the real
    # trailer out of that window and an encrypted PDF came back clean. Every
    # window is pushable, because the window is a guess about where to look, and
    # this scan has now guessed four different ways.
    #
    # `startxref` is not a guess. It is the one offset the file itself declares,
    # and following it is what a reader does. All fifty-five PDFs in this
    # repository's corpus carry one.
    declared = _declared_trailer(data)
    if declared is not None and _scan_dictionary(data, declared, MAX_TRAILER_SCAN)[1]:
        return True

    # And the fallback, for a file damaged, truncated, or written by hand, which
    # is the file that needs one most -- and for the file whose `startxref` was
    # written by somebody hiding the trailer it points away from.
    #
    # Every trailer in the file, newest first, until the reading itself costs too
    # much. `rfind` backwards rather than `finditer` forwards: the forward list
    # was built in full and then sliced, so six million tokens in a 68 KiB
    # archive cost 337 MiB of offsets nobody would look at, and a `deque` of the
    # last few is the window this is here to stop using.
    budget, end = MAX_TRAILER_BYTES, len(data)
    while budget > 0:
        at = data.rfind(b"trailer", 0, end)
        if at == -1:
            return False
        end = at
        # Examining a token costs the look-back, whether or not it turns out to
        # be a keyword. Only the dictionaries were charged before, and a decoy
        # reaches no dictionary: the scan stepped over one space and returned,
        # so a file of them cost one byte each and was examined once per token.
        budget -= min(MAX_LINE_LOOKBACK, at)
        if not _is_a_keyword_here(data, at, len(b"trailer")):
            continue
        spent, found = _scan_dictionary(data, at + len(b"trailer"),
                                        min(MAX_TRAILER_SCAN, budget))
        if found:
            return True
        budget -= max(spent, 1)          # never free, or a decoy is unbounded
    return False


def _declared_trailer(data: bytes):
    """The offset of the trailer dictionary the file's own `startxref` names.

    Two shapes reach it. A classic cross-reference table begins `xref` and the
    dictionary follows the table, however long that table is -- so it is found by
    one `bytes.find` from the declared offset, which is a memchr rather than a
    Python loop. A cross-reference *stream* (PDF 1.5 and later) has no `trailer`
    keyword at all: the dictionary is the stream object's own, and it opens
    within a few bytes of the offset. `None` if the file declares nothing usable.
    """
    # The last one in the file, found by scanning back from the end -- not by
    # looking inside a window at the end. A reader reads the last 1024 bytes
    # because that is where the format promises it; taking that as *our* bound
    # left one more thing an appender could push out of view, and five thousand
    # decoys did. `rfind` is a memchr backwards over the whole file, which costs
    # one pass and takes no guess.
    at = data.rfind(b"startxref")
    if at == -1:
        return None
    hit = _STARTXREF.match(data, at)
    if hit is None:
        return None
    offset = int(hit.group(1))
    if not 0 < offset < len(data):
        return None
    if data[offset:offset + 4] == b"xref":
        found = data.find(b"trailer", offset)
        return None if found == -1 else found + len(b"trailer")
    # A cross-reference *stream* is an object, so the offset names `4 0 obj` and
    # the dictionary opens after that header -- which the scan, requiring `<<`,
    # declined to read. So the docstring here described a branch that could not
    # work, forty lines under another one saying such a file "comes back False".
    # It was the second that was true. Stepping over the header is what makes the
    # first true instead, and every PDF 1.5 and later puts its trailer this way.
    obj = _OBJ_HEADER.match(data, offset)
    return obj.end() if obj else offset


def _is_a_keyword_here(data: bytes, at: int, length: int) -> bool:
    """Whether `data[at:at + length]` is a token and not part of a comment.

    Two things the forward `\\btrailer\\b` search did not have to say out loud.
    Searching backwards takes a literal, so the word boundary is checked here --
    without it `endtrailer` and `trailers` are candidates.

    And a `%` earlier on the same line makes everything after it a comment, all
    the way to the newline, which is the whole of what the decoy attack was: the
    word `trailer` written where the format says nothing reads it. Skipping those
    is not a bound, it is the format -- a conformant reader never saw them
    either. It also stops them from costing anything, because the scan's lead-in
    skips comments looking for `<<` and a run of them walks forward through all
    the rest.

    A `%` inside a string on the same line would make this decline to read a real
    trailer. Writers put `trailer` at the start of its line, the declared
    `startxref` finds that file anyway, and the alternative is tokenising the
    whole file to answer one question about its last few bytes.
    """
    before = data[at - 1:at] if at else b""
    after = data[at + length:at + length + 1]
    if before.isalnum() or before == b"_" or after.isalnum() or after == b"_":
        return False
    window = data[max(0, at - MAX_LINE_LOOKBACK):at]
    cut = max(window.rfind(b"\n"), window.rfind(b"\r"))
    return b"%" not in window[cut + 1:]


def _end_of_comment(data: bytes, i: int, limit: int) -> int:
    """One past the newline that ends the comment starting at `i`.

    Both the lead-in and the dictionary body need this, and when only one of them
    had it a comment between `trailer` and `<<` made the dictionary invisible.
    """
    # One pass. Asking `find` for each of `\n` and `\r` separately meant that a
    # dictionary containing only one of them paid a failing scan to the end of
    # the budget for the other -- on *every* comment. Sixty-four dictionaries of
    # comments cost 11.6 seconds from an archive that deflates to five kilobytes.
    hit = _NEWLINE.search(data, i, limit)
    return (hit.start() if hit else limit) + 1


def _scan_dictionary(data: bytes, start: int, budget: int):
    """`(bytes read, whether the dictionary opening at `start` has `/Encrypt`)`.

    Reads at most `budget` bytes of it. The count went away once, because a
    caller spending one budget across a whole file in *file order* let an
    ordinary earlier trailer -- a long `/ID`, a long `/Info` -- hide the
    encrypted one behind it. The caller now spends it from the end backwards, so
    the authoritative trailer is read first and what an earlier one costs no
    longer matters; what the count buys is a bound on the total work that cannot
    be pushed by appending, the way every bound on *where to look* could be.

    The key is only a key where a key can be: directly inside this dictionary,
    not in an array and not in a nested one, and outside every string and
    comment. Matching at any depth counted an array element and a nested
    dictionary's value, neither of which is the trailer's encryption reference.
    """
    limit = min(len(data), start + budget)
    i = start
    # Whitespace *and* comments. A comment is legal between the keyword and the
    # dictionary, and skipping them inside but not at the door meant a file that
    # wrote one there had its dictionary declared absent -- the same asymmetry
    # this scan has produced four times now, one place at a time. So both places
    # call the one function, and there is no longer a door to forget.
    while i < limit:
        b = data[i:i + 1]
        if b in b" \t\r\n\f\x00":
            i += 1
            continue
        if b == b"%":
            i = _end_of_comment(data, i, limit)
            continue
        break
    if data[i:i + 2] != b"<<":
        return i - start, False          # no dictionary opens here

    depth, in_array = 0, 0
    while i < limit:
        b = data[i:i + 1]

        if b == b"%":                    # comment, to the end of the line
            i = _end_of_comment(data, i, limit)
            continue

        if b == b"(":                    # literal string: nested, backslash escapes
            i, nest = i + 1, 1
            while i < limit and nest:
                c = data[i:i + 1]
                if c == b"\\":
                    i += 2
                    continue
                nest += (c == b"(") - (c == b")")
                i += 1
            continue

        pair = data[i:i + 2]
        if pair == b"<<":
            depth += 1
            i += 2
            continue
        if pair == b">>":
            depth -= 1
            i += 2
            if depth <= 0:
                return i - start, False
            continue

        if b == b"<":                    # hex string, which may hold `3c3c`
            close = data.find(b">", i + 1, limit)
            i = (close + 1) if close != -1 else limit
            continue

        if b == b"[":
            in_array += 1
            i += 1
            continue
        if b == b"]":
            in_array = max(0, in_array - 1)
            i += 1
            continue

        # Only where a key of *this* dictionary can be: directly inside it, not
        # in an array and not in a nested one. Matching at any depth counted an
        # array element and a nested dictionary's value, neither of which is the
        # trailer's encryption reference -- and a false positive here tells a
        # producer to strip protection from a file that has none.
        if (b == b"/" and depth == 1 and not in_array
                and _ENCRYPT_REF.match(data, i, limit)):
            return i - start, True

        i += 1
    return i - start, False


MAX_STREAM_SCAN = 400_000        # compressed bytes read after each stream marker
MAX_INFLATED_PER_STREAM = 4_000_000   # and what we will let one of them become
MAX_STREAMS = 512                     # zlib is cheap per call; a million calls are not
MAX_INFLATED_TOTAL = 32_000_000       # the whole budget for one file
# And the whole budget for one read, however many files it opens. The line above
# bounds a file; a container declares many, and a caller that reads them all
# spends that cap once per file with nothing measuring the product. A 5.7 MB
# archive of 150 declared PDFs inflated 4.47 GiB in 12.7 seconds and returned
# exit 0 -- through a door the archive reader's own 4 GiB whole-read ceiling
# does not watch, because the members it hands over are 38 KiB each and it is
# the PDF scan that expands them.
#
# 4 GiB, the same number `docs/scope.md` already promises for one read. It is
# reachable by ordinary input and the first version of this note said otherwise:
# "the scan stops at the first PDF/A claim it finds, and every PDF in the corpus
# carries its claim in uncompressed bytes -- 0 inflated, measured". That is
# circular. The scan short-circuits only on files that carry a claim, which are
# the ones that would have passed anyway; a file with no claim is scanned to the
# per-file cap, and files with no claim are what the report exists to name.
# Measured over the PDFs on one ordinary machine: a third of them inflate past a
# megabyte and the largest reaches the 32 MB cap, so about 126 documents spend
# this ceiling. The budget therefore has to cost as little as possible when it
# runs out, which is why it stops inflation and nothing else.
MAX_INFLATED_PER_READ = 4 * 1024 * 1024 * 1024


@dataclass(frozen=True)
class PdfFacts:
    is_pdf: bool
    header: str = ""
    encrypted: bool = False
    pdfa_claim: Optional[str] = None   # e.g. "2b" — a CLAIM, never a verdict


# `_OBJ_HEADER` cannot be turned on a whole file. `\d+\s+\d+\s+obj` over 200 KB
# of digits and no match spends **192.9 seconds**, measured: at every one of the
# 200,000 start positions `\d+` swallows the rest and gives it back one character
# at a time. Anchored at a known offset, as the trailer walk uses it, that is one
# attempt and fine. Asked to search, it is a denial of service -- and this repair
# was one line away from shipping it.
#
# So: find the literal, then look backwards over a fixed window. `bytes.find` is
# linear and the window is 48 bytes, so the work per occurrence is constant and
# the bounded repetitions cannot backtrack into the same shape. 0.0000 seconds
# on the same input, same answer.
MAX_OBJ_PROBES = 4096     # occurrences of `obj` examined before answering no
_OBJ_BEFORE = re.compile(rb"\d{1,10}[\x00\t\n\f\r ]{1,16}\d{1,5}[\x00\t\n\f\r ]{1,16}$")


#: What may follow `obj` and leave it a token: whitespace, a PDF delimiter, or
#: the end of the file. Without this, `find` matched inside a longer word and
#: `1 0 objx` was a PDF -- the eighteen-byte text file this check exists to
#: catch, needing only different bytes.
_AFTER_OBJ = b"\x00\t\n\f\r ()<>[]{}/%"


def _has_an_indirect_object(data: bytes) -> Optional[bool]:
    """Does anything in here look like `12 0 obj`? `None` if we stopped looking.

    A PDF has a document catalog and a catalog is an indirect object, so a file
    with none is not a PDF document however it begins.

    Three answers, not two. The cap has to stay -- 64 MB of `obj` costs 15.6
    seconds uncapped, and a member may be 512 MB -- and reporting its exhaustion
    as `False` made a budget into a fact about the file: a conforming PDF whose
    only oddity is a long comment holding 4096 occurrences of the word was
    reported as carrying no indirect object -- an error about the container, on
    the one file whose remedy says there is no second option. That is a budget
    made into a fact about a file, which is the category error this package
    exists to keep out of a caller's report. `None` is "we did not finish
    looking", and a caller must not turn it into an accusation.
    """
    at = tried = 0
    while tried < MAX_OBJ_PROBES:
        at = data.find(b"obj", at)
        if at < 0:
            return False
        after = data[at + 3:at + 4]
        if (not after or after in _AFTER_OBJ) and \
                _OBJ_BEFORE.search(data[max(0, at - 48):at]):
            return True
        at += 3
        tried += 1
    return None


def _haystacks(data: bytes, allowance: Optional[List[int]] = None,
               cut: Optional[List[Optional[str]]] = None):
    """The raw bytes, then each stream inflated — under a budget.

    A PDF stream can expand about a thousandfold, and we are looking for one
    short XMP packet. Inflating everything to find it lets a 3 MB file cost
    gigabytes, so both the per-stream and the total output are bounded, and so
    is the number of streams we will even try.

    `allowance` is a one-element list holding what the whole read may still
    inflate, and it is decremented here. Passing it in rather than returning a
    total is what lets the *next* file in the same read start from what is left:
    a caller that only learned the cost afterwards would have already paid it,
    once per file, which is the shape this bound exists to stop.
    """
    yield data
    spent = 0
    cap = (MAX_INFLATED_TOTAL if allowance is None
           else min(MAX_INFLATED_TOTAL, allowance[0]))
    for seen, m in enumerate(_STREAM.finditer(data)):
        if seen >= MAX_STREAMS or spent >= cap:
            # Stopping here used to be silent, and a caller that cannot tell
            # "searched and found nothing" from "stopped searching" has to
            # guess -- every one of them guessed the first.
            #
            # Which of the three stopped it, too. They do not have the same
            # answer: a delivery split into more containers gets past an
            # allowance spent across the read and gets nowhere against a ceiling
            # one file reached on its own.
            if cut is not None:
                # Which limit `cap` actually was, not whether the allowance
                # happened to reach zero at the same moment. `allowance[0] <= 0`
                # answers the second question, and there is a window where the
                # two disagree: a file whose own ceiling stopped it can also
                # spend the last of an allowance that was larger. It was
                # reported as the read's, and the read's remedy is "split the
                # delivery", which does nothing about a per-file ceiling.
                cut[0] = ("streams" if seen >= MAX_STREAMS
                          else "read" if cap < MAX_INFLATED_TOTAL
                          else "file")
            return
        chunk = data[m.end():m.end() + MAX_STREAM_SCAN]
        try:
            out = zlib.decompressobj().decompress(chunk, MAX_INFLATED_PER_STREAM)
        except zlib.error:
            continue
        spent += len(out)
        if allowance is not None:
            allowance[0] -= len(out)
        yield out


def _packets(hay: bytes):
    """The XMP packets in one haystack, in linear time.

    An unterminated opener ends the search for that kind outright: if there is no
    closing marker after this opener there is none after any later one either, so
    there is nothing to gain by trying them all -- which is exactly what the old
    pattern did, once per opener, over the whole buffer.
    """
    low = hay.lower()
    # Offsets first, then the file's own order. Taking each *kind* in turn meant
    # every `<?xpacket>` was yielded before any bare `<x:xmpmeta>` however late
    # it sat, so which of two disagreeing claims a caller saw was decided by
    # packet syntax -- and packet syntax says nothing about which packet is the
    # document's own, an attachment's XMP being wrapped as often as the
    # catalog's. Spans and not slices: three kinds times `MAX_XMP_PACKETS` is a
    # bounded list of integer pairs, where the same many slices of a haystack
    # are not bounded by anything worth relying on.
    spans = []
    for start_re, end_lit, tail in _PACKET_KINDS:
        pos = seen = 0
        while seen < MAX_XMP_PACKETS:
            begin = start_re.search(hay, pos)
            if begin is None:
                break
            end = low.find(end_lit, begin.end())
            if end < 0:
                break
            stop = end + len(end_lit)
            if tail is not None:
                closer = low.find(tail, stop)
                if closer < 0:
                    break
                stop = closer + len(tail)
            spans.append((begin.start(), stop))
            pos, seen = stop, seen + 1
    for begins, stop in sorted(spans):
        yield hay[begins:stop]


def _claim_in(xmp: bytes) -> Optional[str]:
    """The PDF/A part and conformance level a single XMP packet claims, if any.

    Prefixes come from the packet's own namespace declarations. `pdfaid` is tried
    when the packet declares none, because a producer may bind it on an ancestor
    the packet regex did not capture -- but a prefix bound to some *other* URI is
    not a claim, and matching any prefix at all would turn an unrelated schema
    with a `part` element into one.
    """
    prefixes = []
    for m in _PDFA_NS.finditer(xmp):
        if m.group(1) not in prefixes:
            prefixes.append(m.group(1))
        if len(prefixes) >= MAX_PDFA_PREFIXES:
            break
    for pfx in prefixes or [b"pdfaid"]:
        p = re.escape(pfx)
        part = (re.search(rb"<" + p + rb":part>\s*(\d)\s*</" + p + rb":part>", xmp, re.I)
                or re.search(p + rb"[:\s]*part\s*[=>]\s*[\"']?(\d)", xmp, re.I))
        if not part:
            continue
        conf = (re.search(rb"<" + p + rb":conformance>\s*([ABUEFabuef])\s*</"
                          + p + rb":conformance>", xmp, re.I)
                or re.search(p + rb"[:\s]*conformance\s*[=>]\s*[\"']?([ABUEFabuef])",
                             xmp, re.I))
        if conf:
            return part.group(1).decode() + conf.group(1).decode().lower()
        # No level. For part 4 that is what the file is supposed to look like --
        # ISO 19005-4 drops the conformance element -- and `?` said otherwise
        # about every PDF/A-4 file there is. `E` and `F` are that part's two
        # levels and the pattern accepted neither, so a file claiming `4F` was
        # recorded as claiming `4?`: a level it does not claim, built out of a
        # conformance this reader had just read and thrown away.
        #
        # Parts 1 to 3 do require one, so its absence stays worth reporting, and
        # `?` is how it is carried. It is this reader's punctuation and not the
        # file's, so a caller printing it inside a quoted claim is quoting the
        # file for something the file does not say.
        return part.group(1).decode() + ("" if part.group(1) == b"4" else "?")
    return None


def reader(allowance: int) -> Callable[[bytes], tuple]:
    """`read`, with what it inflates charged to one allowance for the whole read.

    Answers `(facts, cut_short)`, where `cut_short` names the limit that ended
    the claim search early or is `None`. That is not the same answer as "no
    claim in it", and the caller has to say which: a scan that did not finish
    found nothing, and reporting that as a fact about the file is the shape
    `PdfFacts` exists to keep out of a report.

    A factory rather than a parameter on `read`, because `read` is a name this
    package has published and a signature it has promised; the pin that admits
    a patch release would carry a changed one onto installed machines.
    """
    left = [allowance]

    def read_one(data: bytes):
        """`(facts, cut_short)`. The budget bounds inflating, nothing else.

        It used to answer `None` for a file the allowance no longer reached,
        before the file was looked at -- and `is_pdf`, the header and the
        encryption flag are read from bytes no stream has to be inflated for.
        So a delivery of ordinary documents, each inflated to the per-file cap
        because it carries no PDF/A claim to stop at, spent the read's budget
        and the caller then had nothing to judge the reserved main document by.
        126 files of the kind an ordinary machine is full of reach 4 GiB, so
        this was not a hypothetical.

        `cut_short` says the search for a claim did not finish, which is the one
        thing the allowance can take away.

        It used to be decided here, before the file was looked at: *was the
        allowance already spent when this one came up*. That is true of every
        file after the boundary and false of the boundary itself -- the file the
        allowance runs out **inside**. That one had the search start, stop
        partway and report nothing found, which is the sentence this pair exists
        to keep out of a report, said about a file that does carry a claim.

        So the scan says whether it stopped, and which limit did it. A file
        that starts with nothing left is not a special case any more -- its cap
        is zero, so the first stream stops it, and the answer is the allowance.
        """
        return _read(data, left)

    return read_one


def read(data: bytes) -> PdfFacts:
    """The four facts, with no allowance across files.

    This drops whether the claim search was cut short, because `PdfFacts` is a
    published shape and the answer has nowhere to go in it. A caller that needs
    to tell "no claim" from "stopped looking" -- and a caller reporting on
    somebody else's file does -- takes `reader()` instead, which returns both.
    """
    return _read(data, None)[0]


def _read(data: bytes, allowance: Optional[List[int]]):
    """`(facts, cut_short)`, where `cut_short` names which limit stopped the
    claim search before it ran out of file, or is `None`.

    `"read"` for the allowance across the whole read, `"file"` for this file's
    own inflation ceiling, `"streams"` for how many streams will be opened at
    all. A caller reporting on somebody else's container needs the difference:
    the first says nothing about this file -- it was not looked at because of
    the files before it -- and the other two are this file being larger than
    what a bounded scan reads.

    Not every limit reaches here. A stream truncated at
    `MAX_INFLATED_PER_STREAM`, a body longer than `MAX_STREAM_SCAN`, a packet
    past `MAX_XMP_PACKETS` -- all of those also end a search early and all of
    them are per file, which is the answer this distinction exists to give.
    Naming them individually would say more than a caller can act on.

    Only ever set when no claim was found. A search that stopped after finding
    one has its answer, and nothing later could add to it.
    """
    if not data.startswith(b"%PDF-"):
        return PdfFacts(is_pdf=False), None
    header = data[:8].decode("latin-1", "replace")
    # The magic is a claim, and this package does not report a claim as a fact.
    # `is_pdf` was that claim spelled another way, so eight bytes -- `%PDF-1.4`
    # and nothing else -- were a PDF, and a documentation container whose
    # reserved main document was those eight bytes returned exit 0.
    #
    # ISO 32000-1 puts a document catalog in every PDF and a catalog is an
    # indirect object, so bytes carrying no `N G obj` are not a PDF document.
    # That is the whole strengthening: not "conformant", not "openable", not
    # "has an end-of-file marker" -- a truncated PDF is a damaged PDF and this
    # package is not the one to say otherwise. Every PDF in the corpus and the
    # fixtures passes it, measured.
    #
    # The other three facts are still read. A caller asking what a file claims
    # about itself gets the same four answers it always did; only `is_pdf`
    # changed its mind about what it is answering.
    # `is not False`, so a search that did not finish is not an accusation. We
    # say "this is not a PDF" only having looked all the way through.
    is_pdf = _has_an_indirect_object(data) is not False
    encrypted = _is_encrypted(data)
    claim = None
    cut = [None]
    for hay in _haystacks(data, allowance, cut):
        for packet in _packets(hay):
            claim = _claim_in(packet)
            if claim:
                break
        if claim:
            break
    return (PdfFacts(is_pdf=is_pdf, header=header, encrypted=encrypted,
                     pdfa_claim=claim),
            cut[0] if claim is None else None)
