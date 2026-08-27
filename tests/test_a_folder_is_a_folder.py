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


def test_an_archive_with_no_files_says_nothing_about_folders(tmp_path):
    """`Z9`'s title is a claim: *the archive stores files in folders*.

    A directory entry is a folder somebody made, which is why one on its own is
    still collected — but an archive whose *only* entry was `a/` was told it
    stores files in folders, naming one with no file in it, in a report that says
    two lines up the archive is not a container at all.
    """
    import io
    import zipfile

    from vdi2770_validate.runner import check_bytes

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a/", b"")
    fired = {f.rule.id for f in check_bytes(buf.getvalue(), "dir.zip").findings}
    assert "Z9" not in fired, (
        f"an archive holding no files was told it stores files in folders: {sorted(fired)}")

    # And the half that must not go with it: one file inside that folder and the
    # rule speaks again.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a/", b"")
        z.writestr("a/x.pdf", b"%PDF-1.4\n")
    said = [f for f in check_bytes(buf.getvalue(), "dir.zip").findings if f.rule.id == "Z9"]
    assert said and "a/" in (said[0].detail or ""), (
        [f.rule.id for f in check_bytes(buf.getvalue(), "dir.zip").findings])


def _handover_with_folder(folder):
    """A documentation container holding one unzipped document folder."""
    import io
    import zipfile

    from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION

    doc = zipfile.ZipFile(CLEAN_DOCUMENT)
    docn = zipfile.ZipFile(CLEAN_DOCUMENTATION)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Main.xml", docn.read("VDI2770_Main.xml"))
        z.writestr("VDI2770_Main.pdf", docn.read("VDI2770_Main.pdf"))
        z.writestr(folder + "/", b"")           # an explicit directory entry
        for name in doc.namelist():
            z.writestr(folder + "/" + name, doc.read(name))
    return buf.getvalue()


def test_one_folder_is_counted_once_however_its_name_is_spelled():
    """`Z9` said *2 folders: Prüfbericht/, Prüfbericht/* about one folder.

    The directory-entry branch normalises the name and the path branch three
    lines below does not, so a folder whose name is not ASCII — written the way
    macOS writes it, which is also what `zip -r` there emits a directory entry
    for — landed in the set twice. The count was wrong and the two names printed
    identically, so nothing on the page said what the second one was.
    """
    import unicodedata

    from vdi2770_validate.runner import check_bytes

    decomposed = unicodedata.normalize("NFD", "Prüfbericht")
    assert decomposed != "Prüfbericht", "the fixture no longer decomposes"

    report = check_bytes(_handover_with_folder(decomposed), "nfd.zip")
    z9 = [f for f in report.findings if f.rule.id == "Z9"]
    assert z9, [f.rule.id for f in report.findings]
    assert z9[0].detail.startswith("1 folder"), z9[0].detail
    # And the two names it prints are one name, not two that look alike.
    named = z9[0].detail.split(": ", 1)[1]
    assert "," not in named, named


def test_a_folder_this_tool_did_not_open_says_which_remedy_to_follow():
    """Two remedies about one folder, and no order between them.

    `Z13` says to zip that folder into a `.zip` member — which removes the
    folder, so it answers `Z9` as well. Read on its own, `Z9`'s *store the
    members at the root of the archive* flattens a document container, and a
    reader with two findings in front of them and nothing saying which is the
    more specific can do exactly that.

    Both still fire: the reference implementation warns about folders whatever
    is in them, and dropping the finding would drop that. What was missing was
    the sentence tying them together.
    """
    from vdi2770_validate.runner import check_bytes

    report = check_bytes(_handover_with_folder("docdir"), "plain.zip")
    said = {f.rule.id: f for f in report.findings if f.rule.id in ("Z9", "Z13")}
    assert set(said) == {"Z9", "Z13"}, sorted(said)
    assert "docdir/" in said["Z9"].remedy, said["Z9"].remedy
    assert ".zip member" in said["Z9"].remedy, said["Z9"].remedy

    # And an ordinary folder, with no container in it, keeps the plain remedy.
    import io
    import zipfile

    from conftest import CLEAN_DOCUMENT

    doc = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in doc.namelist():
            z.writestr(("extras/" + name) if name == "B.docx" else name, doc.read(name))
    plain = [f for f in check_bytes(buf.getvalue(), "flat.zip").findings
             if f.rule.id == "Z9"]
    assert plain, "premise: an ordinary folder still draws Z9"
    assert "the finding beside this one" not in (plain[0].remedy or ""), plain[0].remedy


def test_two_folders_that_differ_in_spelling_are_two_folders():
    """Fixing the double count folded genuinely distinct folders into one.

    One folder spelled NFD in both its directory entry and its members was
    counted twice because one branch normalised and the other did not; the
    repair normalised both, and then `Prüfbericht(NFC)/a.pdf` beside
    `Prüfbericht(NFD)/b.pdf` — two directory entries, two folders on any
    preserving filesystem — was counted as one. The module that owns these
    names says it in its first lines: mapping every member onto its canonical
    spelling loses a file when an archive holds both spellings.

    Two, then — and rendered so the two lines can be told apart, which is what
    `escaped` is for.
    """
    import io
    import unicodedata
    import zipfile

    from vdi2770_validate.runner import check_bytes

    composed = unicodedata.normalize("NFC", "Prüfbericht")
    decomposed = unicodedata.normalize("NFD", "Prüfbericht")
    assert composed != decomposed

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Metadata.xml", b"<x/>")
        z.writestr(composed + "/a.pdf", b"%PDF-1.4\n")
        z.writestr(decomposed + "/b.pdf", b"%PDF-1.4\n")
    report = check_bytes(buf.getvalue(), "twins.zip")
    z9 = [f for f in report.findings if f.rule.id == "Z9"]
    assert z9, [f.rule.id for f in report.findings]
    assert z9[0].detail.startswith("2 folders"), z9[0].detail
    # And the two names on the page are not the same line twice.
    listed = z9[0].detail.split(": ", 1)[1].split(", ")
    assert len(set(listed)) == 2, z9[0].detail
