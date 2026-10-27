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
from vdi2770_validate.model import Severity
from vdi2770_validate.runner import check_file

from conftest import CORPUS, FIXTURES, ROOT, under_test

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
    ids. The documents are in the container. This tool did not open folders
    then, which is why `Z13` existed and why `Z13` is `about: tool`.

    So the first version of this rule reported two errors saying the delivery
    did not carry documents it was carrying, `about: container`, on a container
    whose only real problem was one this tool had already declined to look at.
    That is the exact failure this project keeps a whole severity axis to avoid:
    our refusal, billed to the sender.

    The rule now speaks only when every metadata file the archive lists was
    read. A set of known identifiers assembled from half a delivery cannot say
    anything is missing from it.

    The sample itself is read in full now -- its verdict is on
    `docs/official-samples.md` -- so the case is held on a copy of it that this
    tool cannot read in full: both folders' metadata streams damaged, the
    documents still listed.
    """
    from vdi2770_validate.runner import check_bytes

    from conftest import CORPUS, unopened

    data = (CORPUS / "missingdocuments" / "folders.zip").read_bytes()
    for folder in ("456-29201", "AB393"):
        data = unopened(data, f"{folder}/VDI2770_Metadata.xml")
    report = check_bytes(data, "folders.zip")
    found = {f.rule.id for f in report.sorted()}
    assert "Z13" in found, "the fixture for this case no longer trips Z13"
    assert report.read.metadata_read < report.read.metadata_found, (
        "this container is the case where metadata was left unread; if that "
        "changed, this test is no longer about anything")
    assert "M11" not in found and "M12" not in found, (
        "documents delivered as folders are in the container. Reporting them "
        "as undelivered bills this tool's refusal to the sender.")


def test_the_same_defect_from_a_document_that_is_not_the_main_one_is_also_an_error():
    """Two rules for two sentences, one severity — and the severity was wrong
    the first time.

    `Document.validateDocumentRelations` really does raise ERROR when the
    referring document is the main one and INFORMATION otherwise, and reading
    that method is where the first version of this rule got `M12` as a note.
    But that method is not the surface anybody validates a container through.
    `ContainerValidator.validateDocumentRelations` takes each directory's own
    metadata — `VDI2770_Main.xml`, or `VDI2770_Metadata.xml` where there is no
    main — and calls it with `isMainDocument` hard-coded `true`. The
    information branch never runs on a container at all.

    The differential sweep is what caught it: the reference reports `D_004` as
    an ERROR on the `M12` fixture, and we reported a note. A note is the
    expensive direction to be wrong in here — it passes a delivery they fail.
    """
    found = findings(FIXTURES / "m12-a-document-refers-to-one-not-delivered.zip")
    assert "M12" in found, sorted(found)
    assert found["M12"].rule.severity is Severity.ERROR, (
        "the container validator hard-codes isMainDocument, so every dangling "
        "reference it finds is an error")
    assert "M11" not in found, (
        "the referring document here is the nested container's own; the two "
        "rules differ in the sentence they print, not in the verdict")
    assert "not-delivered-77" in (found["M12"].detail or "")


def test_a_document_does_not_satisfy_its_own_reference(tmp_path):
    """`ContainerValidator` builds the known set from *other* documents: it
    removes the current one from the map before comparing. A document whose
    relationship names its own identifier is dangling to them, and was not to
    us — a latent divergence with nothing in the corpus to expose it, which is
    why it is built here.

    The clean container's main document is `XCP328490` and refers to
    `ts-ddd-234`. Point it at itself and the delivery still carries every id it
    names, so a set built over all documents finds nothing wrong.
    """
    import zipfile

    target = tmp_path / "self-reference.zip"
    with zipfile.ZipFile(CLEAN) as src, zipfile.ZipFile(target, "w") as out:
        for item in src.namelist():
            data = src.read(item)
            if item == "VDI2770_Main.xml":
                data = data.replace(b">ts-ddd-234<", b">XCP328490<")
            out.writestr(item, data)
    found = findings(target)
    assert "M11" in found, (
        "the main document's only relationship names itself, and no other "
        "document in the delivery declares that id")
    assert "XCP328490" in (found["M11"].detail or ""), found["M11"].detail


# The directory of an unopened archive cannot contribute metadata to the count.
ARCHIVE_PATHS = (
    "method", "member-read", "whole-read", "member-limit", "listing-budget",
    "depth", "container-budget", "byte-budget", "folder-depth",
    "folder-container-budget", "folder-byte-budget", "folder-size",
    "directory-read", "library-read", "member-size", "archive-size",
    "name-shape", "name-repeat", "ratio", "verification-budget",
)


def _delivery_bytes(entries, deflate=None):
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as out:
        for name, data in entries.items():
            out.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), data,
                         compress_type=zipfile.ZIP_DEFLATED if name == deflate else zipfile.ZIP_STORED)
    return buf.getvalue()


def _delivery_case(shape, references, contradiction, monkeypatch):
    """Generate one unopened path with two documents still available to read."""
    import io
    import re
    import struct
    import zipfile

    from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION, unopened
    from vdi2770 import zipread

    with zipfile.ZipFile(CLEAN_DOCUMENTATION) as src:
        main = {n: src.read(n) for n in src.namelist() if not n.lower().endswith(".zip")}
    with zipfile.ZipFile(CLEAN_DOCUMENT) as src:
        document = {n: src.read(n) for n in src.namelist()}

    def metadata(raw, identity, kind, refers):
        text = raw.decode("utf-8")
        text = re.sub(r"<DocumentRelationship\b.*?</DocumentRelationship>", "", text, flags=re.S)
        text = re.sub(r"<DocumentId\b[^>]*>[^<]*</DocumentId>",
                      f'<DocumentId DomainId="BSP-OEM">{identity}</DocumentId>', text, count=1)
        text = re.sub(r"<ObjectId\b[^>]*>[^<]*</ObjectId>",
                      f'<ObjectId ObjectType="{kind}">OBJECT</ObjectId>', text)
        if identity == "ROOT" and contradiction:
            at = text.index('<ObjectId ObjectType="Type">')
            text = text[:at] + text[at:].replace('ObjectType="Type"', 'ObjectType="Individual"', 1)
        if refers:
            relation = ('<DocumentRelationship Type="RefersTo">'
                        '<DocumentId DomainId="BSP-OEM">HELD</DocumentId>'
                        '</DocumentRelationship>')
            text = text.replace("<DigitalFile", relation + "<DigitalFile", 1)
        return text.encode("utf-8")

    main[zipread.MAIN_XML] = metadata(main[zipread.MAIN_XML], "ROOT", "Type", references)
    known = dict(document)
    known[zipread.METADATA_XML] = metadata(
        known[zipread.METADATA_XML], "KNOWN", "Individual" if contradiction else "Type", references)
    held = dict(document)
    held[zipread.METADATA_XML] = metadata(held[zipread.METADATA_XML], "HELD", "Type", False)
    known_bytes = _delivery_bytes(known)
    held_bytes = _delivery_bytes(held)
    entries = dict(main, **{"known.zip": known_bytes})
    if shape == "directory-read":
        held_bytes = b"not an archive"
    elif shape == "library-read":
        data = bytearray(held_bytes)
        with zipfile.ZipFile(io.BytesIO(data)) as src:
            struct.pack_into("<H", data, src.start_dir + 6, 99)
        held_bytes = bytes(data)
    elif shape == "whole-read":
        held_bytes = b"prefix" + held_bytes
    elif shape == "member-size":
        ceiling = max(map(len, [*main.values(), *known.values(), known_bytes])) + 1
        held["0.txt"] = b"x" * (ceiling + 1)
        held_bytes = _delivery_bytes(held)
        monkeypatch.setattr(zipread, "MAX_MEMBER_BYTES", ceiling)
    elif shape == "ratio":
        held["0.txt"] = b"x" * (9 * 1024 * 1024)
        held_bytes = _delivery_bytes(held)
        monkeypatch.setattr(zipread, "MAX_RATIO", 1)
    elif shape == "member-limit":
        held.update({f"{i}.txt": b"x" for i in range(12)})
        held_bytes = _delivery_bytes(held)
        monkeypatch.setattr(zipread, "MAX_MEMBERS", 10)
    elif shape == "listing-budget":
        monkeypatch.setattr(zipread, "MAX_TOTAL_MEMBERS", len(entries) + 1 + len(known))
    elif shape == "depth":
        held_bytes = _delivery_bytes({"held.zip": held_bytes})
        monkeypatch.setattr(zipread, "MAX_CONTAINER_LEVELS", 2)
    elif shape == "container-budget":
        monkeypatch.setattr(zipread, "MAX_CONTAINERS", 1)
    elif shape == "folder-depth":
        monkeypatch.setattr(zipread, "MAX_CONTAINER_LEVELS", 2)
    elif shape == "folder-container-budget":
        monkeypatch.setattr(zipread, "MAX_CONTAINERS", 1)
    elif shape == "folder-size":
        ceiling = max(map(len, [*main.values(), *known.values(), known_bytes])) + 1
        held.update({f"{i}.txt": b"x" * ceiling for i in range(2)})
        monkeypatch.setattr(zipread, "MAX_MEMBER_BYTES", ceiling)
    elif shape == "metadata-cap":
        widest = max(len(main[zipread.MAIN_XML]), len(known[zipread.METADATA_XML]))
        held[zipread.METADATA_XML] += b"<!--" + b" " * widest + b"-->"
        held_bytes = _delivery_bytes(held)
        monkeypatch.setattr(zipread, "MAX_METADATA_BYTES", len(held[zipread.METADATA_XML]) - 1)
    elif shape == "metadata-budget":
        monkeypatch.setattr(zipread, "MAX_TOTAL_METADATA_BYTES", len(main[zipread.MAIN_XML])
                            + len(known[zipread.METADATA_XML]) + len(held[zipread.METADATA_XML]) - 1)
    elif shape == "element-budget":
        from vdi2770 import xmlread
        from vdi2770_validate import runner

        monkeypatch.setattr(runner, "MAX_TOTAL_ELEMENTS",
                            xmlread._markup_charge(main[zipread.MAIN_XML])
                            + xmlread._markup_charge(known[zipread.METADATA_XML]))
    elif shape == "document-cap":
        import xml.etree.ElementTree as ET

        from vdi2770 import xmlread

        most = max(sum(1 for _ in ET.fromstring(raw).iter())
                   for raw in (main[zipread.MAIN_XML], known[zipread.METADATA_XML]))
        held[zipread.METADATA_XML] = held[zipread.METADATA_XML].replace(
            b"<DocumentId", b"<Pad/>" * most + b"<DocumentId", 1)
        held_bytes = _delivery_bytes(held)
        monkeypatch.setattr(xmlread, "MAX_ELEMENTS", most)
    elif shape == "parse-step":
        from vdi2770 import xmlread

        parse, unparsed = xmlread.parse, held[zipread.METADATA_XML]

        def parse_or_fail(raw, *args, **kwargs):
            if raw == unparsed:
                raise RuntimeError("the parse step failed")
            return parse(raw, *args, **kwargs)

        monkeypatch.setattr(xmlread, "parse", parse_or_fail)
    elif shape == "model-step":
        from vdi2770_validate import runner

        build = runner.build

        def build_or_fail(tree, where):
            if (where.container or "").endswith("held.zip"):
                raise RuntimeError("the model step failed")
            return build(tree, where)

        monkeypatch.setattr(runner, "build", build_or_fail)
    elif shape == "not-well-formed":
        held[zipread.METADATA_XML] = held[zipread.METADATA_XML][:-20]
        held_bytes = _delivery_bytes(held)
    elif shape.startswith("declared-bundle-"):
        # KNOWN declares P.zip, a parts bundle holding the HELD container, and
        # the depth limit keeps the bundle closed: at a limit one lower, or,
        # with no limit moved, as the fourth level under a collection.
        declaration = b'<DigitalFile FileFormat="application/zip">P.zip</DigitalFile>'
        known[zipread.METADATA_XML] = known[zipread.METADATA_XML].replace(
            b"</DocumentVersion>", declaration + b"</DocumentVersion>", 1)
        known["P.zip"] = _delivery_bytes({"held.zip": held_bytes})
        if shape == "declared-bundle-at-the-limit":
            entries["known.zip"] = _delivery_bytes(known)
            monkeypatch.setattr(zipread, "MAX_CONTAINER_LEVELS", 2)
        else:
            with zipfile.ZipFile(CLEAN_DOCUMENTATION) as src:
                collection = {n: src.read(n) for n in src.namelist() if not n.lower().endswith(".zip")}
            collection[zipread.MAIN_XML] = metadata(collection[zipread.MAIN_XML], "COLLECTION", "Type", False)
            del entries["known.zip"]
            entries["X.zip"] = _delivery_bytes({**collection, "known.zip": _delivery_bytes(known)})
    if shape == "folder-depth":
        entries["held.zip"] = _delivery_bytes({"held/" + n: value for n, value in held.items()})
    elif shape.startswith("folder-"):
        entries.update({"held/" + n: value for n, value in held.items()})
    elif shape.startswith("declared-bundle-"):
        pass
    elif shape == "declared-bundle":
        held_bytes = _delivery_bytes({"held.zip": held_bytes})
        entries["held.zip"] = held_bytes
        declaration = '<DigitalFile FileFormat="application/zip">held.zip</DigitalFile>'
        entries[zipread.MAIN_XML] = entries[zipread.MAIN_XML].replace(
            b"</DocumentVersion>", declaration.encode() + b"</DocumentVersion>", 1)
    else:
        entries["held.zip"] = held_bytes
    if shape == "archive-size":
        monkeypatch.setattr(zipread, "MAX_TOTAL_BYTES", sum(map(len, entries.values())) - 1)
    elif shape == "name-shape":
        entries["/held.zip"] = entries.pop("held.zip")
    elif shape == "verification-budget":
        monkeypatch.setattr(zipread, "MAX_TOTAL_DECOMPRESSED", sum(map(len, entries.values())) - 1)
    if shape in ("byte-budget", "folder-byte-budget"):
        second = (sum(map(len, held.values())) if shape.startswith("folder-") else len(held_bytes))
        ceiling = sum(map(len, entries.values())) + len(known_bytes) + sum(map(len, known.values())) + second - 1
        monkeypatch.setattr(zipread, "MAX_TOTAL_DECOMPRESSED", ceiling)
    raw = _delivery_bytes(entries, deflate="held.zip" if shape == "ratio" else None)
    if shape == "name-repeat":
        import warnings

        buf = io.BytesIO(raw)
        with warnings.catch_warnings(), zipfile.ZipFile(buf, "a") as out:
            warnings.simplefilter("ignore", UserWarning)
            out.writestr(zipfile.ZipInfo("held.zip", (1980, 1, 1, 0, 0, 0)), held_bytes)
        raw = buf.getvalue()
    if shape == "member-read":
        raw = unopened(raw, "held.zip")
    elif shape == "method":
        data = bytearray(raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as src:
            item = src.getinfo("held.zip")
            struct.pack_into("<H", data, item.header_offset + 8, 99)
            at = src.start_dir
            for info in src.infolist():
                if info.filename == item.filename:
                    struct.pack_into("<H", data, at + 10, 99)
                at += 46 + len(info.filename.encode()) + len(info.extra) + len(info.comment)
        raw = bytes(data)
    return raw


@pytest.mark.parametrize("shape", ARCHIVE_PATHS)
@pytest.mark.parametrize("references", [False, True])
@pytest.mark.parametrize("contradiction", [False, True])
def test_missing_documents_wait_for_every_archive(shape, references, contradiction, monkeypatch):
    """An unopened archive may hold the target; a known contradiction still holds."""
    import json

    from vdi2770_validate.report import as_json
    from vdi2770_validate.runner import check_bytes

    report = check_bytes(_delivery_case(shape, references, contradiction, monkeypatch), "0")
    read = json.loads(as_json(report))["read"]
    found = {f.rule.id for f in report.findings}
    assert report.read.archives_opened < report.read.archives_found
    assert not read["complete"]
    assert not found & {"M11", "M12"}
    assert ("M13" in found) is contradiction


# Every archive opened, and a document still unknown: its metadata refused by
# the reader before its bytes came, or read and not modelled for a reason that
# is this tool's -- its element budget, a document larger than it models, a
# step of its own that failed.
METADATA_PATHS = ("metadata-cap", "metadata-budget", "element-budget", "document-cap",
                  "parse-step", "model-step")


@pytest.mark.parametrize("shape", METADATA_PATHS)
@pytest.mark.parametrize("references", [False, True])
@pytest.mark.parametrize("contradiction", [False, True])
def test_missing_documents_wait_for_every_metadata_file_to_be_modelled(
        shape, references, contradiction, monkeypatch):
    """Metadata this tool did not read, or read and did not model, may declare the target."""
    import json

    from vdi2770_validate.report import as_json
    from vdi2770_validate.runner import check_bytes

    report = check_bytes(_delivery_case(shape, references, contradiction, monkeypatch), "0")
    read = json.loads(as_json(report))["read"]
    found = {f.rule.id for f in report.findings}
    assert report.read.archives_opened == report.read.archives_found
    assert (report.read.metadata_read < report.read.metadata_found) is shape.startswith("metadata-")
    assert not read["complete"]
    assert any(f.severity.value == "error" and f.about.value == "tool" for f in report.findings)
    assert not found & {"M11", "M12"}
    assert ("M13" in found) is contradiction


def test_a_document_whose_metadata_is_not_well_formed_is_one_nothing_declares(monkeypatch):
    """Read, and refused for its own sake: this tool read the whole delivery, and
    nothing in it declares the document that metadata would have."""
    from vdi2770_validate.runner import check_bytes

    report = check_bytes(_delivery_case("not-well-formed", True, False, monkeypatch), "0")
    found = {f.rule.id for f in report.findings}
    assert report.read.archives_opened == report.read.archives_found
    assert report.read.metadata_read == report.read.metadata_found
    assert "X1" in found
    assert {"M11", "M12"} <= found


@pytest.mark.parametrize("shape", ["declared-bundle-at-the-limit", "declared-bundle-past-the-depth-limit"])
@pytest.mark.parametrize("references", [False, True])
@pytest.mark.parametrize("contradiction", [False, True])
def test_missing_documents_do_not_wait_for_a_declared_file_left_closed(
        shape, references, contradiction, monkeypatch):
    """What a document declares as one of its files is its content, and nothing
    in it is searched for the documents a relationship names (`sealed`):
    opened, it does not answer a reference, and kept closed by the depth limit
    it is no reason to wait for one. The read still counts it, unopened, and
    `Z14` says so, as it does for one the walk reaches. The second shape moves
    no limit: a collection, its document, and the document's parts bundle."""
    from vdi2770_validate.runner import check_bytes

    report = check_bytes(_delivery_case(shape, references, contradiction, monkeypatch), "0")
    found = {f.rule.id for f in report.findings}
    assert report.read.archives_opened + 1 == report.read.archives_found
    assert ("M11" in found) is references and ("M12" in found) is references
    assert ("M13" in found) is contradiction
    said = [f.detail for f in report.findings if f.rule.id == "Z14"]
    assert len(said) == 1 and "was not opened" in said[0], said
    assert "Z6" not in found


def test_a_declared_bundle_does_not_contribute_its_contents_to_the_read(monkeypatch):
    """A payload's contents are outside the delivery's metadata search."""
    from vdi2770_validate.runner import check_bytes

    report = check_bytes(_delivery_case("declared-bundle", True, False, monkeypatch), "0")
    assert report.read.archives_opened == report.read.archives_found
    assert report.read.metadata_read == report.read.metadata_found
    assert {"M11", "M12"} <= {f.rule.id for f in report.findings}


def test_a_pdf_check_that_did_not_run_does_not_hide_known_missing_documents(monkeypatch):
    """The delivery guard needs archives and metadata, not every PDF check."""
    from vdi2770_validate import runner

    data = _delivery_case("declared-bundle", True, False, monkeypatch)

    def unavailable(*args, **kwargs):
        raise RuntimeError("PDF check unavailable")

    monkeypatch.setattr(runner.pdfread, "reader", lambda *args: unavailable)
    report = runner.check_bytes(data, "0")
    assert report.read.archives_opened == report.read.archives_found
    assert report.read.metadata_read == report.read.metadata_found
    assert {"M11", "M12", "X5"} <= {f.rule.id for f in report.findings}
