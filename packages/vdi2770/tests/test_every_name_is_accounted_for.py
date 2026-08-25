"""The archive's directory lists names. After a read, each one is either a
member we can open or a member we refused — never both, never neither.

`present` was added so a caller could stop treating "we could not read it" as
"it is not there". That is only true if `present` really is the directory.
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


def directory(data):
    """Every non-directory name the ZIP's own central directory lists."""
    return {i.filename for i in zipfile.ZipFile(io.BytesIO(data)).infolist() if not i.is_dir()}


CASES = {
    "ordinary": {"VDI2770_Metadata.xml": b"<x/>", "a.pdf": b"%PDF-1.7\n"},
    "hostile name": {"VDI2770_Metadata.xml": b"<x/>", "../escape.txt": b"x"},
    "oversized member": {"VDI2770_Metadata.xml": b"<x/>", "big.bin": b"z" * 4096},
    "in a folder": {"VDI2770_Metadata.xml": b"<x/>", "sub/a.pdf": b"%PDF-1.7\n"},
    "no metadata": {"readme.txt": b"hello"},
    "hostile name in a folder": {"VDI2770_Metadata.xml": b"<x/>", "sub/../../x.txt": b"x"},
    "two refusals": {"VDI2770_Metadata.xml": b"<x/>", "../a.txt": b"x", "b:/c.txt": b"x"},
}
# Three of the original five refuse nothing, which makes `present == file_names`
# true by arithmetic and the overlap assertion vacuous for them. They still earn
# their place -- they check that `present` does not *lose* a name -- but the
# table has to carry cases where the two sets really differ, or the invariant is
# never actually exercised.
REFUSING = {"hostile name", "oversized member", "hostile name in a folder", "two refusals"}


@pytest.mark.parametrize("why,members", sorted(CASES.items()))
def test_present_is_exactly_the_archive_directory(monkeypatch, why, members):
    if why == "oversized member":
        monkeypatch.setattr(zipread, "MAX_MEMBER_BYTES", 512)
    data = pack(members)
    c = zipread.read(data, "x.zip")
    assert set(c.present) == directory(data), why


@pytest.mark.parametrize("why,members", sorted(CASES.items()))
def test_readable_and_refused_do_not_overlap(monkeypatch, why, members):
    if why == "oversized member":
        monkeypatch.setattr(zipread, "MAX_MEMBER_BYTES", 512)
    c = zipread.read(pack(members), "x.zip")
    both = set(c.file_names) & set(c.rejected)
    assert not both, f"{why}: {sorted(both)} counted as readable and refused at once"


def test_a_refused_member_is_refused_for_a_reason_the_defects_also_carry():
    """`rejected` holds a second English sentence about each refusal, written
    beside the `Defect` that already records it. Two sentences for one fact can
    disagree; this pins that every refused member has a defect at that member."""
    monkey = zipread.MAX_MEMBER_BYTES
    try:
        zipread.MAX_MEMBER_BYTES = 512
        c = zipread.read(pack({"VDI2770_Metadata.xml": b"<x/>", "big.bin": b"z" * 4096}), "x.zip")
    finally:
        zipread.MAX_MEMBER_BYTES = monkey
    assert "big.bin" in c.rejected
    at_member = [d.kind for d in c.defects if d.where.member == "big.bin"]
    assert at_member, "a member was refused with no defect naming it"


def test_an_archive_we_refused_whole_claims_nothing_about_its_members(monkeypatch):
    """The invariant above is about an archive we read. When the archive itself
    is over a budget we stop before listing anything, and `present` is empty —
    which is not the same as "the archive is empty". `kind` is what says so, and
    a caller reading `present` as the directory has to check it.
    """
    monkeypatch.setattr(zipread, "MAX_MEMBERS", 2)
    data = pack({f"f{i}.txt": b"x" for i in range(5)})
    c = zipread.read(data, "x.zip")
    assert c.kind is zipread.Kind.UNREADABLE
    assert c.present == () and not c.file_names and not c.rejected
    assert len(directory(data)) == 5, "the names are in the archive; we did not look"
    assert any(d.kind == "too-many-members" for d in c.defects)


def test_a_directory_entry_is_not_a_file_name(monkeypatch):
    """`present` promises "every file *name* the archive declares". A directory
    entry is not one, and an unsafe directory was refused before `is_dir()` was
    ever consulted, so it landed in `rejected` and from there in `present`. A
    directory called `VDI2770_Main.pdf/` would then answer for the file.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Metadata.xml", b"<x/>")
        z.writestr("a.pdf", b"%PDF-1.7\n")
        info = zipfile.ZipInfo("../evil/")
        info.external_attr = 0o40755 << 16
        z.writestr(info, b"")
    data = buf.getvalue()
    c = zipread.read(data, "x.zip")
    assert set(c.present) == directory(data), sorted(c.present)
    assert not any(n.endswith("/") for n in c.present), c.present
    # Still reported: refusing it is right, listing it as a file is not.
    assert any(d.kind == "unsafe-member-name" for d in c.defects)


def test_two_entries_with_one_name_are_still_two_entries(monkeypatch):
    """A ZIP may carry the same name twice and readers disagree about which one
    wins — which is the whole reason `duplicate_names` exists. It was derived
    from the surviving members, so refusing one copy made the pair vanish: an
    archive could hide a duplicate by making one of them oversized, and the
    recipient's tool might extract the copy this one never looked at.
    """
    monkeypatch.setattr(zipread, "MAX_MEMBER_BYTES", 512)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Metadata.xml", b"<x/>")
        z.writestr("dup.bin", b"z" * 4096)      # refused for size
        z.writestr("dup.bin", b"z")             # accepted
    c = zipread.read(buf.getvalue(), "x.zip")
    assert "dup.bin" in c.duplicate_names, (
        f"the name is in the archive twice and the reader saw one: {c.duplicate_names}")


def test_the_case_table_exercises_both_sides(monkeypatch):
    """Guards the table above, not the reader: if every case stopped refusing
    anything, both parametrized tests would keep passing and prove nothing."""
    refused = set()
    for why, members in CASES.items():
        if why == "oversized member":
            monkeypatch.setattr(zipread, "MAX_MEMBER_BYTES", 512)
        c = zipread.read(pack(members), "x.zip")
        monkeypatch.undo()
        if c.rejected:
            refused.add(why)
    assert refused == REFUSING, f"the table's refusing cases moved: {sorted(refused)}"
    assert len(refused) >= 3, "too few cases where present and file_names differ"
