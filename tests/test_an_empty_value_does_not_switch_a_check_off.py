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


def _documentation_with_status(tmp_path, written: str):
    """The clean documentation container with its main document's status set.

    `written` is put in place of the whole `StatusValue="…"` attribute, so ""
    removes the attribute and `StatusValue=""` empties it.
    """
    import io
    import re
    import zipfile

    from conftest import CLEAN_DOCUMENTATION

    base = zipfile.ZipFile(CLEAN_DOCUMENTATION)
    meta = base.read("VDI2770_Main.xml").decode("utf-8")
    was = re.search(r'StatusValue="[^"]*"', meta)
    assert was, "the premise: the fixture declares one"
    p = tmp_path / "d.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in base.namelist():
            z.writestr(name, meta.replace(was.group(0), written, 1)
                       if name == "VDI2770_Main.xml" else base.read(name))
    p.write_bytes(buf.getvalue())
    return str(p)


def test_a_main_document_with_no_status_at_all_is_not_released_either(tmp_path):
    """`M7` fired for `Draft` and stayed quiet for an empty value and for no
    value — the truthiness guard this whole file is about, eleven lines below a
    comment condemning it in `M8`.

    Nothing here defers to the schema layer, and the argument that carried the
    `M5` repair does not apply: `StatusValue` is an enumeration of `InReview`
    and `Released`, so the schema rejects an empty one. Two rules saying a true
    thing about one defect is the ordinary overlap `Draft` has always had.
    """
    for written in ('StatusValue=""', 'StatusValue="   "', ""):
        fired = {f.rule.id for f in check_file(
            _documentation_with_status(tmp_path, written)).findings}
        assert "M7" in fired, f"{written!r}: {sorted(fired)}"


def test_that_finding_does_not_quote_a_status_the_file_does_not_carry(tmp_path):
    """The model reads an absent attribute, an empty one and a blank one to one
    value, so a finding that quotes it says `LifeCycleStatus is ''` — which is
    not what any of the three files say."""
    report = check_file(_documentation_with_status(tmp_path, ""))
    said = [f for f in report.findings if f.rule.id == "M7"]
    assert said, sorted({f.rule.id for f in report.findings})
    detail = said[0].detail or ""
    assert "is ''" not in detail, detail
    for where in ("absent", "StatusValue", "blank"):
        assert where in detail, f"{where!r} is not among the places to look: {detail}"


def test_a_document_container_is_still_not_the_main_document(tmp_path):
    """After the guard goes, the container's kind is the only thing keeping this
    rule out of a document container."""
    import io
    import re
    import zipfile

    from conftest import CLEAN_DOCUMENT

    base = zipfile.ZipFile(CLEAN_DOCUMENT)
    meta = base.read("VDI2770_Metadata.xml").decode("utf-8")
    was = re.search(r'StatusValue="[^"]*"', meta)
    p = tmp_path / "doc.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in base.namelist():
            z.writestr(name, meta.replace(was.group(0), "", 1)
                       if name == "VDI2770_Metadata.xml" else base.read(name))
    p.write_bytes(buf.getvalue())
    assert "M7" not in {f.rule.id for f in check_file(str(p)).findings}
