"""`NumberOfPages` is checked here, and not by a rule of ours.

`docs/divergences.md` records that the reference's `DV_013` fires on
`numberOfPages < 0` while its own message says "greater than zero", so `0`
passes there. The sentence beside it used to add that this tool "has no
numberOfPages rule yet" -- true about rules, and misleading about coverage: a
reader of that line concludes the condition goes unreported here.

It does not. The schema VDI publishes types the attribute `xs:positiveInteger`,
so `0` and a negative are refused by the schema layer as `X2`, with the
attribute named, the value quoted and the line given. That is a stronger basis
than a rule of ours would have -- `schema` rather than `ours` -- and writing one
would duplicate the check under a weaker obligation.

This file is what stops that sentence from drifting: it is the measurement the
sentence rests on: if the schema or the layer that reads it stops refusing a
zero, the page becomes wrong and this fails with it rather than after somebody
notices.
"""
import io
import zipfile

import pytest
from vdi2770_validate.runner import check_bytes

from conftest import CORPUS

SAMPLE = CORPUS / "container" / "documentcontainer.zip"


def with_page_count(value):
    """The sample container, with `NumberOfPages` set on its document version."""
    out = io.BytesIO()
    with zipfile.ZipFile(SAMPLE) as z, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as o:
        for name in z.namelist():
            data = z.read(name)
            if name.endswith("VDI2770_Metadata.xml"):
                text = data.decode("utf-8")
                assert "<DocumentVersion>" in text, "the sample no longer has a bare DocumentVersion"
                data = text.replace("<DocumentVersion>",
                                    f'<DocumentVersion NumberOfPages="{value}">',
                                    1).encode("utf-8")
            o.writestr(name, data)
    return out.getvalue()


def ids(data):
    return {f.rule.id for f in check_bytes(data, "pages.zip").findings}


@pytest.mark.parametrize("value", ["0", "-3"])
def test_a_page_count_that_is_not_positive_is_refused(value):
    """By the schema, so the finding cites what VDI publishes rather than us."""
    assert "X2" in ids(with_page_count(value)), (
        f'NumberOfPages="{value}" drew no schema finding; `docs/divergences.md` '
        f"says this condition is caught here without a rule of our own")


def test_the_refusal_names_the_attribute_and_the_value():
    """A schema error that says only "does not conform" leaves a sender reading
    a 300-line file for the character that upset it."""
    said = [f for f in check_bytes(with_page_count("0"), "pages.zip").findings
            if f.rule.id == "X2"]
    assert said, "no X2 to read"
    detail = " ".join(f.detail or "" for f in said)
    assert "NumberOfPages" in detail and "0" in detail, detail
    assert any(f.where.line for f in said), (
        f"the refusal gives no line to look at: {[f.where for f in said]}")


def test_a_positive_page_count_is_left_alone():
    """The other half, and the half that decides whether this is a check or a
    nuisance: a delivery that says a true thing draws nothing for saying it."""
    assert "X2" not in ids(with_page_count("7")), (
        'NumberOfPages="7" is a conforming value and drew a schema finding'
    )
