"""`./VDI2770_Main.pdf` is at the root, and three rules did not think so.

The reader records a `path-prefixed` near-miss for exactly this, and its comment
says why: *"`./name` is at the root ... Reporting it as a subfolder made the
caller tell a sender to move a file that had not gone anywhere."* `Members`,
`folder_path`, `Z9`, `Z3` and `Z13` all agree. Three places compared the raw
string instead, and each one got a different wrong answer out of it.
"""
import io
import re
import zipfile

from conftest import CLEAN_DOCUMENTATION
from vdi2770_validate.runner import check_bytes

JUNK = b"not a pdf at all\n\n"


def documentation(main_pdf_named, body, declared=True):
    """The clean documentation container with its main document stored elsewhere."""
    src = zipfile.ZipFile(CLEAN_DOCUMENTATION)
    main = src.read("VDI2770_Main.xml").decode("utf-8")
    if not declared:
        line = re.search(r"\s*<DigitalFile[^>]*>VDI2770_Main\.pdf</DigitalFile>", main)
        assert line, "the fixture no longer declares its own main document"
        main = main.replace(line.group(0), "")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in src.namelist():
            if name == "VDI2770_Main.pdf":
                z.writestr(main_pdf_named, body)
            elif name == "VDI2770_Main.xml":
                z.writestr(name, main.encode("utf-8"))
            else:
                z.writestr(name, src.read(name))
    return buf.getvalue()


def fired(data):
    return {f.rule.id for f in check_bytes(data, "dotmain.zip").findings}


def test_the_main_document_at_the_root_is_not_reported_missing():
    """`Z7` compared `MAIN_PDF not in container.present` — the raw string.

    So a documentation container storing its main document as
    `./VDI2770_Main.pdf` was told to *add the main document as VDI2770_Main.pdf
    at the root*, in a report that on the next line printed the PDF/A claim it
    had read out of that very file.
    """
    real = zipfile.ZipFile(CLEAN_DOCUMENTATION).read("VDI2770_Main.pdf")
    assert "Z7" not in fired(documentation("VDI2770_Main.pdf", real)), "premise"
    assert "Z7" not in fired(documentation("./VDI2770_Main.pdf", real)), (
        "the main document is at the root and was reported missing")


def test_the_main_document_at_the_root_is_still_looked_at():
    """`_targets` asked the same question the same way, and its own docstring
    says what that costs: *"an undeclared one used to be scanned by nobody, so an
    eighteen-byte text file passed with exit 0"*. Undeclared and spelled `./`, it
    was nobody's again."""
    assert "P1" in fired(documentation("VDI2770_Main.pdf", JUNK, declared=False)), "premise"
    assert "P1" in fired(documentation("./VDI2770_Main.pdf", JUNK, declared=False)), (
        "a file that should be a PDF was never checked for being one")


def test_the_main_document_at_the_root_is_not_called_undeclared():
    """`structural` is the set of names reserved where they are reserved, and it
    held the raw spellings — so the reserved name, spelled `./`, was reported as
    a file nobody declared."""
    assert "F2" not in fired(documentation("./VDI2770_Main.pdf", JUNK, declared=False)), (
        "a reserved name was called undeclared because of the `./` in front of it")


def test_a_main_document_that_differs_only_in_case_is_said_so():
    """The reader records near-misses for all three reserved names; `Z3` read
    them and `Z7` did not.

    A documentation container holding `vdi2770_main.pdf` was told to *add the
    main document as VDI2770_Main.pdf at the root* — which on the supplier's own
    machine is not an action they can take, because the file already answers to
    that name. The reader knew; nothing in the report said it.
    """
    src = zipfile.ZipFile(CLEAN_DOCUMENTATION)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in src.namelist():
            z.writestr("vdi2770_main.pdf" if name == "VDI2770_Main.pdf" else name,
                       src.read(name))
    report = check_bytes(buf.getvalue(), "lc.zip")
    z7 = [f for f in report.findings if f.rule.id == "Z7"]
    assert z7, [f.rule.id for f in report.findings]
    assert "vdi2770_main.pdf" in (z7[0].detail or ""), (
        f"the near-miss the reader recorded is not in the report: {z7[0].detail}")


def _handover(*entries):
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, body in entries:
            z.writestr(name, body)
    return buf.getvalue()


def _document_container():
    import io
    import zipfile

    from conftest import CLEAN_DOCUMENT

    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in src.namelist():
            z.writestr(name, src.read(name))
    return buf.getvalue()


def test_a_near_miss_names_a_member_the_listing_holds():
    """The detail named a basename, and the listing has no such entry.

    `_classify` recorded `n.rsplit("/", 1)[-1]` for the case branch, so an
    archive holding `sub/vdi2770_main.pdf` was told `found as
    'vdi2770_main.pdf'` — a name nothing in it is called. And the diagnosis was
    half of one: fix only the case, as the sentence says, and the next run says
    the file must sit at the root.
    """
    src = zipfile.ZipFile(CLEAN_DOCUMENTATION)
    data = _handover(("VDI2770_Main.xml", src.read("VDI2770_Main.xml")),
                     ("sub/vdi2770_main.pdf", src.read("VDI2770_Main.pdf")),
                     ("doc.zip", _document_container()))
    z7 = [f for f in check_bytes(data, "near.zip").findings if f.rule.id == "Z7"]
    assert z7, "premise"
    said = z7[0].detail or ""
    assert "sub/vdi2770_main.pdf" in said, said
    assert "case" in said and "root" in said, (
        f"the sentence names half the difference: {said}")


def test_a_refused_name_is_not_reported_as_merely_misplaced():
    """`Z4` says the name was refused outright; `Z7` said it was *found at* a
    place and just needs moving.

    `folders_holding_metadata` learned this — a `../` member is not a folder
    somebody delivered — and the near-miss table did not. The tool never read
    those bytes, and `..` is not a subfolder.
    """
    src = zipfile.ZipFile(CLEAN_DOCUMENTATION)
    data = _handover(("VDI2770_Main.xml", src.read("VDI2770_Main.xml")),
                     ("../VDI2770_Main.pdf", src.read("VDI2770_Main.pdf")),
                     ("doc.zip", _document_container()))
    report = check_bytes(data, "escape.zip")
    fired = {f.rule.id for f in report.findings}
    assert "Z4" in fired, sorted(fired)
    z7 = [f for f in report.findings if f.rule.id == "Z7"]
    assert z7, "premise"
    assert "found at" not in (z7[0].detail or ""), z7[0].detail
