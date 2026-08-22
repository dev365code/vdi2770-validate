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
