"""The tree budgets bound bytes and archives. They did not bound the objects
built out of them.

`MAX_CONTAINERS` caps how many archives one read opens; `MAX_TOTAL_METADATA_BYTES`
and `MAX_TOTAL_DECOMPRESSED` cap what it inflates. None of them caps the number
of `Member` and `Defect` records retained — and one is built per entry in every
archive's directory. At the caps that is 10,000 x 1,000 = ten million records,
measured at roughly 460 bytes each: about 4.6 GB, from an input small enough to
email. Measured at one fiftieth of the cap: a 2.34 MB archive produced 320,000
defects and 147 MB, growing linearly.

The largest real container in this repository's corpus lists **twenty** members.
"""
import io
import zipfile

import pytest

from vdi2770 import zipread


def pack(members, compress=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compress) as z:
        for n, d in members.items():
            z.writestr(n, d)
    return buf.getvalue()


META = b"<Document xmlns='http://www.vdi.de/schemas/vdi2770'/>"


def a_wide_tree(kids, members_each, name=lambda i: f"/abs{i}.txt"):
    """Members with unsafe names, so each one costs a `Defect` as well."""
    inner = pack({"VDI2770_Metadata.xml": META,
                  **{name(i): b"" for i in range(members_each)}})
    return pack({"VDI2770_Main.xml": META,
                 **{f"c{i:04d}.zip": inner for i in range(kids)}})


def records(box):
    return sum(len(c.members) + len(c.defects) + len(c.rejected) for c in box.walk())


def test_the_records_one_read_retains_are_bounded(monkeypatch):
    monkeypatch.setattr(zipread, "MAX_TOTAL_MEMBERS", 2_000)
    box = zipread.read(a_wide_tree(kids=40, members_each=1_000), "wide.zip")
    kept = records(box)
    assert kept < 20_000, f"the budget was 2,000 entries and the read kept {kept:,} records"
    assert any(d.kind == "member-budget-exhausted" for c in box.walk() for d in c.defects), (
        "it stopped and said nothing")


def test_stopping_is_reported_as_this_tool_stopping():
    """Not as a verdict on the archive. Whoever sent it may have sent something
    fine; we declined to hold it all."""
    from vdi2770 import DEFECT_KINDS
    assert "member-budget-exhausted" in DEFECT_KINDS


def test_an_ordinary_tree_is_nowhere_near_the_budget():
    """The largest real container lists twenty members. A budget that a real
    delivery could reach is not a budget, it is a bug waiting for a customer."""
    box = zipread.read(a_wide_tree(kids=3, members_each=5), "small.zip")
    assert not any(d.kind == "member-budget-exhausted"
                   for c in box.walk() for d in c.defects)
    assert len(box.children) == 3, "an ordinary tree must still be opened in full"


@pytest.mark.parametrize("kids,members_each", [(20, 500), (40, 500), (40, 1000)])
def test_growth_stays_bounded_as_the_input_grows(kids, members_each, monkeypatch):
    """The shape that made this a finding was linear growth with no ceiling."""
    monkeypatch.setattr(zipread, "MAX_TOTAL_MEMBERS", 5_000)
    box = zipread.read(a_wide_tree(kids, members_each), "x.zip")
    assert records(box) < 40_000, records(box)
