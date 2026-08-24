"""Three facts about a PDF, read by scanning bytes.

We deliberately do not use a PDF parsing library. We need the header, whether
the file is encrypted, and what PDF/A level it *claims* in its XMP packet —
three facts. Pulling a full parser for untrusted supplier files, to read three
facts, is a poor trade in both dependency weight and attack surface.

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
_XMP = re.compile(rb"<\?xpacket\s+begin.*?<\?xpacket\s+end.*?\?>"
                  rb"|<x:xmpmeta[\s>].*?</x:xmpmeta>"
                  rb"|<rdf:RDF[\s>].*?</rdf:RDF>", re.I | re.S)

# The trailer references the encryption dictionary indirectly — that is what the
# format requires. `/Encrypt` on its own appears in comments, content streams and
# field names, and used to be reported as an error.
_ENCRYPT_REF = re.compile(rb"/Encrypt\s+\d+\s+\d+\s+R")

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
    encrypted = _ENCRYPT_REF.search(data) is not None
    claim = None
    for hay in _haystacks(data):
        for packet in _XMP.finditer(hay):
            claim = _claim_in(packet.group(0))
            if claim:
                break
        if claim:
            break
    return PdfFacts(is_pdf=True, header=header, encrypted=encrypted, pdfa_claim=claim)
