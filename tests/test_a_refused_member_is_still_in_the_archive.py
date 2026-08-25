"""A member with a bad CRC is *in* the archive. The reader drops it from the
readable set, and three separate rules read that set as "not there":

  VDI2770_Main.pdf broken -> Z12 "could not be read"  and  Z7 "there is none,
                             add it"  and  F1 "declared but not in the archive"
  VDI2770_Main.xml broken -> Z12  and  Z3 "this is not a VDI 2770 container at
                             all", after which no M, F or X rule ran.

Presence is a fact about the archive's directory. Being unable to inflate the
bytes behind a name does not unsay the name.
"""
import io
import zipfile

from conftest import CLEAN_DOCUMENTATION
from vdi2770 import Kind, zipread
from vdi2770_validate.runner import check_bytes

SRC = zipfile.ZipFile(CLEAN_DOCUMENTATION)


def with_broken_crc(victim):
    """The clean documentation container, with `victim`'s stored CRC damaged."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name in SRC.namelist():
            z.writestr(name, SRC.read(name))
    raw = out.getvalue()
    crc = zipfile.ZipFile(io.BytesIO(raw)).getinfo(victim).CRC
    old = crc.to_bytes(4, "little")
    assert raw.count(old) == 2, "the CRC should appear in the local header and the directory"
    return raw.replace(old, ((crc ^ 0xFFFF) & 0xFFFFFFFF).to_bytes(4, "little"))


def findings(data):
    return check_bytes(data, "broken.zip").findings


def ids(data):
    return {f.rule.id for f in findings(data)}


def test_the_reader_still_lists_a_member_it_could_not_read():
    box = zipread.read(with_broken_crc("VDI2770_Main.xml"), "x.zip")
    assert "VDI2770_Main.xml" not in box.file_names, "it is not readable"
    assert "VDI2770_Main.xml" in box.present, "it is still in the archive"
    assert "VDI2770_Main.xml" in box.rejected


def test_an_unreadable_main_document_does_not_unclassify_the_container():
    data = with_broken_crc("VDI2770_Main.xml")
    assert zipread.read(data, "x.zip").kind is Kind.DOCUMENTATION
    got = ids(data)
    assert "Z12" in got, got
    assert "Z3" not in got, f"we know what this is; we cannot read one member: {got}"


def test_an_unreadable_main_pdf_is_not_a_missing_main_pdf():
    data = with_broken_crc("VDI2770_Main.pdf")
    got = ids(data)
    assert "Z12" in got, got
    assert "Z7" not in got, f"Z12 says it is there and Z7 says to add it: {got}"


def test_f1_says_unreadable_rather_than_absent():
    data = with_broken_crc("VDI2770_Main.pdf")
    f1 = [f for f in findings(data) if f.rule.id == "F1"]
    assert len(f1) == 1, [str(f.where) for f in f1]
    # It fires at the line in the metadata that named the file -- which is what
    # Z12, pointing at the member, cannot give you.
    assert f1[0].where.member == "VDI2770_Main.xml"
    assert "not in the container" not in f1[0].message, f1[0].message
    assert "could not be read" in f1[0].message
    assert "Re-create the archive" in f1[0].remedy


def test_a_genuinely_absent_file_is_still_reported_as_absent():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name in SRC.namelist():
            if name != "VDI2770_Main.pdf":
                z.writestr(name, SRC.read(name))
    data = out.getvalue()
    got = ids(data)
    assert "Z7" in got, f"a file that really is missing must still be reported: {got}"
    f1 = [f for f in findings(data) if f.rule.id == "F1"]
    assert f1 and "not in the container" in f1[0].message
    assert "declared but not in the archive" in f1[0].detail


def test_one_reason_per_member_not_two():
    # `metadata-unreadable` used to be appended on top of whatever had already
    # explained the member, so the report said two things about one file.
    box = zipread.read(with_broken_crc("VDI2770_Main.xml"), "x.zip")
    at_main = [d.kind for d in box.defects if d.where.member == "VDI2770_Main.xml"]
    assert at_main == ["member-unreadable"], at_main


def test_metadata_unreadable_still_has_a_path_and_still_maps_to_z12(monkeypatch):
    """`metadata-unreadable` is the backstop for a read that fails for a reason
    nothing else caught, and it was mapped to "this is not a VDI 2770 container"
    for a container we had already classified.

    Its one remaining route is narrow and worth pinning, because two later
    changes each nearly closed it. The decompression budget must run out
    *during* the sweep — so the metadata member is never verified — while still
    having room for that member when the metadata read charges for it. Budgets
    are per member, not a gate: a big one can be refused and a small one after
    it still fit.
    """
    data = with_broken_crc("VDI2770_Main.xml")
    sizes = {i.filename: i.file_size
             for i in zipfile.ZipFile(io.BytesIO(data)).infolist() if not i.is_dir()}
    order = [i.filename for i in zipfile.ZipFile(io.BytesIO(data)).infolist() if not i.is_dir()]
    meta = "VDI2770_Main.xml"
    before = order[:order.index(meta)]
    assert before, "the metadata must not be the first member, or nothing exhausts first"

    # Room for everything ahead of the metadata, plus the metadata itself, but
    # not for the largest member ahead of it -- so the sweep gives up partway and
    # the metadata read still fits.
    biggest = max(sizes[n] for n in before)
    budget = sum(sizes[n] for n in before) - biggest + sizes[meta]
    monkeypatch.setattr(zipread, "MAX_TOTAL_DECOMPRESSED", budget)

    box = zipread.read(data, "x.zip")
    kinds = [d.kind for d in box.defects]
    assert "decompression-budget-exhausted" in kinds, kinds
    assert "metadata-unreadable" in kinds, (
        f"the backstop is now unreachable and should be deleted rather than kept: {kinds}")
    assert box.kind is Kind.DOCUMENTATION

    got = {f.rule.id for f in check_bytes(data, "x.zip").findings}
    assert "Z12" in got, got
    assert "Z3" not in got, got


def test_the_report_writes_the_refusal_sentence_not_the_reader():
    """`rejected` carries the `Defect`; the sentence a user reads is written
    here. (This test was lost once to an edit that truncated the file, which is
    its own lesson about rewriting a file instead of editing it.)
    """
    from vdi2770_validate.names import Members

    data = with_broken_crc("VDI2770_Main.pdf")
    box = zipread.read(data, "x.zip")
    said = Members(box.file_names, box.rejected).refusal("VDI2770_Main.pdf")
    assert said and said.startswith("it is in the archive but could not be read"), said
    assert "Bad CRC-32" in said, said


def test_every_kind_that_can_refuse_a_member_has_a_sentence():
    """Three versions of this gate, and the first two were wrong.

    A six-element literal of defect kinds — the hand-copied list `DEFECT_KINDS`
    exists to abolish. Then a regex over the reader's source, which broke on the
    first refactor and, worse, silently missed a call site written in a shape it
    did not match. Then a sweep of the corpus, which only ever asked about kinds
    this repository's own fixtures happen to produce — and no fixture reaches
    2 GiB, so `archive-too-large` and `decompression-budget-exhausted` were both
    missing while the gate stayed green, and a user was shown
    `the reader refused it (archive-too-large)`.

    The reader publishes the set. That is the only version of this that cannot
    rot.
    """
    from vdi2770 import REFUSAL_KINDS
    from vdi2770_validate.names import Members

    missing = sorted(REFUSAL_KINDS - set(Members.SAID))
    assert not missing, f"a refused member would print a bare defect kind: {missing}"
    stray = sorted(set(Members.SAID) - REFUSAL_KINDS)
    assert not stray, f"the table names things that cannot refuse a member: {stray}"


def test_the_reader_only_refuses_with_kinds_it_publishes():
    """`REFUSAL_KINDS` is a claim about the reader, so it is checked against the
    reader rather than trusted. Every refusal the corpus and fixtures actually
    produce has to be in it — the set may be wider than what a fixture reaches,
    but it may not be narrower."""
    from conftest import CORPUS, FIXTURES
    from vdi2770 import REFUSAL_KINDS, zipread

    seen = set()
    for z in sorted(CORPUS.rglob("*.zip")) + sorted(FIXTURES.rglob("*.zip")):
        for c in zipread.read(z.read_bytes(), z.name).walk():
            seen |= {d.kind for d in c.rejected.values()}
    assert seen, "no container in this repository refuses anything; this tests nothing"
    assert seen <= REFUSAL_KINDS, sorted(seen - REFUSAL_KINDS)


def test_a_budget_refusal_reads_as_a_sentence():
    """The two that were missing, exercised rather than asserted about."""
    import io
    import zipfile

    from vdi2770 import zipread
    from vdi2770_validate.names import Members

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("readme.txt", b"x" * 8192)
        z.writestr("late.pdf", b"%PDF-1.7\n")
    original = zipread.MAX_TOTAL_BYTES
    try:
        zipread.MAX_TOTAL_BYTES = 4096
        box = zipread.read(buf.getvalue(), "big.zip")
    finally:
        zipread.MAX_TOTAL_BYTES = original

    assert "late.pdf" in box.rejected
    said = Members(box.file_names, box.rejected).refusal("late.pdf")
    assert said and "archive-too-large" not in said, said
    assert said.startswith("the archive passed"), said


def test_each_refusal_says_something_different_and_says_it_in_words():
    """The completeness gate above asks that every kind *has* a sentence. It has
    no opinion on what the sentence is, so nine identical strings — or nine
    copies of the kind — would pass it.

    Not every property is worth pinning: the wording is prose and should be free
    to improve. These three are not wording.

      * Distinct. Two refusals a user cannot tell apart are one refusal, and the
        whole point of the table is that "we did not look" has nine reasons.
      * No raw kind. `member-budget-exhausted` is an identifier this project
        chose; a person reading a report has never seen it and cannot act on it.
        `SAID` exists precisely to not print it.
      * A clause, not a label. Each is spliced into a sentence after "because",
        so it has to read as one: lower case, no full stop, and long enough to be
        a reason rather than a tag.
    """
    from vdi2770_validate.names import Members

    said = Members.SAID
    assert len(set(said.values())) == len(said), (
        "two refusal kinds share a sentence: "
        f"{sorted(k for k, v in said.items() if list(said.values()).count(v) > 1)}")
    for kind, sentence in sorted(said.items()):
        assert kind not in sentence, f"{kind} prints its own identifier: {sentence!r}"
        assert "-" not in sentence.split(" ")[0], f"{kind} opens with a tag: {sentence!r}"
        assert sentence[:1].islower(), f"{kind} is not a clause: {sentence!r}"
        assert not sentence.endswith("."), f"{kind} ends a sentence it is spliced into: {sentence!r}"
        assert len(sentence.split()) >= 5, f"{kind} is a label, not a reason: {sentence!r}"


def test_a_remedy_tells_the_sender_what_to_do_about_that_kind():
    """`REMEDY_FOR_DEFECT` is looked up by kind and dropped into `fix=`, and a
    miss is silent: `.get()` returns None and the finding renders with no remedy
    at all. Nothing connected the keys to the kinds they are keyed by, so a
    renamed kind would take its remedy off every report without a red test.
    """
    from vdi2770.model import DEFECT_KINDS
    from vdi2770_validate.rules.container import REMEDY_FOR_DEFECT

    stray = sorted(set(REMEDY_FOR_DEFECT) - DEFECT_KINDS)
    assert not stray, f"remedies keyed by something the reader cannot emit: {stray}"
    for kind, remedy in sorted(REMEDY_FOR_DEFECT.items()):
        assert kind not in remedy, f"{kind}'s remedy prints the identifier: {remedy!r}"
        assert remedy[:1].isupper() and remedy.rstrip().endswith("."), (
            f"a remedy is a sentence addressed to the sender: {remedy!r}")
