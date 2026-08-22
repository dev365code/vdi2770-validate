"""The readers are the only part that touches untrusted bytes."""
import io
import zipfile

import pytest

from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION
from vdi2770_validate.readers import pdfread, xmlread, zipread


def zip_of(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, d in files.items():
            z.writestr(n, d)
    return buf.getvalue()


def test_a_documentation_container_is_recognised_and_walked():
    c = zipread.read_file(str(CLEAN_DOCUMENTATION))
    assert c.kind is zipread.Kind.DOCUMENTATION
    assert c.metadata_name == zipread.MAIN_XML
    assert c.children, "the nested document container should have been read"
    assert c.children[0].kind is zipread.Kind.DOCUMENT


def test_container_names_are_case_sensitive_and_must_sit_at_the_root():
    c = zipread.read(zip_of({"sub/VDI2770_Metadata.xml": b"<x/>"}), "x.zip")
    assert c.kind is zipread.Kind.UNKNOWN
    assert "VDI2770_Metadata.xml" in c.near_misses
    assert "root of the archive" in c.near_misses["VDI2770_Metadata.xml"]


def test_a_file_that_is_not_a_zip_is_a_defect_not_a_crash():
    c = zipread.read(b"not a zip", "x.zip")
    assert c.kind is zipread.Kind.UNREADABLE
    assert [d.kind for d in c.defects] == ["not-a-zip"]


def test_hostile_member_names_are_refused_without_touching_the_filesystem():
    c = zipread.read(zip_of({"../escape.txt": b"x", "VDI2770_Metadata.xml": b"<x/>"}), "x.zip")
    assert "unsafe-member-name" in {d.kind for d in c.defects}
    assert "../escape.txt" not in c.file_names


def test_xml_keeps_the_line_every_element_was_written_on():
    root = xmlread.parse(b'<?xml version="1.0"?>\n<Document xmlns="%s">\n  <DocumentId>x</DocumentId>\n</Document>'
                         % xmlread.NS.encode())
    assert root.tag == "Document" and root.ns == xmlread.NS
    assert root.find("DocumentId").line == 3


def test_entity_expansion_is_refused():
    with pytest.raises(xmlread.UnsafeXml):
        xmlread.parse(b'<!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><r>&x;</r>')


def test_malformed_xml_reports_where():
    with pytest.raises(xmlread.XmlError) as e:
        xmlread.parse(b"<Document><a></Document>")
    assert e.value.line is not None


def test_pdf_facts_are_read_without_a_pdf_library():
    data = zipfile.ZipFile(CLEAN_DOCUMENT).read("B.pdf")
    facts = pdfread.read(data)
    assert facts.is_pdf and facts.header.startswith("%PDF-")
    assert facts.pdfa_claim == "3a"
    assert facts.encrypted is False


def test_something_that_is_not_a_pdf_says_so():
    assert pdfread.read(b"hello").is_pdf is False
