"""A document container delivered as a folder is read, not refused.

VDI 2770 hands documents over as document containers inside a documentation
container. Some deliveries put a document container's files in a folder of its
own instead of zipping them, and the reference implementation reads such a
folder as the document container it is: given the sample documentation
container with its one document container unpacked into a folder, it reports
nothing louder than a note. This tool said `Z13` -- documents delivered as
folders, which this tool does not open -- and checked nothing inside.

Held here: the same document container, zipped or unpacked into a folder, draws
the same findings. The folder draws `Z9` besides, which says the archive stores
files in folders, and nothing else may differ.
"""
import io
import zipfile
from collections import Counter

from vdi2770_validate.runner import check_bytes

from conftest import CLEAN_DOCUMENTATION


def _unpacked():
    """The sample documentation container with its one document container
    unpacked into a folder of the same name."""
    buf = io.BytesIO()
    with zipfile.ZipFile(CLEAN_DOCUMENTATION) as given, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for name in given.namelist():
            if name != "documentcontainer.zip":
                out.writestr(name, given.read(name))
                continue
            with zipfile.ZipFile(io.BytesIO(given.read(name))) as inner:
                for part in inner.namelist():
                    out.writestr("documentcontainer/" + part, inner.read(part))
    return buf.getvalue()


def _verdict(data, *, leave_out=()):
    return Counter((f.rule.id, f.severity.value) for f in check_bytes(data, "delivery.zip").findings
                   if f.rule.id not in leave_out)


def test_a_document_container_in_a_folder_draws_what_it_draws_zipped():
    zipped = _verdict(CLEAN_DOCUMENTATION.read_bytes())
    folder = _verdict(_unpacked(), leave_out=("Z9",))
    assert folder == zipped, (
        f"unpacked into a folder: {sorted(folder.items())}; "
        f"zipped: {sorted(zipped.items())}")


def test_a_container_inside_a_document_container_is_one_zipped_or_not():
    """`Z11`: a document container carries another container inside it. A
    folder is a container that was not zipped, and `F2` says nothing about the
    files in one, so a rule that saw only `.zip` members let the same inner
    container through unpacked that it stopped zipped -- the check its reason
    says an inner container gets past."""
    from conftest import CLEAN_DOCUMENT

    def carrying(unpacked):
        buf = io.BytesIO()
        with zipfile.ZipFile(CLEAN_DOCUMENT) as outer, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
            for name in outer.namelist():
                out.writestr(name, outer.read(name))
            if not unpacked:
                out.writestr("inner.zip", CLEAN_DOCUMENT.read_bytes())
            else:
                with zipfile.ZipFile(CLEAN_DOCUMENT) as inner:
                    for name in inner.namelist():
                        out.writestr("inner/" + name, inner.read(name))
        return buf.getvalue()

    def z11(data):
        return [f.where.member for f in check_bytes(data, "delivery.zip").findings
                if f.rule.id == "Z11"]

    assert z11(carrying(unpacked=False)) == ["inner.zip"], "the premise"
    assert z11(carrying(unpacked=True)) == ["inner/"], "the same container unpacked went unremarked"


def _nested(unpacked, main_pdf=None):
    """The sample documentation container carrying a second one, `plantA`,
    zipped or unpacked into a folder -- with `plantA`'s main PDF replaced when
    `main_pdf` is given."""
    with zipfile.ZipFile(CLEAN_DOCUMENTATION) as given:
        inner = {n: given.read(n) for n in given.namelist()}
        outer = dict(inner)
    if main_pdf is not None:
        inner["VDI2770_Main.pdf"] = main_pdf
    if unpacked:
        outer.update({"plantA/" + n: d for n, d in inner.items()})
    else:
        packed = io.BytesIO()
        with zipfile.ZipFile(packed, "w", zipfile.ZIP_DEFLATED) as z:
            for n, d in inner.items():
                z.writestr(n, d)
        outer["plantA.zip"] = packed.getvalue()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for n, d in outer.items():
            out.writestr(n, d)
    return buf.getvalue()


def test_a_documentation_container_in_a_folder_draws_what_it_draws_zipped():
    """Both reserved names make a folder a container, and the reader opened only
    the one: a documentation container unpacked into a folder went unchecked
    while the same one zipped was read. And a finding in a folder is at a path
    in that folder -- `plantA/VDI2770_Main.pdf`, not an archive called
    `plantA/` with a member in it."""
    broken = b"this is not a pdf"
    zipped = _verdict(_nested(unpacked=False, main_pdf=broken))
    folder = _verdict(_nested(unpacked=True, main_pdf=broken), leave_out=("Z9",))
    assert folder == zipped, (
        f"unpacked into a folder: {sorted(folder.items())}; "
        f"zipped: {sorted(zipped.items())}")

    def at_main_pdf(data):
        return sorted({(f.rule.id, str(f.where))
                       for f in check_bytes(data, "delivery.zip").findings
                       if "plantA" in str(f.where) and str(f.where).endswith("VDI2770_Main.pdf")})

    was = at_main_pdf(_nested(unpacked=False, main_pdf=broken))
    assert was, "the premise: the broken main PDF draws a finding zipped"
    assert at_main_pdf(_nested(unpacked=True, main_pdf=broken)) == [
        (rid, where.replace("plantA.zip!/", "plantA/")) for rid, where in was]


def _read_all_but(data, refused):
    """What `check_bytes` says, and the findings inside `refused` -- which were
    not to be opened, so there must be none."""
    report = check_bytes(data, "delivery.zip")
    inside = [f"{f.rule.id} {f.where}" for f in report.findings
              if str(f.where).startswith(f"delivery.zip!/{refused}") and str(f.where) != f"delivery.zip!/{refused}"]
    return report, inside


def test_a_folder_is_charged_against_the_budget_a_zip_is(monkeypatch):
    """Opening a folder inflates its members a second time, into the archive
    that is read as the container. That has to be paid for from the read's one
    allowance, as reading a nested `.zip` whole is -- or a folder is the door
    the tree budget does not watch."""
    from vdi2770 import zipread

    for unpacked, refused in ((False, "documentcontainer.zip"), (True, "documentcontainer/")):
        data = _unpacked() if unpacked else CLEAN_DOCUMENTATION.read_bytes()
        listing = zipfile.ZipFile(io.BytesIO(data))
        # Enough for the sweep over the outer archive and its own metadata, and
        # not a byte more: the next thing charged is the inner container.
        spent = (sum(i.file_size for i in listing.infolist() if not i.is_dir())
                 + listing.getinfo("VDI2770_Main.xml").file_size)
        monkeypatch.setattr(zipread, "MAX_TOTAL_DECOMPRESSED", spent)
        report, inside = _read_all_but(data, refused)
        assert not inside, f"{refused} was opened past the budget: {inside}"
        assert [str(f.where) for f in report.findings if f.rule.id == "Z5"] == [
            f"delivery.zip!/{refused}"], sorted(f"{f.rule.id} {f.where}" for f in report.findings)


def test_a_folder_counts_as_a_container_opened(monkeypatch):
    """The other allowance: how many containers one read opens below the one
    it was given. None, here."""
    from vdi2770 import zipread

    monkeypatch.setattr(zipread, "MAX_CONTAINERS", 0)
    for unpacked, refused in ((False, "documentcontainer.zip"), (True, "documentcontainer/")):
        data = _unpacked() if unpacked else CLEAN_DOCUMENTATION.read_bytes()
        report, inside = _read_all_but(data, refused)
        assert not inside, f"{refused} was opened past the container limit: {inside}"
        assert f"delivery.zip!/{refused}" in {str(f.where) for f in report.findings
                                                if f.rule.id == "Z5"}, (
            sorted(f"{f.rule.id} {f.where}" for f in report.findings))


def test_a_folder_too_deep_is_said_to_be_as_a_zip_is(monkeypatch):
    from vdi2770 import zipread

    monkeypatch.setattr(zipread, "MAX_CONTAINER_LEVELS", 1)
    for unpacked, refused in ((False, "documentcontainer.zip"), (True, "documentcontainer/")):
        data = _unpacked() if unpacked else CLEAN_DOCUMENTATION.read_bytes()
        report, inside = _read_all_but(data, refused)
        assert not inside, inside
        assert [str(f.where) for f in report.findings if f.rule.id == "Z6"] == [
            f"delivery.zip!/{refused}"], sorted(f"{f.rule.id} {f.where}" for f in report.findings)


def test_a_folder_that_reads_once_and_not_twice_is_refused_not_a_crash(monkeypatch):
    """The sweep reads every member once to see that it can. A folder is read
    a second time to put it together, and a member that fails then -- the
    stream the sweep never verified because the budget had run out, say --
    is a folder this tool did not open, not a crash of the whole run."""
    from vdi2770 import zipread

    real = zipread._whole

    def fails_in_the_folder(zf, name):
        if name.startswith("documentcontainer/"):
            raise OSError("the second read failed")
        return real(zf, name)

    monkeypatch.setattr(zipread, "_whole", fails_in_the_folder)
    report, inside = _read_all_but(_unpacked(), "documentcontainer/")
    fired = {f.rule.id for f in report.findings}
    assert "X5" not in fired, sorted(fired)
    assert not inside, inside
    assert "delivery.zip!/documentcontainer/" in {str(f.where) for f in report.findings
                                                   if f.rule.id == "Z12"}, sorted(fired)
    assert "Z13" in fired, "a folder this tool did not open was not said to be one"


def test_a_member_refused_in_a_folder_is_refused_once_as_it_is_zipped():
    """What the reader refuses -- a name that climbs out of the folder, a name
    stored twice -- it refuses once, in the archive that holds it. The folder is
    put together from what that read accepted, so the container it is does not
    meet the member a second time; zipped, the inner read is the one that
    refuses it. Either way one finding, and the same one."""
    from conftest import CLEAN_DOCUMENT

    with zipfile.ZipFile(CLEAN_DOCUMENT) as doc:
        inner = [(n, doc.read(n)) for n in doc.namelist()]
        twice = doc.read("B.pdf")
    with zipfile.ZipFile(CLEAN_DOCUMENTATION) as docn:
        root = [(n, docn.read(n)) for n in ("VDI2770_Main.xml", "VDI2770_Main.pdf")]

    def packed(entries):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for n, d in entries:
                z.writestr(n, d)
        return buf.getvalue()

    for extra in ([("../escaped.txt", b"x")], [("B.pdf", twice)]):
        zipped = _verdict(packed(root + [("documentcontainer.zip", packed(inner + extra))]))
        folder = _verdict(packed(root + [("documentcontainer/" + n, d) for n, d in inner + extra]),
                          leave_out=("Z9",))
        assert folder == zipped, (
            f"{extra[0][0]} unpacked: {sorted(folder.items())}; zipped: {sorted(zipped.items())}")
