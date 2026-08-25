"""Containers built to slip through. Every one of these was clean once.

The shape of the bug is always the same: a rule guards on a field the document
controls, so emptying the field means "skip" instead of "complain". A validator
that can be switched off by deleting a filename is not a validator.
"""
import io
import zipfile

import pytest

from conftest import CLEAN_DOCUMENT
from vdi2770_validate.model import Severity
from vdi2770_validate.runner import check_bytes

BASE = {n: zipfile.ZipFile(CLEAN_DOCUMENT).read(n)
        for n in zipfile.ZipFile(CLEAN_DOCUMENT).namelist()}
META = "VDI2770_Metadata.xml"


def pack(members, *, duplicate=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in members.items():
            z.writestr(n, d)
        if duplicate:
            z.writestr(*duplicate)
    return buf.getvalue()


def edited(old, new, *, drop=()):
    m = dict(BASE)
    for d in drop:
        m.pop(d)
    text = BASE[META].decode()
    assert text.count(old) >= 1, old
    m[META] = text.replace(old, new, 1).encode()
    return m


def verdict(members, **kw):
    rep = check_bytes(pack(members, **kw), "evasion.zip")
    return {f.rule.id for f in rep.findings}, rep.count(Severity.ERROR)


def test_an_empty_filename_does_not_hide_a_missing_document():
    ids, errors = verdict(edited(
        '<DigitalFile FileFormat="application/pdf">B.pdf</DigitalFile>',
        '<DigitalFile FileFormat="application/pdf"></DigitalFile>', drop=["B.pdf"]))
    assert errors, f"a container with no document at all reported clean: {sorted(ids)}"


def test_a_whitespace_filename_does_not_hide_a_missing_document():
    ids, errors = verdict(edited(
        '<DigitalFile FileFormat="application/pdf">B.pdf</DigitalFile>',
        '<DigitalFile FileFormat="application/pdf">   </DigitalFile>', drop=["B.pdf"]))
    assert errors, f"a container with no document at all reported clean: {sorted(ids)}"


def test_an_empty_language_does_not_switch_off_the_class_name_check():
    ids, _ = verdict(edited(
        '<ClassName Language="de">Technische Spezifikation</ClassName>',
        '<ClassName Language="">COMPLETE NONSENSE</ClassName>'))
    assert {"M3", "M8"} & ids, f"a nonsense class name went unreported: {sorted(ids)}"


def test_a_trailing_space_in_the_classification_system_is_not_a_missing_classification():
    ids, _ = verdict(edited('ClassificationSystem="VDI2770:2018"',
                            'ClassificationSystem="VDI2770:2018 "'))
    assert "M1" not in ids, "a trailing space should not read as 'no classification at all'"


def test_a_document_container_inside_a_document_container_is_reported():
    m = dict(BASE)
    m["inner.zip"] = pack(BASE)
    ids, _ = verdict(m)
    assert ids - {"P4"}, f"a stowaway container went unreported: {sorted(ids)}"


def test_a_duplicate_member_name_is_reported():
    """Two members with one name: readers disagree about which wins, so a
    container can show one thing to us and another to the recipient."""
    ids, _ = verdict(dict(BASE), duplicate=(META, b"<Document/>"))
    assert "Z10" in ids, f"the duplicate name went unreported: {sorted(ids)}"


HOSTILE_METADATA = {
    "1001 levels of nesting":
        b"<Document xmlns='http://www.vdi.de/schemas/vdi2770'>" + b"<a>" * 1001
        + b"</a>" * 1001 + b"</Document>",
    "UTF-16 metadata":
        BASE[META].decode().replace('encoding="UTF-8"', 'encoding="UTF-16"').encode("utf-16"),
    "Latin-1 metadata":
        BASE[META].decode().replace('encoding="UTF-8"', 'encoding="ISO-8859-1"')
        .encode("iso-8859-1"),
}


@pytest.mark.parametrize("label", sorted(HOSTILE_METADATA))
def test_hostile_metadata_produces_a_finding_not_a_traceback(label):
    body = HOSTILE_METADATA[label]
    m = dict(BASE)
    m[META] = body
    ids, _ = verdict(m)          # must not raise
    assert ids, f"{label}: expected a finding"
    # "some finding" is not enough: while the schema layer reported a document
    # it could not finish as a broken installation, this passed on X0 — a
    # finding that told the reader to reinstall the tool. What hostile input
    # must produce is a finding about the input.
    assert ids != {"X0"}, (
        f"{label}: the only thing reported was our own installation")


def test_a_bad_language_on_a_description_is_reported_too():
    """M5 was only ever exercised through DocumentVersion/Language; the
    DocumentDescription branch had no coverage."""
    ids, _ = verdict(edited('<DocumentDescription Language="de">',
                            '<DocumentDescription Language="deutsch">'))
    assert "M5" in ids, f"a bad description language went unreported: {sorted(ids)}"


def test_a_schema_error_whose_path_we_cannot_resolve_still_reports():
    """xsdvalidate walks the reported XPath through our own tree to recover a
    line number. When that walk fails the finding must survive without one."""
    from vdi2770 import xmlread
    from vdi2770_validate import xsdvalidate
    tree = xmlread.parse(b'<Document xmlns="http://www.vdi.de/schemas/vdi2770"/>')
    bad = BASE[META].replace(b"<ClassId>", b"<NotAThing>").replace(b"</ClassId>", b"</NotAThing>")
    errors = xsdvalidate.validate(bad, tree)
    assert errors, "expected the schema to complain"
    assert all("reason" in e for e in errors)


def test_a_repeated_document_identifier_is_reported():
    """The model parsed DocumentId and no rule read it, so a document could
    identify itself twice with the same value and nothing said anything."""
    ids, _ = verdict(edited(
        '<DocumentId DomainId="BSP-OEM">data-sheet-br-01-26</DocumentId>',
        '<DocumentId DomainId="BSP-OEM">ts-ddd-234</DocumentId>'))
    assert "M9" in ids, f"the duplicate identifier went unreported: {sorted(ids)}"


def test_an_empty_document_identifier_is_reported():
    ids, _ = verdict(edited('<DocumentId DomainId="BSP-OEM" IsPrimary="true">ts-ddd-234</DocumentId>',
                            '<DocumentId DomainId="BSP-OEM" IsPrimary="true"></DocumentId>'))
    assert "M10" in ids, f"the empty identifier went unreported: {sorted(ids)}"
