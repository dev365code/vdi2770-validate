"""A PDF/A identification is identified by its namespace URI, not by the letters
someone chose to bind it to.

The scan matched the literal token `pdfaid`. Under XML Namespaces a prefix is a
local choice — `pa:part` bound to `http://www.aiim.org/pdfa/ns/id/` says exactly
the same thing — so a file produced by a conforming exporter read as having no
claim at all, and the caller's rule told them to fix an exporter that was right.
"""
import vdi2770

PDFA_NS = "http://www.aiim.org/pdfa/ns/id/"


def xmp(prefix, part="3", conformance="B", ns=PDFA_NS, attribute_form=False):
    body = (f'<{prefix}:part>{part}</{prefix}:part>'
            f'<{prefix}:conformance>{conformance}</{prefix}:conformance>')
    if attribute_form:
        body = f'{prefix}:part="{part}" {prefix}:conformance="{conformance}"'
        desc = f'<rdf:Description rdf:about="" xmlns:{prefix}="{ns}" {body}/>'
    else:
        desc = f'<rdf:Description rdf:about="" xmlns:{prefix}="{ns}">{body}</rdf:Description>'
    return ('<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>'
            '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            f'{desc}</rdf:RDF></x:xmpmeta><?xpacket end="w"?>').encode()


def pdf(payload: bytes) -> bytes:
    return (b"%PDF-1.7\n1 0 obj\n<</Type/Metadata/Subtype/XML/Length "
            + str(len(payload)).encode() + b">>\nstream\n" + payload
            + b"\nendstream\nendobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")


def test_the_conventional_prefix_still_works():
    assert vdi2770.read_pdf(pdf(xmp("pdfaid"))).pdfa_claim == "3b"


def test_another_prefix_bound_to_the_same_namespace_says_the_same_thing():
    assert vdi2770.read_pdf(pdf(xmp("pa"))).pdfa_claim == "3b"


def test_the_attribute_form_reads_the_prefix_too():
    assert vdi2770.read_pdf(pdf(xmp("pa", attribute_form=True))).pdfa_claim == "3b"


def test_a_prefix_bound_to_something_else_is_not_a_pdfa_claim():
    """`pa:part` alone means nothing; it means something because of the URI it is
    bound to. Matching any prefix would turn an unrelated schema into a claim."""
    other = xmp("pa", ns="http://example.invalid/parts/")
    assert vdi2770.read_pdf(pdf(other)).pdfa_claim is None


def test_a_file_with_no_claim_still_has_none():
    assert vdi2770.read_pdf(b"%PDF-1.7\n% nothing here\n").pdfa_claim is None


def test_the_namespace_outside_an_xmp_packet_is_still_ignored():
    """Scoping to XMP packets is what stops a comment from inventing a claim, and
    reading the prefix from the document must not widen that."""
    smuggled = (b"%PDF-1.7\n% xmlns:pa=\"" + PDFA_NS.encode()
                + b"\" <pa:part>3</pa:part><pa:conformance>B</pa:conformance>\n%%EOF\n")
    assert vdi2770.read_pdf(smuggled).pdfa_claim is None
