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

_PART_EL = re.compile(rb"<pdfaid:part>\s*(\d)\s*</pdfaid:part>", re.I)
_CONF_EL = re.compile(rb"<pdfaid:conformance>\s*([ABUabu])\s*</pdfaid:conformance>", re.I)
_PART_AT = re.compile(rb"pdfaid[:\s]*part\s*[=>]\s*[\"']?(\d)", re.I)
_CONF_AT = re.compile(rb"pdfaid[:\s]*conformance\s*[=>]\s*[\"']?([ABUabu])", re.I)
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


def read(data: bytes) -> PdfFacts:
    if not data.startswith(b"%PDF-"):
        return PdfFacts(is_pdf=False)
    header = data[:8].decode("latin-1", "replace")
    encrypted = _ENCRYPT_REF.search(data) is not None
    claim = None
    for hay in _haystacks(data):
        for packet in _XMP.finditer(hay):
            xmp = packet.group(0)
            part = _PART_EL.search(xmp) or _PART_AT.search(xmp)
            if not part:
                continue
            conf = _CONF_EL.search(xmp) or _CONF_AT.search(xmp)
            claim = part.group(1).decode() + (conf.group(1).decode().lower() if conf else "?")
            break
        if claim:
            break
    return PdfFacts(is_pdf=True, header=header, encrypted=encrypted, pdfa_claim=claim)
