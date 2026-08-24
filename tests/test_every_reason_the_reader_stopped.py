"""`Z8` keeps quiet when the reader stopped descending. It knew about three of
the six ways that happens.

The guard listed defect kinds — depth, the tree budget, an unreadable member —
and missed the three rejections that drop a `.zip` before the descent loop ever
sees it: an unsafe name, an oversized member, a suspicious compression ratio.
Each of those produces the contradiction the guard was written to kill: `Z4` or
`Z5` names the archive it refused, and `Z8` says on the next line that this
container holds no document containers.

`container.rejected` is the list of members the reader dropped. Asking it covers
every reason at once, including reasons added later.
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


def documentation(tmp_path, name, extra, compress=zipfile.ZIP_DEFLATED):
    p = tmp_path / name
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compress) as z:
        z.writestr("VDI2770_Main.xml", MAINXML)
        z.writestr("VDI2770_Main.pdf", MAINPDF)
        for n, d in extra:
            z.writestr(n, d)
    p.write_bytes(buf.getvalue())
    return str(p)


def ids(path):
    return {f.rule.id for f in check_file(path).findings}


def test_a_zip_refused_for_its_compression_ratio_is_not_an_absence(tmp_path):
    p = documentation(tmp_path, "ratio.zip", [("inner.zip", b"\0" * (16 * 1024 * 1024))])
    got = ids(p)
    assert "Z5" in got, got
    assert "Z8" not in got, f"Z5 named the archive it refused and Z8 said there was none: {got}"


def test_a_zip_refused_for_its_name_is_not_an_absence(tmp_path):
    p = documentation(tmp_path, "unsafe.zip", [("sub\\documentcontainer.zip", INNER)])
    got = ids(p)
    assert "Z4" in got, got
    assert "Z8" not in got, got


def test_a_zip_refused_for_its_size_is_not_an_absence(tmp_path):
    from vdi2770 import zipread

    big = io.BytesIO()
    with zipfile.ZipFile(big, "w", zipfile.ZIP_STORED) as z:
        z.writestr("filler.bin", b"\0" * 1024)
    payload = big.getvalue()
    # A stored member whose declared size is over the per-member ceiling.
    p = tmp_path / "toobig.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VDI2770_Main.xml", MAINXML)
        z.writestr("VDI2770_Main.pdf", MAINPDF)
        z.writestr("inner.zip", payload + b"\0" * (zipread.MAX_MEMBER_BYTES + 1))
    p.write_bytes(buf.getvalue())
    got = ids(str(p))
    assert "Z5" in got, got
    assert "Z8" not in got, got


def test_a_documentation_container_with_nothing_in_it_still_says_so(tmp_path):
    assert "Z8" in ids(documentation(tmp_path, "empty.zip", []))


def test_a_refused_ordinary_member_does_not_excuse_an_empty_container(tmp_path):
    """Only a refused `.zip` can explain missing children."""
    p = documentation(tmp_path, "refused_pdf.zip", [("beilage.pdf", b"\0" * (16 * 1024 * 1024))])
    got = ids(p)
    assert "Z5" in got and "Z8" in got, got


def test_the_budget_says_how_many_it_did_not_open(tmp_path, monkeypatch):
    """`break` left the remaining siblings unmentioned, so a report naming one
    skipped container was really hiding several."""
    from vdi2770 import zipread

    monkeypatch.setattr(zipread, "MAX_CONTAINERS", 2)
    p = documentation(tmp_path, "budget.zip", [(f"d{i}.zip", INNER) for i in range(5)])
    box = zipread.read(pathlib.Path(p).read_bytes(), "budget.zip")
    assert len(box.children) == 2, [c.path for c in box.children]
    exhausted = [d for d in box.defects if d.kind == "container-budget-exhausted"]
    assert len(exhausted) == 1, [(d.kind, d.detail) for d in box.defects]
    assert "3 more" in exhausted[0].detail, exhausted[0].detail


def test_the_container_count_does_not_drift_past_the_limit(tmp_path, monkeypatch):
    """The counter is a number that reaches the user, in the metadata-budget
    message. Incrementing it on refusals made it climb past the limit it names,
    and the only way to see that is to ask the budget rather than the tree —
    counting opened containers cannot tell the two implementations apart.
    """
    from vdi2770 import zipread

    monkeypatch.setattr(zipread, "MAX_CONTAINERS", 2)
    budget = zipread._Budget()
    taken = [budget.take_container() for _ in range(6)]
    assert taken == [True, True, False, False, False, False], taken
    assert budget.containers == 2, (
        f"the counter reads {budget.containers} after two were opened and four refused")

    p = documentation(tmp_path, "drift.zip", [(f"d{i}.zip", INNER) for i in range(9)])
    box = zipread.read(pathlib.Path(p).read_bytes(), "drift.zip")
    assert sum(1 for _ in box.walk()) - 1 == 2      # the root is not counted
