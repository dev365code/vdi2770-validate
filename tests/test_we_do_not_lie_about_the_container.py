"""A finding must be true about the user's file.

Two ways to break that, both found by audit rather than by a gate: say the
archive is empty when we merely refused to read what was in it, and say a value
is wrong when the element holding it is absent.
"""
import io
import zipfile

from conftest import FIXTURES  # noqa: F401  (keeps the fixture dir on the radar)
from vdi2770_validate.runner import check_file

META_NO_CLASSID = b"""<?xml version="1.0"?>
<Document xmlns="http://www.vdi.de/schemas/vdi2770">
  <DocumentId DomainId="acme">D-1</DocumentId>
  <DocumentClassification ClassificationSystem="VDI2770:2018">
    <ClassName Language="de">Allgemeine technische Daten</ClassName>
  </DocumentClassification>
  <DocumentVersion><DocumentVersionId>1.0</DocumentVersionId>
    <DigitalFile FileFormat="application/pdf">a.pdf</DigitalFile></DocumentVersion>
</Document>"""


def build(tmp_path, name, members):
    p = tmp_path / name
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in members.items():
            z.writestr(n, b)
    p.write_bytes(buf.getvalue())
    return check_file(str(p))


def ids(report):
    return {f.rule.id for f in report.findings}


def test_an_archive_we_refused_to_read_is_not_called_empty(tmp_path):
    """One 200MB member: the archive has contents, we declined them. Telling the
    user to 'add the metadata file and the documents' is false and unactionable."""
    rep = build(tmp_path, "one-bomb.zip", {"boom.bin": b"\0" * 200_000_000})
    assert "Z5" in ids(rep), "the refusal itself must still be reported"
    assert "Z2" not in ids(rep), (
        "Z2 says the archive is empty; it has a member that we dropped. "
        + str([(f.rule.id, f.message) for f in rep.findings]))


def test_a_genuinely_empty_archive_is_still_called_empty(tmp_path):
    rep = build(tmp_path, "empty.zip", {})
    assert "Z2" in ids(rep)


def test_an_unreadable_archive_still_reports_that_it_is_unclassifiable(tmp_path):
    """Z2's early return used to swallow Z3, so a container with nothing usable
    left got one misleading finding instead of the accurate one."""
    rep = build(tmp_path, "junk.zip", {"notes.txt": b"hello"})
    assert "Z3" in ids(rep), str(ids(rep))


def test_an_absent_class_id_is_the_schema_layer_s_business_not_the_table_s(tmp_path):
    """M2's remedy is 'use one of these twelve values'. With no ClassId element
    there is no value to correct, and X2 already reports the missing element."""
    rep = build(tmp_path, "no-classid.zip",
                {"VDI2770_Metadata.xml": META_NO_CLASSID, "a.pdf": b"%PDF-1.7\n"})
    assert "X2" in ids(rep), "the schema layer must still catch it"
    assert "M2" not in ids(rep), (
        "M2 tells the user to pick a valid class id for an element that is absent")


def test_a_present_but_wrong_class_id_is_still_caught(tmp_path):
    meta = META_NO_CLASSID.replace(
        b"<ClassName", b"<ClassId>99-99</ClassId>\n    <ClassName")
    rep = build(tmp_path, "bad-classid.zip",
                {"VDI2770_Metadata.xml": meta, "a.pdf": b"%PDF-1.7\n"})
    assert "M2" in ids(rep), str(ids(rep))
