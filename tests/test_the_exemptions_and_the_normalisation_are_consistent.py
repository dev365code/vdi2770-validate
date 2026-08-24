"""Two ways of applying a rule to only some of the things it compares.

`nfc()` was put on `present` and `declared` and not on the F1 lookup, so the
NFD-in-metadata direction still reported a file as declared-but-missing while
F2 stayed quiet about it — the file was simultaneously absent and accounted for.
Only one of the two directions had a test.

And the structural exemption named all three reserved files in every container,
so `VDI2770_Main.pdf` was exempt inside a document container, where the name is
reserved for nothing.
"""
import io
import unicodedata
import zipfile

from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION
from vdi2770_validate.runner import check_file

DOC = zipfile.ZipFile(CLEAN_DOCUMENT)
META = DOC.read("VDI2770_Metadata.xml").decode()
PDF = DOC.read("B.pdf")
DOCX = DOC.read("B.docx")
DOCN = zipfile.ZipFile(CLEAN_DOCUMENTATION)
MAINXML = DOCN.read("VDI2770_Main.xml").decode()
MAINPDF = DOCN.read("VDI2770_Main.pdf")
INNER = CLEAN_DOCUMENT.read_bytes()

NFC = "Größe.pdf"
NFD = unicodedata.normalize("NFD", NFC)


def build(tmp_path, name, entries):
    p = tmp_path / name
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in entries:
            z.writestr(n, d)
    p.write_bytes(buf.getvalue())
    return str(p)


def ids(path):
    return {f.rule.id for f in check_file(path).findings}


def test_the_two_spellings_are_the_same_name_in_both_directions(tmp_path):
    """Metadata composed and archive decomposed was tested. The reverse was not,
    and it was broken: `present` and `declared` were normalised, the F1 lookup
    was not, so the file was reported missing and undeclared-nothing at once."""
    for label, in_meta, in_zip in (("nfc/nfd", NFC, NFD), ("nfd/nfc", NFD, NFC)):
        meta = META.replace(">B.pdf<", f">{in_meta}<")
        p = build(tmp_path, f"{label.replace('/', '_')}.zip",
                  [("VDI2770_Metadata.xml", meta), (in_zip, PDF), ("B.docx", DOCX)])
        assert not ids(p) & {"F1", "F2"}, f"{label}: {ids(p)}"
        assert "P4" in ids(p), f"{label}: the file was never scanned either"


def test_a_genuinely_absent_file_is_still_absent(tmp_path):
    meta = META.replace(">B.pdf<", ">nirgends.pdf<")
    p = build(tmp_path, "absent.zip",
              [("VDI2770_Metadata.xml", meta), ("B.docx", DOCX)])
    assert "F1" in ids(p)


def test_the_main_pdf_is_only_structural_where_it_is_reserved(tmp_path):
    """Inside a document container the name is reserved for nothing, so a file
    carrying it is an undeclared file like any other."""
    p = build(tmp_path, "stray_main.zip", [
        ("VDI2770_Metadata.xml", META), ("B.pdf", PDF), ("B.docx", DOCX),
        ("VDI2770_Main.pdf", b"%PDF-1.7\n")])
    assert "F2" in ids(p), ids(p)


def test_the_main_pdf_stays_structural_where_it_is_reserved(tmp_path):
    """The corpus declares its main PDF, so the exemption is doing nothing there —
    which is how the first version of this guard let a mutation through. The
    exemption only matters when the file is *not* declared."""
    decl = '<DigitalFile FileFormat="application/pdf">VDI2770_Main.pdf</DigitalFile>'
    assert MAINXML.count(decl) == 1
    mm = MAINXML.replace(decl, '<DigitalFile FileFormat="application/pdf">Haupt.pdf</DigitalFile>')
    p = build(tmp_path, "undeclared_main.zip", [
        ("VDI2770_Main.xml", mm), ("VDI2770_Main.pdf", MAINPDF),
        ("Haupt.pdf", MAINPDF), ("documentcontainer.zip", INNER)])
    assert "F2" not in ids(p), ids(p)


def test_a_stray_metadata_file_in_a_documentation_container_is_undeclared(tmp_path):
    """`VDI2770_Metadata.xml` is reserved in a document container. At the root of
    a documentation container it is a file nobody declared."""
    p = build(tmp_path, "stray_metadata.zip", [
        ("VDI2770_Main.xml", MAINXML), ("VDI2770_Main.pdf", MAINPDF),
        ("VDI2770_Metadata.xml", META), ("documentcontainer.zip", INNER)])
    assert "F2" in ids(p), ids(p)
