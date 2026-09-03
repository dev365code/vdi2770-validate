"""`VDI2770_Main.pdf` is the file a documentation container is built around, and
nothing checked what was in it.

Three rules each handed it to the next. `Z7` is satisfied by the name alone.
`F2` exempts it as structural, so an undeclared one raises no flag. The P rules
only look at files the metadata declares as `application/pdf`. Declaring some
other PDF is schema-legal, so an eighteen-byte text file called
`VDI2770_Main.pdf` passed with exit 0.
"""
import io
import zipfile

from conftest import A_PDF, CLEAN_DOCUMENT, CLEAN_DOCUMENTATION
from vdi2770_validate.runner import check_file

DOCN = zipfile.ZipFile(CLEAN_DOCUMENTATION)
MAINXML = DOCN.read("VDI2770_Main.xml").decode()
MAINPDF = DOCN.read("VDI2770_Main.pdf")
INNER = CLEAN_DOCUMENT.read_bytes()

DECL = '<DigitalFile FileFormat="application/pdf">VDI2770_Main.pdf</DigitalFile>'
OTHER = '<DigitalFile FileFormat="application/pdf">Hauptdokument.pdf</DigitalFile>'


def test_the_fixture_declares_its_main_pdf():
    """Positive control: every case below turns that declaration into something
    else, and a no-op rewrite would make them pass for the wrong reason."""
    assert MAINXML.count(DECL) == 1


def build(tmp_path, name, entries):
    p = tmp_path / name
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in entries:
            z.writestr(n, d)
    p.write_bytes(buf.getvalue())
    return str(p)


def at(path, member):
    return [f for f in check_file(path).findings if f.where.member == member]


def undeclared(tmp_path, name, main_pdf_bytes):
    """A documentation container whose metadata names a different PDF, so the
    reserved main document is present but undeclared."""
    return build(tmp_path, name, [
        ("VDI2770_Main.xml", MAINXML.replace(DECL, OTHER)),
        ("VDI2770_Main.pdf", main_pdf_bytes),
        ("Hauptdokument.pdf", MAINPDF),
        ("documentcontainer.zip", INNER)])


def test_an_undeclared_main_document_that_is_not_a_pdf_is_caught(tmp_path):
    p = undeclared(tmp_path, "not_a_pdf.zip", b"this is not a pdf\n")
    assert {f.rule.id for f in at(p, "VDI2770_Main.pdf")} == {"P1"}, \
        [(f.rule.id, str(f.where)) for f in check_file(p).findings]


def test_an_undeclared_main_document_is_scanned_like_any_other_pdf(tmp_path):
    """Not only P1: if the recipient cannot open it, that matters more here than
    for any other file in the delivery."""
    p = undeclared(tmp_path, "no_claim.zip", A_PDF + b"% no xmp here\n")
    assert "P3" in {f.rule.id for f in at(p, "VDI2770_Main.pdf")}


def test_a_declared_main_document_is_still_reported_exactly_once(tmp_path):
    """The reserved name is an implicit declaration, and the corpus declares it
    explicitly too. Counting it twice would be the obvious way to get this wrong."""
    p = build(tmp_path, "declared.zip", [
        ("VDI2770_Main.xml", MAINXML), ("VDI2770_Main.pdf", MAINPDF),
        ("documentcontainer.zip", INNER)])
    hits = at(p, "VDI2770_Main.pdf")
    assert len(hits) == 1 and hits[0].rule.id == "P4", [(f.rule.id) for f in hits]


def test_the_clean_corpus_container_is_unchanged():
    ids = sorted((f.rule.id, str(f.where)) for f in check_file(str(CLEAN_DOCUMENTATION)).findings)
    assert ids == [
        ("P4", "documentationcontainer.zip!/VDI2770_Main.pdf"),
        ("P4", "documentationcontainer.zip!/documentcontainer.zip!/B.pdf"),
    ], ids


def test_a_document_container_gains_nothing(tmp_path):
    """Only a documentation container reserves VDI2770_Main.pdf."""
    before = sorted(f.rule.id for f in check_file(str(CLEAN_DOCUMENT)).findings)
    assert before == ["P4"], before


def test_one_file_declared_by_three_versions_is_one_note(tmp_path):
    """The notes were emitted per declaration. A metadata file naming the same
    PDF in three document versions printed three identical lines about one file."""
    doc = zipfile.ZipFile(CLEAN_DOCUMENT)
    meta = doc.read("VDI2770_Metadata.xml").decode()
    version = meta[meta.index("<DocumentVersion>"):meta.index("</DocumentVersion>") + 18]
    assert "B.pdf" in version, "the fixture's first version no longer declares B.pdf"
    meta3 = meta.replace(version, version * 3, 1)
    p = build(tmp_path, "three_versions.zip", [
        ("VDI2770_Metadata.xml", meta3),
        ("B.pdf", doc.read("B.pdf")), ("B.docx", doc.read("B.docx"))])
    notes = [f for f in at(p, "B.pdf") if f.rule.id == "P4"]
    assert len(notes) == 1, f"{len(notes)} identical notes for one file"


def test_a_decomposed_filename_is_still_scanned(tmp_path):
    """Reconciling NFD and NFC in the F rules alone would have been worse than
    not doing it: F1 stops complaining that the file is missing, and the P rules
    go on failing to find it, so the file is silently never scanned at all."""
    import unicodedata

    doc = zipfile.ZipFile(CLEAN_DOCUMENT)
    nfc_name = "Größe.pdf"
    meta = doc.read("VDI2770_Metadata.xml").decode().replace(">B.pdf<", f">{nfc_name}<")
    p = build(tmp_path, "nfd_pdf.zip", [
        ("VDI2770_Metadata.xml", meta),
        (unicodedata.normalize("NFD", nfc_name), doc.read("B.pdf")),
        ("B.docx", doc.read("B.docx"))])
    scanned = {f.rule.id for f in check_file(p).findings}
    assert "P4" in scanned, f"the PDF was never scanned: {scanned}"
    assert not scanned & {"F1", "F2"}, scanned


def test_the_name_is_only_reserved_in_a_documentation_container(tmp_path):
    """A document container holding a file called `VDI2770_Main.pdf` is holding a
    file with a confusing name, not a main document. Scanning it as one would be
    inventing a requirement -- and the first version of this file did not notice,
    because the clean document container has no such member to test against.
    """
    doc = zipfile.ZipFile(CLEAN_DOCUMENT)
    p = build(tmp_path, "confusing_name.zip", [
        ("VDI2770_Metadata.xml", doc.read("VDI2770_Metadata.xml")),
        ("B.pdf", doc.read("B.pdf")), ("B.docx", doc.read("B.docx")),
        ("VDI2770_Main.pdf", b"not a pdf, and not a main document either\n")])
    assert "P1" not in {f.rule.id for f in check_file(p).findings}, \
        [(f.rule.id, str(f.where)) for f in check_file(p).findings]


def test_a_pdf_header_with_no_document_after_it_is_not_a_pdf(tmp_path):
    """Eight bytes named `VDI2770_Main.pdf`, and the container was clean.

    `_targets` closed the case where the reserved main document was scanned by
    nobody -- "an eighteen-byte text file passed with exit 0". That repair made
    the file *reachable*. It did not make it *judged*: the whole test for being a
    PDF was `data.startswith(b"%PDF-")`, so the same eighteen bytes with five
    different ones at the front went through, and the one file a recipient's
    system certainly opens was a header and nothing else.

    ISO 32000-1 puts a document catalog in every PDF, and a catalog is an
    indirect object. Bytes carrying no `N G obj` at all are not a PDF document,
    which is a claim this tool can make and defend -- and `P1` is the sentence
    for it, cited from the reference implementation's own check.
    """
    from conftest import CLEAN_DOCUMENTATION

    base = zipfile.ZipFile(CLEAN_DOCUMENTATION)
    shell = tmp_path / "shell.zip"
    with zipfile.ZipFile(shell, "w") as z:
        for name in base.namelist():
            z.writestr(name, b"%PDF-1.4" if name == "VDI2770_Main.pdf"
                       else base.read(name))
    report = check_file(str(shell))
    main = [f for f in report.findings
            if f.rule.id == "P1" and f.where.member == "VDI2770_Main.pdf"]
    assert main, (
        "a header with no document after it was reported as a PDF: "
        f"{sorted(f.rule.id for f in report.findings)}")
    # And the sentence has to survive the sender looking at the file, which does
    # begin with the four bytes everyone knows.
    assert "header" in (main[0].detail or ""), main[0].detail
