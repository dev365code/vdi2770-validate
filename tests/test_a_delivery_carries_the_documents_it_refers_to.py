"""A main document that points at documents the container does not carry.

`VDI2770_Main.xml` declares `DocumentRelationship` entries, each naming a
`DocumentId`. Nothing in this project read them — the whole element was
invisible to every rule — so a documentation container whose main document
refers to two documents and delivers neither came back with
`0 error(s)` and exit `0`. That is the shape an intake gate exists to stop: the
delivery names what it is supposed to contain and does not contain it.

The reference implementation calls it `D_004`, and it makes a distinction this
follows rather than invents. Read at the pinned commit this project's oracle
uses, `Document.validateDocumentRelations` raises

    isMainDocument ? FaultLevel.ERROR : FaultLevel.INFORMATION

— an error when the *main* document is the one pointing at nothing, and merely
informational when any other document is. Identity is `id + "@" + domainId`,
compared case-insensitively. Both halves of that are asserted below, because
`obligation: reference` is a promise that our judgement is theirs, and a rule
that turned their information into our error would be making a claim about
VDI 2770 that nobody here can support.
"""
import subprocess
import sys

import pytest

from conftest import CORPUS, FIXTURES, ROOT, under_test
from vdi2770_validate.model import Severity
from vdi2770_validate.runner import check_file

DANGLING = FIXTURES / "m11-refers-to-a-document-not-delivered.zip"
CLEAN = CORPUS / "container" / "documentationcontainer.zip"


def findings(path):
    return {f.rule.id: f for f in check_file(str(path)).sorted()}


def test_the_fixture_differs_from_its_clean_pair_in_one_id():
    """The pair, asserted rather than trusted: everything else about these two
    containers is the same, so anything this rule says is about the id."""
    import zipfile

    a = zipfile.ZipFile(CLEAN).read("VDI2770_Main.xml")
    b = zipfile.ZipFile(DANGLING).read("VDI2770_Main.xml")
    assert a != b
    assert a.replace(b"ts-ddd-234", b"ts-ddd-999") == b, (
        "the fixture no longer differs from the clean container in exactly the "
        "referenced id, so a finding here need not be about the reference")


def test_a_main_document_pointing_at_a_document_nobody_delivers_is_an_error():
    found = findings(DANGLING)
    assert "M11" in found, (
        f"the main document refers to a document the container does not carry "
        f"and nothing said so; findings were {sorted(found)}")
    assert found["M11"].rule.severity is Severity.ERROR


def test_that_delivery_no_longer_leaves_by_the_front_door():
    """The point of the rule, stated as the thing that changes. This container
    exited `0` under the default `--fail-on error`, which is what a CI intake
    gate reads."""
    done = subprocess.run([sys.executable, "-m", "vdi2770_validate", "check",
                           str(DANGLING)], cwd=ROOT, capture_output=True,
                          text=True, env=under_test())
    assert done.returncode == 1, done.stdout


def test_the_clean_container_says_nothing_about_relationships():
    """The other half of the pair. The clean container's main document refers to
    `ts-ddd-234` and the nested document container declares exactly that, so a
    rule that fired here would be reporting a delivery that is complete."""
    assert "M11" not in findings(CLEAN)
    assert "M12" not in findings(CLEAN)


def test_the_finding_names_the_id_that_could_not_be_found():
    """A reader has to know *which* reference dangles. The reference
    implementation interpolates the id into its message for the same reason."""
    detail = findings(DANGLING)["M11"].detail or ""
    assert "ts-ddd-999" in detail, detail


def test_the_domain_is_part_of_the_identity(tmp_path):
    """`documentIdAsText` is `id + "@" + domainId`, so the same number issued by
    two domains is two documents. A comparison on the bare id would accept a
    delivery that carries something else entirely under a coincidentally equal
    number and call it the document that was referred to.

    The first version of this test asserted that two functions could be
    imported, which is a statement about this file and not about the rule.
    """
    import zipfile

    target = tmp_path / "other-domain.zip"
    with zipfile.ZipFile(CLEAN) as src, zipfile.ZipFile(target, "w") as out:
        for item in src.namelist():
            data = src.read(item)
            if item == "VDI2770_Main.xml":
                # The same number, issued by somebody else. Everything the
                # delivery carries is unchanged.
                data = data.replace(b'<DocumentId DomainId="BSP-OEM">ts-ddd-234',
                                    b'<DocumentId DomainId="OTHER-OEM">ts-ddd-234')
            out.writestr(item, data)
    found = findings(target)
    assert "M11" in found, (
        "the reference names ts-ddd-234 in a domain nothing here issued, and "
        "the delivery was reported as carrying it")
    assert "OTHER-OEM" in (found["M11"].detail or ""), found["M11"].detail


@pytest.mark.parametrize("spelling", ["TS-DDD-234", "ts-DDD-234"])
def test_the_comparison_ignores_case(spelling, tmp_path):
    """`StringUtils.equalsIgnoreCase` at the pinned commit. A case-sensitive
    comparison would report a dangling reference for a delivery that carries the
    document, which is the more expensive direction to be wrong in: it fails a
    container nothing is wrong with."""
    import shutil
    import zipfile

    target = tmp_path / "cased.zip"
    with zipfile.ZipFile(CLEAN) as src, zipfile.ZipFile(target, "w") as out:
        for item in src.namelist():
            data = src.read(item)
            if item == "VDI2770_Main.xml":
                data = data.replace(b"ts-ddd-234", spelling.encode())
            out.writestr(item, data)
    assert "M11" not in findings(target), (
        f"{spelling!r} names the delivered document in another case and the "
        f"rule reported it missing")
    shutil.rmtree(tmp_path, ignore_errors=True)


def test_a_reference_is_not_dangling_when_this_tool_declined_to_read_the_delivery():
    """The corpus caught this and the fixture above could not have.

    `corpus/examples/missingdocuments/folders.zip` delivers its documents as
    *folders* — `456-29201/` and `AB393/`, each with its own
    `VDI2770_Metadata.xml` — and its main document refers to exactly those two
    ids. The documents are in the container. This tool does not open folders,
    which is why `Z13` exists and why `Z13` is `about: tool`.

    So the first version of this rule reported two errors saying the delivery
    did not carry documents it was carrying, `about: container`, on a container
    whose only real problem was one this tool had already declined to look at.
    That is the exact failure this project keeps a whole severity axis to avoid:
    our refusal, billed to the sender.

    The rule now speaks only when every metadata file the archive lists was
    read. A set of known identifiers assembled from half a delivery cannot say
    anything is missing from it.
    """
    from conftest import CORPUS

    folders = CORPUS / "missingdocuments" / "folders.zip"
    report = check_file(str(folders))
    found = {f.rule.id for f in report.sorted()}
    assert "Z13" in found, "the fixture for this case no longer trips Z13"
    assert report.read.metadata_read < report.read.metadata_found, (
        "this container is the case where metadata was left unread; if that "
        "changed, this test is no longer about anything")
    assert "M11" not in found and "M12" not in found, (
        "documents delivered as folders are in the container. Reporting them "
        "as undelivered bills this tool's refusal to the sender.")


def test_the_same_defect_from_a_document_that_is_not_the_main_one_is_a_note():
    """The asymmetry, which is the whole reason there are two rules.

    `Document.validateDocumentRelations` raises ERROR when the referring
    document is the main one and INFORMATION otherwise, and `obligation:
    reference` says our judgement is theirs. A single rule at one severity would
    either invent an error they do not raise, or lose the one they do.
    """
    found = findings(FIXTURES / "m12-a-document-refers-to-one-not-delivered.zip")
    assert "M12" in found, sorted(found)
    assert found["M12"].rule.severity is Severity.INFO
    assert "M11" not in found, (
        "the referring document here is the nested container's own, not the "
        "main document; raising M11 would report their information as our error")
    assert "not-delivered-77" in (found["M12"].detail or "")
