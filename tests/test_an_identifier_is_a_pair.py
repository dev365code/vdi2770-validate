"""An identifier is (domain, value), not a bare string.

The schema makes `DomainId` required on every `DocumentId` — an id belongs to
whoever runs that domain. `M9` compared the text alone, so the same drawing
number registered in the OEM's domain and in the supplier's read as a repeat, and
the remedy told the user to delete one of them. Following that advice destroys
real information, which makes a warning worse than silence.
"""
import io
import zipfile

from conftest import CLEAN_DOCUMENT
from vdi2770_validate.runner import check_file

SRC = zipfile.ZipFile(CLEAN_DOCUMENT)
META = SRC.read("VDI2770_Metadata.xml").decode()
PDF = SRC.read("B.pdf")
DOCX = SRC.read("B.docx")

OEM = '<DocumentId DomainId="BSP-OEM">data-sheet-br-01-26</DocumentId>'
PRIMARY = '<DocumentId DomainId="BSP-OEM" IsPrimary="true">ts-ddd-234</DocumentId>'


def build(tmp_path, name, meta):
    p = tmp_path / name
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VDI2770_Metadata.xml", meta)
        z.writestr("B.pdf", PDF)
        z.writestr("B.docx", DOCX)
    p.write_bytes(buf.getvalue())
    return str(p)


def findings(path, rule_id):
    return [f for f in check_file(path).findings if f.rule.id == rule_id]


def test_the_fixture_still_has_the_element_this_file_edits():
    """A positive control: every test below rewrites these two lines, and a
    silent no-op rewrite would make all of them pass for the wrong reason."""
    assert META.count(OEM) == 1 and META.count(PRIMARY) == 1


def test_one_number_in_two_domains_is_two_identifiers(tmp_path):
    """An OEM and its supplier both registering the same drawing number is
    ordinary. Neither system loses anything, because they are keyed differently."""
    meta = META.replace(OEM, '<DocumentId DomainId="BSP-SUPPLIER">ts-ddd-234</DocumentId>')
    p = build(tmp_path, "two_domains.zip", meta)
    assert not findings(p, "M9"), [f.detail for f in findings(p, "M9")]


def test_the_same_number_twice_in_one_domain_is_still_a_repeat(tmp_path):
    meta = META.replace(OEM, '<DocumentId DomainId="BSP-OEM">ts-ddd-234</DocumentId>')
    p = build(tmp_path, "one_domain.zip", meta)
    hits = findings(p, "M9")
    assert len(hits) == 1, [f.detail for f in hits]
    assert "BSP-OEM" in (hits[0].detail or ""), hits[0].detail


def test_the_repeat_is_reported_where_it_was_written(tmp_path):
    """The old finding pointed at the document element. Pointing at the second
    DocumentId is the difference between a report you can act on and one you
    have to go looking through the file for."""
    meta = META.replace(OEM, '<DocumentId DomainId="BSP-OEM">ts-ddd-234</DocumentId>')
    p = build(tmp_path, "located.zip", meta)
    where = findings(p, "M9")[0].where
    line = meta[:meta.index('<DocumentId DomainId="BSP-OEM">ts-ddd-234')].count("\n") + 1
    assert where.line == line, f"reported line {where.line}, element is on {line}"


def test_an_empty_identifier_is_still_empty(tmp_path):
    meta = META.replace(OEM, '<DocumentId DomainId="BSP-OEM"></DocumentId>')
    p = build(tmp_path, "empty.zip", meta)
    assert findings(p, "M10"), "M10 stopped catching an empty identifier"


def test_the_reader_carries_the_domain(tmp_path):
    """The domain has to survive parsing for any of the above to be possible."""
    import vdi2770

    doc = vdi2770.build_document(vdi2770.parse_xml(META.encode()), vdi2770.Location())
    pairs = {(i.domain_id, i.id) for i in doc.identifiers}
    assert ("BSP-OEM", "data-sheet-br-01-26") in pairs, pairs
    assert doc.ids == tuple(i.id for i in doc.identifiers), "the old view must still work"
