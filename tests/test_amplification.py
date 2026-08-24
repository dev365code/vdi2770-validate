"""Bounds on what a small input can make this tool spend.

The ZIP-level caps only bound the *archive*. Amplification that happens after a
member is accepted — inflating a PDF stream, building a parse tree — was
unbounded, so a 3 MB container could cost gigabytes.
"""
import io
import time
import zipfile

import pytest

from conftest import CLEAN_DOCUMENT
from vdi2770 import pdfread, zipread
from vdi2770_validate.runner import check_bytes

BASE = {n: zipfile.ZipFile(CLEAN_DOCUMENT).read(n)
        for n in zipfile.ZipFile(CLEAN_DOCUMENT).namelist()}
META = "VDI2770_Metadata.xml"


def pack(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in members.items():
            z.writestr(n, d)
    return buf.getvalue()


def test_an_inflated_pdf_stream_is_bounded():
    """A PDF may contain a stream that expands ~1000x. We read three facts out
    of a PDF; we do not need to inflate all of it to do that."""
    payload = b"A" * (200 * 1024 * 1024)
    import zlib
    body = b"%PDF-1.7\n" + b"stream\n" + zlib.compress(payload) + b"\nendstream\n"
    inflated = sum(len(h) for h in pdfread._haystacks(body))
    assert inflated < 40 * 1024 * 1024, f"inflated {inflated} bytes from a {len(body)} byte PDF"


def test_a_pdf_full_of_stream_markers_does_not_take_forever():
    body = b"%PDF-1.7\n" + b"stream\n" * 400_000
    started = time.monotonic()
    facts = pdfread.read(body)
    assert time.monotonic() - started < 5, "scanning stream markers should not be quadratic"
    assert facts.is_pdf


def test_metadata_larger_than_we_will_parse_is_refused_not_parsed():
    """A metadata file that compresses well can still be enormous once expanded,
    and a parse tree costs many times the text. Refuse it rather than build it."""
    huge = ("<Document xmlns='http://www.vdi.de/schemas/vdi2770'>"
            + "<DocumentId DomainId='d'>x</DocumentId>" * 700_000
            + "</Document>").encode()
    assert len(huge) > zipread.MAX_METADATA_BYTES
    started = time.monotonic()
    rep = check_bytes(pack({META: huge}), "xmlbomb.zip")
    assert time.monotonic() - started < 10, "the metadata should have been refused, not parsed"
    assert {f.rule.id for f in rep.findings}, "refusing it must still produce a finding"


@pytest.mark.parametrize("name", ["documentcontainer.zip"])
def test_the_bounds_do_not_disturb_an_ordinary_container(name):
    rep = check_bytes(pack(BASE), name)
    assert [f.rule.id for f in rep.findings] == ["P4"]
