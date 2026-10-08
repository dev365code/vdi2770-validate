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
    monkeypatch.setattr(pdfread, "MAX_PAGE_OBJECTS", 3)
    assert pdfread.read(generated.compressed(), page_count=True).page_count == 7
    facts = pdfread.read(generated.compressed(length_mode="integer"), page_count=True)
    assert facts.page_count is None and "object limit 3" in facts.page_count_why


@pytest.mark.parametrize("mode", ["noninteger", "missing", "reference"])
def test_an_object_stream_length_must_resolve_to_an_integer(generated, mode):
    facts = pdfread.read(generated.compressed(length_mode=mode), page_count=True)
    assert facts.page_count is None and "stream Length" in facts.page_count_why


def test_a_cross_reference_stream_length_remains_direct(generated):
    facts = pdfread.read(generated.compressed(xref_length=True), page_count=True)
    assert facts.page_count is None and facts.page_count_why == "stream Length integer range or type"


@pytest.mark.parametrize("row", [(0, "f"), (1, "n")])
def test_a_classic_lookup_refuses_a_free_or_changed_generation(generated, row):
    facts = pdfread.read(generated.table_pdf(rows={2: row}), page_count=True)
    assert facts.page_count is None and facts.page_count_why == "xref object is free or its generation changed"


def test_classic_subsections_do_not_overlap_even_outside_size(generated):
    facts = pdfread.read(generated.table_pdf(size=2, ranges=[(0, 101), (2, 1)]), page_count=True)
    assert facts.page_count is None and facts.page_count_why == "xref table subsection overlap or Size range"


def test_a_required_classic_entry_at_size_is_missing(generated):
    facts = pdfread.read(generated.table_pdf(size=2), page_count=True)
    assert facts.page_count is None and facts.page_count_why == "xref object is missing (outside Size)"


@pytest.mark.parametrize("header", [(20, 0), (2, 1)])
def test_an_object_header_has_the_requested_number_and_generation(generated, header):
    facts = pdfread.read(generated.table_pdf(headers={2: header}), page_count=True)
    assert facts.page_count is None and facts.page_count_why == "xref does not point to the declared object header"


def test_a_stream_index_still_requires_all_its_encoded_rows(generated):
    facts = pdfread.read(generated.compressed(outside_index=True), page_count=True)
    assert facts.page_count is None and facts.page_count_why == "damaged xref stream length"


@pytest.mark.parametrize("size,count,reason", [
    (103, 7, None), (2, None, "xref object is missing (outside Size)"),
    (0, None, "xref object is missing (outside Size)"),
    (-1, None, "xref Size integer range or type"),
    ("2.0", None, "xref Size integer range or type"),
])
def test_stream_index_entries_outside_size_are_missing_only_when_requested(generated, size, count, reason):
    body = generated.compressed().replace(b"/Size 104", f"/Size {size}".encode("ascii"))
    facts = pdfread.read(body, page_count=True)
    assert facts.page_count == count and facts.page_count_why == reason


@pytest.mark.parametrize("size,reason", [
    (0, "xref object is missing (outside Size)"),
    (-1, "xref Size integer range or type"),
    ("2.0", "xref Size integer range or type"),
])
def test_invalid_or_empty_table_size_is_a_catchable_refusal(generated, size, reason):
    facts = pdfread.read(generated.table_pdf(size=size), page_count=True)
    assert facts.page_count is None and facts.page_count_why == reason


@pytest.mark.parametrize("required,count,reason", [
    (False, 7, None), (True, None, "xref object is missing (outside Size)"),
])
def test_an_older_out_of_size_entry_does_not_poison_other_lookups(generated, required, count, reason):
    import re

    initial = generated.outside_size(required=required)
    previous = int(re.findall(rb"startxref\n([0-9]+)", initial)[-1])
    body = generated.append_revision(initial, {1000: b"0"}, root=None, prev=previous)
    facts = pdfread.read(body, page_count=True)
    assert facts.page_count == count and facts.page_count_why == reason


def test_a_current_missing_entry_does_not_resurrect_an_older_pages_object(generated):
    import re

    initial = generated.classic()
    previous = int(re.findall(rb"startxref\n([0-9]+)", initial)[-1])
    body = generated.append_revision(initial, {2: b"<< /Count 9 >>"}, prev=previous)
    body = body[:len(initial)] + body[len(initial):].replace(b"/Size 101", b"/Size 2")
    facts = pdfread.read(body, page_count=True)
    assert facts.page_count is None and facts.page_count_why == "xref object is missing (outside Size)"


def test_a_compressed_object_has_generation_zero(generated):
    facts = pdfread.read(generated.compressed(nonzero_generation=True), page_count=True)
    assert facts.page_count is None and facts.page_count_why == "compressed object generation is not zero"


def test_the_section_allowance_does_not_depend_on_the_visit_set(generated, monkeypatch):
    class Untracked(set):
        def add(self, item):
            pass

    reader = _pdfpages.PageReader(generated.prev_cycle(), None, [pdfread.MAX_INFLATED_TOTAL])
    reader.offsets = Untracked()
    section = reader.section
    attempts = []

    def counted(at):
        attempts.append(at)
        # Bound the red run too; the test never depends on a timeout.
        assert len(attempts) <= pdfread.MAX_TRAILERS + 1, "the section cap was bypassed"
        return section(at)

    monkeypatch.setattr(reader, "section", counted)
    with pytest.raises(ValueError, match=f"xref section limit {pdfread.MAX_TRAILERS}"):
        reader.count()
    assert len(attempts) == pdfread.MAX_TRAILERS + 1


def test_a_linearized_trailer_without_root_names_the_missing_root(generated):
    facts = pdfread.read(generated.linearized(root=False), page_count=True)
    assert facts.page_count is None and facts.page_count_why == "trailer Root is missing"


@pytest.mark.parametrize("revisions", [14, 20])
def test_xref_stream_revisions_do_not_spend_page_object_interpretations(generated, revisions):
    reader = _pdfpages.PageReader(generated.compressed_revisions(revisions), None,
                                   [pdfread.MAX_INFLATED_TOTAL])
    assert reader.count() == 7
    assert reader.xref_objects == revisions + 1
    assert reader.objects == 3, "one ObjStm and its two requested objects"
    assert reader.section_count == revisions + 1


def test_xref_stream_revisions_still_stop_at_the_section_allowance(generated):
    facts = pdfread.read(generated.compressed_revisions(pdfread.MAX_TRAILERS), page_count=True)
    assert facts.page_count is None and facts.page_count_why == f"xref section limit {pdfread.MAX_TRAILERS}"


def test_seventeen_page_objects_are_not_given_the_xref_allowance(generated):
    values = generated.objects(7)
    values[2] = b"<< /Type /Pages /Count 110 0 R >>"
    # Catalog + Pages + fifteen integer/reference objects: seventeen reads.
    for number in range(110, 124):
        values[number] = f"{number + 1} 0 R".encode("ascii")
    values[124] = b"7"
    facts = pdfread.read(generated.append_revision(b"%PDF-1.7\n", values), page_count=True)
    assert facts.page_count is None and facts.page_count_why == "object limit 16"


def measured_inflation(monkeypatch):
    actual = pdfread.zlib.decompressobj
    expanded = []

    class Measured:
        def __init__(self):
            self.inner = actual()

        def decompress(self, body, cap):
            out = self.inner.decompress(body, cap)
            expanded.append(len(out))
            return out

        @property
        def eof(self):
            return self.inner.eof

    monkeypatch.setattr(pdfread.zlib, "decompressobj", Measured)
    return expanded


def test_page_inflation_stops_before_a_second_four_mb_xref(generated, monkeypatch):
    body = generated.compressed_revisions(2, row_count=571428)
    expanded = measured_inflation(monkeypatch)
    reader = _pdfpages.PageReader(body, [pdfread.MAX_INFLATED_PER_READ],
                                   [pdfread.MAX_INFLATED_TOTAL])
    why = None
    try:
        reader.count()
    except ValueError as error:
        why = str(error)
    print("page-inflation-counts", expanded, "reason", why)
    assert why is not None and "inflation budget" in why
    assert expanded == [3_999_996], "the second known-size xref must not be inflated"
    assert reader.page_inflated == sum(expanded)
    assert reader.page_inflated <= pdfread.MAX_PAGE_INFLATED_TOTAL


def test_png_work_is_charged_with_xref_and_object_stream_inflation(generated, monkeypatch):
    expanded = measured_inflation(monkeypatch)
    reader = _pdfpages.PageReader(generated.compressed(predictor=True), None,
                                   [pdfread.MAX_INFLATED_TOTAL])
    actual = reader.predict
    processed = []

    def measured(data, parameters):
        if parameters is not None:
            processed.append(len(data))
        return actual(data, parameters)

    monkeypatch.setattr(reader, "predict", measured)
    assert reader.count() == 7
    assert len(expanded) == 2 and processed == [832]
    print("page-work-counts", expanded, processed)
    assert reader.page_inflated == sum(expanded) + sum(processed)


def test_png_processing_uses_the_page_budget_and_reports_an_incomplete_read(generated, monkeypatch):
    import json

    from vdi2770_validate.model import About
    from vdi2770_validate.report import as_json
    from vdi2770_validate.runner import check_file

    from conftest import FIXTURES

    monkeypatch.setattr(pdfread, "MAX_PAGE_INFLATED_TOTAL", 1100, raising=False)
    assert pdfread.read(generated.compressed(), page_count=True).page_count == 7
    report = check_file(str(FIXTURES / "pages/png-xref.zip"))
    pages = [f for f in report.findings if f.rule.id == "P6"]
    assert len(pages) == 1 and pages[0].about is About.TOOL
    assert "inflation budget" in pages[0].detail
    assert json.loads(as_json(report))["read"]["complete"] is False
    assert "Z5" not in {f.rule.id for f in report.findings}
