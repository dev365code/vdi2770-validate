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

import collections
import re
import zlib
from dataclasses import dataclass
from typing import Optional

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

_STARTXREF = re.compile(rb"startxref\s+(\d+)")
_NEWLINE = re.compile(rb"[\r\n]")


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

    A PDF whose trailer lives in a cross-reference stream has no `trailer`
    keyword and comes back False. That is a miss and not a false alarm, and
    docs/scope.md says so rather than leaving a reader to assume otherwise.
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
    if declared is not None and _scan_dictionary(data, declared, MAX_TRAILER_SCAN):
        return True

    # And the fallback, for a file damaged, truncated, or written by hand, which
    # is the file that needs one most. `deque` rather than a list: the list was
    # built in full and then sliced, so six million tokens in a 68 KiB archive
    # cost 337 MiB of offsets nobody would look at.
    tail = collections.deque(_TRAILER.finditer(data), maxlen=MAX_TRAILERS)
    return any(_scan_dictionary(data, hit.end(), MAX_TRAILER_SCAN) for hit in tail)


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
    return offset


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


def _scan_dictionary(data: bytes, start: int, budget: int) -> bool:
    """Whether the dictionary opening at `start` has an `/Encrypt` key.

    Reads at most `budget` bytes of it. It used to return how many it had read
    as well, so a caller could spend one budget across a whole file -- which is
    what made an ordinary earlier trailer able to hide the encrypted one behind
    it. Nothing has needed the count since that was undone, and a return value
    nobody reads is the shape the wrong design leaves behind.

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
        return False                     # no dictionary opens here

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
                return False
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
            return True

        i += 1
    return False


MAX_STREAM_SCAN = 400_000        # compressed bytes read after each stream marker
MAX_INFLATED_PER_STREAM = 4_000_000   # and what we will let one of them become
MAX_STREAMS = 512                     # zlib is cheap per call; a million calls are not
MAX_INFLATED_TOTAL = 32_000_000       # the whole budget for one file


@dataclass(frozen=True)
class PdfFacts:
    is_pdf: bool
    header: str = ""
    encrypted: bool = False
    pdfa_claim: Optional[str] = None   # e.g. "2b" — a CLAIM, never a verdict


def _haystacks(data: bytes):
    """The raw bytes, then each stream inflated — under a budget.

    A PDF stream can expand about a thousandfold, and we are looking for one
    short XMP packet. Inflating everything to find it lets a 3 MB file cost
    gigabytes, so both the per-stream and the total output are bounded, and so
    is the number of streams we will even try.
    """
    yield data
    spent = 0
    for seen, m in enumerate(_STREAM.finditer(data)):
        if seen >= MAX_STREAMS or spent >= MAX_INFLATED_TOTAL:
            return
        chunk = data[m.end():m.end() + MAX_STREAM_SCAN]
        try:
            out = zlib.decompressobj().decompress(chunk, MAX_INFLATED_PER_STREAM)
        except zlib.error:
            continue
        spent += len(out)
        yield out


def _packets(hay: bytes):
    """The XMP packets in one haystack, in linear time.

    An unterminated opener ends the search for that kind outright: if there is no
    closing marker after this opener there is none after any later one either, so
    there is nothing to gain by trying them all -- which is exactly what the old
    pattern did, once per opener, over the whole buffer.
    """
    low = hay.lower()
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
            yield hay[begin.start():stop]
            pos, seen = stop, seen + 1


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
        conf = (re.search(rb"<" + p + rb":conformance>\s*([ABUabu])\s*</" + p + rb":conformance>",
                          xmp, re.I)
                or re.search(p + rb"[:\s]*conformance\s*[=>]\s*[\"']?([ABUabu])", xmp, re.I))
        return part.group(1).decode() + (conf.group(1).decode().lower() if conf else "?")
    return None


def read(data: bytes) -> PdfFacts:
    if not data.startswith(b"%PDF-"):
        return PdfFacts(is_pdf=False)
    header = data[:8].decode("latin-1", "replace")
    encrypted = _is_encrypted(data)
    claim = None
    for hay in _haystacks(data):
        for packet in _packets(hay):
            claim = _claim_in(packet)
            if claim:
                break
        if claim:
            break
    return PdfFacts(is_pdf=True, header=header, encrypted=encrypted, pdfa_claim=claim)
