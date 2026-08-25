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
from vdi2770_validate.runner import check_bytes, check_file

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
    """It said "both levels" and checked one. `a/b/B.pdf` puts the file in `a/b/`
    and also in `a/`, and the rule derived only the last component — so a
    two-level layout was reported as "1 folder"."""
    meta = META.replace(">B.pdf<", ">a/b/B.pdf<")
    p = build(tmp_path, "deep.zip", [
        ("VDI2770_Metadata.xml", meta), ("a/b/B.pdf", PDF), ("B.docx", DOCX)])
    detail = z9(p)[0].detail or ""
    assert "a/b/" in detail and "a/, " in detail + ", ", detail
    assert detail.startswith("2 folders:"), detail


def test_a_declared_folder_path_resolves_so_z9_stands_alone():
    """Z9's remedy used to say *"metadata refers to files by name, so a file
    inside a folder is not the file the metadata names"*. The tool says
    otherwise: a name that carries its folder path resolves, and the file-set
    rules stay quiet. A remedy that gives a false reason teaches the reader the
    wrong model of the tool.
    """
    import io
    import re
    import zipfile

    from conftest import CLEAN_DOCUMENT
    from vdi2770_validate.catalog import rule
    from vdi2770_validate.runner import check_bytes

    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    meta = src.read("VDI2770_Metadata.xml").decode()
    victim = next(n for n in re.findall(r"<DigitalFile[^>]*>([^<]+)</DigitalFile>", meta)
                  if n.lower().endswith(".pdf"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in src.namelist():
            if n == victim:
                z.writestr(f"unterlagen/{n}", src.read(n))
            elif n == "VDI2770_Metadata.xml":
                z.writestr(n, meta.replace(f">{victim}<", f">unterlagen/{victim}<"))
            else:
                z.writestr(n, src.read(n))

    fired = {f.rule.id for f in check_bytes(buf.getvalue(), "foldered.zip").findings}
    assert "Z9" in fired
    assert not fired & {"F1", "F2"}, (
        f"the declared path did not resolve, so Z9's remedy could say it does not: {fired}")
    remedy = rule("Z9").remedy
    assert "is not the file the metadata names" not in remedy
    assert "resolves" in remedy, remedy


def test_a_directory_entry_for_the_root_is_not_a_folder():
    """`./` is a directory entry many writers put at the front of an archive, and
    it names the root. Reported as a folder it produced *"1 folder: ./"* with a
    remedy — "store the members at the root" — that the archive already obeys.

    The path branch of this rule learned to drop `.` segments; the `is_dir`
    branch beside it did not, which is the same miss one line apart.
    """
    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("./"), b"")
        for name in src.namelist():
            z.writestr(name, src.read(name))

    fired = {f.rule.id for f in check_bytes(buf.getvalue(), "dot.zip").findings}
    assert "Z9" not in fired, f"a root directory entry read as a folder: {sorted(fired)}"
