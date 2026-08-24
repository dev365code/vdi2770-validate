"""An archive can hold both Unicode spellings of one visible name. They are two
members with different bytes, and collapsing them loses a file.

Reconciling NFD and NFC was right — macOS writes decomposed names and metadata
authored elsewhere is composed — but it was done by mapping every member onto
its canonical spelling, so an archive holding both spellings kept whichever came
last. The declared, valid PDF was reported as not a PDF because the scan read
its junk twin; the twin itself was never reported as undeclared, because the set
of present names had collapsed to one; and reversing the member order flipped
the whole verdict.
"""
import io
import unicodedata
import zipfile

from conftest import CLEAN_DOCUMENT
from vdi2770_validate.runner import check_file

SRC = zipfile.ZipFile(CLEAN_DOCUMENT)
META = SRC.read("VDI2770_Metadata.xml").decode()
PDF = SRC.read("B.pdf")
DOCX = SRC.read("B.docx")

NFC = "Prüfbericht.pdf"
NFD = unicodedata.normalize("NFD", NFC)
assert NFC != NFD


def build(tmp_path, name, members, declared=NFC):
    p = tmp_path / name
    meta = META.replace(">B.pdf<", f">{declared}<")
    assert meta != META
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VDI2770_Metadata.xml", meta)
        z.writestr("B.docx", DOCX)
        for n, d in members:
            z.writestr(n, d)
    p.write_bytes(buf.getvalue())
    return str(p)


def report(path):
    return [(f.rule.id, f.where.member) for f in check_file(path).sorted()]


def ids(path):
    return {r for r, _ in report(path)}


def test_both_spellings_present_is_reported_as_the_ambiguity_it_is(tmp_path):
    p = build(tmp_path, "twins.zip", [(NFC, PDF), (NFD, b"not a pdf\n")])
    got = ids(p)
    assert "Z10" in got, f"the two members were treated as one: {report(p)}"
    assert "P1" not in got, f"the declared PDF is valid; something else was scanned: {report(p)}"


def test_the_verdict_does_not_depend_on_which_twin_comes_first(tmp_path):
    forward = ids(build(tmp_path, "fwd.zip", [(NFC, PDF), (NFD, b"not a pdf\n")]))
    reverse = ids(build(tmp_path, "rev.zip", [(NFD, b"not a pdf\n"), (NFC, PDF)]))
    assert forward == reverse, f"{sorted(forward)} vs {sorted(reverse)}"


def test_the_undeclared_twin_is_reported_under_its_own_name(tmp_path):
    p = build(tmp_path, "undeclared_twin.zip", [(NFC, PDF), (NFD, b"anything\n")])
    f2 = [m for r, m in report(p) if r == "F2"]
    assert f2 == [NFD], f"F2 reported {f2!r}; the archive's own spelling is {NFD!r}"


def test_one_spelling_still_matches_the_other(tmp_path):
    """The reconciliation this replaces was there for a reason: a lone
    decomposed member declared in composed form is one file, not a mismatch."""
    p = build(tmp_path, "lone.zip", [(NFD, PDF)])
    assert not ids(p) & {"F1", "F2", "Z10"}, report(p)
    assert "P4" in ids(p), "the file was never scanned"


def test_an_exact_duplicate_is_still_one_complaint(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VDI2770_Metadata.xml", META)
        z.writestr("B.pdf", PDF)
        z.writestr("B.docx", DOCX)
        z.writestr("B.pdf", PDF)
    p = tmp_path / "exact.zip"
    p.write_bytes(buf.getvalue())
    assert [m for r, m in report(str(p)) if r == "Z10"] == ["B.pdf"]


def test_a_refused_member_is_found_under_either_spelling(tmp_path):
    """`rejected` is keyed by the archive's spelling and was looked up with the
    metadata's. The user was told the file is not in the archive when it is
    there and we declined it — the exact untruth that dict exists to prevent."""
    p = build(tmp_path, "refused.zip",
              [(NFD, b"\0" * (16 * 1024 * 1024))])   # over the ratio floor, refused
    f1 = [f for f in check_file(p).findings if f.rule.id == "F1"]
    assert f1, ids(p)
    assert "refused" in (f1[0].detail or ""), f1[0].detail


# Two decompositions that differ only in the order of their combining marks.
# Both normalise to the same composed form and neither equals it, so a name
# declared in that composed form matches two members and none of them exactly.
ORDER_A = "ẹ́.pdf"
ORDER_B = "ẹ́.pdf"
COMPOSED = unicodedata.normalize("NFC", ORDER_A)
assert ORDER_A != ORDER_B
assert COMPOSED not in (ORDER_A, ORDER_B)
assert unicodedata.normalize("NFC", ORDER_B) == COMPOSED


def test_a_name_that_matches_two_members_and_neither_exactly_is_not_guessed(tmp_path):
    """The exact-match branch covers the common twin. This is the case that
    reaches the ambiguity branch, and it is the one where answering with either
    member is a guess: combining marks in two orders, declared in the composed
    form that equals neither.
    """
    p = build(tmp_path, "combining.zip",
              [(ORDER_A, PDF), (ORDER_B, b"not a pdf\n")], declared=COMPOSED)
    got = report(p)
    ids_ = {r for r, _ in got}
    assert "Z10" in ids_, f"the ambiguity was not reported: {got}"
    assert "P1" not in ids_, f"one of the two was read as if it were the declared file: {got}"
    assert "F1" in ids_, f"nothing said the declared name resolves to no single file: {got}"
