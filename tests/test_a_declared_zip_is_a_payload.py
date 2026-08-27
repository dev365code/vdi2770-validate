"""A `.zip` the metadata declares as a file is a file, not a container.

The reader opens every member ending in `.zip` and classifies it, because the
reader has no metadata and cannot know better. The rules do have the metadata,
and until now they did not use it: a parts list attached as `teileliste.zip`
earned `Z3` -- "neither a document container nor a documentation container" --
which it had never claimed to be. Our own `F3` remedy blesses `application/zip`
with `.zip` in the same breath.

`Z11` is suppressed for the same reason and by its own argument: it exists
because an undeclared container is "a way to carry something past a check that
only looks at declared files". A declared one is not past that check.
"""
import io
import zipfile

from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION
from vdi2770_validate.runner import check_file

DOC = zipfile.ZipFile(CLEAN_DOCUMENT)
DOCN = zipfile.ZipFile(CLEAN_DOCUMENTATION)
META = DOC.read("VDI2770_Metadata.xml").decode()
MAINXML = DOCN.read("VDI2770_Main.xml").decode()
MAINPDF = DOCN.read("VDI2770_Main.pdf")
DOC_BYTES = CLEAN_DOCUMENT.read_bytes()

PAYLOAD = io.BytesIO()
with zipfile.ZipFile(PAYLOAD, "w") as _z:
    _z.writestr("teileliste.csv", b"pos;bezeichnung\n1;Motor\n")
PAYLOAD = PAYLOAD.getvalue()

DECL_MAIN = '<DigitalFile FileFormat="application/pdf">VDI2770_Main.pdf</DigitalFile>'
DECL_PDF = '<DigitalFile FileFormat="application/pdf">B.pdf</DigitalFile>'


def build(tmp_path, name, entries):
    p = tmp_path / name
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in entries:
            z.writestr(n, d)
    p.write_bytes(buf.getvalue())
    return str(p)


def fired(path):
    return {(f.rule.id, f.where.member) for f in check_file(path).findings}


def ids(path):
    return {f.rule.id for f in check_file(path).findings}


def test_a_declared_zip_in_a_documentation_container_is_not_judged_as_one(tmp_path):
    mm = MAINXML.replace(
        DECL_MAIN,
        DECL_MAIN + '\n        <DigitalFile FileFormat="application/zip">teileliste.zip</DigitalFile>')
    p = build(tmp_path, "declared_docn.zip", [
        ("VDI2770_Main.xml", mm), ("VDI2770_Main.pdf", MAINPDF),
        ("documentcontainer.zip", DOC_BYTES), ("teileliste.zip", PAYLOAD)])
    assert "Z3" not in ids(p), f"a declared parts list was called a broken container: {ids(p)}"


def test_a_declared_zip_in_a_document_container_is_not_smuggling(tmp_path):
    m = META.replace(
        DECL_PDF,
        DECL_PDF + '\n        <DigitalFile FileFormat="application/zip">anhang.zip</DigitalFile>')
    p = build(tmp_path, "declared_doc.zip", [
        ("VDI2770_Metadata.xml", m), ("B.pdf", DOC.read("B.pdf")),
        ("B.docx", DOC.read("B.docx")), ("anhang.zip", PAYLOAD)])
    assert not ids(p) & {"Z3", "Z11"}, f"a declared attachment was flagged: {ids(p)}"


def test_an_undeclared_container_inside_a_document_container_still_fires(tmp_path):
    """Z11's whole argument is about what is *not* declared. That case must stay."""
    p = build(tmp_path, "smuggled.zip", [
        ("VDI2770_Metadata.xml", META), ("B.pdf", DOC.read("B.pdf")),
        ("B.docx", DOC.read("B.docx")), ("smuggled.zip", PAYLOAD)])
    assert ("Z11", "smuggled.zip") in fired(p), f"{fired(p)}"


def test_an_undeclared_non_container_in_a_documentation_container_still_fires(tmp_path):
    """An inner zip nobody declared is structural, and a documentation container's
    structural zips are supposed to be document containers."""
    p = build(tmp_path, "junk_inside.zip", [
        ("VDI2770_Main.xml", MAINXML), ("VDI2770_Main.pdf", MAINPDF),
        ("documentcontainer.zip", DOC_BYTES), ("junk.zip", PAYLOAD)])
    # `or "Z3" in ids(p)` used to sit here and swallowed the whole assertion.
    assert ("Z3", None) in fired(p), f"{sorted(fired(p))}"


def test_a_declared_payload_that_is_a_real_container_is_still_validated(tmp_path):
    """Suppressing "this is not a container" must not suppress everything else.
    If a declared payload turns out to be a document container with a bad class
    id, saying so is useful and we should keep saying it."""
    bad = META.replace("<ClassId>02-01</ClassId>", "<ClassId>99-99</ClassId>")
    assert bad != META, "the fixture no longer has the ClassId this test edits"
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("VDI2770_Metadata.xml", bad)
        z.writestr("B.pdf", DOC.read("B.pdf"))
        z.writestr("B.docx", DOC.read("B.docx"))
    mm = MAINXML.replace(
        DECL_MAIN,
        DECL_MAIN + '\n        <DigitalFile FileFormat="application/zip">sub.zip</DigitalFile>')
    p = build(tmp_path, "declared_real.zip", [
        ("VDI2770_Main.xml", mm), ("VDI2770_Main.pdf", MAINPDF),
        ("documentcontainer.zip", DOC_BYTES), ("sub.zip", inner.getvalue())])
    assert "M2" in ids(p), f"the declared payload was skipped entirely: {ids(p)}"
    assert "Z3" not in ids(p)



def _payload_container(tmp_path, name, inner):
    """A document container declaring `cad.zip`, whose payload holds `inner`."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, d in inner.items():
            z.writestr(n, d)
    meta = META.replace(
        DECL_PDF, DECL_PDF + '<DigitalFile FileFormat="application/zip">cad.zip</DigitalFile>')
    return build(tmp_path, name, [
        ("VDI2770_Metadata.xml", meta), ("B.pdf", DOC.read("B.pdf")),
        ("cad.zip", buf.getvalue())])


def test_a_declared_payload_is_not_judged_on_how_it_arranges_itself(tmp_path):
    """A CAD bundle keeps its own folders, and an empty one is not "the archive
    is empty".

    A `.zip` the metadata declares as a `DigitalFile` is one of the document's
    *files*. Its inside is its own business, exactly as a PDF's is. `Z3` and
    `Z11` already know this; `Z9` and `Z2` did not, so a conforming delivery
    carrying `cad.zip` with `cad/part.step` in it drew *"The archive stores
    files in folders -- store the members at the root of the archive"*.
    Following that flattens a parts bundle and breaks the delivery; not
    following it leaves a warning that never clears.
    """
    for name, inner in (("folders.zip", {"cad/part.step": b"ISO-10303-21;"}),
                        ("empty.zip", {})):
        got = ids(_payload_container(tmp_path, name, inner))
        assert "Z9" not in got, (name, got)
        assert "Z2" not in got, (name, got)


def test_a_payload_that_is_unsafe_is_still_reported(tmp_path):
    """The other half. Suppressing what a payload says about *structure* must
    not suppress what it says about *bytes*: a member that cannot be handed
    over safely is a delivery risk whatever the metadata calls the archive."""
    got = ids(_payload_container(tmp_path, "unsafe.zip", {"../escape.txt": b"x"}))
    assert "Z4" in got, got


def test_a_document_container_we_could_not_model_does_not_draw_z11(tmp_path):
    """`declared` is `None` when this container's own metadata went unmodelled.

    `Z11` reads it with `nfc(m.name) not in declared`, which on `None` is a
    `TypeError` — so the guard above it is load-bearing, and nothing exercised
    it: replacing it with `if False:` left the whole suite green, which proves
    no test built a document container that holds a `.zip` *and* whose metadata
    the reader declined to model.

    "We did not model this" is not "you declared nothing", and a crash in a rule
    is not a verdict either. The report should carry the tool's own explanation
    and no accusation about the member.
    """
    from vdi2770_validate.runner import MAX_TOTAL_ELEMENTS

    head = (b'<?xml version="1.0"?>'
            b'<Document xmlns="http://www.vdi.de/schemas/vdi2770">')
    bomb = head + b"<a>" * (MAX_TOTAL_ELEMENTS + 20_000) + b"</Document>"
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as z:
        z.writestr("cad/part.step", b"ISO-10303-21;")

    path = build(tmp_path, "unmodelled.zip", [
        ("VDI2770_Metadata.xml", bomb),
        ("B.pdf", DOC.read("B.pdf")),
        ("inner.zip", payload.getvalue()),
    ])
    got = ids(path)
    assert "X6" in got, f"the premise: the metadata was not modelled — {got}"
    assert "Z11" not in got, (
        f"Z11 accused a member while the tool was saying it had not read the "
        f"metadata that would declare it: {got}")
    assert "X5" not in got, f"a rule crashed instead of standing aside: {got}"


def test_metadata_the_reader_would_not_hand_over_declares_nothing_known():
    """The other door into the same room, and the guard was on this side of it.

    `modelled` was cleared when a parse we attempted came back with nothing. When
    the *reader* refuses the metadata member -- a bad CRC, over the metadata
    budget, out of container budget -- there are no bytes to attempt, the flag
    stayed true, and `declared` was an empty `frozenset`: *this container
    declares no files*, asserted about a file nobody read.

    A conforming document container declaring an `inner.zip` payload, with forty
    bytes of its metadata member corrupted, then said:

        Z11  A document container carries another container inside it
        Z12  A file in the container could not be read
        Z3   The archive is neither a document container nor a documentation …
        Z9   The archive stores files in folders

    `Z12` is the true one. The other three are about a payload that *is*
    declared, derived from an emptiness the same report says came from not
    looking. The condition is about the kind, not about the bytes: a container
    whose kind names a metadata member and does not have it is a container
    nobody modelled, however it came to be that way.
    """
    import io
    import re
    import zipfile

    from conftest import CLEAN_DOCUMENT
    from vdi2770_validate.runner import check_bytes

    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    meta = src.read("VDI2770_Metadata.xml").decode("utf-8")
    one = re.search(r"(\s*)<DigitalFile[^>]*>[^<]*</DigitalFile>", meta)
    assert one, "the fixture no longer declares a file"
    meta = meta.replace(one.group(0), one.group(0) + one.group(1)
                        + '<DigitalFile FileFormat="application/zip">inner.zip</DigitalFile>', 1)
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as z:
        z.writestr("cad/part.stp", b"ISO-10303-21;\n")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in src.namelist():
            z.writestr(name, meta.encode() if name == "VDI2770_Metadata.xml"
                       else src.read(name))
        z.writestr("inner.zip", payload.getvalue())
    healthy = buf.getvalue()
    assert not [f.rule.id for f in check_bytes(healthy, "ok.zip").findings
                if f.rule.id in ("Z11", "Z3", "Z9")], "premise: this container is fine"

    # The member's stored bytes, corrupted where the CRC notices and the central
    # directory does not: the reader hands back a defect instead of data.
    raw = bytearray(healthy)
    at = raw.find(meta.encode()[:40])
    assert at != -1, "the metadata member is not stored the way this test assumes"
    raw[at:at + 40] = b"@" * 40

    fired = {f.rule.id for f in check_bytes(bytes(raw), "unreadable-metadata.zip").findings}
    assert "Z12" in fired, f"the reader's refusal is not reported at all: {sorted(fired)}"
    anyway = fired & {"Z11", "Z3", "Z9", "Z2"}
    assert not anyway, (
        "rules judged the shape of a container whose metadata was never read: "
        f"{sorted(anyway)}")


def test_an_undeclared_payload_is_told_once_and_told_what_to_do():
    """Two errors about one member, and the two remedies pointed apart.

    `Z11` said *a document container carries another container inside it* and to
    move it up into the documentation container. `Z3`, on the same member,
    said the archive is neither kind of container and to put a
    `VDI2770_Metadata.xml` at its root. Follow the first and the second still
    fires where you moved it; follow the second and the first still fires. The
    answer this tool actually accepts — declare it as a `DigitalFile` with
    `FileFormat` `application/zip` — was offered by neither, and it is the one
    that makes the whole report clean.

    `Z3` is the same fact said from the other side. It is `Z11`'s to report.
    """
    import io
    import zipfile

    from conftest import CLEAN_DOCUMENT
    from vdi2770_validate.runner import check_bytes

    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("drawing.dwg", b"AC1027\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in src.namelist():
            z.writestr(name, src.read(name))
        z.writestr("cad.zip", inner.getvalue())

    report = check_bytes(buf.getvalue(), "payload.zip")
    about = [f for f in report.findings if (f.where.member or "").endswith("cad.zip")
             or (f.where.container or "").endswith("cad.zip")]
    ids = {f.rule.id for f in about}
    assert "Z11" in ids, f"nothing reported the undeclared inner container: {sorted(ids)}"
    assert "Z3" not in ids, (
        "the member is reported twice, with remedies that point apart")
    z11 = next(f for f in about if f.rule.id == "Z11")
    assert "application/zip" in (z11.remedy or ""), (
        f"the remedy does not offer the answer this tool accepts: {z11.remedy}")


def test_z13_does_not_look_inside_a_declared_payload():
    """`Z13` was lifted out of the documentation branch and past the guard.

    The decision that keeps `Z2`, `Z3` and `Z9` quiet about a declared
    `application/zip` member says what it is for: *what is inside it is its own
    business, the way a PDF's is*. `Z13` sat above that guard, so a conforming
    document container carrying a declared CAD bundle became exit 1 and its
    supplier was told to restructure the inside of a parts bundle that is not a
    VDI 2770 artefact at all.
    """
    import io
    import re
    import zipfile

    from conftest import CLEAN_DOCUMENT
    from vdi2770_validate.runner import check_bytes

    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    meta = src.read("VDI2770_Metadata.xml").decode("utf-8")
    one = re.search(r"(\s*)<DigitalFile[^>]*>B\.pdf</DigitalFile>", meta)
    assert one, "the fixture no longer declares B.pdf"
    meta = meta.replace(one.group(0), one.group(0) + one.group(1)
                        + '<DigitalFile FileFormat="application/zip">cad.zip</DigitalFile>', 1)

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as z:
        z.writestr("partA/VDI2770_Metadata.xml", b"not vdi metadata")
        z.writestr("partA/model.step", b"ISO-10303-21;\n")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in src.namelist():
            z.writestr(name, meta.encode("utf-8") if name == "VDI2770_Metadata.xml"
                       else src.read(name))
        z.writestr("cad.zip", payload.getvalue())

    report = check_bytes(buf.getvalue(), "payload.zip")
    fired = {f.rule.id for f in report.findings}
    assert "Z13" not in fired, (
        f"a declared payload's insides were judged as a delivery: {sorted(fired)}")
    assert report.clean, [f"{f.rule.id}: {f.message}" for f in report.findings
                          if f.severity.value == "error"]
