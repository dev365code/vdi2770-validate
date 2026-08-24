"""The runner keeps one raw buffer and one declared-name set per nesting level,
which is only sound if every container writes its own before anything skips.

It did not. Both were published after two `continue` statements, so a container
with no metadata — or metadata that would not parse — never wrote its own, and
its children read whatever the previous subtree had left at that depth. The tool
printed a PDF/A-3a claim for a fifty-four-byte text file, having read a different
member of a different archive.

The declared-name set had a second way to go wrong: it was keyed by path, and the
parent's path was reconstructed by splitting on the JAR separator — which the
reader's own comment says gets the wrong answer for a member whose name contains
one. A member called `sub.zip!/fake.zip` therefore looked declared, and `Z3` was
suppressed on an archive nobody declared.
"""
import io
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
MAIN_DECL = '<DigitalFile FileFormat="application/pdf">VDI2770_Main.pdf</DigitalFile>'


def zbytes(entries, compress=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compress) as z:
        for n, d in entries:
            z.writestr(n, d)
    return buf.getvalue()


def report(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return [(f.rule.id, str(f.where)) for f in check_file(str(p)).sorted()]


def test_the_fixture_declares_its_main_pdf():
    assert MAINXML.count(MAIN_DECL) == 1


def test_a_child_of_a_metadata_less_container_reads_its_own_archive(tmp_path):
    """A is a real document container and publishes bytes at depth 1. B has no
    metadata at all, so it used to publish nothing — and C, B's child, read A's
    archive instead of B's."""
    inner = zbytes([("VDI2770_Metadata.xml", META.replace(">B.pdf<", ">X.pdf<")),
                    ("X.pdf", b"this is not a PDF at all\n"), ("B.docx", DOCX)])
    a = zbytes([("VDI2770_Metadata.xml", META), ("B.pdf", PDF), ("B.docx", DOCX)])
    b = zbytes([("C.zip", inner), ("readme.txt", b"nothing here\n")])
    main = MAINXML.replace(
        MAIN_DECL, MAIN_DECL + '\n        <DigitalFile FileFormat="application/zip">B.zip</DigitalFile>')
    got = report(tmp_path, "stale.zip", zbytes([
        ("VDI2770_Main.xml", main), ("VDI2770_Main.pdf", MAINPDF),
        ("A.zip", a), ("B.zip", b)]))
    assert ("P1", "stale.zip!/B.zip!/C.zip!/X.pdf") in got, got
    assert not any(r == "P4" and "C.zip" in w for r, w in got), (
        "a PDF/A claim was reported for a file that makes none: " + str(got))


def test_the_same_container_one_level_up_says_the_same_thing(tmp_path):
    """The control the bug was invisible without: identical inner archive, no
    metadata-less parent in front of it."""
    inner = zbytes([("VDI2770_Metadata.xml", META.replace(">B.pdf<", ">X.pdf<")),
                    ("X.pdf", b"this is not a PDF at all\n"), ("B.docx", DOCX)])
    got = report(tmp_path, "control.zip", zbytes([
        ("VDI2770_Main.xml", MAINXML), ("VDI2770_Main.pdf", MAINPDF), ("C.zip", inner)]))
    assert ("P1", "control.zip!/C.zip!/X.pdf") in got, got


def test_a_jar_separator_in_a_member_name_does_not_forge_a_declaration(tmp_path):
    """`sub.zip!/fake.zip` used to resolve to parent `outer!/sub.zip`, member
    `fake.zip` — a name the real `sub.zip` declares — so an undeclared archive
    was taken for a declared payload and `Z3` kept quiet about it."""
    smuggled = zbytes([("notes.txt", b"nothing that looks like a container\n")])
    sub_meta = MAINXML.replace(
        MAIN_DECL, MAIN_DECL + '\n        <DigitalFile FileFormat="application/zip">fake.zip</DigitalFile>')
    sub = zbytes([("VDI2770_Main.xml", sub_meta), ("VDI2770_Main.pdf", MAINPDF),
                  ("fake.zip", smuggled)])
    got = report(tmp_path, "spoof.zip", zbytes([
        ("VDI2770_Main.xml", MAINXML), ("VDI2770_Main.pdf", MAINPDF),
        ("sub.zip", sub), ("sub.zip!/fake.zip", smuggled)]))
    assert any(r == "Z3" and w.endswith("sub.zip!/fake.zip") for r, w in got), got


def test_a_genuinely_declared_payload_is_still_quiet(tmp_path):
    payload = zbytes([("teile.csv", b"1;Motor\n")])
    main = MAINXML.replace(
        MAIN_DECL, MAIN_DECL + '\n        <DigitalFile FileFormat="application/zip">anhang.zip</DigitalFile>')
    got = report(tmp_path, "declared.zip", zbytes([
        ("VDI2770_Main.xml", main), ("VDI2770_Main.pdf", MAINPDF),
        ("documentcontainer.zip", CLEAN_DOCUMENT.read_bytes()), ("anhang.zip", payload)]))
    assert not any(r == "Z3" for r, _ in got), got
