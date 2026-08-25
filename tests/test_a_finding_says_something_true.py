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
    data = built(extra=[(f"d{i:03d}/x.txt", b"x") for i in range(MAX_FOLDERS + 44)])
    z9 = findings(data, "Z9")
    assert z9, "the premise: this archive stores files in folders"
    detail = z9[0].detail
    assert "at least" in detail, (
        f"the count stops at {MAX_FOLDERS} and the detail states it flatly: {detail}")


def test_a_dot_prefix_is_not_a_folder_and_not_a_subfolder():
    data = built(rename=lambda n: "./" + n)
    z9 = findings(data, "Z9")
    assert not z9, f"'./' is a path prefix, not a folder: {[f.detail for f in z9]}"

    z3 = findings(data, "Z3")
    if z3 and z3[0].detail:
        assert "must sit at the root" not in z3[0].detail, (
            f"the file is at the root; the sentence tells the sender to move it "
            f"there: {z3[0].detail}")
