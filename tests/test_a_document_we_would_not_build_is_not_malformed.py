"""A document this tool refused to model is not a document that is broken.

Bounding the XML tree closed a hole worth 952 MB from a 115 KB archive. It also
handed the same archive a verdict that was false in the other direction: the
metadata is perfectly well-formed XML, and the report said *"The metadata file
is not well-formed XML"* — because `schema.py` mapped every `XmlError` that was
not an `UnsafeXml` onto `X1`.

`X1` is a statement about the sender's file. This is a statement about our
limit, and the project keeps those apart everywhere else.
"""
import io
import zipfile

from conftest import CLEAN_DOCUMENT
from vdi2770 import xmlread
from vdi2770_validate.catalog import rules
from vdi2770_validate.model import About
from vdi2770_validate.runner import check_bytes

HEAD = b'<?xml version="1.0"?><Document xmlns="http://www.vdi.de/schemas/vdi2770">'


def _with_metadata(meta: bytes) -> bytes:
    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for name in src.namelist():
            out.writestr(name, meta if name.endswith("VDI2770_Metadata.xml") else src.read(name))
    return buf.getvalue()


def _wide() -> bytes:
    return _with_metadata(HEAD + b"<a/>" * (xmlread.MAX_ELEMENTS + 2) + b"</Document>")


def test_it_does_not_call_a_well_formed_document_malformed():
    fired = {f.rule.id: f for f in check_bytes(_wide(), "wide.zip").findings}
    assert "X1" not in fired, (
        "the metadata is well-formed XML and the report says it is not: "
        + (fired["X1"].detail or ""))
    assert "X6" in fired, sorted(fired)


def test_the_finding_is_about_this_tool_not_the_container():
    fired = {f.rule.id: f for f in check_bytes(_wide(), "wide.zip").findings}
    assert fired["X6"].about is About.TOOL
    assert rules()["X6"].about is About.TOOL
    assert "not necessarily wrong" in fired["X6"].remedy.lower() or \
           "belongs to this tool" in fired["X6"].remedy.lower(), fired["X6"].remedy


def test_it_says_which_limit_and_where():
    only = [f for f in check_bytes(_wide(), "wide.zip").findings if f.rule.id == "X6"]
    assert len(only) == 1
    assert str(xmlread.MAX_ELEMENTS) in (only[0].detail or ""), only[0].detail
    assert only[0].where.member == "VDI2770_Metadata.xml", only[0].where
    assert only[0].where.line, "a refusal with no line is a refusal you cannot look at"


def test_a_run_that_modelled_nothing_does_not_exit_zero():
    from vdi2770_validate.model import Severity

    report = check_bytes(_wide(), "wide.zip")
    assert report.count(Severity.ERROR), (
        "nothing downstream of the metadata was checked; a clean exit would say it was")
