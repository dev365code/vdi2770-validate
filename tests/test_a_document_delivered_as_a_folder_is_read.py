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


# What follows was found by building the same content zipped and unpacked, at
# every level a delivery nests, and comparing the two reports line by line.

def _entries(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return [(i.filename, z.read(i)) for i in z.infolist() if not i.is_dir()]


def _pack(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in entries:
            z.writestr(n, d)
    return buf.getvalue()


def _unzipped(entries, depth=0, levels=99):
    """Every `.zip` member unpacked into a folder of its name, down `levels` levels."""
    out = []
    for n, d in entries:
        if n.endswith(".zip") and depth < levels:
            out += [(n[:-4] + "/" + m, x) for m, x in _unzipped(_entries(d), depth + 1, levels)]
        else:
            out.append((n, d))
    return out


def test_folders_inside_folders_draw_what_the_zips_inside_zips_draw():
    """A folder inside an opened folder is that folder's container to open, and
    it did -- while the outer one reported it as a folder nobody opened."""
    from conftest import CORPUS

    nested = (CORPUS / "container" / "vdi2770_excel.zip").read_bytes()
    zipped = check_bytes(nested, "d.zip")
    folder = check_bytes(_pack(_unzipped(_entries(nested))), "d.zip")
    assert not [f.where for f in folder.findings if f.rule.id == "Z13"], "an opened folder called unopened"
    assert Counter((f.rule.id, f.severity.value) for f in folder.findings if f.rule.id != "Z9") == \
        Counter((f.rule.id, f.severity.value) for f in zipped.findings if f.rule.id != "Z9")


def test_a_container_inside_a_folder_is_at_a_path_in_that_folder():
    from conftest import CORPUS

    nested = _entries((CORPUS / "container" / "vdi2770_excel.zip").read_bytes())
    report = check_bytes(_pack(_unzipped(nested, levels=1)), "d.zip")
    wheres = {str(f.where) for f in report.findings}
    assert wheres and not [w for w in wheres if "/!/" in w], sorted(wheres)


def test_a_member_refused_in_a_folder_is_said_to_be_refused_not_missing():
    """The zipped container says `B.pdf` is in the archive and was refused;
    unpacked, it said the file was not there, and told the sender to add it."""
    from conftest import CLEAN_DOCUMENT, unopened

    doc = _entries(CLEAN_DOCUMENT.read_bytes())
    with zipfile.ZipFile(CLEAN_DOCUMENTATION) as docn:
        root = [(n, docn.read(n)) for n in ("VDI2770_Main.xml", "VDI2770_Main.pdf")]
    twice = dict(doc)["B.pdf"]
    for zipped, folder in (
            (_pack(root + [("documentcontainer.zip", unopened(_pack(doc), "B.pdf"))]),
             unopened(_pack(root + [("documentcontainer/" + n, d) for n, d in doc]), "documentcontainer/B.pdf")),
            (_pack(root + [("documentcontainer.zip", _pack(doc + [("B.pdf", twice)]))]),
             _pack(root + [("documentcontainer/" + n, d) for n, d in doc + [("B.pdf", twice)]]))):
        # The reader's own sentence names the member as the archive holding it
        # spells it: `B.pdf` in the inner archive, `documentcontainer/B.pdf` in
        # the one the folder is in. Nothing else may differ.
        said = [[(f.detail or "").replace("documentcontainer/B.pdf", "B.pdf")
                 for f in check_bytes(data, "d.zip").findings if f.rule.id == "F1"]
                for data in (zipped, folder)]
        assert said[1] == said[0], said


def test_two_spellings_of_one_path_in_a_folder_are_the_parents_to_report():
    """`./x` beside `x`, or one name composed and decomposed: the archive holding
    them reports the pair, and the folder is read with one of them -- zipped,
    the inner archive reports the pair and reads it. Written into the folder's
    archive as one name twice, both were refused and the document went unread."""
    import unicodedata

    from conftest import CLEAN_DOCUMENT

    doc = _entries(CLEAN_DOCUMENT.read_bytes())
    d = dict(doc)
    with zipfile.ZipFile(CLEAN_DOCUMENTATION) as docn:
        root = [(n, docn.read(n)) for n in ("VDI2770_Main.xml", "VDI2770_Main.pdf")]
    for extra in ([("./B.pdf", d["B.pdf"])], [("./VDI2770_Metadata.xml", d["VDI2770_Metadata.xml"])],
                  [("Prüf.pdf", b"%PDF-1.4"), (unicodedata.normalize("NFD", "Prüf.pdf"), b"%PDF-1.4")]):
        zipped = check_bytes(_pack(root + [("documentcontainer.zip", _pack(doc + extra))]), "d.zip")
        folder = check_bytes(_pack(root + [("documentcontainer/" + n, x) for n, x in doc]
                                   + [(("./documentcontainer/" + n[2:]) if n.startswith("./")
                                       else "documentcontainer/" + n, x) for n, x in extra]), "d.zip")
        count = [Counter((f.rule.id, f.severity.value) for f in r.findings if f.rule.id != "Z9")
                 for r in (folder, zipped)]
        assert count[0] == count[1], (extra[0][0], sorted(count[0].items()), sorted(count[1].items()))
        assert (folder.read.metadata_read, folder.read.metadata_found) == \
            (zipped.read.metadata_read, zipped.read.metadata_found), extra[0][0]


def test_a_folder_is_held_to_the_size_a_nested_container_is_read_within(monkeypatch):
    """A nested `.zip` over `MAX_MEMBER_BYTES` is refused, because a nested
    container is held whole while it is read. A folder is read as one too,
    whole, and was held to nothing but the read's total."""
    from conftest import CLEAN_DOCUMENT
    from vdi2770 import zipread

    doc = _entries(CLEAN_DOCUMENT.read_bytes())
    with zipfile.ZipFile(CLEAN_DOCUMENTATION) as docn:
        root = [(n, docn.read(n)) for n in ("VDI2770_Main.xml",)]
    # Under every member, over the container they make together.
    cap = max(len(d) for _n, d in doc) + 1
    assert cap < sum(len(d) for _n, d in doc), "the premise"
    monkeypatch.setattr(zipread, "MAX_MEMBER_BYTES", cap)
    for data, refused in ((_pack(root + [("documentcontainer.zip", _pack(doc))]), "documentcontainer.zip"),
                          (_pack(root + [("documentcontainer/" + n, d) for n, d in doc]), "documentcontainer/")):
        report = check_bytes(data, "d.zip")
        assert f"d.zip!/{refused}" in {str(f.where) for f in report.findings if f.rule.id == "Z5"}, (
            refused, sorted(f"{f.rule.id} {f.where}" for f in report.findings))
        assert not [f for f in report.findings if str(f.where).startswith(f"d.zip!/{refused}")
                    and str(f.where) != f"d.zip!/{refused}"], refused


def test_a_refusal_reaches_a_folder_inside_a_folder():
    """Handed to a folder's container after it had read itself, a refusal never
    reached the folders inside it: two folders down, a damaged PDF was a file
    never sent, with a remedy asking for it."""
    from conftest import CORPUS, unopened

    nested = _entries((CORPUS / "container" / "vdi2770_excel.zip").read_bytes())
    unpacked = _pack(_unzipped(nested))
    damaged = next(n for n, _d in _unzipped(nested) if n.endswith("/U1D1/U1D1.pdf"))
    said = [f.detail for f in check_bytes(unopened(unpacked, damaged), "d.zip").findings if f.rule.id == "F1"]
    assert said and all("in the archive but was refused" in d for d in said), said


def test_a_folder_whose_reserved_name_is_spelled_with_a_dot_is_judged_as_zipped():
    """`docdir/./VDI2770_Metadata.xml`: zipped, `./VDI2770_Metadata.xml` is not at
    the archive's root and the archive is no container, which is `Z3`. Unpacked,
    the folder was opened, found to be no container either, and then passed
    over in silence -- a folder is never a file the metadata declared, and was
    treated as one nobody could tell about."""
    from conftest import CLEAN_DOCUMENT

    pdf = dict(_entries(CLEAN_DOCUMENT.read_bytes()))["B.pdf"]
    with zipfile.ZipFile(CLEAN_DOCUMENTATION) as docn:
        root = [(n, docn.read(n)) for n in docn.namelist()]
    zipped = check_bytes(_pack(root + [("docdir.zip", _pack([("./VDI2770_Metadata.xml", b"not xml"),
                                                              ("B.pdf", pdf)]))]), "d.zip")
    folder = check_bytes(_pack(root + [("docdir/./VDI2770_Metadata.xml", b"not xml"),
                                       ("docdir/B.pdf", pdf)]), "d.zip")
    assert not zipped.clean, "the premise"
    assert Counter((f.rule.id, f.severity.value) for f in folder.findings if f.rule.id != "Z9") == \
        Counter((f.rule.id, f.severity.value) for f in zipped.findings if f.rule.id != "Z9")


def test_a_refused_metadata_file_in_a_folder_is_counted_once():
    from conftest import CLEAN_DOCUMENT, unopened

    doc = _entries(CLEAN_DOCUMENT.read_bytes())
    with zipfile.ZipFile(CLEAN_DOCUMENTATION) as docn:
        root = [(n, docn.read(n)) for n in ("VDI2770_Main.xml", "VDI2770_Main.pdf")]
    inner = doc + [("sub/" + n, d) for n, d in doc]
    zipped = check_bytes(_pack(root + [("documentcontainer.zip",
                                        unopened(_pack(inner), "sub/VDI2770_Metadata.xml"))]), "d.zip")
    folder = check_bytes(unopened(_pack(root + [("documentcontainer/" + n, d) for n, d in inner]),
                                  "documentcontainer/sub/VDI2770_Metadata.xml"), "d.zip")
    assert (folder.read.metadata_read, folder.read.metadata_found) == \
        (zipped.read.metadata_read, zipped.read.metadata_found)
