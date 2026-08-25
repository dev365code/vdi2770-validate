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

import pytest

from conftest import CLEAN_DOCUMENT
from vdi2770_validate.runner import check_bytes, check_file

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


def test_an_exactly_repeated_name_is_as_ambiguous_as_a_normalised_one():
    """`Members.resolve` guards the NFC collision and short-circuits on an exact
    match, so a name that denotes *two* entries resolves to whichever the ZIP
    reader hands back — the last one.

    Reproduced: one archive, two members both called `B.pdf`, one a real PDF/A-3a
    and one sixteen bytes of text. Swapping their order swaps the verdict.

        real first  -> P1  "A file that should be a PDF is not one"
        junk first  -> P4  "The PDF claims a PDF/A level"  (about the text file)

    Both are wrong, in opposite directions, and `runner.py`'s own comment records
    "the tool printed a PDF/A claim for a text file" as a fixed regression. `Z10`
    already reports the ambiguity; the P rules should decline, which is exactly
    the argument `names.py` makes for the normalised case.
    """
    import io
    import zipfile

    from conftest import CLEAN_DOCUMENT
    from vdi2770_validate.runner import check_bytes

    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    real, junk = src.read("B.pdf"), b"not a pdf at all"

    def built(order):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for name in src.namelist():
                if name == "B.pdf":
                    for payload in order:
                        z.writestr("B.pdf", payload)
                else:
                    z.writestr(name, src.read(name))
        return check_bytes(buf.getvalue(), "dup.zip")

    forward = {f.rule.id for f in built([real, junk]).findings}
    backward = {f.rule.id for f in built([junk, real]).findings}

    assert "Z10" in forward and "Z10" in backward, "the duplicate itself must be reported"
    assert forward == backward, (
        f"the verdict depends on which entry the archive stores last: "
        f"{sorted(forward)} vs {sorted(backward)}")
    assert not (forward & {"P1", "P4"}), (
        f"a name that denotes two different files was judged as one: {sorted(forward)}")


def _respelled(mapping):
    """`CLEAN_DOCUMENT` with some members stored under a different spelling."""
    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in src.namelist():
            z.writestr(mapping.get(name, name), src.read(name))
    return buf.getvalue()


# `d//B.pdf` is deliberately absent: it normalises to `d/B.pdf`, which is a
# different file from the `B.pdf` this metadata declares. Only segments that
# drop out entirely -- `.` and empty -- may be reconciled away.
@pytest.mark.parametrize("spelling", ["./B.pdf", ".//B.pdf", ".///./B.pdf"])
def test_a_member_spelled_with_a_dot_segment_is_the_file_the_metadata_declares(spelling):
    """One file, reported as two contradictory things.

    `names.py` exists because "every place that compares a name has to reconcile
    them the *same* way" -- its own words. It reconciles NFC and nothing else,
    while three other places in this codebase deliberately drop `.` segments on
    the stated grounds that writers mix `./` prefixes freely inside one archive.
    So `./B.pdf` was reported `F1` *declared but not in the archive* and `F2` *in
    the container but not named in the metadata*, in the same report, about the
    same file -- verbatim the failure this module's docstring says it prevents.
    Both remedies are unactionable: adding the file again changes nothing, and
    removing the `DigitalFile` entry breaks conformant metadata.
    """
    report = check_bytes(_respelled({"B.pdf": spelling}), "dot.zip")
    fired = {f.rule.id for f in report.findings}
    assert "F1" not in fired, [f.detail for f in report.findings if f.rule.id == "F1"]
    assert "F2" not in fired, [f.where.member for f in report.findings if f.rule.id == "F2"]


def test_a_dot_segment_does_not_stop_the_pdf_being_looked_at():
    """The quiet half of the same defect.

    `pdf._targets` resolves declared names through `Members` too, so a member the
    resolution could not find is a member nobody scans -- the `P4` note that
    reads the file's PDF/A claim simply disappears, and nothing in the report
    says a PDF went unexamined.
    """
    plain = {f.rule.id for f in check_bytes(_respelled({}), "plain.zip").findings}
    dotted = {f.rule.id for f in check_bytes(_respelled({"B.pdf": "./B.pdf"}),
                                             "dot.zip").findings}
    assert "P4" in plain, "the premise: this container's PDF carries a claim"
    assert "P4" in dotted, "the PDF was never scanned once its name gained a `./`"
