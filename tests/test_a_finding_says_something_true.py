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
import zipfile

from conftest import CLEAN_DOCUMENT, CORPUS
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
