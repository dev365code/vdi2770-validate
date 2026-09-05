"""`MAX_INFLATED_TOTAL` bounds one file. A container declares many.

`docs/scope.md` sells "more than a thousand containers, 64 MiB of metadata, or
4 GiB inflated, in one read" as three limits that bound *the tree*, and says why
the third was added: "a 6.4 MB file inflated two terabytes and returned a clean
verdict". The ZIP reader keeps that promise for the bytes it inflates. The PDF
scan inflates through a door that budget does not watch — the members it reads
are tiny, and each one is then expanded on its own 32 MB allowance — so the
product of declared files and that allowance was bounded by nothing.

Measured before the repair: a 5.7 MB archive of 150 declared PDFs inflated
4.47 GiB in 12.7 seconds and returned exit 0. At `MAX_MEMBERS` the same shape
reaches about 300 GiB.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
import zlib

import pytest

from conftest import A_PDF, CLEAN_DOCUMENT, CLEAN_DOCUMENTATION
from vdi2770 import pdfread
from vdi2770_validate.model import About, Severity
from vdi2770_validate.report import as_json
from vdi2770_validate.runner import check_bytes

# Ten streams, so one file wants ten times what a single stream may become.
_BLOB = zlib.compress(b"A" * 400_000)
_GREEDY = A_PDF + b"".join(b"stream\n" + _BLOB for _ in range(10))


def _container(count: int) -> bytes:
    """A conforming document container that also declares `count` greedy PDFs."""
    base = zipfile.ZipFile(CLEAN_DOCUMENT)
    meta = base.read("VDI2770_Metadata.xml").decode("utf-8")
    declared = "\n      ".join(
        f'<DigitalFile FileFormat="application/pdf">g{i}.pdf</DigitalFile>'
        for i in range(count))
    meta = meta.replace("<DigitalFile", declared + "\n      <DigitalFile", 1)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in base.namelist():
            z.writestr(name, meta if name == "VDI2770_Metadata.xml" else base.read(name))
        for i in range(count):
            z.writestr(f"g{i}.pdf", _GREEDY)
    return buf.getvalue()


def _declared_pdfs(raw: bytes) -> set:
    """Every member the metadata declares as a PDF — the scan's whole work list.

    Derived from the container rather than written down, because the clean
    fixture declares PDFs of its own: an expected total that counted only the
    files this test adds is a test that disagrees with the tool about how many
    files there are, and then blames the tool.
    """
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        meta = z.read("VDI2770_Metadata.xml").decode("utf-8")
    return set(re.findall(r'FileFormat="application/pdf">([^<]+)<', meta))


@pytest.fixture
def counted(monkeypatch):
    """Bytes handed back by zlib during one read, and small budgets to hit."""
    monkeypatch.setattr(pdfread, "MAX_INFLATED_PER_STREAM", 400_000)
    monkeypatch.setattr(pdfread, "MAX_INFLATED_TOTAL", 4_000_000)
    total = [0]
    real = zlib.decompressobj

    class Counting:
        def __init__(self, *a, **k):
            self._o = real(*a, **k)

        def decompress(self, data, limit=0):
            out = (self._o.decompress(data, limit) if limit
                   else self._o.decompress(data))
            total[0] += len(out)
            return out

        def __getattr__(self, name):
            return getattr(self._o, name)

    monkeypatch.setattr(zlib, "decompressobj", Counting)
    return total


def test_the_inflation_budget_is_for_the_read_not_for_each_file(counted,
                                                               monkeypatch):
    """Eight greedy files, and a read allowed less than three of them."""
    assert pdfread.MAX_INFLATED_PER_READ >= pdfread.MAX_INFLATED_TOTAL, (
        "a read may not be allowed less than the one file it is given")
    ceiling = 10_000_000
    monkeypatch.setattr(pdfread, "MAX_INFLATED_PER_READ", ceiling)
    each = pdfread.MAX_INFLATED_TOTAL

    counted[0] = 0
    check_bytes(_container(8), "greedy.zip")
    # One file may overshoot the ceiling; the next must not start. Before the
    # repair this input cost eight files' worth however many the read had left.
    assert counted[0] <= ceiling + each, (
        f"the read inflated {counted[0]} bytes against a ceiling of {ceiling}")
    assert counted[0] < 8 * each, (
        f"the premise: eight files unbounded is {8 * each} bytes")


def test_a_file_we_stopped_short_of_reading_is_not_called_claimless(counted,
                                                                    monkeypatch):
    """P3 says a bounded scan found no PDF/A claim. It did not scan at all.

    The other findings still stand: what the allowance takes away is the search
    for a claim, so every declared file either had that search run -- and draws
    `P3` when it found none or `P4` when it found one -- or is counted by `Z5`,
    and never both.
    """
    monkeypatch.setattr(pdfread, "MAX_INFLATED_PER_READ", 4_000_000)
    raw = _container(8)
    declared = _declared_pdfs(raw)
    assert len(declared) > 8, "the premise: the clean container declares PDFs too"
    report = check_bytes(raw, "greedy.zip")
    searched = {f.where.member for f in report.findings
                if f.rule.id in ("P3", "P4")} & declared

    stopped = [f for f in report.findings if f.rule.id == "Z5"]
    assert stopped, (
        f"files had their claim search cut short and no finding says so: "
        f"{sorted(f.rule.id for f in report.findings)}")
    said = int(re.search(r"inside (\d+) declared", stopped[0].detail).group(1))
    assert said, "the premise: this read must stop before the last file"

    assert said + len(searched) == len(declared), (
        f"{len(declared)} declared, {len(searched)} searched, {said} said cut short")
    named = re.search(r"cut short for: (.*?)\. Nothing is said", stopped[0].detail).group(1)
    listed = named.replace(", ...", "").split(", ")
    for one in listed:
        assert one not in searched, f"{one} was both searched and counted"
    # Several of them, and not all: a list of one is a count wearing a name, and
    # a list of all of them is what the bound exists to stop. Written against the
    # numbers this test set up rather than against `MAX_NAMED`, which a mutation
    # moves on both sides of an assertion that reads it.
    assert said > 5, "the premise: more files than the sentence will name"
    assert 2 <= len(listed) < said, listed
    assert named.endswith(", ...") or ", ..." in named, named
    # And the budget is quoted the way every other page quotes one.
    assert f"{pdfread.MAX_INFLATED_PER_READ / 1024 ** 3:g} GiB" in stopped[0].detail, (
        stopped[0].detail)


#: Greedy like `_GREEDY`, and it carries a claim after the greed. Eight streams
#: rather than ten, so one of these fits inside `MAX_INFLATED_TOTAL` and the
#: claim is reachable in an unbudgeted read — the truth this is compared
#: against. What runs out partway through it is the budget for the whole read,
#: and everything the search wants is on the far side of where that stopped.
_CLAIMED = (A_PDF + b"".join(b"stream\n" + _BLOB for _ in range(8))
            + b"stream\n" + zlib.compress(
                b'<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>'
                b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
                b'<rdf:Description xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">'
                b"<pdfaid:part>2</pdfaid:part>"
                b"<pdfaid:conformance>B</pdfaid:conformance>"
                b"</rdf:Description></rdf:RDF><?xpacket end=\"w\"?>"))


def _container_of(bodies: dict) -> bytes:
    """A conforming document container declaring each name in `bodies`."""
    base = zipfile.ZipFile(CLEAN_DOCUMENT)
    meta = base.read("VDI2770_Metadata.xml").decode("utf-8")
    declared = "\n      ".join(
        f'<DigitalFile FileFormat="application/pdf">{name}</DigitalFile>'
        for name in bodies)
    meta = meta.replace("<DigitalFile", declared + "\n      <DigitalFile", 1)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in base.namelist():
            z.writestr(name, meta if name == "VDI2770_Metadata.xml" else base.read(name))
        for name, body in bodies.items():
            z.writestr(name, body)
    return buf.getvalue()


def _a_boundary_file_exists(raw: bytes, names, ceiling: int, counted) -> bool:
    """Whether some file's claim search starts under this allowance and does not
    finish — which is what these two tests are about, and what "a `Z5` exists"
    does not give.

    An allowance that is an exact multiple of what one file inflates stops
    cleanly *between* files: every later file is cut short before it is opened,
    a `Z5` says so, and there is no boundary file at all. Both tests then pass
    against the code they were written to fail against, and their premises stay
    true while they do it. The window is narrow — multiples of one file's cost,
    and one byte either side — which is why it is measured here rather than
    argued from the fixture's arithmetic.
    """
    read_one = pdfread.reader(ceiling)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for name in names:
            counted[0] = 0
            _, cut_short = read_one(archive.read(name))
            if counted[0] and cut_short:
                return True          # it inflated something and still stopped
    return False


def test_a_file_the_budget_ran_out_inside_is_not_accused_of_carrying_no_claim(
        counted, monkeypatch):
    """The test above conserves a count, and a file can be on the wrong side of
    one that adds up.

    It asserts every declared file is either searched — `P3` for no claim, `P4`
    for one — or counted by `Z5`, never both. A file the budget runs out
    *inside* satisfies that and is still wrong: the read reached it, so the
    search started and it draws `P3`; `Z5` begins at the file after it. Both
    numbers add up, and the sentence the sender is handed says their file has no
    PDF/A claim in it.

    `cut_short` was decided before the file was looked at — "the allowance was
    already spent when this one came up" — which is true of every file after the
    boundary and false of the boundary itself.

    Counted against the truth rather than against the bookkeeping: an unbudgeted
    read of the same bytes says what is really in them.
    """
    monkeypatch.setattr(pdfread, "MAX_INFLATED_PER_READ", 6_000_000)
    bodies = {f"c{i}.pdf": _CLAIMED for i in range(4)}
    raw = _container_of(bodies)

    assert _a_boundary_file_exists(raw, bodies, 6_000_000, counted), (
        "the premise: some file's search has to start and not finish")
    report = check_bytes(raw, "boundary.zip")

    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        carries = {name for name in bodies
                   if pdfread.read(z.read(name)).pdfa_claim is not None}
    assert carries == set(bodies), "the premise: every one of them carries a claim"

    accused = {f.where.member for f in report.findings if f.rule.id == "P3"}
    assert not accused & carries, (
        f"{sorted(accused & carries)} carry a PDF/A claim and were told they do "
        f"not. The scan was cut short inside them and reported that as a fact "
        f"about the file")


def test_the_boundary_file_is_not_reported_as_a_complete_read(counted,
                                                              monkeypatch):
    """`docs/scope.md`: the flag "is false when anything was declined".

    Nothing about the boundary file was declined *in the bookkeeping* — it drew
    a finding on the container axis like any judged file — so a read that never
    finished looking came back saying it had.

    **The boundary file is the last one**, which is the arrangement this needs.
    Give the read a file after it and that one is never started at all, so the
    flag would come down for a file nobody looked at — a case the tool already
    handled — rather than for the one it looked at halfway.
    """
    import json

    from vdi2770_validate.report import as_json

    monkeypatch.setattr(pdfread, "MAX_INFLATED_PER_READ", 5_000_000)
    raw = _container_of({f"c{i}.pdf": _CLAIMED for i in range(2)})
    names = [f"c{i}.pdf" for i in range(2)]
    assert _a_boundary_file_exists(raw, names, 5_000_000, counted), (
        "the premise: some file's search has to start and not finish")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert all(pdfread.read(z.read(n)).pdfa_claim for n in names), (
            "the premise: there is something in these files to have missed")
    payload = json.loads(as_json(check_bytes(raw, "boundary.zip")))
    assert payload["read"]["complete"] is False, (
        "a read that stopped inside a file reported itself complete")


#: Over `MAX_INFLATED_TOTAL` on its own, so this one is stopped by its own
#: ceiling however much the read has left.
_OVERSIZE = (A_PDF + b"".join(b"stream\n" + _BLOB for _ in range(12))
             + _CLAIMED[len(A_PDF):])


def test_a_ceiling_this_file_reached_on_its_own_is_not_an_error_about_the_tool(
        counted, monkeypatch):
    """Three limits can cut a claim search short and only one of them is `Z5`.

    `Z5` is `about: tool` and an error, and it is right for the allowance spent
    across the *read*: that file was not looked at because of the files before
    it, which is nothing to do with the file. A ceiling one file reaches on its
    own is `P3` — the rule written to say "this scan found no PDF/A claim",
    whose remedy already ends *"if the file does carry one, our scan did not
    reach it"*.

    Treating the two alike turned a 2 KB archive of an ordinary multi-page PDF
    from exit 0 into exit 1, which is the class `test_tool_limits_are_not_
    verdicts.py` exists to keep out: a limit of this program reported as an
    error about somebody else's document.
    """
    monkeypatch.setattr(pdfread, "MAX_INFLATED_PER_READ", 1_000_000_000)
    report = check_bytes(_container_of({"big.pdf": _OVERSIZE}), "oversize.zip")

    assert not [f for f in report.findings if f.rule.id == "Z5"], (
        "one file over a ceiling of its own is not the read declining to look")
    assert "big.pdf" in {f.where.member for f in report.findings
                         if f.rule.id == "P3"}, (
        f"produced {sorted(f.rule.id for f in report.findings)}")
    assert report.count(Severity.ERROR) == 0, (
        "an ordinary file this tool cannot scan to the end must not fail a build")


def test_the_read_allowance_is_still_the_one_that_says_so(counted, monkeypatch):
    """The other side of the split: spent across the read, `Z5` and its remedy."""
    monkeypatch.setattr(pdfread, "MAX_INFLATED_PER_READ", 5_000_000)
    report = check_bytes(_container_of({f"c{i}.pdf": _CLAIMED for i in range(3)}),
                         "spent.zip")
    stopped = [f for f in report.findings if f.rule.id == "Z5"]
    assert stopped, sorted(f.rule.id for f in report.findings)
    assert "this read spent" in stopped[0].detail, stopped[0].detail
    assert "Split the delivery" in stopped[0].remedy, stopped[0].remedy


def test_a_scan_that_stopped_inside_a_file_says_so_and_owns_it(counted,
                                                              monkeypatch):
    """`P3` said one sentence whether the scan reached the end of the file or
    not, and `complete` came back `true` either way.

    The remedy already covered both — *"if the file does carry one, our scan did
    not reach it"* — so the rule knew this could happen. The detail did not say
    which had happened, and a sender cannot tell those apart from the outside.
    `_OVERSIZE` carries a PDF/A-2b claim; an unbudgeted read of the same bytes
    finds it.

    Not `Z5`: that is an error on the tool axis and an ordinary multi-page PDF
    reaches this ceiling. The finding stays a warning about the container's
    document, and takes the tool axis for this one occurrence — which is what
    `Finding.as_about` is for, and what makes `complete` false without a rule
    changing severity.
    """
    monkeypatch.setattr(pdfread, "MAX_INFLATED_PER_READ", 1_000_000_000)
    raw = _container_of({"big.pdf": _OVERSIZE})
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        body = z.read("big.pdf")
    with monkeypatch.context() as wide:
        # `counted` lowers the per-file ceiling to make this file reach it, so
        # the oracle has to be read with that ceiling out of the way -- the
        # question is what is in the file, not what a bounded scan sees.
        wide.setattr(pdfread, "MAX_INFLATED_TOTAL", 100_000_000)
        assert pdfread.read(body).pdfa_claim, (
            "the premise: an unbudgeted read finds a claim in this file")

    report = check_bytes(raw, "oversize.zip")
    p3 = [f for f in report.findings
          if f.rule.id == "P3" and f.where.member == "big.pdf"]
    assert len(p3) == 1, sorted(f.rule.id for f in report.findings)
    one = p3[0]

    assert "did not reach" in one.detail or "stopped" in one.detail, (
        f"the detail does not say the scan was cut short: {one.detail!r}")
    assert one.about is About.TOOL, (
        "a scan this tool stopped is this tool's, not the sender's")
    assert one.severity is Severity.WARNING, (
        "an ordinary file this tool cannot scan to the end must not fail a build")
    assert report.count(Severity.ERROR) == 0

    payload = json.loads(as_json(report))
    assert payload["read"]["complete"] is False, (
        "the read stopped inside a file and reported itself complete")


def test_a_scan_that_did_reach_the_end_still_says_the_plain_thing(counted):
    """The control. Without it the test above passes on a rule that says "cut
    short" about everything, which is the same defect pointing the other way."""
    raw = _container_of({"tiny.pdf": A_PDF})
    report = check_bytes(raw, "tiny.zip")
    p3 = [f for f in report.findings
          if f.rule.id == "P3" and f.where.member == "tiny.pdf"]
    assert len(p3) == 1, sorted(f.rule.id for f in report.findings)
    one = p3[0]

    assert one.detail == "no pdfaid identification found in the XMP metadata", one.detail
    assert one.about is About.CONTAINER, (
        "a scan that ran to the end and found nothing is about the file")
    assert json.loads(as_json(report))["read"]["complete"] is True


def _real_pdf(decoys: int = 0) -> bytes:
    """A PDF a reader opens, with `decoys` occurrences of `obj` in a comment.

    A comment is legal anywhere between tokens (ISO 32000-1 §7.2.4), so this is
    a conforming file with five indirect objects and nothing unusual about it
    beyond a long remark.
    """
    remark = b"% " + b"obj " * decoys + b"\n" if decoys else b""
    body = (b"%PDF-1.4\n" + remark
            + b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            + b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            + b"3 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n"
            + b"trailer\n<< /Root 1 0 R /Size 4 >>\nstartxref\n0\n%%EOF\n")
    return body


def test_a_budget_running_out_is_not_a_fact_about_the_file(monkeypatch):
    """`P1` is an error about the container whose remedy for the main document
    says there is no second option. Saying it because a *search* gave up is the
    category error this file's first test removed one rule over: a fact about a
    scan that did not happen. The file below carries five indirect objects."""
    monkeypatch.setattr(pdfread, "MAX_OBJ_PROBES", 8)
    facts = pdfread.read(_real_pdf(decoys=64))
    assert facts.is_pdf, (
        "a conforming PDF was reported as carrying no indirect object because "
        "the search for one stopped early")


def test_obj_inside_a_longer_word_is_not_an_indirect_object():
    """`bytes.find` matches anywhere. Without a delimiter on the right, the
    eighteen-byte text file this rule exists to catch needs only different
    bytes: `1 0 objx` passed."""
    assert not pdfread.read(b"%PDF-1.7\n1 0 objx").is_pdf
    assert not pdfread.read(b"%PDF-1.7\n1 0 objects\n").is_pdf
    # And the token is the whole word: matching a prefix of it accepts a file
    # that has no `obj` in it at all.
    assert not pdfread.read(b"%PDF-1.7\n1 0 ob\n").is_pdf
    assert not pdfread.read(b"%PDF-1.7\n1 0 ob").is_pdf
    assert pdfread.read(b"%PDF-1.7\n1 0 obj\n<< >>\nendobj\n").is_pdf
    assert pdfread.read(b"%PDF-1.7\n1 0 obj<</Type/Page>>").is_pdf


def test_spending_the_budget_withholds_the_claim_and_nothing_else(monkeypatch):
    """The ceiling bounds inflation. It was bounding the whole read of a file.

    `is_pdf`, the header and the encryption flag are read from bytes no stream
    has to be inflated for, and the reader was answering `None` before it looked
    at any of them — so a delivery of ordinary documents, each inflated to the
    per-file cap because it carries no PDF/A claim to stop at, spent the read's
    budget and then `P1` stopped firing on `VDI2770_Main.pdf`.
    """
    from conftest import CLEAN_DOCUMENTATION

    monkeypatch.setattr(pdfread, "MAX_INFLATED_PER_READ", 4_000_000)
    monkeypatch.setattr(pdfread, "MAX_INFLATED_TOTAL", 4_000_000)
    monkeypatch.setattr(pdfread, "MAX_INFLATED_PER_STREAM", 400_000)

    base = zipfile.ZipFile(CLEAN_DOCUMENTATION)
    meta = base.read("VDI2770_Main.xml").decode("utf-8")
    declared = "\n      ".join(
        f'<DigitalFile FileFormat="application/pdf">g{i}.pdf</DigitalFile>'
        for i in range(4))
    meta = meta.replace("<DigitalFile", declared + "\n      <DigitalFile", 1)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in base.namelist():
            z.writestr(name, meta if name == "VDI2770_Main.xml"
                       else b"%PDF-1.4" if name == "VDI2770_Main.pdf"
                       else base.read(name))
        for i in range(4):
            z.writestr(f"g{i}.pdf", _GREEDY)
    report = check_bytes(buf.getvalue(), "spent.zip")

    ids = {(f.rule.id, f.where.member) for f in report.findings}
    assert ("P1", "VDI2770_Main.pdf") in ids, (
        f"the reserved main document is eight bytes and nothing said so: {ids}")
    assert ("P3", "VDI2770_Main.pdf") not in ids
    assert any(r == "Z5" for r, _ in ids), ids


def test_the_allowance_is_one_per_read_and_not_one_per_container(counted,
                                                                 monkeypatch):
    """"This read" is the walk, not the archive at the top of it.

    Both tests above use a single container, so building a fresh reader inside
    the per-container loop passed all of them — and a tree of containers each
    paying its own ceiling is the same unbounded product one level up, which is
    the sentence the runner's own comment makes.
    """
    ceiling = 10_000_000
    monkeypatch.setattr(pdfread, "MAX_INFLATED_PER_READ", ceiling)
    each = pdfread.MAX_INFLATED_TOTAL

    inner = _container(8)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Main.xml",
                   zipfile.ZipFile(CLEAN_DOCUMENTATION).read("VDI2770_Main.xml"))
        z.writestr("VDI2770_Main.pdf",
                   zipfile.ZipFile(CLEAN_DOCUMENTATION).read("VDI2770_Main.pdf"))
        for i in range(3):
            z.writestr(f"child{i}.zip", inner)

    counted[0] = 0
    check_bytes(buf.getvalue(), "tree.zip")
    assert counted[0] <= ceiling + each, (
        f"three containers inflated {counted[0]} bytes against one ceiling of "
        f"{ceiling}; the allowance is being handed out per container")


def test_one_files_allowance_is_the_smaller_of_the_two(counted, monkeypatch):
    """`MAX_INFLATED_TOTAL` bounds a file and the read's allowance bounds what
    is left. Taking only the first lets the file that spends the last of the
    budget overshoot by a whole file's worth, however little was left."""
    monkeypatch.setattr(pdfread, "MAX_INFLATED_PER_READ", 1)
    counted[0] = 0
    pdfread.reader(1)(_GREEDY)
    assert counted[0] <= pdfread.MAX_INFLATED_PER_STREAM, (
        f"one byte of allowance bought {counted[0]} bytes of inflation")
