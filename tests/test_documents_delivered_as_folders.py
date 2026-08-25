"""A documentation container may deliver its documents as folders rather than as
inner `.zip` files. This tool opens `.zip` members and nothing else, so those
documents were never checked — and three rules said things about them anyway.

Reproduced on a container built from this repository's own corpus: a folder
holding a `VDI2770_Metadata.xml` with an unknown `ClassId` and an empty
`DocumentId`, both of which are *error* rules.

    warning F2  A file in the container is not named in the metadata   (x2)
    warning Z8  The documentation container holds no document containers
    warning Z9  The archive stores files in folders
    0 error(s), exit 0

`M2` and `M10` never ran. `Z8` is false — it holds one. `F2` is false — those
files are declared, in the metadata this tool did not open. The vendored
`corpus/examples/missingdocuments/folders.zip` shows the same shape, and the
recorded sweep has the reference implementation emitting, for that container,
the codes it emits for containers that *do* hold document containers.

Opening them is a feature. Not lying about them is not.
"""
import io
import zipfile

import pytest

from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION
from vdi2770_validate.model import Severity
from vdi2770_validate.runner import check_bytes

DOC = zipfile.ZipFile(CLEAN_DOCUMENT)
DOCN = zipfile.ZipFile(CLEAN_DOCUMENTATION)
META = DOC.read("VDI2770_Metadata.xml").decode()


def foldered(folder="AB393", metadata=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VDI2770_Main.xml", DOCN.read("VDI2770_Main.xml"))
        z.writestr("VDI2770_Main.pdf", DOCN.read("VDI2770_Main.pdf"))
        z.writestr(f"{folder}/VDI2770_Metadata.xml", metadata or META)
        z.writestr(f"{folder}/B.pdf", DOC.read("B.pdf"))
    return buf.getvalue()


def report(data):
    return check_bytes(data, "foldered.zip")


def test_a_folder_that_holds_metadata_is_not_nothing():
    """The verdict may not be clean. We did not look, and exit 0 says we did."""
    rep = report(foldered())
    assert not rep.clean, (
        "a documentation container whose documents were never checked came back clean: "
        + str(sorted(f.rule.id for f in rep.findings)))


def test_it_says_that_it_did_not_look():
    fired = {f.rule.id for f in report(foldered()).findings}
    # By name. "Some `about: tool` rule fired" is satisfied by `X5` — a bug
    # report about this tool — so renaming the rule to `X5` left all six tests in
    # this file green while the finding said something else entirely.
    assert "Z13" in fired, f"nothing in {sorted(fired)} says this tool declined to open them"
    assert "X5" not in fired, f"a rule crashed rather than reporting: {sorted(fired)}"


def test_z8_does_not_claim_there_are_none():
    fired = {f.rule.id for f in report(foldered()).findings}
    assert "Z8" not in fired, "it holds one, delivered as a folder"


def test_f2_does_not_accuse_a_file_it_never_checked_the_metadata_for():
    f2 = [f for f in report(foldered()).findings if f.rule.id == "F2"]
    assert not f2, (
        "these files are declared in the folder's own metadata, which this tool did "
        f"not open: {[f.where.member for f in f2]}")


def test_the_vendored_upstream_container_gets_the_same_treatment():
    from conftest import CORPUS
    rep = check_bytes((CORPUS / "missingdocuments" / "folders.zip").read_bytes(),
                      "folders.zip")
    fired = {f.rule.id for f in rep.findings}
    assert "Z8" not in fired, fired
    assert not [f for f in rep.findings if f.rule.id == "F2"], fired


def test_an_ordinary_documentation_container_is_untouched():
    """The container that delivers documents the way this tool reads them must
    not gain a finding from any of this."""
    rep = check_bytes(CLEAN_DOCUMENTATION.read_bytes(), "clean.zip")
    assert rep.count(Severity.ERROR) == 0, sorted(f.rule.id for f in rep.findings)


def test_a_dot_slash_prefix_is_not_a_folder():
    """`./VDI2770_Metadata.xml` **is** at the root. Some writers spell it that
    way and the file has not gone anywhere.

    Two other places in this release learned that: `Z9` skips a `.` segment
    because "counting it invented one and told the sender to move a file that
    had not gone anywhere", and the reader grew a `path-prefixed` near-miss kind
    for the same reason. This function got neither, so it reported `Z13` — an
    **error**, saying this tool did not look inside — about a document it had
    read, and suppressed `Z8` while it was at it.
    """
    body = b"<Document xmlns='http://www.vdi.de/schemas/vdi2770'/>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Main.xml", body)
        z.writestr("VDI2770_Main.pdf", b"%PDF-1.7\n")
        z.writestr("./VDI2770_Metadata.xml", body)
        z.writestr("./B.pdf", b"%PDF-1.7\n")

    fired = {f.rule.id for f in report(buf.getvalue()).findings}
    assert "Z13" not in fired, f"a root-level metadata file read as a folder: {sorted(fired)}"


def test_it_says_one_folder_in_english():
    """`1 folder hold VDI2770_Metadata.xml` — the plural was on the noun and not
    on the verb. A sentence a person reads is part of the finding."""
    fired = [f for f in report(foldered()).findings if f.rule.id == "Z13"]
    assert fired, "the fixture no longer produces Z13"
    detail = fired[0].detail or ""
    assert " hold " not in detail or not detail.startswith("1 "), detail


def test_a_dot_slash_folder_still_suppresses_the_files_inside_it():
    """Dropping `.` segments fixed the false `Z13` and broke the thing `Z13`
    exists to enable.

    `files.py` suppresses `F2` for members under a folder this tool did not open,
    by matching the archive's own name against the prefix this function returns.
    Normalising `./AB393/` to `AB393/` made that match nothing, so both files in
    the folder were reported as undeclared — accusing files inside a container
    the same report says was never opened.

    The decision uses the normalised path; the prefix has to stay the archive's
    spelling, which is also what the finding shows a user who has to find it in
    their ZIP listing.
    """
    body = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VDI2770_Main.xml",
                   b'<?xml version="1.0"?><Document xmlns="http://www.vdi.de/schemas/vdi2770"/>')
        z.writestr("VDI2770_Main.pdf", b"%PDF-1.7\n")
        for name in ("VDI2770_Metadata.xml", "B.pdf"):
            z.writestr(f"./AB393/{name}", body.read(name))

    fired = [f.rule.id for f in report(buf.getvalue()).findings]
    assert "Z13" in fired, fired
    assert "F2" not in fired, (
        "the files inside a folder this tool did not open were called undeclared: "
        + str(fired))


@pytest.mark.parametrize("meta_name,file_name", [
    ("docdir/VDI2770_Metadata.xml", "docdir/B.pdf"),
    ("./docdir/VDI2770_Metadata.xml", "docdir/B.pdf"),
    ("docdir/VDI2770_Metadata.xml", "./docdir/B.pdf"),
    ("./docdir/VDI2770_Metadata.xml", "./docdir/B.pdf"),
    ("docf//VDI2770_Metadata.xml", "docf/B.pdf"),
    ("docf/VDI2770_Metadata.xml", "docf//B.pdf"),
])
def test_a_folder_is_the_same_folder_however_its_members_are_spelled(meta_name, file_name):
    """`Z13` says this tool did not open the folder, so `files.py` suppresses
    `F2` for what is inside it — by matching the folder's prefix against the
    archive's member names. Writers mix `./` prefixes and doubled slashes freely
    within one archive, and a literal match on those spellings meant a file whose
    path differed from its own metadata's by a `.` was reported undeclared, in
    the same report that said the folder was never opened.

    Two rules contradicting each other about one file is the thing the whole
    `Z13`/`F2` arrangement exists to prevent.
    """
    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VDI2770_Main.xml",
                   b'<?xml version="1.0"?><Document xmlns="http://www.vdi.de/schemas/vdi2770"/>')
        z.writestr("VDI2770_Main.pdf", b"%PDF-1.7\n")
        z.writestr(meta_name, src.read("VDI2770_Metadata.xml"))
        z.writestr(file_name, src.read("B.pdf"))

    fired = [f.rule.id for f in report(buf.getvalue()).findings]
    assert "Z13" in fired, fired
    assert "F2" not in fired, (
        f"{file_name} sits in the folder {meta_name} names, and was called "
        f"undeclared: {fired}")
