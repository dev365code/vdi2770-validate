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


def _two_spellings_of(declared, first, second):
    """`CLEAN_DOCUMENT` with `declared` in the metadata and two members whose
    names differ in bytes but normalise to it."""
    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    meta = src.read("VDI2770_Metadata.xml").decode("utf-8").replace("B.pdf", declared)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in src.namelist():
            if name == "B.pdf":
                continue
            z.writestr(name, meta.encode("utf-8")
                       if name == "VDI2770_Metadata.xml" else src.read(name))
        z.writestr(first, src.read("B.pdf"))
        z.writestr(second, src.read("B.pdf"))
    return buf.getvalue()


COMBINING = ("ẹ́.pdf",                    # ẹ + acute
             "ẹ́.pdf",                   # e + dot below + acute
             "ẹ́.pdf")                   # e + acute + dot below


def test_a_name_the_archive_spells_two_ways_is_not_reported_as_absent():
    """`F1` said the file was not in the archive. It is there twice.

    Two members whose bytes differ but whose canonical form is the declared
    name: `Members.resolve` cannot choose between them and returns `None`, and
    every branch that reads `None` treats it as absence. The remedy a reader
    then gets is "add the missing file, or remove its DigitalFile entry" —
    adding makes it three members and changes nothing, and removing deletes a
    declaration that was correct.

    What the reader needs to be told is that the archive is ambiguous about
    this name, which `Z10` is already saying on another line. So `F1` must
    either say the same thing or say nothing; it must not say the file is
    missing.
    """
    declared, first, second = COMBINING
    assert unicodedata.normalize("NFC", first) == unicodedata.normalize("NFC", declared)
    assert unicodedata.normalize("NFC", second) == unicodedata.normalize("NFC", declared)
    assert first != second

    report = check_bytes(_two_spellings_of(declared, first, second), "pair.zip")
    absent = [f for f in report.findings
              if f.rule.id == "F1" and "not in the archive" in (f.detail or "")]
    assert not absent, [f.detail for f in absent]


def test_the_report_can_tell_two_identical_looking_members_apart():
    """`Z10` printed the same line twice, with no detail and no remedy.

    The two members do not have the same name — they have different names that
    render identically, which is the whole reason this is worth reporting. A
    reader given two byte-identical lines cannot act: they cannot tell which
    member each line is about, and nothing on the screen says Unicode
    normalisation is involved at all.
    """
    declared, first, second = COMBINING
    report = check_bytes(_two_spellings_of(declared, first, second), "pair.zip")
    z10 = [f for f in report.findings if f.rule.id == "Z10"]
    assert len(z10) == 2, [f.rule.id for f in report.findings]

    rendered = {(f.message, f.detail, f.where.member) for f in z10}
    assert len(rendered) == 2, (
        "two findings rendered identically; a reader cannot tell them apart")
    for f in z10:
        assert f.detail, "no detail, so the finding names nothing to look at"
        assert f.remedy, "no remedy"


def _stored_as(name, extra=None, metadata=None):
    """`CLEAN_DOCUMENT` with `B.pdf` stored under `name`."""
    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for member in src.namelist():
            if member == "B.pdf":
                continue
            z.writestr(member, (metadata or src.read("VDI2770_Metadata.xml"))
                       if member == "VDI2770_Metadata.xml" else src.read(member))
        z.writestr(name, src.read("B.pdf"))
        for n, d in (extra or {}).items():
            z.writestr(n, d)
    return buf.getvalue()


def test_two_members_that_extract_to_one_path_are_reported():
    """The archive holds `B.pdf` and `./B.pdf`. `unzip` writes one file.

    Which bytes the recipient ends up with depends on the order the archive
    stores them in — the declared PDF/A, or the junk that overwrote it. The
    verdict was **clean**, with a warning about the twin being undeclared, and
    the twin was never scanned: `Z10` keys duplicates on composition alone, so a
    pair that differs by a `.` segment is invisible to it while every rule that
    *resolves* a name treats the two as one.

    `Z10`'s own argument — one member overwrites the other on extraction — is
    stronger here than for the composition pairs it does report, because this
    one collides on every filesystem.
    """
    data = _stored_as("B.pdf", extra={"./B.pdf": b"not a pdf at all\n"})
    report = check_bytes(data, "collide.zip")
    fired = {f.rule.id for f in report.findings}
    assert "Z10" in fired, (
        f"two members extract to one path and nothing said so: {sorted(fired)}")
    assert not report.clean, "a container whose delivered bytes are a coin toss came back clean"


def test_a_declared_payload_keeps_its_exemption_however_it_is_spelled():
    """The same conforming delivery, with the member stored `./cad.zip`.

    A `.zip` the metadata declares is one of the document's files, and `Z3` and
    `Z11` are excused for it. Both exemptions compared the declared name to the
    member name with composition alone, so a `.` segment on either side lost
    the match and a conforming container drew two errors — while `F1` stayed
    silent on the same name, because *its* comparison had already been repaired.
    One report, two answers, from two spellings of one comparison.
    """
    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    meta = src.read("VDI2770_Metadata.xml").decode("utf-8")
    docx = [line for line in meta.splitlines() if "B.docx" in line]
    assert len(docx) == 1, docx
    meta = meta.replace(docx[0].strip(),
                        '<DigitalFile FileFormat="application/zip">cad.zip</DigitalFile>')
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as z:
        z.writestr("part.step", b"ISO-10303-21;\n")

    plain = {f.rule.id for f in check_bytes(
        _stored_as("B.pdf", extra={"cad.zip": payload.getvalue()},
                   metadata=meta.encode("utf-8")), "plain.zip").findings}
    dotted = {f.rule.id for f in check_bytes(
        _stored_as("B.pdf", extra={"./cad.zip": payload.getvalue()},
                   metadata=meta.encode("utf-8")), "dotted.zip").findings}
    assert "Z3" not in plain and "Z11" not in plain, f"the premise moved: {sorted(plain)}"
    assert dotted == plain, (
        f"spelling the member `./cad.zip` changed the verdict: {sorted(dotted)} "
        f"against {sorted(plain)}")


def _document_holding(*members, declared="B.pdf"):
    """The clean document container with `B.pdf` stored under other spellings.

    `declared` renames it in the metadata too, so the declaration reaches the
    spellings rather than missing them -- without that the container is a
    different finding entirely (*declared but not in the archive*) and every
    assertion below would pass for the wrong reason.
    """
    import io
    import zipfile

    from conftest import CLEAN_DOCUMENT

    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in src.namelist():
            if name == "B.pdf":
                for spelling in members:
                    z.writestr(spelling, src.read(name))
            elif name == "VDI2770_Metadata.xml":
                meta = src.read(name).decode("utf-8")
                assert meta.count(">B.pdf<") == 1, "the fixture no longer declares B.pdf once"
                z.writestr(name, meta.replace(">B.pdf<", f">{declared}<").encode("utf-8"))
            else:
                z.writestr(name, src.read(name))
    return buf.getvalue()


def test_two_spellings_that_do_not_print_alike_are_not_said_to():
    """`F1` had one sentence for two different ways of matching twice.

    `.//B.pdf` and `./B.pdf` reach one declaration because `folder_path` drops
    segments that name nothing -- not because they look the same, which they
    plainly do not. The finding said *2 members that print alike* and the remedy
    said *different bytes that print the same*, both about names a reader can
    tell apart at a glance, which leaves them looking for a difference that is
    not there.
    """
    from vdi2770_validate.runner import check_bytes

    report = check_bytes(_document_holding(".//B.pdf", "./B.pdf"), "dots.zip")
    f1 = [f for f in report.findings if f.rule.id == "F1"]
    assert len(f1) == 1, [f.detail for f in f1]
    assert "print alike" not in (f1[0].detail or ""), f1[0].detail
    assert "print the same" not in (f1[0].remedy or ""), f1[0].remedy


def test_two_spellings_that_do_print_alike_still_say_so():
    """The other half, so the sentence above cannot be fixed by deleting it.

    Two orders of the same two combining marks, declared as the composed form
    they both canonicalise to — so the declaration matches neither member
    exactly and reaches both. These really do print alike, and the finding
    should still say so.
    """
    from vdi2770_validate.runner import check_bytes

    report = check_bytes(
        _document_holding(ORDER_A, ORDER_B, declared=COMPOSED), "twins.zip")
    f1 = [f for f in report.findings if f.rule.id == "F1"]
    assert any("print alike" in (f.detail or "") for f in f1), [f.detail for f in f1]


def test_a_declaration_that_matches_twice_does_not_also_leave_them_undeclared():
    """One report said both things about one file.

    `F1`: *this declaration matches 2 members*. `F2`, twice, on the next lines:
    *a file in the container is not named in the metadata*, about those same two
    members. The declaration reaches them -- ambiguously, which is what `F1` is
    for -- so telling the sender to declare them or remove them points away from
    the fix `F1` just gave, and away from the truth.
    """
    from vdi2770_validate.runner import check_bytes

    report = check_bytes(_document_holding(".//B.pdf", "./B.pdf"), "dots.zip")
    stray = [f.where.subject for f in report.findings if f.rule.id == "F2"]
    assert not any(s and s.endswith("B.pdf") for s in stray), (
        f"F2 called a member undeclared that F1 says a declaration matches: {stray}")


def test_two_members_at_one_path_are_named_and_given_a_remedy():
    """`Z10` grouped by one relation and then filtered by a narrower one.

    `duplicate_names` is keyed on `folder_path` — canonical form *and* dropping
    segments that name nothing — while the look-alike branch selected with `nfc`
    alone. So `B.pdf` beside `./B.pdf` produced two findings carrying the rule's
    bare title, no detail and no remedy: nothing saying which members, nothing
    saying what to do. The branch that would have said both was reached through
    a door it was not watching.

    They do not print alike, so the sentence for that case would be false here —
    what is true is that they extract to one path, and a recipient ends up with
    one of them.
    """
    from vdi2770_validate.runner import check_bytes

    report = check_bytes(_document_holding("B.pdf", "./B.pdf"), "dot.zip")
    z10 = [f for f in report.findings if f.rule.id == "Z10"]
    assert z10, "nothing reported the collision at all"
    for f in z10:
        assert f.detail, f"a finding with no detail: {f.message}"
        assert f.remedy, f"a finding with no remedy: {f.message}"
        # `message` as well as `detail`. The first draft asserted only on the
        # detail, and the words *print alike* live in the title — so the branch
        # could be forced on, the finding could be headed "names that print
        # alike" about `B.pdf` and `./B.pdf`, and this passed.
        said = f"{f.message} {f.detail}"
        assert "print alike" not in said, said
        assert "extract to the same path" in said, said
        assert "./B.pdf" in f.detail and "B.pdf" in f.detail, f.detail


def test_two_spellings_that_print_alike_are_said_to_print_alike():
    """The mirror of the test above, so neither branch can be forced on.

    Two orders of the same combining marks: canonically equivalent, one path
    once the archive is unpacked, and they really do print alike.
    """
    from vdi2770_validate.runner import check_bytes

    report = check_bytes(_document_holding(ORDER_A, ORDER_B, declared=COMPOSED),
                         "twins.zip")
    z10 = [f for f in report.findings if f.rule.id == "Z10"]
    assert z10, "nothing reported the look-alike pair"
    for f in z10:
        said = f"{f.message} {f.detail}"
        assert "print alike" in said, said
        assert "extract to the same path" not in said, said


def test_a_pair_that_differs_both_ways_is_not_said_to_land_on_one_path():
    """`./` in front of a *decomposed* name, beside the composed spelling.

    `folder_path` groups them because it normalises and drops `.` segments, but
    they extract to two different paths and they do not print alike either. The
    branch said *Two members of the archive extract to the same path* and
    printed an anchor that is neither member's path — and `F2`, two lines down
    in the same report, correctly treated them as two files. It is `F2` that was
    right.
    """
    import unicodedata

    from vdi2770_validate.names import extracts_to
    from vdi2770_validate.runner import check_bytes

    composed = unicodedata.normalize("NFC", "\u00c4.pdf")
    decomposed = unicodedata.normalize("NFD", "\u00c4.pdf")
    assert composed != decomposed, "the two spellings arrived as one string"
    assert extracts_to("./" + decomposed) != extracts_to(composed), "premise"

    report = check_bytes(
        _document_holding(composed, "./" + decomposed, declared=composed), "both.zip")
    z10 = [f for f in report.findings if f.rule.id == "Z10"]
    assert z10, "nothing reported the collision"
    for f in z10:
        said = f"{f.message} {f.detail}"
        assert "extract to the same path" not in said, said
        assert "print alike" not in said, said
        assert "one file" in said, said


def test_a_path_collision_does_not_spell_out_a_blameless_name():
    """Two members differing by `./`, both written the way macOS writes them.

    Nothing about the *spelling* is in question — the difference is two visible
    ASCII characters — and the finding came back as four walls of hex, which is
    the failure this release says it fixed, arriving through a new door.
    """
    import unicodedata

    from vdi2770_validate.runner import check_bytes

    name = unicodedata.normalize("NFD", "\uc124\uba85\uc11c_Pr\u00fcfbericht.pdf")
    report = check_bytes(_document_holding(name, "./" + name, declared=name),
                         "mac.zip")
    z10 = [f for f in report.findings if f.rule.id == "Z10"]
    assert z10, "nothing reported the collision"
    for f in z10:
        assert "\\u" not in (f.detail or ""), (
            f"a name with nothing wrong with its spelling was printed as code "
            f"points: {f.detail}")
