"""`MAX_INFLATED_TOTAL` bounds one file. A container declares many.

`docs/scope.md` sells "more than a thousand containers, 64 MiB of metadata, or
4 GiB inflated, in one read" as three limits that bound *the tree*, and says why
the third was added: "a 6.4 MB file inflated two terabytes and returned a clean
verdict". The ZIP reader keeps that promise for the bytes it inflates. The PDF
scan inflates through a door that budget does not watch — the members it reads
are tiny, and each one is then expanded on its own 32 MB allowance — so the
product of declared files and that allowance was bounded by nothing.

Measured before the repair: a 5.7 MB archive of 150 declared PDFs inflated
4.47 GiB in 12.7 seconds and returned exit 0. At `MAX_MEMBERS` the same shape
reaches about 300 GiB.
"""
from __future__ import annotations

import io
import re
import zipfile
import zlib

import pytest

from conftest import A_PDF, CLEAN_DOCUMENT, CLEAN_DOCUMENTATION
from vdi2770 import pdfread
from vdi2770_validate.runner import check_bytes

# Ten streams, so one file wants ten times what a single stream may become.
_BLOB = zlib.compress(b"A" * 400_000)
_GREEDY = A_PDF + b"".join(b"stream\n" + _BLOB for _ in range(10))


def _container(count: int) -> bytes:
    """A conforming document container that also declares `count` greedy PDFs."""
    base = zipfile.ZipFile(CLEAN_DOCUMENT)
    meta = base.read("VDI2770_Metadata.xml").decode("utf-8")
    declared = "\n      ".join(
        f'<DigitalFile FileFormat="application/pdf">g{i}.pdf</DigitalFile>'
        for i in range(count))
    meta = meta.replace("<DigitalFile", declared + "\n      <DigitalFile", 1)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in base.namelist():
            z.writestr(name, meta if name == "VDI2770_Metadata.xml" else base.read(name))
        for i in range(count):
            z.writestr(f"g{i}.pdf", _GREEDY)
    return buf.getvalue()


def _declared_pdfs(raw: bytes) -> set:
    """Every member the metadata declares as a PDF — the scan's whole work list.

    Derived from the container rather than written down, because the clean
    fixture declares PDFs of its own: an expected total that counted only the
    files this test adds is a test that disagrees with the tool about how many
    files there are, and then blames the tool.
    """
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        meta = z.read("VDI2770_Metadata.xml").decode("utf-8")
    return set(re.findall(r'FileFormat="application/pdf">([^<]+)<', meta))


@pytest.fixture
def counted(monkeypatch):
    """Bytes handed back by zlib during one read, and small budgets to hit."""
    monkeypatch.setattr(pdfread, "MAX_INFLATED_PER_STREAM", 400_000)
    monkeypatch.setattr(pdfread, "MAX_INFLATED_TOTAL", 4_000_000)
    total = [0]
    real = zlib.decompressobj

    class Counting:
        def __init__(self, *a, **k):
            self._o = real(*a, **k)

        def decompress(self, data, limit=0):
            out = (self._o.decompress(data, limit) if limit
                   else self._o.decompress(data))
            total[0] += len(out)
            return out

        def __getattr__(self, name):
            return getattr(self._o, name)

    monkeypatch.setattr(zlib, "decompressobj", Counting)
    return total


def test_the_inflation_budget_is_for_the_read_not_for_each_file(counted,
                                                               monkeypatch):
    """Eight greedy files, and a read allowed less than three of them."""
    assert pdfread.MAX_INFLATED_PER_READ >= pdfread.MAX_INFLATED_TOTAL, (
        "a read may not be allowed less than the one file it is given")
    ceiling = 10_000_000
    monkeypatch.setattr(pdfread, "MAX_INFLATED_PER_READ", ceiling)
    each = pdfread.MAX_INFLATED_TOTAL

    counted[0] = 0
    check_bytes(_container(8), "greedy.zip")
    # One file may overshoot the ceiling; the next must not start. Before the
    # repair this input cost eight files' worth however many the read had left.
    assert counted[0] <= ceiling + each, (
        f"the read inflated {counted[0]} bytes against a ceiling of {ceiling}")
    assert counted[0] < 8 * each, (
        f"the premise: eight files unbounded is {8 * each} bytes")


def test_a_file_we_stopped_short_of_reading_is_not_called_claimless(counted,
                                                                    monkeypatch):
    """P3 says a bounded scan found no PDF/A claim. It did not scan at all.

    The other findings still stand: what the allowance takes away is the search
    for a claim, so every declared file either had that search run -- and draws
    `P3` when it found none or `P4` when it found one -- or is counted by `Z5`,
    and never both.
    """
    monkeypatch.setattr(pdfread, "MAX_INFLATED_PER_READ", 4_000_000)
    raw = _container(8)
    declared = _declared_pdfs(raw)
    assert len(declared) > 8, "the premise: the clean container declares PDFs too"
    report = check_bytes(raw, "greedy.zip")
    searched = {f.where.member for f in report.findings
                if f.rule.id in ("P3", "P4")} & declared

    stopped = [f for f in report.findings if f.rule.id == "Z5"]
    assert stopped, (
        f"files had their claim search cut short and no finding says so: "
        f"{sorted(f.rule.id for f in report.findings)}")
    said = int(re.search(r"inside (\d+) declared", stopped[0].detail).group(1))
    assert said, "the premise: this read must stop before the last file"

    assert said + len(searched) == len(declared), (
        f"{len(declared)} declared, {len(searched)} searched, {said} said cut short")
    named = re.search(r"cut short for: (.*?)\. Nothing is said", stopped[0].detail).group(1)
    listed = named.replace(", ...", "").split(", ")
    for one in listed:
        assert one not in searched, f"{one} was both searched and counted"
    # Several of them, and not all: a list of one is a count wearing a name, and
    # a list of all of them is what the bound exists to stop. Written against the
    # numbers this test set up rather than against `MAX_NAMED`, which a mutation
    # moves on both sides of an assertion that reads it.
    assert said > 5, "the premise: more files than the sentence will name"
    assert 2 <= len(listed) < said, listed
    assert named.endswith(", ...") or ", ..." in named, named
    # And the budget is quoted the way every other page quotes one.
    assert f"{pdfread.MAX_INFLATED_PER_READ / 1024 ** 3:g} GiB" in stopped[0].detail, (
        stopped[0].detail)


def _real_pdf(decoys: int = 0) -> bytes:
    """A PDF a reader opens, with `decoys` occurrences of `obj` in a comment.

    A comment is legal anywhere between tokens (ISO 32000-1 §7.2.4), so this is
    a conforming file with five indirect objects and nothing unusual about it
    beyond a long remark.
    """
    remark = b"% " + b"obj " * decoys + b"\n" if decoys else b""
    body = (b"%PDF-1.4\n" + remark
            + b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            + b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            + b"3 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n"
            + b"trailer\n<< /Root 1 0 R /Size 4 >>\nstartxref\n0\n%%EOF\n")
    return body


def test_a_budget_running_out_is_not_a_fact_about_the_file(monkeypatch):
    """`P1` is an error about the container whose remedy for the main document
    says there is no second option. Saying it because a *search* gave up is the
    category error this file's first test removed one rule over: a fact about a
    scan that did not happen. The file below carries five indirect objects."""
    monkeypatch.setattr(pdfread, "MAX_OBJ_PROBES", 8)
    facts = pdfread.read(_real_pdf(decoys=64))
    assert facts.is_pdf, (
        "a conforming PDF was reported as carrying no indirect object because "
        "the search for one stopped early")


def test_obj_inside_a_longer_word_is_not_an_indirect_object():
    """`bytes.find` matches anywhere. Without a delimiter on the right, the
    eighteen-byte text file this rule exists to catch needs only different
    bytes: `1 0 objx` passed."""
    assert not pdfread.read(b"%PDF-1.7\n1 0 objx").is_pdf
    assert not pdfread.read(b"%PDF-1.7\n1 0 objects\n").is_pdf
    # And the token is the whole word: matching a prefix of it accepts a file
    # that has no `obj` in it at all.
    assert not pdfread.read(b"%PDF-1.7\n1 0 ob\n").is_pdf
    assert not pdfread.read(b"%PDF-1.7\n1 0 ob").is_pdf
    assert pdfread.read(b"%PDF-1.7\n1 0 obj\n<< >>\nendobj\n").is_pdf
    assert pdfread.read(b"%PDF-1.7\n1 0 obj<</Type/Page>>").is_pdf


def test_spending_the_budget_withholds_the_claim_and_nothing_else(monkeypatch):
    """The ceiling bounds inflation. It was bounding the whole read of a file.

    `is_pdf`, the header and the encryption flag are read from bytes no stream
    has to be inflated for, and the reader was answering `None` before it looked
    at any of them — so a delivery of ordinary documents, each inflated to the
    per-file cap because it carries no PDF/A claim to stop at, spent the read's
    budget and then `P1` stopped firing on `VDI2770_Main.pdf`.
    """
    from conftest import CLEAN_DOCUMENTATION

    monkeypatch.setattr(pdfread, "MAX_INFLATED_PER_READ", 4_000_000)
    monkeypatch.setattr(pdfread, "MAX_INFLATED_TOTAL", 4_000_000)
    monkeypatch.setattr(pdfread, "MAX_INFLATED_PER_STREAM", 400_000)

    base = zipfile.ZipFile(CLEAN_DOCUMENTATION)
    meta = base.read("VDI2770_Main.xml").decode("utf-8")
    declared = "\n      ".join(
        f'<DigitalFile FileFormat="application/pdf">g{i}.pdf</DigitalFile>'
        for i in range(4))
    meta = meta.replace("<DigitalFile", declared + "\n      <DigitalFile", 1)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in base.namelist():
            z.writestr(name, meta if name == "VDI2770_Main.xml"
                       else b"%PDF-1.4" if name == "VDI2770_Main.pdf"
                       else base.read(name))
        for i in range(4):
            z.writestr(f"g{i}.pdf", _GREEDY)
    report = check_bytes(buf.getvalue(), "spent.zip")

    ids = {(f.rule.id, f.where.member) for f in report.findings}
    assert ("P1", "VDI2770_Main.pdf") in ids, (
        f"the reserved main document is eight bytes and nothing said so: {ids}")
    assert ("P3", "VDI2770_Main.pdf") not in ids
    assert any(r == "Z5" for r, _ in ids), ids


def test_the_allowance_is_one_per_read_and_not_one_per_container(counted,
                                                                 monkeypatch):
    """"This read" is the walk, not the archive at the top of it.

    Both tests above use a single container, so building a fresh reader inside
    the per-container loop passed all of them — and a tree of containers each
    paying its own ceiling is the same unbounded product one level up, which is
    the sentence the runner's own comment makes.
    """
    ceiling = 10_000_000
    monkeypatch.setattr(pdfread, "MAX_INFLATED_PER_READ", ceiling)
    each = pdfread.MAX_INFLATED_TOTAL

    inner = _container(8)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Main.xml",
                   zipfile.ZipFile(CLEAN_DOCUMENTATION).read("VDI2770_Main.xml"))
        z.writestr("VDI2770_Main.pdf",
                   zipfile.ZipFile(CLEAN_DOCUMENTATION).read("VDI2770_Main.pdf"))
        for i in range(3):
            z.writestr(f"child{i}.zip", inner)

    counted[0] = 0
    check_bytes(buf.getvalue(), "tree.zip")
    assert counted[0] <= ceiling + each, (
        f"three containers inflated {counted[0]} bytes against one ceiling of "
        f"{ceiling}; the allowance is being handed out per container")


def test_one_files_allowance_is_the_smaller_of_the_two(counted, monkeypatch):
    """`MAX_INFLATED_TOTAL` bounds a file and the read's allowance bounds what
    is left. Taking only the first lets the file that spends the last of the
    budget overshoot by a whole file's worth, however little was left."""
    monkeypatch.setattr(pdfread, "MAX_INFLATED_PER_READ", 1)
    counted[0] = 0
    pdfread.reader(1)(_GREEDY)
    assert counted[0] <= pdfread.MAX_INFLATED_PER_STREAM, (
        f"one byte of allowance bought {counted[0]} bytes of inflation")
