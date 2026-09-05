"""Three things `read()` decompresses, and the budget was charged for one.

`MAX_TOTAL_DECOMPRESSED` was added to bound what one `read()` can inflate across
a whole tree — `MAX_TOTAL_BYTES` (2 GiB) times `MAX_CONTAINERS` (1000) is two
terabytes otherwise. It was wired into the readability sweep and neither of the
other two decompressions in the same function: the metadata member and each
inner container.

That leaves the cheapest possible attack: trip the budget with one small member
so the sweep stops verifying, after which every remaining read is free.
"""
import io
import zipfile

from vdi2770 import zipread


def pack(members, compress=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compress) as z:
        for n, d in members.items():
            z.writestr(n, d)
    return buf.getvalue()


def inflated_during(data, monkeypatch):
    """How many bytes `read()` actually pulls out of the archive."""
    seen = [0]
    real_read, real_open = zipfile.ZipFile.read, zipfile.ZipFile.open

    def counted_read(self, name, pwd=None):
        out = real_read(self, name, pwd)
        seen[0] += len(out)
        return out

    class Counting(io.RawIOBase):
        def __init__(self, fh):
            self.fh = fh

        def read(self, n=-1):
            out = self.fh.read(n)
            seen[0] += len(out)
            return out

        def close(self):
            self.fh.close()

    def counted_open(self, name, mode="r", pwd=None, *, force_zip64=False):
        return Counting(real_open(self, name, mode, pwd, force_zip64=force_zip64))

    monkeypatch.setattr(zipfile.ZipFile, "read", counted_read)
    monkeypatch.setattr(zipfile.ZipFile, "open", counted_open)
    zipread.read(data, "x.zip")
    return seen[0]


def a_tree():
    # Stored, not deflated: what this measures is what `zf.read` has to pull out
    # of the archive, and a payload that compresses to nothing makes the inner
    # containers free to read. That is how the first version of this test passed
    # against the very code it was written to catch.
    inner = pack({"VDI2770_Metadata.xml": b"<Document xmlns='http://www.vdi.de/schemas/vdi2770'/>",
                  "payload.bin": bytes(range(256)) * 2_000},
                 compress=zipfile.ZIP_STORED)
    assert len(inner) > 400_000, f"the inner container must be big on the wire: {len(inner)}"
    members = {"VDI2770_Main.xml": b"<Document xmlns='http://www.vdi.de/schemas/vdi2770'/>",
               "VDI2770_Main.pdf": b"%PDF-1.7\n" + b"x" * 200,
               "filler.bin": b"F" * 100_000}
    for i in range(20):
        members[f"c{i:02d}.zip"] = inner
    return pack(members, compress=zipfile.ZIP_STORED)


def test_a_spent_budget_stops_every_decompression_not_just_the_sweep(monkeypatch):
    data = a_tree()
    monkeypatch.setattr(zipread, "MAX_TOTAL_DECOMPRESSED", 1)
    spent = inflated_during(data, monkeypatch)
    assert spent < 1_000_000, (
        f"the budget was one byte and {spent:,} bytes were inflated anyway")


def test_the_budget_still_lets_an_ordinary_tree_through(monkeypatch):
    data = a_tree()
    spent = inflated_during(data, monkeypatch)
    assert spent > 1_000_000, f"the premise: this tree really does inflate a lot ({spent:,})"
    box = zipread.read(data, "x.zip")
    assert len(box.children) == 20, "an ordinary tree must still be opened in full"


def test_a_trailer_the_keyword_check_declines_still_costs_budget(monkeypatch):
    """`MAX_TRAILERS` bounds how many trailer dictionaries the fallback reads.
    A token the keyword check declined never reached the subtraction — `continue`
    stepped over it — so a file of decoys was examined once per decoy.

    That would be linear and survivable on its own. The check itself is what
    squares it: to see whether a `%` opens the line, it walks back to the last
    newline, and a file with no newline in it makes every one of those walks run
    to the start of the file. Measured on this machine: 64 KB took 0.14 s, 128 KB
    0.66 s, 256 KB 2.76 s, 512 KB 11.17 s — four times the work for twice the
    input. End to end that is a 13 KB archive holding a 2 MB member and taking
    minutes, on a path the compression-ratio and member-size guards never see,
    because it reads raw bytes and inflates nothing.

    The same shape as the XMP scan that once held this tool for hours on a 20 KB
    file. It is counted here rather than timed: the budget exists to bound how
    many times the file is examined, so that is the number asserted.

    The charge has to stay small. `test_a_decoy_that_brings_its_own_startxref…`
    holds the opposite corner: make examining a token expensive and a supplier
    can bury the real trailer behind enough decoys to spend the budget before it
    is reached, which hides an encrypted document. `MAX_LINE_LOOKBACK` is the
    only thing holding both off, so both tests have to pass at one value of it.
    """
    from vdi2770 import pdfread

    seen = []
    real = pdfread._is_a_keyword_here
    monkeypatch.setattr(pdfread, "_is_a_keyword_here",
                        lambda data, at, length: (seen.append(at),
                                                  real(data, at, length))[1])

    def probes(decoys: int) -> int:
        seen.clear()
        # No newline anywhere, so every look-back runs the length of the file,
        # and a `%` early in the line makes every token decline.
        pdfread._is_encrypted(b"%PDF-1.4 1 0 obj % " + b"trailer " * decoys
                              + b" endobj")
        return len(seen)

    small, big = probes(20_000), probes(80_000)
    assert big <= small, (
        f"{small} probes for 20,000 decoys and {big} for 80,000: the decoys are "
        f"paying nothing, so the file is scanned once per token")

    ceiling = pdfread.MAX_TRAILER_BYTES // pdfread.MAX_LINE_LOOKBACK + pdfread.MAX_TRAILERS
    assert big <= ceiling, (
        f"{big} probes, and the budget allows {ceiling}: a declined token has to "
        f"cost what its look-back read, or the budget bounds nothing")


def test_a_claim_search_cut_off_inside_a_stream_says_so():
    """The loop that walks the streams reports when it stops. Three limits stop
    the search *inside* one and were silent: a stream truncated at
    `MAX_INFLATED_PER_STREAM`, a body longer than `MAX_STREAM_SCAN`, and packets
    past `MAX_XMP_PACKETS` in one haystack.

    Each of them leaves a file whose claim sits past the cut looking exactly
    like a file with no claim in it — which is the answer this pair exists to
    keep apart. All three are the file being larger than a bounded scan reads,
    so all three answer `"file"`.
    """
    import zlib

    from vdi2770 import pdfread

    xmp = (b'<?xpacket begin="" ?><rdf:RDF '
           b'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
           b'<rdf:Description xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">'
           b"<pdfaid:part>2</pdfaid:part>"
           b"<pdfaid:conformance>B</pdfaid:conformance>"
           b'</rdf:Description></rdf:RDF><?xpacket end="w"?>')
    head = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n"
    decoy = b'<?xpacket begin="" ?><rdf:RDF></rdf:RDF><?xpacket end="w"?>'

    ways = {
        "inflated past the per-stream cap":
            head + b"stream\n" + zlib.compress(
                b"A" * (pdfread.MAX_INFLATED_PER_STREAM + 10_000) + xmp),
        "compressed body past the scan window":
            head + b"stream\n" + zlib.compress(b"A" * 20_000_000 + xmp, 9),
        "claim after more packets than one haystack is read for":
            head + b"stream\n" + zlib.compress(
                decoy * (pdfread.MAX_XMP_PACKETS + 2) + xmp),
    }
    for why, body in ways.items():
        facts, cut_short = pdfread.reader(1 << 32)(body)
        if facts.pdfa_claim is not None:
            continue          # it was reached after all; nothing to report
        assert cut_short == "file", (
            f"a claim {why} was not found and the scan did not say it stopped: "
            f"cut_short={cut_short!r}")
