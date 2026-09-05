"""Three findings that were each true in outline and false in the sentence a
user actually reads.

  * `P3` on an encrypted PDF: *"no pdfaid identification found in the XMP
    metadata"*, and a remedy telling the producer to fix their exporter — for a
    file whose XMP this tool never decrypted. The title hedges ("this scan found
    no…"); the detail and the remedy drop the hedge.
  * `Z9` prints the number of folders it *collected*, which stops at
    `MAX_FOLDERS`. An archive with three hundred was reported as having 256.
    `report.py` argues the same point about the listing cap: "printing the capped
    number over an uncapped summary contradicts it."
  * `./VDI2770_Metadata.xml` **is** at the root, and `Z3` said "it must sit at
    the root of the archive"; `Z9` counted `./` as a folder.
"""
import io
import pathlib
import re
import zipfile

from conftest import CLEAN_DOCUMENT, CORPUS, counts_line
from vdi2770_validate.rules.container import MAX_FOLDERS
from vdi2770_validate.runner import check_bytes

SRC = zipfile.ZipFile(CLEAN_DOCUMENT)


def built(rename=lambda n: n, extra=(), swap=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in SRC.namelist():
            body = swap(name) if swap else None
            z.writestr(rename(name), body if body is not None else SRC.read(name))
        for name, data in extra:
            z.writestr(name, data)
    return buf.getvalue()


def findings(data, rule_id):
    return [f for f in check_bytes(data, "x.zip").findings if f.rule.id == rule_id]


def test_an_encrypted_pdf_is_not_told_to_fix_its_exporter():
    encrypted = CORPUS / "pdf" / "encrypted.pdf"
    assert encrypted.exists(), "the corpus no longer carries an encrypted PDF"
    data = built(swap=lambda n: encrypted.read_bytes() if n == "B.pdf" else None)

    assert findings(data, "P2"), "the premise: this PDF is detected as encrypted"
    p3 = findings(data, "P3")
    assert not p3, (
        "the XMP is encrypted and was never read; saying no claim was found there "
        f"is a statement about something we did not look at: {[f.detail for f in p3]}")


def test_z9_does_not_print_a_capped_count_as_a_fact():
    """Exact under the cap, and hedged only when the collection actually stopped.

    Asserting `"at least" in detail` was not enough: `capped` is derived from the
    count rather than from whether collection stopped, so with the cap removed an
    archive of 300 folders still says "at least" — now an untrue hedge over an
    exact number, which is the mirror of the defect this exists for. Deleting all
    three `MAX_FOLDERS` breaks left the whole suite green.
    """
    under = MAX_FOLDERS - 40
    data = built(extra=[(f"d{i:03d}/x.txt", b"x") for i in range(under)])
    z9 = findings(data, "Z9")
    assert z9, "the premise: this archive stores files in folders"
    assert z9[0].detail.startswith(f"{under} folder"), (
        f"an archive with {under} folders, under the cap, is counted exactly: "
        f"{z9[0].detail}")

    over = MAX_FOLDERS + 44
    data = built(extra=[(f"d{i:03d}/x.txt", b"x") for i in range(over)])
    detail = findings(data, "Z9")[0].detail
    assert detail.startswith(f"at least {MAX_FOLDERS} folder"), (
        f"the collection stops at {MAX_FOLDERS}, so the count is a floor and the "
        f"detail has to say so — and has to say {MAX_FOLDERS}, not {over}: {detail}")


def test_a_dot_prefix_is_not_a_folder_and_not_a_subfolder():
    data = built(rename=lambda n: "./" + n)
    z9 = findings(data, "Z9")
    assert not z9, f"'./' is a path prefix, not a folder: {[f.detail for f in z9]}"

    z3 = findings(data, "Z3")
    if z3 and z3[0].detail:
        assert "must sit at the root" not in z3[0].detail, (
            f"the file is at the root; the sentence tells the sender to move it "
            f"there: {z3[0].detail}")


def test_a_refused_member_is_not_counted_as_a_delivered_folder():
    """`Z13` counted a folder the reader had refused to open at all.

    An archive whose only extra member is `../VDI2770_Metadata.xml` drew `Z4` —
    *a member name would escape the extraction directory* — and, on the line
    above it, `Z13` saying one folder holds metadata, with a remedy opening
    "Nothing here is necessarily wrong with the container". There is no such
    folder: `Z9`, whose job is counting folders, reports none.

    The two decisions behind it are each defensible. `folders_holding_metadata`
    reads `present`, which by design lists members the reader rejected, so a
    caller can see what was in the archive. `folder_path` keeps `..`, because
    dropping it would quietly make an escaping name look ordinary. Composed,
    they turn a refusal into a delivery — and silence `Z8`, which would
    otherwise say this documentation container holds no documents at all.
    """
    from conftest import CLEAN_DOCUMENTATION

    src = zipfile.ZipFile(CLEAN_DOCUMENTATION)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Main.xml", src.read("VDI2770_Main.xml"))
        z.writestr("VDI2770_Main.pdf", src.read("VDI2770_Main.pdf"))
        z.writestr("../VDI2770_Metadata.xml", b"<x/>")

    report = check_bytes(buf.getvalue(), "escape.zip")
    fired = {f.rule.id for f in report.findings}
    assert "Z4" in fired, f"the premise: the member escapes: {sorted(fired)}"
    assert "Z13" not in fired, (
        "a member the reader refused was counted as a document delivered in a "
        "folder, next to the finding calling it a path-traversal attempt")
    assert "Z8" in fired, (
        f"this documentation container holds no documents and nothing said so: "
        f"{sorted(fired)}")


def test_the_published_german_name_is_accepted_however_it_is_spelled():
    """`M3` fired on the name it was asking for.

    `Zeichnungen, Plane` for class `02-02` is the published German name, and
    `a` is one character composed or two characters decomposed. Both spell the
    same word; Unicode calls them canonically equivalent and an editor picks
    whichever its platform prefers without telling anyone. Comparing the code
    points reported the published name as not belonging to its own class, and
    printed the two strings side by side, where they rendered identically:

        'Zeichnungen, Plane' for class 02-02; published name is 'Zeichnungen, Plane'

    which asks a user to fix a difference they cannot see. Names are reconciled
    in one place in this package for exactly this reason; the metadata layer was
    comparing text the reader had not put through it.
    """
    import unicodedata

    from conftest import CLEAN_DOCUMENT

    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    xml = src.read("VDI2770_Metadata.xml").decode("utf-8")
    for was, now in (("<ClassId>02-01</ClassId>", "<ClassId>02-02</ClassId>"),
                     ("Technische Spezifikation", "Zeichnungen, Pläne"),
                     ("Technical specification", "Drawings, plans")):
        assert xml.count(was) == 1, f"fixture no longer says {was!r}"
        xml = xml.replace(was, now)
    nfd = unicodedata.normalize("NFD", xml)
    assert nfd != xml, "the name did not decompose"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for m in src.namelist():
            z.writestr(m, nfd.encode("utf-8") if m == "VDI2770_Metadata.xml"
                       else src.read(m))
    report = check_bytes(buf.getvalue(), "nfd.zip")
    fired = [f for f in report.findings if f.rule.id == "M3"]
    assert not fired, (
        "the published German name, spelled the other legal way, was reported as "
        f"not belonging to its class: {[f.detail for f in fired]}")


def test_a_folder_we_did_not_open_is_said_so_in_any_container():
    """The report went quiet instead of saying it had not looked.

    `F2` does not report the files inside a folder that holds its own
    `VDI2770_Metadata.xml`: they are declared in metadata this tool never opened,
    so calling them undeclared would be a claim about a file we did not read. The
    sentence that makes that silence honest -- `Z13`, *this tool does not open
    folders* -- was emitted only for documentation containers. Put the same
    folder in a document container and the files vanished from the report with
    nothing said, which is the one outcome the suppression was written to avoid.
    """
    from conftest import CLEAN_DOCUMENT

    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for m in src.namelist():
            z.writestr(m, src.read(m))
        z.writestr("sub/VDI2770_Metadata.xml", b"<x/>")
        z.writestr("sub/nobody_declared_this.pdf", b"%PDF-1.4\n")
    report = check_bytes(buf.getvalue(), "folder-in-a-document.zip")
    fired = {f.rule.id for f in report.findings}
    assert not any(f.rule.id == "F2" and "nobody_declared_this" in (f.detail or "")
                   for f in report.findings), \
        "a file inside a folder we did not open was called undeclared"
    assert "Z13" in fired, (
        "nothing in the report said the folder had not been opened: "
        f"{sorted(fired)}")


def test_a_folder_whose_metadata_we_could_not_read_is_still_a_folder():
    """The guard for one refusal swallowed a different one.

    `folders_holding_metadata` skips members the reader refused, because
    `../VDI2770_Metadata.xml` is a path-traversal attempt and not a folder
    anybody delivered. But *unreadable* is not *not a name*: a folder whose own
    `VDI2770_Metadata.xml` has a bad CRC is a document container that was not
    zipped, delivered, and unopened — which is the strongest case there is for
    saying so.

    With the guard as written, one damaged member turned the report into two
    false claims and a missing one: `F2` said nothing declares the files in that
    folder — asserted from a metadata file the line above says could not be read
    — and `Z8` told the sender to add the document containers it was looking at,
    while nothing said a folder had gone unexamined.
    """
    import struct

    from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION

    docn = zipfile.ZipFile(CLEAN_DOCUMENTATION)
    doc = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Main.xml", docn.read("VDI2770_Main.xml"))
        z.writestr("VDI2770_Main.pdf", docn.read("VDI2770_Main.pdf"))
        for name in doc.namelist():
            z.writestr("doc1/" + name, doc.read(name))
    raw = bytearray(buf.getvalue())

    # That member's bytes, found through its own header rather than by searching
    # for them: the document's metadata and the documentation's main file open
    # with the same forty bytes, and searching corrupted the wrong one.
    info = zipfile.ZipFile(io.BytesIO(bytes(raw))).getinfo("doc1/VDI2770_Metadata.xml")
    name_len, extra_len = struct.unpack("<HH", bytes(raw[info.header_offset + 26:
                                                        info.header_offset + 30]))
    at = info.header_offset + 30 + name_len + extra_len
    raw[at:at + 40] = b"@" * 40

    report = check_bytes(bytes(raw), "folder.zip")
    fired = {f.rule.id for f in report.findings}
    assert "Z12" in fired, f"the refusal itself is not reported: {sorted(fired)}"
    assert "Z13" in fired, (
        f"nothing said the folder had not been opened: {sorted(fired)}")
    assert "F2" not in fired, (
        "files inside a folder we did not open were called undeclared")
    assert "Z8" not in fired, (
        "the container was said to deliver nothing while a folder sat in it")


def test_an_archive_with_an_unnameable_entry_is_not_called_empty():
    """`Z2` said *the archive is empty* beside `Z12` saying there was an entry.

    The guard reads `members` and `rejected`, and `nameless-member` is the one
    refusal recorded as a bare defect and never in `rejected` — so it walked
    past, and the remedy told a sender to add the files they had sent.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(zipfile.ZipInfo(""), b"something is in here")
    report = check_bytes(buf.getvalue(), "nameless.zip")
    fired = {f.rule.id for f in report.findings}
    assert "Z12" in fired, sorted(fired)
    assert "Z2" not in fired, "an archive with an entry in it was called empty"

    said = next(f.detail for f in report.findings if f.rule.id == "Z12")
    assert "has no name" in said and "extract it" in said, (
        f"one entry, told about in the plural: {said}")


def test_a_locked_member_is_not_told_to_send_the_same_archive_again():
    """Repaired on `F1`'s path and not on `Z12`'s, so one member drew two
    remedies and one of them was a loop: re-creating the archive from the same
    directory produces the same member and the same finding."""
    import shutil
    import subprocess

    import pytest

    if not shutil.which("zip"):
        pytest.skip("needs the zip(1) command to build an encrypted member")

    from conftest import CLEAN_DOCUMENT

    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        src.extractall(tmp)
        out = f"{tmp}/enc.zip"
        rest = [f"{tmp}/{n}" for n in src.namelist() if n != "B.pdf"]
        subprocess.run(["zip", "-jq", out, *rest], check=True)
        subprocess.run(["zip", "-jq", "-P", "secret", out, f"{tmp}/B.pdf"], check=True)
        report = check_bytes(pathlib.Path(out).read_bytes(), "enc.zip")

    z12 = [f for f in report.findings if f.rule.id == "Z12"]
    assert z12, [f.rule.id for f in report.findings]
    for f in z12:
        assert "send it again" not in (f.remedy or ""), (
            f"a locked member was told to re-send the same archive: {f.remedy}")
        assert "password" in (f.remedy or "").lower(), f.remedy


def test_the_summary_says_how_many_errors_are_this_tool_declining():
    """`1 error(s)` and exit 1, over a remedy opening *Nothing here is
    necessarily wrong with the container*.

    Seven rules are `about: tool` and all seven are errors, on the documented
    ground that exit 0 must never mean "checked". Every one of their titles says
    the tool declined — *the schema check could not run*, *this tool did not
    build a model*, *which this tool does not open*. What said nothing was the
    count. A supplier reads the last line of the report, sees one error against
    their delivery, and the axis lives only in the JSON.
    """
    from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION
    from vdi2770_validate.report import as_text

    docn = zipfile.ZipFile(CLEAN_DOCUMENTATION)
    doc = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Main.xml", docn.read("VDI2770_Main.xml"))
        z.writestr("VDI2770_Main.pdf", docn.read("VDI2770_Main.pdf"))
        for name in doc.namelist():
            z.writestr("doc1/" + name, doc.read(name))
    report = check_bytes(buf.getvalue(), "folders.zip")
    assert "Z13" in {f.rule.id for f in report.findings}, "premise"
    summary = counts_line(as_text(report, True))
    assert "declin" in summary, f"the summary hides the axis: {summary!r}"

    # And a container whose errors really are its own says nothing of the kind.
    ordinary = check_bytes(zipfile.ZipFile(CLEAN_DOCUMENT).read("VDI2770_Metadata.xml"),
                           "notazip.zip")
    line = counts_line(as_text(ordinary, True))
    assert "declin" not in line, f"a container-axis error was excused: {line!r}"


def test_a_documentation_folder_is_a_folder_this_tool_did_not_open_too():
    """Exit 0 on a delivery whose nested documentation container is junk.

    `folders_holding_metadata` matched `VDI2770_Metadata.xml` and nothing else,
    so a *documentation* container delivered as an unzipped folder was not a
    folder as far as this tool was concerned. A handover holding `plantA/` whose
    `VDI2770_Main.xml` is not XML and whose `VDI2770_Main.pdf` is not a PDF came
    back with two warnings and a clean verdict — and `Z8` on top of it, saying
    the container holds no document containers while looking at one.

    Nothing in that report said a folder had gone unexamined, and the `.zip`
    inside such a folder *is* opened and reported on, so a reader takes the rest
    as checked too.
    """
    from conftest import CLEAN_DOCUMENTATION

    docn = zipfile.ZipFile(CLEAN_DOCUMENTATION)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Main.xml", docn.read("VDI2770_Main.xml"))
        z.writestr("VDI2770_Main.pdf", docn.read("VDI2770_Main.pdf"))
        z.writestr("plantA/VDI2770_Main.xml", b"<<< not even XML >>>")
        z.writestr("plantA/VDI2770_Main.pdf", b"this is not a pdf")

    report = check_bytes(buf.getvalue(), "handover.zip")
    fired = {f.rule.id for f in report.findings}
    assert "Z13" in fired, (
        f"nothing said the folder had not been opened: {sorted(fired)}")
    assert not report.clean, "a delivery nobody looked inside came back clean"
    assert "F2" not in fired, (
        "files inside a folder we did not open were called undeclared")
    assert "Z8" not in fired, (
        "the container was said to hold no document containers while holding one")


def test_a_declared_name_that_escapes_is_not_said_to_be_unreadable():
    """`F1` said the bytes could not be read and that the metadata was right.

    Both false, and the second contradicts `Z4` two lines away: the metadata is
    what names `../evil.pdf`. The bytes are fine — the *name* is what this tool
    refused, which the detail on the next line says in as many words. And the
    remedy, *re-create the archive and send it again*, is the loop this project
    already removed for a locked member and for a repeated name: re-zipping the
    same tree produces the same name and the same finding.
    """
    import re

    from conftest import CLEAN_DOCUMENT

    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    meta = src.read("VDI2770_Metadata.xml").decode("utf-8")
    assert meta.count(">B.pdf<") == 1, "the fixture no longer declares B.pdf once"

    for escaping in ("../evil.pdf", "/etc/passwd.pdf"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name in src.namelist():
                if name == "B.pdf":
                    z.writestr(escaping, src.read(name))
                elif name == "VDI2770_Metadata.xml":
                    z.writestr(name, meta.replace(">B.pdf<", f">{escaping}<").encode("utf-8"))
                else:
                    z.writestr(name, src.read(name))
        report = check_bytes(buf.getvalue(), "escape.zip")
        f1 = [f for f in report.findings if f.rule.id == "F1"]
        assert f1, [f.rule.id for f in report.findings]
        said = f"{f1[0].message} {f1[0].remedy}"
        assert "could not be read" not in said, said
        assert "the metadata is right" not in said, said
        assert "send it again" not in said, said
        assert re.search(r"escape|name", f1[0].message), f1[0].message


def test_a_member_no_declaration_can_name_is_told_so():
    """One file, present and declared, reported as missing *and* undeclared.

    The metadata's text is read with the whitespace around it removed — it has
    to be, because `<DigitalFile>\\n    B.pdf\\n  </DigitalFile>` is how a
    pretty-printer writes an ordinary declaration. The schema types the element
    `xs:string`, which preserves whitespace, so that stripping is this tool's
    choice and every other implementation's too. The consequence is that a
    member whose name carries a space at its edge **cannot be declared by
    anyone**: whatever the sender writes is read back without it.

    So the archive held `B.pdf␠`, the metadata declared `B.pdf␠`, and the report
    said `'B.pdf' is declared but not in the archive` over `B.pdf` is in the
    container but not named in the metadata — two findings that cannot both be
    true, and a remedy asking the sender to do the thing they had already done.
    """
    from conftest import CLEAN_DOCUMENT

    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    meta = src.read("VDI2770_Metadata.xml").decode("utf-8")
    assert meta.count(">B.pdf<") == 1, "the fixture no longer declares B.pdf once"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in src.namelist():
            if name == "B.pdf":
                z.writestr("B.pdf ", src.read(name))
            elif name == "VDI2770_Metadata.xml":
                z.writestr(name, meta.replace(">B.pdf<", ">B.pdf <").encode("utf-8"))
            else:
                z.writestr(name, src.read(name))

    report = check_bytes(buf.getvalue(), "space.zip")
    said = {f.rule.id: f for f in report.findings if f.rule.id in ("F1", "F2")}
    assert said, [f.rule.id for f in report.findings]

    # Whatever is reported, the page has to name the member as the archive
    # spells it and say why no declaration reaches it.
    page = " ".join(f"{f.message} {f.detail or ''} {f.remedy or ''}" for f in said.values())
    assert "\\u0020" in page, f"the trailing space is nowhere on the page: {page}"
    assert "declare" in page.lower(), page
    assert "rename" in page.lower(), (
        f"nothing tells the sender the one thing that can fix it: {page}")


def test_one_name_stored_four_times_is_counted_the_same_way_twice():
    """`F1` said *names 1 members* under a headline saying *more than once*,
    beside a `Z10` whose detail says four entries.

    The count walked `container.present`, whose own construction collapses a
    repeated name to one entry — `rejected` is a dict keyed by name — so on this
    branch it could never be anything but 1, and the comment defending it was
    false. The reader's refusal already carries the true count; the finding now
    carries the reader's sentence instead of a number it cannot know.
    """
    meta = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Document xmlns="http://www.vdi.de/schemas/vdi2770"><DocumentVersion>'
            '<DigitalFile FileFormat="application/pdf">B.pdf</DigitalFile>'
            '</DocumentVersion></Document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Metadata.xml", meta)
        for _ in range(4):
            z.writestr("B.pdf", b"%PDF-1.4 x")
    report = check_bytes(buf.getvalue(), "four.zip")
    f1 = [f for f in report.findings if f.rule.id == "F1"]
    assert f1, [f.rule.id for f in report.findings]
    said = f"{f1[0].detail} {f1[0].remedy}"
    assert "1 members" not in said and "two members" not in said, said
    assert "4 entries" in said, f"the true count is nowhere in the finding: {said}"

    z10 = [f for f in report.findings if f.rule.id == "Z10"]
    assert z10 and "Two entries share" not in (z10[0].remedy or ""), (
        z10[0].remedy)


def test_z13_names_the_reserved_file_each_folder_actually_holds():
    """The detail always said `VDI2770_Metadata.xml`, whichever file the folder
    holds — widened matching, unwidened sentence. A reader grepped their ZIP
    listing for a name that is not in it."""
    from conftest import CLEAN_DOCUMENTATION

    docn = zipfile.ZipFile(CLEAN_DOCUMENTATION)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Main.xml", docn.read("VDI2770_Main.xml"))
        z.writestr("VDI2770_Main.pdf", docn.read("VDI2770_Main.pdf"))
        z.writestr("plantA/VDI2770_Main.xml", b"<x/>")
    report = check_bytes(buf.getvalue(), "docnfolder.zip")
    z13 = [f for f in report.findings if f.rule.id == "Z13"]
    assert z13, [f.rule.id for f in report.findings]
    assert "VDI2770_Main.xml" in (z13[0].detail or ""), z13[0].detail
    assert "VDI2770_Metadata.xml" not in (z13[0].detail or ""), z13[0].detail


def test_z3_offers_only_the_near_misses_that_decide_the_kind():
    """`Z3` rendered the `VDI2770_Main.pdf` near-miss, and acting on it
    reproduces the finding: only the two XML names classify an archive, so
    fixing the PDF's case changes nothing. The one line that looked actionable
    was the one that could not help."""
    from conftest import CLEAN_DOCUMENTATION

    docn = zipfile.ZipFile(CLEAN_DOCUMENTATION)
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("vdi2770_main.pdf", b"%PDF-1.4\n")
        z.writestr("a.txt", b"x")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Main.xml", docn.read("VDI2770_Main.xml"))
        z.writestr("VDI2770_Main.pdf", docn.read("VDI2770_Main.pdf"))
        z.writestr("inner.zip", inner.getvalue())
    report = check_bytes(buf.getvalue(), "case.zip")
    z3 = [f for f in report.findings if f.rule.id == "Z3"]
    assert z3, [f.rule.id for f in report.findings]
    assert "vdi2770_main.pdf" not in (z3[0].detail or ""), z3[0].detail


def _one_file_container(member, declared):
    meta = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Document xmlns="http://www.vdi.de/schemas/vdi2770"><DocumentVersion>'
            f'<DigitalFile FileFormat="application/pdf">{declared}</DigitalFile>'
            '</DocumentVersion></Document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Metadata.xml", meta)
        z.writestr(member, b"%PDF-1.4\n")
    return buf.getvalue()


def test_unreachable_means_what_the_reader_actually_strips():
    """The helper stripped every segment; the reader strips the whole string.

    A declaration is read as `f.text.strip()` — whitespace removed from the two
    ends of the whole name, nowhere else. So `sub /B.pdf` **can** be declared,
    verbatim, and it resolves; the helper stripped each segment and said no
    declaration can reach it, with `F2` withdrawing the one remedy that works.
    And ` sub /B.pdf ` — genuinely unreachable — stripped to `sub/B.pdf`, which
    matches no declaration, so the very contradiction the helper exists to
    remove was still on the page for it.
    """
    from vdi2770_validate.names import without_edge_space

    # The predicate is the reader's own operation.
    assert without_edge_space("sub /B.pdf") == "sub /B.pdf"
    assert without_edge_space(" sub /B.pdf ") == "sub /B.pdf"

    # A member with an interior segment edge, declared verbatim: reachable.
    report = check_bytes(_one_file_container("sub /B.pdf", "sub /B.pdf"), "a.zip")
    assert not [f for f in report.findings if f.rule.id in ("F1", "F2")], (
        [f"{f.rule.id}: {f.message}" for f in report.findings])

    # The same member, declared with the space collapsed: missing, plainly.
    report = check_bytes(_one_file_container("sub /B.pdf", "sub/B.pdf"), "b.zip")
    f1 = [f for f in report.findings if f.rule.id == "F1"]
    assert f1 and "no declaration can" not in f"{f1[0].message} {f1[0].detail}", (
        f1[0].detail)

    # Whole-name edge whitespace: unreachable, and the report says so.
    report = check_bytes(_one_file_container(" sub /B.pdf ", "sub /B.pdf"), "c.zip")
    f1 = [f for f in report.findings if f.rule.id == "F1"]
    assert f1, [f.rule.id for f in report.findings]
    said = f"{f1[0].message} {f1[0].detail} {f1[0].remedy}"
    assert "no declaration can" in said, said
    f2 = [f for f in report.findings if f.rule.id == "F2"]
    assert f2 and "Rename" in (f2[0].remedy or ""), (
        f"F2's remedy still offers the declaration that cannot work: "
        f"{f2[0].remedy}")


def test_a_near_miss_is_skipped_only_for_the_reason_that_names_it():
    """`_classify` skipped every refused name; only an unsafe one is not a
    near-miss.

    `docs/VDI2770_Metadata.xml` stored twice is refused as `ambiguous-name` — a
    refusal about the archive holding it twice, not about the name — and the
    diagnosis *it must sit at the root* is as true and as useful as ever. The
    skip erased it, and for a wrong-case copy in a subfolder nothing on the page
    said the archive nearly has a metadata file at all.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("B.pdf", b"%PDF-1.4\n")
        z.writestr("docs/VDI2770_Metadata.xml", b"<x/>")
        z.writestr("docs/VDI2770_Metadata.xml", b"<y/>")
    report = check_bytes(buf.getvalue(), "twice.zip")
    z3 = [f for f in report.findings if f.rule.id == "Z3"]
    assert z3, [f.rule.id for f in report.findings]
    assert "docs/VDI2770_Metadata.xml" in (z3[0].detail or ""), (
        f"the near-miss the reader knew is not on the page: {z3[0].detail!r}")


def test_the_other_kinds_classifying_name_is_not_just_an_undeclared_file():
    """An archive answering to both container kinds was silently one of them.

    `VDI2770_Main.xml` and `VDI2770_Metadata.xml` side by side at the root:
    classification prefers the documentation reading, the document metadata
    drew a bare `F2` — *a file in the container is not named in the metadata* —
    and following that finding's remedy ("declare it") produced a fully clean
    report for an archive whose kind depends on which name a reader looks for
    first.

    `F2` still fires; what changes is that its sentence says what the file is.
    The other kind's classifying name at the root is not an undeclared file, and
    "declare it" is the one remedy that must not be offered for it.
    """
    from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION

    doc = zipfile.ZipFile(CLEAN_DOCUMENT)
    docn = zipfile.ZipFile(CLEAN_DOCUMENTATION)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Main.xml", docn.read("VDI2770_Main.xml"))
        z.writestr("VDI2770_Main.pdf", docn.read("VDI2770_Main.pdf"))
        z.writestr("VDI2770_Metadata.xml", doc.read("VDI2770_Metadata.xml"))
    report = check_bytes(buf.getvalue(), "both.zip")
    f2 = [f for f in report.findings if f.rule.id == "F2"
          and (f.where.member or "") == "VDI2770_Metadata.xml"]
    assert f2, [f.rule.id for f in report.findings]
    said = f"{f2[0].detail or ''} {f2[0].remedy or ''}"
    assert "document container" in said, (
        f"nothing says this is the other kind's classifying name: {said!r}")
    assert "Declare the file" not in (f2[0].remedy or ""), f2[0].remedy


def test_m4_does_not_offer_a_choice_where_the_sources_agree():
    """`M4` exists because two published sources give different English names
    for five of the twelve classes. For the other seven they agree, and the
    sentence written for the disagreement was said about those too:

        The English class name matches neither published rendering
        'identification' for class 01-01; published renderings are 'Identification'
        -> Either published spelling is defensible until the disagreement is resolved.

    Three claims, three of them false where there is one rendering: *neither* of
    one thing, a plural verb over a single item, and a disagreement to wait out
    that does not exist. It reproduces on a container this repository ships.
    """
    from conftest import CORPUS
    from vdi2770_validate.runner import check_bytes

    raw = (CORPUS / "demo_invalid_doc_type_names.zip").read_bytes()
    m4 = [f for f in check_bytes(raw, "demo.zip").findings if f.rule.id == "M4"]
    assert m4, "the premise: this container has to produce an M4"

    from vdi2770_validate.catalog import english_for

    for f in m4:
        cls = re.search(r"for class (\S+?);", f.detail).group(1)
        if len(english_for(cls)) > 1:
            continue                      # the disagreement M4 was written for
        said = f"{f.message} {f.detail} {f.remedy}"
        for wrong in ("neither", "renderings are", "the disagreement"):
            assert wrong not in said, (
                f"class {cls} has one published English name and the finding "
                f"says {wrong!r}: {said}")
