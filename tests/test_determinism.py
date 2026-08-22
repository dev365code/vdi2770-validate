"""The same container must produce the same bytes, twice, and regardless of the
order its members happen to be stored in."""
import io
import zipfile

from conftest import CLEAN_DOCUMENT
from vdi2770_validate import report as rendering
from vdi2770_validate.runner import check_bytes, check_file


def test_two_runs_are_byte_identical():
    a = rendering.as_json(check_file(str(CLEAN_DOCUMENT)))
    b = rendering.as_json(check_file(str(CLEAN_DOCUMENT)))
    assert a == b


def test_member_order_does_not_change_the_verdict():
    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    names = src.namelist()
    forward, backward = io.BytesIO(), io.BytesIO()
    with zipfile.ZipFile(forward, "w") as z:
        for n in names:
            z.writestr(n, src.read(n))
    with zipfile.ZipFile(backward, "w") as z:
        for n in reversed(names):
            z.writestr(n, src.read(n))
    a = check_bytes(forward.getvalue(), "x.zip")
    b = check_bytes(backward.getvalue(), "x.zip")
    assert [f.rule.id for f in a.sorted()] == [f.rule.id for f in b.sorted()]
