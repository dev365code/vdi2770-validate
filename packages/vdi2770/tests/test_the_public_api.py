"""What `import vdi2770` promises, held by a test.

These run without `vdi2770-validate` installed and without touching the corpus,
because the point of splitting the package was that the library stands alone.
"""
import dataclasses
import io
import zipfile
from pathlib import Path

import pytest

import vdi2770

META = b"""<?xml version="1.0" encoding="utf-8"?>
<Document xmlns="http://www.vdi.de/schemas/vdi2770">
  <DocumentId DomainId="acme">D-1</DocumentId>
  <DocumentClassification ClassificationSystem="VDI2770:2018">
    <ClassId>02-01</ClassId>
    <ClassName Language="de">Allgemeine technische Daten</ClassName>
    <ClassName Language="en">General technical data</ClassName>
  </DocumentClassification>
  <DocumentVersion>
    <DocumentVersionId>1.0</DocumentVersionId>
    <Language>de</Language>
    <DocumentDescription Language="de"><Title>Datenblatt</Title></DocumentDescription>
    <LifeCycleStatus StatusValue="Released"/>
    <DigitalFile FileFormat="application/pdf">datenblatt.pdf</DigitalFile>
  </DocumentVersion>
</Document>
"""


def container(members, name="doc.zip"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in members.items():
            z.writestr(n, b)
    return vdi2770.read_container(buf.getvalue(), name)


# -- the round trip, which is the whole product ------------------------------

def test_a_document_container_reads_end_to_end():
    box = container({"VDI2770_Metadata.xml": META, "datenblatt.pdf": b"%PDF-1.7\n"})
    assert box.kind is vdi2770.Kind.DOCUMENT
    doc = vdi2770.build_document(vdi2770.parse_xml(box.metadata_bytes), box.where)
    assert doc.ids == ("D-1",)
    k = doc.classifications[0]
    assert k.class_id == "02-01" and k.system == "VDI2770:2018"
    assert dict(k.names)["de"] == "Allgemeine technische Daten"
    v = doc.versions[0]
    assert v.version_id == "1.0" and v.life_cycle_status == "Released"
    assert v.languages == ("de",)
    assert v.descriptions[0].title == "Datenblatt"
    assert v.files[0].file_name == "datenblatt.pdf"
    assert v.files[0].file_format == "application/pdf"


def test_every_node_remembers_where_it_was_written():
    """The reason to carry our own parser: a caller can point at the line."""
    base = vdi2770.Location("doc.zip", "VDI2770_Metadata.xml")
    doc = vdi2770.build_document(vdi2770.parse_xml(META), base)
    where = doc.classifications[0].src
    assert where.line == 4, f"expected the classification on line 4, got {where.line}"
    assert where.subject == "02-01"
    assert str(where).startswith("doc.zip!/VDI2770_Metadata.xml:4:")


def test_a_documentation_container_is_recognised_and_walked():
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("VDI2770_Metadata.xml", META)
    box = container({"VDI2770_Main.xml": META, "VDI2770_Main.pdf": b"%PDF-1.7\n",
                     "d1.zip": inner.getvalue()}, "handover.zip")
    assert box.kind is vdi2770.Kind.DOCUMENTATION
    seen = sorted(c.path for c in box.walk())
    assert seen == ["handover.zip", "handover.zip!/d1.zip"], seen
    assert box.children[0].kind is vdi2770.Kind.DOCUMENT


def test_a_name_that_nearly_matched_is_reported_rather_than_ignored():
    box = container({"vdi2770_metadata.xml": META})
    assert box.kind is vdi2770.Kind.UNKNOWN
    assert "case-sensitive" in box.near_misses[vdi2770.METADATA_XML]


# -- the three properties ----------------------------------------------------

def test_a_budget_breach_is_a_defect_and_not_an_exception():
    """One hostile member must not cost the caller the other four hundred."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VDI2770_Metadata.xml", META)
        z.writestr("bomb.bin", b"\0" * (vdi2770.zipread.MAX_MEMBER_BYTES + 1))
        z.writestr("ok.pdf", b"%PDF-1.7\n")
    box = vdi2770.read_container(buf.getvalue(), "doc.zip")
    assert box.metadata_bytes == META, "the good metadata still came back"
    assert "ok.pdf" in box.file_names, "the innocent member survived its neighbour"
    assert box.defects or box.rejected, "the oversized member was reported"
    for d in box.defects:
        assert isinstance(d, vdi2770.Defect) and d.kind


def test_an_entity_declaration_is_refused_rather_than_resolved():
    evil = (b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
            b'<Document xmlns="http://www.vdi.de/schemas/vdi2770">&x;</Document>')
    with pytest.raises(vdi2770.UnsafeXml):
        vdi2770.parse_xml(evil)
    assert issubclass(vdi2770.UnsafeXml, vdi2770.XmlError)


def test_reading_from_a_path_names_the_container_by_its_basename():
    """`read_container_file` is the first line of the README and had no test."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "sub" / "handover.zip"
        p.parent.mkdir()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("VDI2770_Metadata.xml", META)
        p.write_bytes(buf.getvalue())
        box = vdi2770.read_container_file(str(p))
    assert box.path == "handover.zip", "the caller's directory layout is not the container's name"
    assert box.kind is vdi2770.Kind.DOCUMENT


def test_nothing_is_written_to_disk(tmp_path, monkeypatch):
    """Both entry points, because the one the README recommends is the one that
    opens a file, and a mutation that made it write survived when this test
    only exercised the other."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Metadata.xml", META)
        z.writestr("a.pdf", b"%PDF-1.7\n")
    on_disk = tmp_path / "in" / "doc.zip"
    on_disk.parent.mkdir()
    on_disk.write_bytes(buf.getvalue())

    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    real_open = open

    def no_writing(f, mode="r", *a, **kw):
        assert not set(mode) & set("wa+x"), f"the library opened {f} for writing"
        return real_open(f, mode, *a, **kw)

    monkeypatch.setattr("builtins.open", no_writing)
    for box in (vdi2770.read_container(buf.getvalue(), "doc.zip"),
                vdi2770.read_container_file(str(on_disk))):
        vdi2770.build_document(vdi2770.parse_xml(box.metadata_bytes), box.where)
        for _ in box.walk():
            pass
        vdi2770.read_pdf(vdi2770.member_bytes(buf.getvalue(), "a.pdf") or b"")
    assert not list(work.iterdir()), f"the library left {list(work.iterdir())} behind"


def test_no_socket_is_opened(monkeypatch):
    import socket

    def boom(*a, **kw):
        raise AssertionError("the library opened a socket")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    box = container({"VDI2770_Metadata.xml": META})
    vdi2770.build_document(vdi2770.parse_xml(box.metadata_bytes), box.where)


# -- what a PDF claims, and only that ----------------------------------------

def test_the_pdf_reader_reports_a_claim_and_never_a_verdict():
    facts = vdi2770.read_pdf(b"%PDF-1.7\n<?xpacket begin='' id='W5M0'?>"
                             b"<x><pdfaid:part>3</pdfaid:part>"
                             b"<pdfaid:conformance>A</pdfaid:conformance></x>"
                             b"<?xpacket end='w'?>")
    assert facts.is_pdf and facts.pdfa_claim == "3a"
    names = [f.name for f in dataclasses.fields(facts)]
    assert "pdfa_claim" in names
    assert not any(n in names for n in ("is_pdfa", "pdfa_valid", "conforms")), \
        f"a field named like a verdict invites one: {names}"


def test_a_file_that_is_not_a_pdf_says_so_without_guessing():
    facts = vdi2770.read_pdf(b"MZ\x90\x00not a pdf at all")
    assert facts.is_pdf is False and facts.pdfa_claim is None
