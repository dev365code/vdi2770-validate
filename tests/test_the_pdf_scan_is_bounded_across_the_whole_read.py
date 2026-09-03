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

from conftest import A_PDF, CLEAN_DOCUMENT
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
    """P3 says a bounded scan found no PDF/A claim. It did not scan at all."""
    monkeypatch.setattr(pdfread, "MAX_INFLATED_PER_READ", 4_000_000)
    raw = _container(8)
    declared = _declared_pdfs(raw)
    assert len(declared) > 8, "the premise: the clean container declares PDFs too"
    report = check_bytes(raw, "greedy.zip")
    judged = {f.where.member for f in report.findings
              if f.rule.id.startswith("P")} & declared

    stopped = [f for f in report.findings if f.rule.id == "Z5"]
    assert stopped, (
        f"files were left unopened and no finding says so: "
        f"{sorted(f.rule.id for f in report.findings)}")
    counted = int(re.search(r"so (\d+) declared", stopped[0].detail).group(1))
    assert counted, "the premise: this read must stop before the last file"

    # Every declared file is either judged or counted as unopened, and never
    # both: a file this scan did not open must not also carry a sentence about
    # what the scan found in it.
    assert counted + len(judged) == len(declared), (
        f"{len(declared)} declared, {len(judged)} judged, {counted} said unopened")
    named = re.search(r"not opened: ([^.]*)", stopped[0].detail).group(1)
    for one in named.replace(", ...", "").split(", "):
        assert one not in judged, f"{one} is both unopened and judged"
