"""`F1` reports a declared file that is not in the container. When the file *is*
there and this tool refused it, `F1` said "in the container but could not be
read" and told the sender to re-create the archive.

For a bad CRC that is true and the remedy works. For a refusal by budget it is
false three ways, and it reproduces from a fixture in this repository:

    $ vdi2770-validate check tests/fixtures/z5b-declared-bomb.zip
      error  F1  A file named in the metadata is in the container but could not be read
             'bomb.pdf' … was refused: it expands further than this tool will allow
             -> Re-create the archive and send it again … the bytes behind the name
                are not readable.

`bomb.pdf` is forty mebibytes of zeros. Its bytes are perfectly readable; this
tool declined to inflate them. Re-creating the identical archive reproduces the
identical finding. And the JSON marked it `about: "container"`, so a CI job
filtering for the sender's faults saw an error caused only by our ratio floor.
"""
import json

from conftest import FIXTURES
from vdi2770_validate import report as rendering
from vdi2770_validate.model import About
from vdi2770_validate.runner import check_file

BUDGET = FIXTURES / "z5b-declared-bomb.zip"


def f1_of(path):
    rep = check_file(str(path))
    found = [f for f in rep.findings if f.rule.id == "F1"]
    assert found, f"the fixture no longer produces F1: {sorted(f.rule.id for f in rep.findings)}"
    return rep, found[0]


def test_a_budget_refusal_is_not_reported_as_unreadable_bytes():
    _, f = f1_of(BUDGET)
    assert "could not be read" not in f.message, f.message
    assert "this tool" in f.message.lower(), f.message


def test_its_remedy_is_not_one_that_reproduces_the_finding():
    _, f = f1_of(BUDGET)
    assert "Re-create the archive and send it again" not in f.remedy, f.remedy


def test_the_json_says_the_finding_is_about_this_tool():
    rep, f = f1_of(BUDGET)
    assert f.about is About.TOOL, f.about
    doc = json.loads(rendering.as_json(rep))
    row = next(r for r in doc["findings"] if r["rule"] == "F1")
    assert row["about"] == "tool", row


def test_a_broken_member_is_still_the_containers_problem():
    """The distinction is the point. A bad CRC really is unreadable bytes and
    re-creating the archive really is the fix."""
    import io
    import zipfile

    from conftest import CLEAN_DOCUMENTATION
    from vdi2770_validate.runner import check_bytes

    src = zipfile.ZipFile(CLEAN_DOCUMENTATION)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name in src.namelist():
            z.writestr(name, src.read(name))
    raw = out.getvalue()
    crc = zipfile.ZipFile(io.BytesIO(raw)).getinfo("VDI2770_Main.pdf").CRC
    raw = raw.replace(crc.to_bytes(4, "little"),
                      ((crc ^ 0xFFFF) & 0xFFFFFFFF).to_bytes(4, "little"))

    rep = check_bytes(raw, "crc.zip")
    f = next(f for f in rep.findings if f.rule.id == "F1")
    assert "could not be read" in f.message, f.message
    assert "Re-create the archive" in f.remedy, f.remedy
    assert f.about is About.CONTAINER
