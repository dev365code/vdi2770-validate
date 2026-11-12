"""`M5` says a language is not an ISO 639 code, and its remedy said to write a
two-letter ISO 639-1 code -- which is no help to someone who wrote `english`
because they did not know what one looks like. The remedy shows two now.

And where the value is a regional form whose first part is a code the table
holds -- `de-DE`, `en_US` -- the remedy names that code. Nothing is guessed:
the code is the value's own first part, and only when the table holds it, so
`jp-JP` is told what a code looks like and not that it means `ja`. A name such
as `english` is not looked up either; this reader keeps no table of names. The
verdict is the one it was.
"""
import io
import zipfile

import pytest
from vdi2770_validate.runner import check_bytes

from conftest import CLEAN_DOCUMENT

META = "VDI2770_Metadata.xml"
SHOWN = "a two-letter ISO 639-1 code, such as en or de,"


def _with_language(value: str) -> bytes:
    base = zipfile.ZipFile(CLEAN_DOCUMENT)
    text = base.read(META).decode("utf-8")
    old = "<Language>de</Language>"
    assert text.count(old) == 1, "the premise"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name in base.namelist():
            z.writestr(name, text.replace(old, f"<Language>{value}</Language>").encode("utf-8")
                       if name == META else base.read(name))
    return out.getvalue()


def _m5(value: str):
    found = [f for f in check_bytes(_with_language(value), "language.zip").findings if f.rule.id == "M5"]
    assert [(f.rule.id, f.severity.value) for f in found] == [("M5", "error")], found
    return found[0]


@pytest.mark.parametrize("value,code", [("de-DE", "de"), ("en_US", "en")])
def test_a_regional_form_is_told_the_code_it_begins_with(value, code):
    f = _m5(value)
    assert f.remedy == (f"Write the language as {code}, the two-letter ISO 639-1 code it begins "
                        f"with; the region after it does not belong here."), f.remedy


def test_a_regional_form_whose_first_part_is_no_code_is_told_what_a_code_looks_like():
    """`jp` is a country, and the language there is `ja`: the remedy does not
    say so, because the table does not."""
    f = _m5("jp-JP")
    assert f.fix is None and SHOWN in f.remedy, f.remedy


def test_a_language_name_is_told_what_a_code_looks_like():
    f = _m5("english")
    assert f.fix is None and SHOWN in f.remedy, f.remedy
