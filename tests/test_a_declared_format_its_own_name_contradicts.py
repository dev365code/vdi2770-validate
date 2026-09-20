"""`F3` knew two formats, and the delivery that needed it declared a third.

The rule asks whether `FileFormat` and the file's name agree. It answered only
for `application/pdf` and `application/zip`, so every other declaration passed
whatever it was attached to -- a Word document declared as RTF among them,
which is the one the corpus actually holds and the one the reference
implementation reports and we did not.

The table stays a table of formats whose extension is not a matter of taste.
Nothing here guesses: a format the table does not know draws nothing, because a
rule that reports on a declaration it cannot judge is worse than one that is
quiet about it.
"""
import io
import zipfile

from vdi2770_validate.runner import check_file

from conftest import CLEAN_DOCUMENT, ROOT

DOC = zipfile.ZipFile(CLEAN_DOCUMENT)
META = DOC.read("VDI2770_Metadata.xml").decode()
PDF = DOC.read("B.pdf")
DECL_PDF = '<DigitalFile FileFormat="application/pdf">B.pdf</DigitalFile>'


def build(tmp_path, name, entries):
    p = tmp_path / name
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in entries:
            z.writestr(n, d)
    p.write_bytes(buf.getvalue())
    return str(p)


def with_extra(tmp_path, name, declared, member, payload=b"x"):
    """A clean document container plus one more declared file."""
    m = META.replace(
        DECL_PDF,
        DECL_PDF + f'\n        <DigitalFile FileFormat="{declared}">{member}</DigitalFile>')
    return build(tmp_path, name, [
        ("VDI2770_Metadata.xml", m), ("B.pdf", PDF), (member, payload)])


def ids(path):
    return {f.rule.id for f in check_file(path).findings}


def detail_of(path, rule_id):
    return " ".join(f.detail or "" for f in check_file(path).findings
                    if f.rule.id == rule_id)


def test_a_word_document_declared_as_rtf_is_caught(tmp_path):
    """The shape the corpus holds: a `.docx` declared `application/rtf`.

    Two formats that are both "a document somebody types in" and are not each
    other. A recipient's system routes on the declaration, opens an RTF reader
    and hands it a zip.
    """
    p = with_extra(tmp_path, "rtf.zip", "application/rtf", "B.docx")
    assert "F3" in ids(p), (
        f"a .docx declared as RTF drew no finding: {sorted(ids(p))}")
    assert "application/rtf" in detail_of(p, "F3")


def test_the_container_the_reference_warns_about_is_no_longer_silent():
    """The divergence this closes, asked of the real container rather than a
    fixture shaped like it.

    `documentcontainer-invalid.zip` draws a warning from the reference
    implementation and drew nothing but a PDF/A note from us. Its metadata
    declares `B.docx` as `application/rtf`; nothing else in it is wrong.
    """
    p = ROOT / "corpus" / "examples" / "container" / "documentcontainer-invalid.zip"
    assert p.exists(), "the corpus container this divergence is about is missing"
    assert "F3" in ids(str(p)), (
        f"the container the reference warns about still draws nothing from us: "
        f"{sorted(ids(str(p)))}")


def test_a_format_with_two_ordinary_spellings_accepts_either(tmp_path):
    """`.jpg` and `.jpeg` are one format with two names, and a rule that picked
    one would report half the world's photographs."""
    for member in ("plate.jpg", "plate.jpeg"):
        p = with_extra(tmp_path, f"ok-{member}.zip", "image/jpeg", member)
        assert "F3" not in ids(p), f"{member} declared image/jpeg was reported"


def test_a_format_the_table_does_not_know_draws_nothing(tmp_path):
    """The precision pin, and the reason the table is short.

    `text/plain` is honestly carried by `.txt`, `.log`, `.md`, `.csv` and more;
    a table that named one of those would turn a correct delivery red. A
    declaration this rule cannot judge is one it says nothing about.
    """
    for declared, member in (("text/plain", "notes.log"),
                             ("application/octet-stream", "firmware.bin")):
        p = with_extra(tmp_path, f"quiet-{member}.zip", declared, member)
        assert "F3" not in ids(p), (
            f"{member} declared {declared} was reported, and this rule cannot "
            f"know that is wrong")


def test_a_parameter_after_the_format_does_not_hide_the_mismatch(tmp_path):
    """`application/rtf; charset=utf-8` is still `application/rtf`."""
    p = with_extra(tmp_path, "param.zip", "application/rtf; charset=utf-8", "B.docx")
    assert "F3" in ids(p), "a media type with a parameter was not read as its type"
