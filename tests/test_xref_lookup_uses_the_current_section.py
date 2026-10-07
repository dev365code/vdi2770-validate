"""Declared object lookup follows ISO 32000-1 §§7.5.4 and 7.5.8.4."""
import pytest

from conftest import ROOT
from vdi2770 import _pdfpages, pdfread


@pytest.fixture
def generated(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    import page_fixtures

    return page_fixtures


@pytest.mark.parametrize("options", [{}, {"conflict": True}, {"pages_in_stream": True},
                                     {"conflict": True, "previous": True}])
def test_a_hybrid_section_uses_its_table_before_its_stream(generated, options):
    body = generated.hybrid(**options)
    reader = _pdfpages.PageReader(body, None, [pdfread.MAX_INFLATED_TOTAL])
    assert reader.count() == 7
    value, stream_at = reader.object(_pdfpages.Ref(200, 0))
    assert value == {"Marker": _pdfpages.Name("Hidden")} and stream_at is None


@pytest.mark.parametrize("total,ranges", [(3300, None), (10000, None),
                                         (3300, [(0, 100), (100, 3200)]),
                                         (3300, [(100, 3200), (0, 100)])])
def test_classic_table_size_does_not_spend_an_object_window(generated, total, ranges):
    facts = pdfread.read(generated.table_pdf(total, ranges=ranges), page_count=True)
    assert facts.page_count == 7 and facts.page_count_why is None


@pytest.mark.parametrize("width", [19, 21])
def test_classic_rows_still_have_exactly_twenty_bytes(generated, width):
    facts = pdfread.read(generated.table_pdf(row_width=width), page_count=True)
    assert facts.page_count is None and "damaged xref row" in facts.page_count_why


def test_classic_subsection_headers_stop_at_their_own_cap(generated):
    ranges = [(n, 1) for n in range(pdfread.MAX_XREF_SUBSECTIONS + 1)] + [(100, 1)]
    facts = pdfread.read(generated.table_pdf(ranges=ranges), page_count=True)
    assert facts.page_count is None and "xref subsection limit" in facts.page_count_why


def test_large_tables_keep_the_page_object_window_bounded(generated):
    facts = pdfread.read(generated.classic(padding=pdfread.MAX_PAGE_OBJECT_WINDOW), page_count=True)
    assert facts.page_count is None and "window" in facts.page_count_why
    assert pdfread.read(generated.table_pdf(10000), page_count=True).page_count == 7


def test_classic_lookup_cost_is_headers_and_requested_rows(generated):
    class Charged(bytes):
        sliced = []
        searched = 0

        def __getitem__(self, key):
            value = super().__getitem__(key)
            if isinstance(key, slice):
                self.sliced.append(len(value))
            return value

        def rfind(self, sub, start=0, end=None):
            end = len(self) if end is None else end
            self.searched += end - start
            return super().rfind(sub, start, end)

    costs = []
    for total in (3300, 10000):
        body = Charged(generated.table_pdf(total))
        body.sliced = []
        reader = _pdfpages.PageReader(body, None, [pdfread.MAX_INFLATED_TOTAL])
        assert reader.count() == 7
        assert body.sliced.count(20) == 2, "only the two requested classic rows are read"
        assert max(body.sliced) <= pdfread.MAX_PAGE_OBJECT_WINDOW
        assert len(body.sliced) <= 8
        assert body.searched == len(body)
        costs.append((total, len(body), len(body.sliced), sum(body.sliced), body.searched))
    assert costs[1][3] <= costs[0][3] + 128
    print("classic-xref-cost-coefficients", costs)


def test_an_object_stream_length_can_be_one_indirect_integer(generated):
    body = generated.compressed(length_mode="integer")
    reader = _pdfpages.PageReader(body, None, [pdfread.MAX_INFLATED_TOTAL])
    assert reader.count() == 7
    direct = _pdfpages.PageReader(generated.compressed(), None, [pdfread.MAX_INFLATED_TOTAL])
    assert direct.count() == 7
    assert reader.objects == direct.objects + 1
    assert _pdfpages.Ref(104, 0) in reader.cache


def test_an_indirect_stream_length_spends_the_object_allowance(generated, monkeypatch):
    monkeypatch.setattr(pdfread, "MAX_PAGE_OBJECTS", 4)
    assert pdfread.read(generated.compressed(), page_count=True).page_count == 7
    facts = pdfread.read(generated.compressed(length_mode="integer"), page_count=True)
    assert facts.page_count is None and "object limit 4" in facts.page_count_why


@pytest.mark.parametrize("mode", ["noninteger", "missing", "reference"])
def test_an_object_stream_length_must_resolve_to_an_integer(generated, mode):
    facts = pdfread.read(generated.compressed(length_mode=mode), page_count=True)
    assert facts.page_count is None and "stream Length" in facts.page_count_why


def test_a_cross_reference_stream_length_remains_direct(generated):
    facts = pdfread.read(generated.compressed(xref_length=True), page_count=True)
    assert facts.page_count is None and facts.page_count_why == "stream Length integer range or type"
