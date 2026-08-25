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
MAX_TRAILER_SCAN = 65536  # the most of one trailer dictionary that is read


def _is_encrypted(data: bytes) -> bool:
    """Whether a trailer dictionary has an `/Encrypt` key.

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

    And one budget for the *file*. Per-keyword bounds were the other half of the
    same mistake: every shape that reached the bound multiplied by however many
    `trailer` keywords a sender cared to write. 16,000 bare ones cost 135
    seconds; when that was fixed, 8,000 that *open* a dictionary cost 28 seconds
    from a 20 KB archive. A total is the only bound with no shape behind it.

    A PDF whose trailer lives in a cross-reference stream has no `trailer`
    keyword and comes back False. That is a miss and not a false alarm, and
    docs/scope.md says so rather than leaving a reader to assume otherwise.
    """
    left = MAX_TRAILER_SCAN
    for hit in _TRAILER.finditer(data):
        if left <= 0:
            break
        found, used = _scan_dictionary(data, hit.end(), left)
        left -= used
        if found:
            return True
    return False


def _scan_dictionary(data: bytes, start: int, budget: int) -> tuple:
    """Look for an `/Encrypt` key in the dictionary opening at `start`.

    Returns `(found, bytes examined)`. Reads at most `budget` bytes, so a caller
    can bound a whole file rather than each dictionary in it.

    The key is only a key where a key can be: at depth one or more, outside every
    string and comment. That is the whole difference between this and the three
    scans before it.
    """
    limit = min(len(data), start + budget)
    i = start
    while i < limit and data[i:i + 1] in b" \t\r\n\f\x00":
        i += 1
    if data[i:i + 2] != b"<<":
        return False, i - start          # no dictionary opens here

    depth = 0
    while i < limit:
        b = data[i:i + 1]

        if b == b"%":                    # comment, to the end of the line
            nl = min((x for x in (data.find(c, i, limit) for c in (b"\n", b"\r"))
                      if x != -1), default=limit)
            i = nl + 1
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
                return False, i - start
            continue

        if b == b"<":                    # hex string, which may hold `3c3c`
            close = data.find(b">", i + 1, limit)
            i = (close + 1) if close != -1 else limit
            continue

        # No `depth > 0` here: the loop returns the moment the dictionary closes,
        # so everything it still sees is inside one. Writing the condition anyway
        # looked like a guard and guarded nothing -- removing it changed no
        # behaviour, which is how it was found.
        if b == b"/" and _ENCRYPT_REF.match(data, i, limit):
            return True, i - start

        i += 1
    return False, limit - start


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
