"""Whether `Z9` fires depended on which library wrote the archive.

The check was `ZipInfo.is_dir()`, which is a trailing slash on a member name.
Explicit directory entries are optional in the ZIP format — `zipfile.writestr`,
Java's `ZipOutputStream` and plenty of others emit none — so a container that
puts every file in a folder could pass clean while a byte-identical layout with
one `anhang/` entry added did not.
"""
import io
import zipfile

from conftest import CLEAN_DOCUMENT
from vdi2770_validate.runner import check_file

SRC = zipfile.ZipFile(CLEAN_DOCUMENT)
META = SRC.read("VDI2770_Metadata.xml").decode()
PDF = SRC.read("B.pdf")
DOCX = SRC.read("B.docx")


def build(tmp_path, name, entries):
    p = tmp_path / name
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in entries:
            z.writestr(n, d)
    p.write_bytes(buf.getvalue())
    return str(p)


def z9(path):
    return [f for f in check_file(path).findings if f.rule.id == "Z9"]


def test_a_foldered_container_with_no_directory_entry_is_still_foldered(tmp_path):
    meta = META.replace(">B.pdf<", ">docs/B.pdf<").replace(">B.docx<", ">docs/B.docx<")
    assert meta != META, "the fixture no longer declares the files this test moves"
    p = build(tmp_path, "no_direntry.zip", [
        ("VDI2770_Metadata.xml", meta), ("docs/B.pdf", PDF), ("docs/B.docx", DOCX)])
    assert not any(i.is_dir() for i in zipfile.ZipFile(p).infolist()), \
        "the premise is that no directory entry was written"
    hits = z9(p)
    assert hits, [f.rule.id for f in check_file(p).findings]
    assert "docs/" in (hits[0].detail or ""), hits[0].detail


def test_an_explicit_directory_entry_still_fires(tmp_path):
    p = build(tmp_path, "with_direntry.zip", [
        ("VDI2770_Metadata.xml", META), ("B.pdf", PDF), ("B.docx", DOCX),
        ("anhang/", b"")])
    hits = z9(p)
    assert hits and "anhang/" in (hits[0].detail or ""), \
        [f.detail for f in hits] or [f.rule.id for f in check_file(p).findings]


def test_a_flat_container_says_nothing(tmp_path):
    p = build(tmp_path, "flat.zip", [
        ("VDI2770_Metadata.xml", META), ("B.pdf", PDF), ("B.docx", DOCX)])
    assert not z9(p)


def test_a_nested_folder_names_both_levels(tmp_path):
    meta = META.replace(">B.pdf<", ">a/b/B.pdf<")
    p = build(tmp_path, "deep.zip", [
        ("VDI2770_Metadata.xml", meta), ("a/b/B.pdf", PDF), ("B.docx", DOCX)])
    detail = z9(p)[0].detail or ""
    assert "a/b/" in detail, detail
