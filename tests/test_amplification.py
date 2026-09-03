"""Bounds on what a small input can make this tool spend.

The ZIP-level caps only bound the *archive*. Amplification that happens after a
member is accepted — inflating a PDF stream, building a parse tree — was
unbounded, so a 3 MB container could cost gigabytes.
"""
import io
import time
import zipfile

from conftest import A_PDF, CLEAN_DOCUMENT
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
    body = A_PDF + b"stream\n" + zlib.compress(payload) + b"\nendstream\n"
    sizes = [len(h) for h in pdfread._haystacks(body)]
    # A ceiling with no floor passes when the scanner does nothing: a
    # `_haystacks` that yielded an empty list satisfied the bound below, and a
    # PDF nobody looks inside reports no PDF/A claim at all.
    assert len(body) in sizes, "the raw bytes must be searched, budget or no budget"
    inflated = sum(sizes) - len(body)
    assert inflated > 0, "a budget that inflates nothing is a stub, not a budget"
    assert inflated < 40 * 1024 * 1024, f"inflated {inflated} bytes from a {len(body)} byte PDF"


def test_a_pdf_full_of_stream_markers_does_not_take_forever():
    body = A_PDF + b"stream\n" * 400_000
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


def test_the_bounds_do_not_disturb_an_ordinary_container():
    rep = check_bytes(pack(BASE), "documentcontainer.zip")
    assert [f.rule.id for f in rep.findings] == ["P4"]


def test_a_member_named_as_a_deep_path_does_not_cost_the_machine():
    """`MAX_FOLDER_DEPTH` and `MAX_FOLDERS` had their *size* pinned and their
    *mechanism* untested — the half `test_defences.py`'s docstring says exists
    "because a mechanism that works perfectly at 10**18 protects nobody", read in
    the other direction.

    Removing both caps: a 223 KB archive whose one extra member is named
    `p0/` twenty thousand times cost **604 MB**, and the whole suite stayed
    green. The comment beside the code records the attack — "one member named
    `p0/` thirty-two thousand times cost 1.2 GB" — and had no test.
    """
    import tracemalloc

    from vdi2770_validate.rules.container import MAX_FOLDER_DEPTH, MAX_FOLDERS

    members = dict(BASE)
    members["p0/" * 20_000 + "x.pdf"] = b"x"
    data = pack(members)

    tracemalloc.start()
    try:
        rep = check_bytes(data, "deep.zip")
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()

    assert peak < 60 * 1024 * 1024, (
        f"a {len(data) / 1024:.0f} KB archive cost {peak / 1e6:.0f} MB")

    z9 = [f for f in rep.findings if f.rule.id == "Z9"]
    assert z9, "the premise: this container does store files in folders"
    named = int(z9[0].detail.split()[0])
    assert named <= MAX_FOLDERS, f"{named} folders derived, cap is {MAX_FOLDERS}"
    assert MAX_FOLDER_DEPTH < 20_000, "the depth cap has to be the thing that bit"


def test_looking_for_an_indirect_object_does_not_backtrack(monkeypatch):
    """The repair that made `is_pdf` mean something nearly shipped a worse bug.

    `_OBJ_HEADER` is `\\d+\\s+\\d+\\s+obj`, and it is used anchored at a known
    offset by the trailer walk, where it costs one attempt. Turned on a whole
    file it is quadratic: 200 KB of digits with no match spends **192.9
    seconds**, measured — at each of 200,000 start positions `\\d+` swallows the
    rest and hands it back one character at a time.

    Counted, not timed: a stopwatch here has twice failed under load. The claim
    is that the work per occurrence of `obj` is bounded and that occurrences are
    what bound the loop — so a file of nothing but digits does no regex work at
    all, and a file of nothing but `obj` does one bounded look-behind each,
    capped.
    """
    looks = []
    real = pdfread._OBJ_BEFORE

    class Counting:
        def search(self, window, *a, **k):
            looks.append(len(window))
            return real.search(window, *a, **k)

    monkeypatch.setattr(pdfread, "_OBJ_BEFORE", Counting())

    # First, and deliberately: an implementation that went back to searching
    # with the quadratic pattern does no look-behinds at all, and this fails on
    # the line below rather than after three minutes on the line after it.
    # `obj ` and not `obj`: without the space the delimiter check rejects each
    # occurrence before the look-behind is reached, which is cheaper still but
    # measures the wrong half. This input reaches the look-behind every time.
    assert not pdfread._has_an_indirect_object(b"obj " * 350_000)
    assert len(looks) == pdfread.MAX_OBJ_PROBES, (
        f"{len(looks)} look-behinds; the loop is not what bounds this")
    assert max(looks) <= 48, f"a look-behind read {max(looks)} bytes"

    looks.clear()
    assert not pdfread._has_an_indirect_object(b"1" * 200_000)
    assert looks == [], f"digits carry no `obj` and cost {len(looks)} look-behinds"

    # And it still answers yes to the thing it is looking for.
    assert pdfread._has_an_indirect_object(b"%PDF-1.7\n12 0 obj\n<< >>\nendobj\n")


def test_the_object_probe_gives_up_rather_than_scanning_forever(monkeypatch):
    """The cap is a cap: past it the answer is no, not a longer search."""
    monkeypatch.setattr(pdfread, "MAX_OBJ_PROBES", 3)
    decoys = b"obj " * 10
    assert not pdfread._has_an_indirect_object(decoys + b"1 0 obj\n")
    monkeypatch.setattr(pdfread, "MAX_OBJ_PROBES", 64)
    assert pdfread._has_an_indirect_object(decoys + b"1 0 obj\n")
