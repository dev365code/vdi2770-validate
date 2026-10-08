"""Syntax nesting is an implementation limit independent of object lookups."""
import pytest

from vdi2770 import _pdfpages, pdfread


@pytest.mark.parametrize("opening,closing", [(b"[", b"]"), (b"<< /Key ", b" >>")])
@pytest.mark.parametrize("levels", [15, 16])
def test_one_object_stops_at_sixteen_syntax_levels(opening, closing, levels):
    body = opening * levels + b"0" + closing * levels
    if levels == 15:
        assert _pdfpages.Syntax(body).value() is not None
    else:
        with pytest.raises(ValueError, match="^object syntax depth limit$"):
            _pdfpages.Syntax(body).value()


@pytest.mark.parametrize("levels", [16, 17])
def test_literal_string_nesting_keeps_its_sixteen_level_boundary(levels):
    body = b"(" * levels + b"text" + b")" * levels
    if levels == 16:
        assert _pdfpages.Syntax(body).value() == body
    else:
        with pytest.raises(ValueError, match="^object syntax depth limit$"):
            _pdfpages.Syntax(body).value()


@pytest.mark.parametrize("body", [b"[[0]]", b"<< /Key << /Key 0 >> >>", b"((text))"])
def test_syntax_depth_does_not_spend_the_page_object_allowance(monkeypatch, body):
    monkeypatch.setattr(pdfread, "MAX_PAGE_OBJECTS", 1)
    assert _pdfpages.Syntax(body).value() is not None


@pytest.mark.parametrize("depth,accepted", [(15, False), (17, True)])
def test_the_separate_syntax_allowance_controls_both_parsers(monkeypatch, depth, accepted):
    monkeypatch.setattr(_pdfpages, "MAX_SYNTAX_DEPTH", depth)
    for body in (b"[" * 15 + b"0" + b"]" * 15, b"(" * 16 + b"text" + b")" * 16):
        if accepted:
            assert _pdfpages.Syntax(body).value() is not None
        else:
            with pytest.raises(ValueError, match="^object syntax depth limit$"):
                _pdfpages.Syntax(body).value()
