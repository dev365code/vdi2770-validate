"""The two PDF rules decide an error from a string search, which is the thing
this project refuses to do about PDF/A. If a guess is going to carry error
severity, the guess has to be a good deal better than a substring.
"""

import pytest

from conftest import CORPUS
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
    stub = (b"%PDF-1.7\n"
            b"% <pdfaid:part>3</pdfaid:part><pdfaid:conformance>a</pdfaid:conformance>\n")
    assert pdfread.read(stub).pdfa_claim is None


def test_a_claim_in_a_real_xmp_packet_is_read():
    packet = (b"%PDF-1.7\n<?xpacket begin='' id='W5M0MpCehiHzreSzNTczkc9d'?>"
              b"<x:xmpmeta xmlns:x='adobe:ns:meta/'><rdf:RDF "
              b"xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>"
              b"<rdf:Description xmlns:pdfaid='http://www.aiim.org/pdfa/ns/id/'>"
              b"<pdfaid:part>2</pdfaid:part><pdfaid:conformance>b</pdfaid:conformance>"
              b"</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end='w'?>\n")
    assert pdfread.read(packet).pdfa_claim == "2b"
