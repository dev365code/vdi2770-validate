"""Every cap in the reader bounds one archive or one member. None bounded the
whole container tree, and the tree is where the amplification lives.

Measured before the fix: a 274 KB file produced 265 MB of resident memory, and
the caps that were supposed to stop that never engaged -- the outer archive's
uncompressed total was 254 KB, nowhere near MAX_TOTAL_BYTES. The only binding
limit was MAX_MEMBERS, so ten thousand inner containers each holding sixteen
megabytes of metadata was a permitted input: about 156 GiB, from a file small
enough to email.
"""
import io
import zipfile

from vdi2770.zipread import MAX_TOTAL_METADATA_BYTES, read


def nest(n_inner: int, meta_bytes: int) -> bytes:
    meta = (b'<?xml version="1.0"?><Document xmlns="http://www.vdi.de/schemas/vdi2770">'
            + b"<!-- " + b"A" * meta_bytes + b" -->"
            + b"<DocumentId>D</DocumentId></Document>")
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("VDI2770_Metadata.xml", meta)
    payload = inner.getvalue()
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w", zipfile.ZIP_STORED) as z:
        z.writestr("VDI2770_Main.xml", b'<Document xmlns="http://www.vdi.de/schemas/vdi2770"/>')
        z.writestr("VDI2770_Main.pdf", b"%PDF-1.7\n")
        for i in range(n_inner):
            z.writestr(f"d{i:05d}.zip", payload)
    return outer.getvalue()


def retained(container) -> int:
    return sum(len(c.metadata_bytes or b"") for c in container.walk())


def test_the_metadata_a_tree_can_hold_is_bounded():
    data = nest(300, 1024 * 1024)
    assert len(data) < 1024 * 1024, "the premise is that the input is small"
    box = read(data, "amp.zip")
    assert retained(box) <= MAX_TOTAL_METADATA_BYTES, (
        f"held {retained(box) / 1e6:.0f} MB of metadata from a "
        f"{len(data) / 1e3:.0f} KB file")


def test_hitting_that_bound_is_reported_and_not_silent():
    box = read(nest(300, 1024 * 1024), "amp.zip")
    kinds = {d.kind for c in box.walk() for d in c.defects}
    assert "container-budget-exhausted" in kinds, (
        f"stopped reading without saying so: {kinds}")


def test_an_ordinary_nested_container_is_untouched():
    """Three real documents inside a documentation container must still be read."""
    box = read(nest(3, 2_000), "small.zip")
    assert len(box.children) == 3
    assert all(c.metadata_bytes for c in box.children)
    assert not any(d.kind == "container-budget-exhausted"
                   for c in box.walk() for d in c.defects)


def test_the_measured_amplification_stays_in_three_figures_of_megabytes():
    """The number that matters to whoever runs this in a plant.

    The first version of this could not fail, in two independent ways.
    `ru_maxrss` is a process high-water mark that never comes back down, so
    inside the full suite it was already above anything this could add; and on
    Linux it is in kilobytes, not bytes, so the threshold on the only platform CI
    runs was a thousand times looser than it reads. Demonstrated by mutation:
    with the budget removed the test failed alone and passed in the suite.

    `tracemalloc` measures what this code allocates, on both platforms, and
    resets when it is stopped.
    """
    import tracemalloc

    data = nest(300, 1024 * 1024)
    tracemalloc.start()
    try:
        read(data, "amp.zip")
        peak_mb = tracemalloc.get_traced_memory()[1] / (1024 * 1024)
    finally:
        tracemalloc.stop()
    assert peak_mb < 200, f"allocated {peak_mb:.0f} MB reading a sub-megabyte file"


def test_the_number_of_containers_is_bounded_on_its_own(monkeypatch):
    """The two budgets fail independently, and the first version of this file only
    exercised one: 300 inner containers tripped the metadata budget, so removing
    MAX_CONTAINERS entirely changed nothing and the suite stayed green.

    Tiny metadata, many containers -- the count is the only thing that can stop it.

    The limit is monkeypatched down rather than built up to. Sizing the archive
    from the real constant meant raising that constant made this test *hang*
    instead of fail, which is a worse answer than either. The size itself is
    pinned in test_defences.py, where the rest of the budgets are.
    """
    from vdi2770 import zipread

    limit = 40
    monkeypatch.setattr(zipread, "MAX_CONTAINERS", limit)
    data = nest(limit + 20, 50)
    box = read(data, "many.zip")
    opened = sum(1 for _ in box.walk())
    assert opened == limit + 1, f"opened {opened} containers, root included"
    assert retained(box) < MAX_TOTAL_METADATA_BYTES // 8, (
        "the premise is that the metadata budget is nowhere near engaging")
    kinds = {d.kind for c in box.walk() for d in c.defects}
    assert "container-budget-exhausted" in kinds, f"stopped silently: {kinds}"
