"""Z8's title is 'holds no document containers'. It used to test whether the
reader had opened *any* archive, which is a different question: one declared
`.zip` payload made a documentation container delivering nothing come back
clean, exit 0."""
import io
import zipfile

from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION
from vdi2770_validate.runner import check_bytes

SRC = zipfile.ZipFile(CLEAN_DOCUMENTATION)
MAIN_XML = SRC.read("VDI2770_Main.xml").decode()
MAIN_PDF = SRC.read("VDI2770_Main.pdf")
PDF_LINE = '<DigitalFile FileFormat="application/pdf">VDI2770_Main.pdf</DigitalFile>'


def documentation(members, declaring=()):
    """A documentation container whose main document declares `declaring`."""
    extra = "".join(f'\n<DigitalFile FileFormat="application/zip">{n}</DigitalFile>'
                    for n in declaring)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VDI2770_Main.xml", MAIN_XML.replace(PDF_LINE, PDF_LINE + extra))
        z.writestr("VDI2770_Main.pdf", MAIN_PDF)
        for n, d in members.items():
            z.writestr(n, d)
    return buf.getvalue()


def zip_of(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, d in members.items():
            z.writestr(n, d)
    return buf.getvalue()


def ids(data, name="d.zip"):
    return {f.rule.id for f in check_bytes(data, name).findings}


def test_a_declared_zip_payload_does_not_answer_for_a_document_container():
    # The payload is declared, so Z11 is right to stay quiet about it. That is
    # not a reason for Z8 to stay quiet: nothing here is a document container.
    data = documentation({"payload.zip": zip_of({"readme.txt": b"not a container"})},
                         declaring=["payload.zip"])
    assert "Z8" in ids(data)
    assert "Z11" not in ids(data)


def test_a_real_document_container_still_silences_z8():
    data = documentation({"documentcontainer.zip": CLEAN_DOCUMENT.read_bytes()})
    assert "Z8" not in ids(data)


def test_an_empty_documentation_container_still_fires():
    assert "Z8" in ids(documentation({}))


def test_a_child_we_could_not_read_is_not_a_report_of_absence():
    # Z1 already says the archive was not readable. It might have been a
    # document container; "there are none" would be a second claim, and false.
    data = documentation({"broken.zip": b"PK\x03\x04 this is not a zip"},
                         declaring=["broken.zip"])
    found = ids(data)
    assert "Z8" not in found, "we could not look, so we do not get to say"
    assert "Z1" in found, f"Z1 must say the archive was not readable: {found}"
