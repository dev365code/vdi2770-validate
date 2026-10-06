"""ISO 32000-1's Count is a declaration, not a rendering or a leaf walk."""
import json
import zipfile

import pytest

import vdi2770
from conftest import FIXTURES

CASES = json.loads((FIXTURES / "pages/MANIFEST.json").read_text(encoding="utf-8"))


def pdf(name):
    with zipfile.ZipFile(FIXTURES / "pages" / (name + ".zip")) as archive:
        return archive.read("B.pdf")


@pytest.mark.parametrize("name", CASES)
def test_the_model_keeps_the_original_number_of_pages(name):
    with zipfile.ZipFile(FIXTURES / "pages" / (name + ".zip")) as archive:
        data = archive.read("VDI2770_Metadata.xml")
    document = vdi2770.build_document(vdi2770.parse_xml(data), vdi2770.Location(member="VDI2770_Metadata.xml"))
    assert document.versions[0].number_of_pages == CASES[name]["number"]
    assert document.versions[0].src.line and document.versions[0].src.column is not None


@pytest.mark.parametrize("name", CASES)
def test_the_reader_follows_the_declared_page_tree(name):
    facts = vdi2770.read_pdf(pdf(name), page_count=True)
    expected = CASES[name]["page_count"]
    if isinstance(expected, int):
        assert facts.page_count == expected
        assert facts.page_count_why is None
    elif expected is None:
        assert facts.encrypted and facts.page_count is None
    else:
        assert facts.page_count is None
        assert expected in facts.page_count_why
    assert facts.is_pdf is True
    assert facts.pdfa_claim == "2b"


def test_an_unrequested_page_count_costs_nothing():
    facts = vdi2770.read_pdf(pdf("different"))
    assert facts.page_count is None and facts.page_count_why is None


def test_a_real_number_is_not_read_as_an_integer():
    body = pdf("real-count")
    facts = vdi2770.read_pdf(body, page_count=True)
    assert facts.page_count is None and "integer" in facts.page_count_why


def test_a_large_pdf_integer_is_refused_before_int_conversion():
    body = pdf("large-count")
    facts = vdi2770.read_pdf(body, page_count=True)
    assert facts.page_count is None and "range" in facts.page_count_why


def test_the_page_count_does_not_follow_an_attachment_tree():
    body = pdf("equal")
    # A second catalog/page tree outside Root cannot choose the result.
    body += b"\n200 0 obj << /Type /Catalog /Pages 201 0 R >> endobj\n201 0 obj << /Count 99 >> endobj\n"
    assert vdi2770.read_pdf(body, page_count=True).page_count == 7


def test_page_reading_windows_are_bounded_and_the_file_search_is_linear(monkeypatch):
    from vdi2770 import _pdfpages, pdfread

    real = _pdfpages.PageReader.window
    sampled = []

    def counted(self, at):
        out = real(self, at)
        sampled.append(len(out))
        return out

    class Charged(bytes):
        searched = 0

        def rfind(self, sub, start=0, end=None):
            end = len(self) if end is None else end
            self.searched += end - start
            return super().rfind(sub, start, end)

    monkeypatch.setattr(_pdfpages.PageReader, "window", counted)
    costs = []
    for size in (100_000, 400_000, 1_600_000):
        sampled.clear()
        body = Charged(pdf("equal") + b" " * size)
        facts = vdi2770.read_pdf(body, page_count=True)
        assert facts.page_count == 7
        assert sampled and max(sampled) <= pdfread.MAX_PAGE_OBJECT_WINDOW
        assert len(sampled) <= pdfread.MAX_TRAILERS + pdfread.MAX_PAGE_OBJECTS
        assert body.searched <= 4 * len(body)
        costs.append((size, len(sampled), sum(sampled), body.searched))
    assert len({c[1] for c in costs}) == 1
    assert max(c[2] for c in costs) <= min(c[2] for c in costs) + pdfread.MAX_PAGE_OBJECT_WINDOW
    print("page-cost-coefficients", costs)


def test_object_resolution_stops_at_its_cap():
    import sys

    from conftest import ROOT
    from vdi2770 import pdfread

    sys.path.insert(0, str(ROOT / "tools"))
    try:
        from page_fixtures import append_revision, objects
    finally:
        sys.path.pop(0)
    values = objects(7)
    values[2] = b"<< /Type /Pages /Count 110 0 R >>"
    for n in range(110, 140):
        values[n] = f"{n + 1} 0 R".encode("ascii")
    values[140] = b"7"
    facts = vdi2770.read_pdf(append_revision(b"%PDF-1.7\n", values), page_count=True)
    assert facts.page_count is None
    assert f"object limit {pdfread.MAX_PAGE_OBJECTS}" in facts.page_count_why


def test_xref_resolution_stops_at_its_section_cap(monkeypatch):

    from conftest import ROOT
    from vdi2770 import pdfread

    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    from page_fixtures import append_revision

    body = pdf("equal")
    import re
    for _ in range(pdfread.MAX_TRAILERS):
        previous = int(re.findall(rb"startxref\n([0-9]+)", body)[-1])
        body = append_revision(body, {200: b"0"}, root=None, prev=previous)
    facts = vdi2770.read_pdf(body, page_count=True)
    assert facts.page_count is None
    assert "xref section limit" in facts.page_count_why


@pytest.mark.parametrize("limit", ["file", "read"])
def test_page_reading_spends_the_shared_inflation_before_claim_search(monkeypatch, limit):
    from vdi2770 import pdfread

    body = pdf("compressed-claim")
    real = pdfread.zlib.decompressobj
    expanded = []

    class Counted:
        def __init__(self):
            self.inner = real()

        def decompress(self, body, cap):
            out = self.inner.decompress(body, cap)
            expanded.append(len(out))
            return out

        @property
        def eof(self):
            return self.inner.eof

    monkeypatch.setattr(pdfread.zlib, "decompressobj", Counted)
    if limit == "file":
        monkeypatch.setattr(pdfread, "MAX_INFLATED_TOTAL", 1000)
    read = pdfread.reader(1000 if limit == "read" else pdfread.MAX_INFLATED_PER_READ)
    facts, cut = read(body, page_count=True)
    assert facts.page_count == 7, "claim search must not spend the allowance first"
    assert sum(expanded) <= 1000
    assert facts.pdfa_claim is None
    assert cut == limit
    print("shared-page-inflation", limit, expanded)


def test_a_latest_null_root_is_not_replaced_by_an_older_root(monkeypatch):
    import re

    from conftest import ROOT

    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    from page_fixtures import append_revision

    body = pdf("equal")
    previous = int(re.findall(rb"startxref\n([0-9]+)", body)[-1])
    body = append_revision(body, {200: b"0"}, root=None, prev=previous, extra=b" /Root null")
    facts = vdi2770.read_pdf(body, page_count=True)
    assert facts.page_count is None and "Root" in facts.page_count_why
