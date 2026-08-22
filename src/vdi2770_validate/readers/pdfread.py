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

MAX_STREAM_SCAN = 400_000


@dataclass(frozen=True)
class PdfFacts:
    is_pdf: bool
    header: str = ""
    encrypted: bool = False
    pdfa_claim: Optional[str] = None   # e.g. "2b" — a CLAIM, never a verdict


def _haystacks(data: bytes):
    yield data
    for m in _STREAM.finditer(data):
        chunk = data[m.end():m.end() + MAX_STREAM_SCAN]
        try:
            yield zlib.decompressobj().decompress(chunk)
        except zlib.error:
            continue


def read(data: bytes) -> PdfFacts:
    if not data.startswith(b"%PDF-"):
        return PdfFacts(is_pdf=False)
    header = data[:8].decode("latin-1", "replace")
    encrypted = b"/Encrypt" in data
    claim = None
    for hay in _haystacks(data):
        part = _PART_EL.search(hay) or _PART_AT.search(hay)
        if not part:
            continue
        conf = _CONF_EL.search(hay) or _CONF_AT.search(hay)
        claim = part.group(1).decode() + (conf.group(1).decode().lower() if conf else "?")
        break
    return PdfFacts(is_pdf=True, header=header, encrypted=encrypted, pdfa_claim=claim)
