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
