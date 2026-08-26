"""A `.zip` the metadata declares as a file is a file, not a container.

The reader opens every member ending in `.zip` and classifies it, because the
reader has no metadata and cannot know better. The rules do have the metadata,
and until now they did not use it: a parts list attached as `teileliste.zip`
earned `Z3` -- "neither a document container nor a documentation container" --
which it had never claimed to be. Our own `F3` remedy blesses `application/zip`
with `.zip` in the same breath.

`Z11` is suppressed for the same reason and by its own argument: it exists
because an undeclared container is "a way to carry something past a check that
only looks at declared files". A declared one is not past that check.
"""
import io
import zipfile

from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION
from vdi2770_validate.runner import check_file

DOC = zipfile.ZipFile(CLEAN_DOCUMENT)
DOCN = zipfile.ZipFile(CLEAN_DOCUMENTATION)
META = DOC.read("VDI2770_Metadata.xml").decode()
MAINXML = DOCN.read("VDI2770_Main.xml").decode()
MAINPDF = DOCN.read("VDI2770_Main.pdf")
DOC_BYTES = CLEAN_DOCUMENT.read_bytes()

PAYLOAD = io.BytesIO()
with zipfile.ZipFile(PAYLOAD, "w") as _z:
    _z.writestr("teileliste.csv", b"pos;bezeichnung\n1;Motor\n")
PAYLOAD = PAYLOAD.getvalue()

DECL_MAIN = '<DigitalFile FileFormat="application/pdf">VDI2770_Main.pdf</DigitalFile>'
DECL_PDF = '<DigitalFile FileFormat="application/pdf">B.pdf</DigitalFile>'


def build(tmp_path, name, entries):
    p = tmp_path / name
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in entries:
            z.writestr(n, d)
    p.write_bytes(buf.getvalue())
    return str(p)


def fired(path):
    return {(f.rule.id, f.where.member) for f in check_file(path).findings}


def ids(path):
    return {f.rule.id for f in check_file(path).findings}


def test_a_declared_zip_in_a_documentation_container_is_not_judged_as_one(tmp_path):
    mm = MAINXML.replace(
        DECL_MAIN,
        DECL_MAIN + '\n        <DigitalFile FileFormat="application/zip">teileliste.zip</DigitalFile>')
    p = build(tmp_path, "declared_docn.zip", [
        ("VDI2770_Main.xml", mm), ("VDI2770_Main.pdf", MAINPDF),
        ("documentcontainer.zip", DOC_BYTES), ("teileliste.zip", PAYLOAD)])
    assert "Z3" not in ids(p), f"a declared parts list was called a broken container: {ids(p)}"


def test_a_declared_zip_in_a_document_container_is_not_smuggling(tmp_path):
    m = META.replace(
        DECL_PDF,
        DECL_PDF + '\n        <DigitalFile FileFormat="application/zip">anhang.zip</DigitalFile>')
    p = build(tmp_path, "declared_doc.zip", [
        ("VDI2770_Metadata.xml", m), ("B.pdf", DOC.read("B.pdf")),
        ("B.docx", DOC.read("B.docx")), ("anhang.zip", PAYLOAD)])
    assert not ids(p) & {"Z3", "Z11"}, f"a declared attachment was flagged: {ids(p)}"


def test_an_undeclared_container_inside_a_document_container_still_fires(tmp_path):
    """Z11's whole argument is about what is *not* declared. That case must stay."""
    p = build(tmp_path, "smuggled.zip", [
        ("VDI2770_Metadata.xml", META), ("B.pdf", DOC.read("B.pdf")),
        ("B.docx", DOC.read("B.docx")), ("smuggled.zip", PAYLOAD)])
    assert ("Z11", "smuggled.zip") in fired(p), f"{fired(p)}"


def test_an_undeclared_non_container_in_a_documentation_container_still_fires(tmp_path):
    """An inner zip nobody declared is structural, and a documentation container's
    structural zips are supposed to be document containers."""
    p = build(tmp_path, "junk_inside.zip", [
        ("VDI2770_Main.xml", MAINXML), ("VDI2770_Main.pdf", MAINPDF),
        ("documentcontainer.zip", DOC_BYTES), ("junk.zip", PAYLOAD)])
    # `or "Z3" in ids(p)` used to sit here and swallowed the whole assertion.
    assert ("Z3", None) in fired(p), f"{sorted(fired(p))}"


def test_a_declared_payload_that_is_a_real_container_is_still_validated(tmp_path):
    """Suppressing "this is not a container" must not suppress everything else.
    If a declared payload turns out to be a document container with a bad class
    id, saying so is useful and we should keep saying it."""
    bad = META.replace("<ClassId>02-01</ClassId>", "<ClassId>99-99</ClassId>")
    assert bad != META, "the fixture no longer has the ClassId this test edits"
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("VDI2770_Metadata.xml", bad)
        z.writestr("B.pdf", DOC.read("B.pdf"))
        z.writestr("B.docx", DOC.read("B.docx"))
    mm = MAINXML.replace(
        DECL_MAIN,
        DECL_MAIN + '\n        <DigitalFile FileFormat="application/zip">sub.zip</DigitalFile>')
    p = build(tmp_path, "declared_real.zip", [
        ("VDI2770_Main.xml", mm), ("VDI2770_Main.pdf", MAINPDF),
        ("documentcontainer.zip", DOC_BYTES), ("sub.zip", inner.getvalue())])
    assert "M2" in ids(p), f"the declared payload was skipped entirely: {ids(p)}"
    assert "Z3" not in ids(p)



def _payload_container(tmp_path, name, inner):
    """A document container declaring `cad.zip`, whose payload holds `inner`."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, d in inner.items():
            z.writestr(n, d)
    meta = META.replace(
        DECL_PDF, DECL_PDF + '<DigitalFile FileFormat="application/zip">cad.zip</DigitalFile>')
    return build(tmp_path, name, [
        ("VDI2770_Metadata.xml", meta), ("B.pdf", DOC.read("B.pdf")),
        ("cad.zip", buf.getvalue())])


def test_a_declared_payload_is_not_judged_on_how_it_arranges_itself(tmp_path):
    """A CAD bundle keeps its own folders, and an empty one is not "the archive
    is empty".

    A `.zip` the metadata declares as a `DigitalFile` is one of the document's
    *files*. Its inside is its own business, exactly as a PDF's is. `Z3` and
    `Z11` already know this; `Z9` and `Z2` did not, so a conforming delivery
    carrying `cad.zip` with `cad/part.step` in it drew *"The archive stores
    files in folders -- store the members at the root of the archive"*.
    Following that flattens a parts bundle and breaks the delivery; not
    following it leaves a warning that never clears.
    """
    for name, inner in (("folders.zip", {"cad/part.step": b"ISO-10303-21;"}),
                        ("empty.zip", {})):
        got = ids(_payload_container(tmp_path, name, inner))
        assert "Z9" not in got, (name, got)
        assert "Z2" not in got, (name, got)


def test_a_payload_that_is_unsafe_is_still_reported(tmp_path):
    """The other half. Suppressing what a payload says about *structure* must
    not suppress what it says about *bytes*: a member that cannot be handed
    over safely is a delivery risk whatever the metadata calls the archive."""
    got = ids(_payload_container(tmp_path, "unsafe.zip", {"../escape.txt": b"x"}))
    assert "Z4" in got, got
