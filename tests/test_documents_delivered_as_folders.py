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
