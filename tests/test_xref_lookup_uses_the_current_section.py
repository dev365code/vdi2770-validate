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
