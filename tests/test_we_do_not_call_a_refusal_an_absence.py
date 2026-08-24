"""`Z8` said a documentation container holds no document containers. `Z6`, one
line above, named the document container it had found inside it.

`Z8` tests `not container.children`, and the reader stops populating children at
three levels — and, since the tree budget landed, at a thousand containers. A
refusal to look is not an absence, and printing both is the kind of output
someone reports as a bug on sight.
"""
import io
import pathlib
import zipfile

from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION
from vdi2770_validate.runner import check_file

DOCN = zipfile.ZipFile(CLEAN_DOCUMENTATION)
MAINXML = DOCN.read("VDI2770_Main.xml").decode()
MAINPDF = DOCN.read("VDI2770_Main.pdf")
INNER = CLEAN_DOCUMENT.read_bytes()


def documentation(extra):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VDI2770_Main.xml", MAINXML)
        z.writestr("VDI2770_Main.pdf", MAINPDF)
        for n, d in extra:
            z.writestr(n, d)
    return buf.getvalue()


def write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


def ids(path):
    return {f.rule.id for f in check_file(path).findings}


def test_stopping_at_the_depth_limit_is_not_an_empty_container(tmp_path):
    level3 = documentation([("documentcontainer.zip", INNER)])
    level2 = documentation([("level3.zip", level3)])
    p = write(tmp_path, "four_levels.zip", documentation([("level2.zip", level2)]))
    got = ids(p)
    assert "Z6" in got, got
    assert "Z8" not in got, (
        "Z6 named the container it found and Z8 said there was none: " + str(got))


def test_a_documentation_container_with_nothing_in_it_still_says_so(tmp_path):
    p = write(tmp_path, "really_empty.zip", documentation([]))
    assert "Z8" in ids(p)


def test_an_unreadable_inner_container_is_not_an_absence(tmp_path):
    """The member has to be genuinely undecompressable, which means damaging the
    outer archive's stream rather than the inner archive's bytes. Corrupting the
    inner file leaves its central directory intact, the reader opens it anyway,
    and a child is created — so the first version of this test never reached the
    suppression it was written for and passed regardless.
    """
    data = bytearray(documentation([("documentcontainer.zip", INNER)]))
    info = zipfile.ZipFile(io.BytesIO(bytes(data))).getinfo("documentcontainer.zip")
    start = info.header_offset + 30 + len(info.filename) + 500
    for k in range(start, start + 60):
        data[k] ^= 0xFF
    p = write(tmp_path, "unreadable_inner.zip", bytes(data))

    from vdi2770.zipread import read
    box = read(pathlib.Path(p).read_bytes(), "x.zip")
    assert not box.children, "the premise is that the reader could not open it"
    assert any(d.kind == "member-unreadable" for d in box.defects)

    got = ids(p)
    assert "Z12" in got, f"the unreadable member went unreported: {got}"
    assert "Z8" not in got, got


def test_a_corrupt_ordinary_member_does_not_excuse_an_empty_container(tmp_path):
    """The suppression keys on containers we could not open, not on any defect at
    all — a PDF we could not decompress says nothing about whether document
    containers are present. The member has to be genuinely unreadable for this to
    test anything: a file full of zero bytes decompresses perfectly well, which is
    what the first version of this guard used, and the mutation walked past it.
    """
    data = bytearray(documentation([("beilage.pdf", b"%PDF-1.7\n" + b"x" * 4000)]))
    info = zipfile.ZipFile(io.BytesIO(bytes(data))).getinfo("beilage.pdf")
    # Stay inside the compressed stream: this payload deflates to about forty
    # bytes, and running past it damages the next local header instead, which
    # makes the whole archive unreadable and tests something else entirely.
    start = info.header_offset + 30 + len(info.filename) + 2
    assert info.compress_size > 12, info.compress_size
    for k in range(start, start + 8):
        data[k] ^= 0xFF
    p = write(tmp_path, "broken_pdf.zip", bytes(data))

    from vdi2770.zipread import read
    box = read(pathlib.Path(p).read_bytes(), "x.zip")
    assert any(d.kind == "member-unreadable" and d.where.member == "beilage.pdf"
               for d in box.defects), [(d.kind, d.where.member) for d in box.defects]

    got = ids(p)
    assert "Z12" in got and "Z8" in got, got


def test_a_normal_two_level_container_says_nothing(tmp_path):
    p = write(tmp_path, "normal.zip", documentation([("documentcontainer.zip", INNER)]))
    assert not ids(p) & {"Z6", "Z8"}, ids(p)


def test_running_out_of_container_budget_is_not_an_absence(tmp_path, monkeypatch):
    """The tree budget can leave a container childless for a reason that has
    nothing to do with what the sender packed — and it lands on whichever
    container happens to be next, which is nobody's fault at all.

    The boundary is reached by lowering the limit rather than by building a
    thousand archives: with three containers allowed, the second sibling is
    opened and then refused its own child.
    """
    from vdi2770 import zipread

    monkeypatch.setattr(zipread, "MAX_CONTAINERS", 3)
    one = documentation([("documentcontainer.zip", INNER)])
    p = write(tmp_path, "budget.zip",
              documentation([("a-filler.zip", one), ("b-victim.zip", one)]))

    box = zipread.read(pathlib.Path(p).read_bytes(), "budget.zip")
    victim = next(c for c in box.walk() if c.path.endswith("b-victim.zip"))
    assert not victim.children, "the premise is that the budget stopped here"
    assert any(d.kind == "container-budget-exhausted" for d in victim.defects), \
        [(d.kind, d.where.member) for d in victim.defects]

    at_victim = {f.rule.id for f in check_file(p).findings
                 if f.where.container.endswith("b-victim.zip")}
    assert "Z8" not in at_victim, at_victim
