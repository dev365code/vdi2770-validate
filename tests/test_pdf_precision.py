"""The two PDF rules decide an error from a string search, which is the thing
this project refuses to do about PDF/A. If a guess is going to carry error
severity, the guess has to be a good deal better than a substring.
"""

import io
import zipfile

import pytest

from conftest import A_PDF, CLEAN_DOCUMENT, CORPUS
from vdi2770 import pdfread

VALID = (CORPUS / "Valid.pdf").read_bytes()
ENCRYPTED = (CORPUS / "pdf" / "encrypted.pdf").read_bytes()
PASSWORD = (CORPUS / "pdf" / "password.pdf").read_bytes()
CLAIMS = {                      # measured against the corpus, not assumed
    "Valid.pdf": "3a", "PDFA1b_File.pdf": "1b", "PDFA2b_File.pdf": "2b",
    "PDFA3b_File.pdf": "3b", "Invalid1.pdf": "1a",
}
NO_CLAIM = ["Invalid2.pdf", "pdf/scan.pdf", "pdf/encrypted.pdf", "pdf/password.pdf"]


# --- P2: encryption ----------------------------------------------------------

@pytest.mark.parametrize("data,name", [(ENCRYPTED, "encrypted.pdf"), (PASSWORD, "password.pdf")])
def test_a_really_encrypted_pdf_is_still_detected(data, name):
    assert pdfread.read(data).encrypted is True


def test_a_pdf_that_merely_mentions_encrypt_is_not_called_encrypted():
    """`/Encrypt` in a comment, a content stream or a form-field name is not
    encryption. The trailer references the encryption dictionary indirectly —
    that is what the format actually requires, and what we should look for."""
    for decoy in (b"\n% a comment mentioning /Encrypt\n",
                  b"\n(/Encrypt is a PDF key) Tj\n",
                  b"\n/Fields [(/Encrypt)]\n"):
        assert pdfread.read(VALID + decoy).encrypted is False, decoy


def test_the_encryption_test_is_not_defeated_by_whitespace():
    assert pdfread.read(VALID + b"\ntrailer\n<< /Encrypt   12   0   R >>\n").encrypted is True


# --- P3: the PDF/A claim -----------------------------------------------------

@pytest.mark.parametrize("name,level", sorted(CLAIMS.items()))
def test_a_real_claim_is_still_read(name, level):
    assert pdfread.read((CORPUS / name).read_bytes()).pdfa_claim == level


@pytest.mark.parametrize("name", NO_CLAIM)
def test_a_file_with_no_claim_still_has_none(name):
    assert pdfread.read((CORPUS / name).read_bytes()).pdfa_claim is None


def test_a_claim_outside_an_xmp_packet_is_not_a_claim():
    """`P3` is an error, so silencing it must take more than writing the words
    in a comment. A PDF/A identification lives in the XMP metadata."""
    stub = (A_PDF
            + b"% <pdfaid:part>3</pdfaid:part><pdfaid:conformance>a</pdfaid:conformance>\n")
    assert pdfread.read(stub).pdfa_claim is None


def test_a_claim_in_a_real_xmp_packet_is_read():
    packet = (A_PDF + b"<?xpacket begin='' id='W5M0MpCehiHzreSzNTczkc9d'?>"
              b"<x:xmpmeta xmlns:x='adobe:ns:meta/'><rdf:RDF "
              b"xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>"
              b"<rdf:Description xmlns:pdfaid='http://www.aiim.org/pdfa/ns/id/'>"
              b"<pdfaid:part>2</pdfaid:part><pdfaid:conformance>b</pdfaid:conformance>"
              b"</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end='w'?>\n")
    assert pdfread.read(packet).pdfa_claim == "2b"


def test_the_level_the_report_prints_is_the_level_the_file_claims():
    """The one number this product exists to report, and nothing joined the two
    halves: `pdfread` was pinned at the reader, the wording was pinned at the
    rule, and the value in between could be a constant.

    Measured: hard-coding `claims PDF/A-1a` left the whole suite green while the
    corpus container's B.pdf claims 3a.
    """
    import zipfile

    from conftest import CORPUS
    from vdi2770 import read_pdf
    from vdi2770_validate.runner import check_file

    for container in sorted(CORPUS.rglob("*.zip")):
        claims = {}
        with zipfile.ZipFile(container) as z:
            for name in z.namelist():
                if name.lower().endswith(".pdf"):
                    claim = read_pdf(z.read(name)).pdfa_claim
                    if claim:
                        claims[name] = claim
        if not claims:
            continue
        for f in check_file(str(container)).findings:
            if f.rule.id != "P4" or f.where.member not in claims:
                continue
            want = claims[f.where.member]
            assert f"PDF/A-{want}" in (f.detail or ""), (
                f"{container.name}!/{f.where.member} claims {want} and the report "
                f"says {f.detail!r}")
        assert claims, container.name


def test_the_real_encrypted_pdf_in_the_corpus_is_still_found():
    """The trailer scan was rewritten as one structure-aware pass. Seventeen
    synthetic shapes say it reads PDF correctly; this says it still reads the one
    genuinely encrypted file this repository has.

    It lives here and not beside the reader because `test_layering.py` forbids the
    reader's own suite from reaching the corpus — an sdist of that package
    contains the package and nothing else.
    """
    from conftest import CORPUS
    from vdi2770 import read_pdf

    body = CORPUS / "pdf" / "encrypted.pdf"
    assert body.exists(), body
    facts = read_pdf(body.read_bytes())
    assert facts.is_pdf and facts.encrypted, facts


def _packet(part: str, conformance: str = "") -> bytes:
    """One XMP packet claiming a PDF/A part, and a conformance level or none."""
    conf = (f"<pdfaid:conformance>{conformance}</pdfaid:conformance>"
            if conformance else "")
    return (A_PDF + b"<?xpacket begin='' id='W5M0MpCehiHzreSzNTczkc9d'?>"
            b"<x:xmpmeta xmlns:x='adobe:ns:meta/'><rdf:RDF "
            b"xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>"
            b"<rdf:Description xmlns:pdfaid='http://www.aiim.org/pdfa/ns/id/'>"
            + f"<pdfaid:part>{part}</pdfaid:part>{conf}".encode()
            + b"</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end='w'?>\n")


def test_a_conformance_level_this_reader_did_not_know_was_read_past():
    """`E` and `F` are PDF/A-4's two levels and the pattern accepted neither, so
    a file claiming `4F` was recorded as claiming `4?` — a level it does not
    claim, built out of a conformance the reader had just read and discarded."""
    assert pdfread.read(_packet("4", "E")).pdfa_claim == "4e"
    assert pdfread.read(_packet("4", "F")).pdfa_claim == "4f"
    assert pdfread.read(_packet("2", "b")).pdfa_claim == "2b"


def test_no_conformance_level_is_what_part_4_is_supposed_to_look_like():
    """ISO 19005-4 drops the conformance level: a PDF/A-4 file that carries none
    is claiming exactly what it should, and `4?` said otherwise about every one
    of them."""
    assert pdfread.read(_packet("4")).pdfa_claim == "4"


def test_a_part_that_requires_a_level_and_carries_none_is_still_not_a_level():
    """Parts 1 to 3 do require one, so its absence is worth keeping — but `?` is
    the reader's punctuation, not the file's, and a report that prints
    `claims PDF/A-1?` is quoting the file for something the file does not say."""
    assert pdfread.read(_packet("1")).pdfa_claim == "1?"

    from vdi2770_validate.runner import check_bytes
    box = io.BytesIO()
    with zipfile.ZipFile(box, "w") as z:
        base = zipfile.ZipFile(CLEAN_DOCUMENT)
        for name in base.namelist():
            z.writestr(name, _packet("1") if name == "B.pdf" else base.read(name))
    said = [f for f in check_bytes(box.getvalue(), "half.zip").findings
            if f.rule.id == "P4" and f.where.member == "B.pdf"]
    assert said, "the premise"
    assert "PDF/A-1?" not in (said[0].detail or ""), said[0].detail
    assert "conformance" in (said[0].detail or ""), said[0].detail
    assert "well-formed" not in (said[0].remedy or ""), said[0].remedy
