"""A member the reader refused must not then be decompressed.

`_classify` was changed to read `present` — every name the archive declares,
including refused ones — so that a container with an unreadable
`VDI2770_Main.xml` would still be recognised as a documentation container
instead of "not a VDI 2770 container at all". True, and it had a consequence
nobody looked for: `kind` sets `wanted`, and `wanted` was read unconditionally.
So the refusal decided the classification and then the refused bytes were
inflated anyway.

Two ways that bites, both measured:

  * a zip bomb refused for its compression ratio is inflated regardless — a
    9.5 KB archive produced 9.4 MB of metadata *after* the reader recorded
    `suspicious-compression`;
  * a member whose deflate stream is damaged raises `zlib.error`, which is not
    in the except tuple around the read, and the whole container dies. 140 of
    300 single-bit flips inside one metadata stream did it.
"""
import io
import zipfile

import pytest

from vdi2770 import zipread


def pack(members, level=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in members.items():
            z.writestr(n, d)
    return buf.getvalue()


PDF = b"%PDF-1.7\n" + b"x" * 200


def test_a_member_refused_for_its_ratio_is_not_inflated_anyway():
    # Inside the window the ratio cap is for: over MIN_SUSPICIOUS_BYTES, under
    # MAX_METADATA_BYTES, and compressing about a thousandfold.
    body = (b"<Document xmlns='http://www.vdi.de/schemas/vdi2770'>"
            + b" " * 9_400_000 + b"</Document>")
    data = pack({"VDI2770_Main.xml": body, "VDI2770_Main.pdf": PDF})
    assert len(data) < 100_000, f"the premise is a small archive: {len(data)}"

    c = zipread.read(data, "bomb.zip")
    assert "VDI2770_Main.xml" in c.rejected
    assert any(d.kind == "suspicious-compression" for d in c.defects)
    assert c.metadata_bytes is None, (
        f"the reader refused this member and then inflated "
        f"{len(c.metadata_bytes):,} bytes of it anyway")


def test_a_damaged_stream_in_the_metadata_is_a_defect_not_a_crash():
    body = (b"<Document xmlns='http://www.vdi.de/schemas/vdi2770'>"
            + b"<DocumentId DomainId='d'>x</DocumentId>" * 200 + b"</Document>")
    raw0 = pack({"VDI2770_Main.xml": body, "VDI2770_Main.pdf": PDF})
    info = zipfile.ZipFile(io.BytesIO(raw0)).getinfo("VDI2770_Main.xml")
    lo = info.header_offset + 30 + len(info.filename)

    # Every byte of the compressed stream, one flipped bit each. Not a sample:
    # the failure was in 47% of them and a sample would have looked like a
    # flake.
    for offset in range(lo, lo + info.compress_size):
        raw = bytearray(raw0)
        raw[offset] ^= 0x01
        try:
            c = zipread.read(bytes(raw), "damaged.zip")
        except Exception as e:                       # noqa: BLE001
            pytest.fail(f"byte {offset - lo} of the stream: {type(e).__name__}: {e}")
        assert c.kind is not None
        # Either it still parsed, or the reader said why it could not.
        assert c.metadata_bytes is not None or c.defects, offset


def test_the_metadata_is_still_read_when_nothing_refused_it():
    """The guard must not become "never read the metadata"."""
    body = b"<Document xmlns='http://www.vdi.de/schemas/vdi2770'/>"
    c = zipread.read(pack({"VDI2770_Main.xml": body, "VDI2770_Main.pdf": PDF}), "ok.zip")
    assert c.metadata_bytes == body
    assert c.metadata_name == "VDI2770_Main.xml"


# --- the same name twice, which defeated every refusal above ---------------

def _two_entries_one_name(second: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VDI2770_Metadata.xml", b"<x/>")
        z.writestr("a.pdf", b"%PDF-1.7\n")          # accepted
        z.writestr("a.pdf", second)                 # refused
    return buf.getvalue()


def test_a_name_that_means_two_entries_reads_neither():
    """Every refusal in this file is recorded against a *name*, and `zipfile`
    resolves a duplicated name to the **last** entry — so the accepted `Member`,
    the budget charge and the allow-list all came from the first entry while the
    bytes came from the second.

    Measured: a 505 KiB archive whose second `d.zip` is 400 MB of zeros drove
    this process to 1.25 GiB while the report said the member was refused for
    expanding 1028x. The refusal was recorded and then read around.

    Two entries with one name is not a member this reader can identify. It says
    so rather than picking one.
    """
    raw = _two_entries_one_name(b"\0" * (64 * 1024 * 1024))
    box = zipread.read(raw, "x.zip")

    assert zipread.member_bytes(raw, "a.pdf") is None, (
        "the name names two entries and one of them came back")
    assert zipread.member_bytes(raw, "a.pdf", allowed=set(box.file_names)) is None, (
        "the allow-list is by name, so it allowed the entry it never accepted")


def test_it_says_the_name_is_the_problem():
    raw = _two_entries_one_name(b"\0" * (64 * 1024 * 1024))
    box = zipread.read(raw, "x.zip")
    said = {d.kind for d in box.defects if d.where.member == "a.pdf"}
    assert "ambiguous-name" in said, sorted(said)
    assert "a.pdf" in box.rejected


def test_an_inner_container_with_a_repeated_name_is_not_opened():
    """The 1.25 GiB path: `read()` opened nested archives with `zf.read(name)`,
    which is the same lookup and the same last-entry answer."""
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("VDI2770_Metadata.xml", b"<x/>")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VDI2770_Main.xml", b"<x/>")
        z.writestr("d.zip", inner.getvalue())
        z.writestr("d.zip", b"\0" * (64 * 1024 * 1024))

    box = zipread.read(buf.getvalue(), "outer.zip")
    assert [c.path for c in box.walk()] == ["outer.zip"], (
        f"it opened something it cannot identify: {[c.path for c in box.walk()]}")
    assert "ambiguous-name" in {d.kind for d in box.defects}, (
        f"it skipped the archive and did not say why: "
        f"{[(d.kind, d.where.member) for d in box.defects]}")
