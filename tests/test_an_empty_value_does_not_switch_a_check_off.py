"""`M5` fired on an empty `<Language/>` element and stayed silent on an empty
`Language=""` attribute. Same rule, same empty value, opposite verdicts.

The guard was `if d.language and not _iso_ok(d.language)`. `M8`'s own `whyOurs`
names this exact shape: "silently unchecked is how an empty attribute turns the
check off". The schema types the attribute `xs:string` and only requires it to be
present, so an empty one is reachable in a document the schema accepts.
"""
import io
import zipfile

from conftest import CLEAN_DOCUMENT
from vdi2770_validate.runner import check_file

SRC = zipfile.ZipFile(CLEAN_DOCUMENT)
META = SRC.read("VDI2770_Metadata.xml").decode()
PDF = SRC.read("B.pdf")
DOCX = SRC.read("B.docx")

ATTR = '<DocumentDescription Language="de">'
ELEM = "<Language>de</Language>"


def test_the_fixture_has_both_places_this_file_edits():
    assert META.count(ATTR) >= 1 and META.count(ELEM) >= 1


def build(tmp_path, name, meta):
    p = tmp_path / name
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VDI2770_Metadata.xml", meta)
        z.writestr("B.pdf", PDF)
        z.writestr("B.docx", DOCX)
    p.write_bytes(buf.getvalue())
    return str(p)


def m5(path):
    return [f for f in check_file(path).findings if f.rule.id == "M5"]


def test_an_empty_language_attribute_is_reported(tmp_path):
    p = build(tmp_path, "empty_attr.zip", META.replace(ATTR, '<DocumentDescription Language="">', 1))
    hits = m5(p)
    assert hits, [f.rule.id for f in check_file(p).findings]
    assert "DocumentDescription" in (hits[0].detail or ""), hits[0].detail


def test_the_schema_accepts_it_so_this_is_our_rule_to_make(tmp_path):
    """If the schema rejected an empty Language, X2 would already say so and M5
    would be noise. It does not: the attribute is required, not non-empty."""
    p = build(tmp_path, "empty_attr2.zip", META.replace(ATTR, '<DocumentDescription Language="">', 1))
    assert "X2" not in {f.rule.id for f in check_file(p).findings}


def test_an_empty_language_element_is_still_reported(tmp_path):
    p = build(tmp_path, "empty_elem.zip", META.replace(ELEM, "<Language></Language>", 1))
    assert m5(p)


def test_a_valid_language_is_left_alone(tmp_path):
    p = build(tmp_path, "fine.zip", META)
    assert not m5(p)


def test_a_wrong_language_is_still_wrong(tmp_path):
    p = build(tmp_path, "bad.zip", META.replace(ATTR, '<DocumentDescription Language="xx1">', 1))
    assert m5(p)


def test_an_absent_language_attribute_is_the_schema_layer_s_business(tmp_path):
    """The same distinction M2 had to learn: an attribute that is not there has no
    value to be wrong. The schema requires it, X2 says so, and M5 telling the user
    their language code is not ISO 639 would be describing a code that does not
    exist."""
    p = build(tmp_path, "absent_attr.zip", META.replace(ATTR, "<DocumentDescription>", 1))
    got = {f.rule.id for f in check_file(p).findings}
    assert "X2" in got, got
    assert "M5" not in got, got
