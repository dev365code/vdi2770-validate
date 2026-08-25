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

from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION
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


# --- the same limit, one level up ------------------------------------------

MAIN = zipfile.ZipFile(CLEAN_DOCUMENTATION).read("VDI2770_Main.xml")


def _tree_of(n: int, elements: int) -> bytes:
    """A documentation container holding `n` document containers, each carrying
    metadata of `elements` elements."""
    meta = HEAD + b"<a/>" * elements + b"</Document>"
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VDI2770_Metadata.xml", meta)
    payload = inner.getvalue()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        out.writestr("VDI2770_Main.xml", MAIN)
        out.writestr("VDI2770_Main.pdf", b"%PDF-1.7\n")
        for i in range(n):
            out.writestr(f"d{i}.zip", payload)
    return buf.getvalue()


def test_one_read_cannot_parse_without_limit_across_the_tree():
    """`MAX_ELEMENTS` bounds one document. Nothing bounded the sum.

    A documentation container holding forty document containers, each with
    metadata just under the per-document cap, is **12 KiB** on disk and cost
    **74 seconds** of CPU — measured. Memory stays flat, because the trees are
    built and dropped one at a time, so every budget the reader has lets it
    through: the bytes are tiny, the members are few, nothing inflates.

    The cost is real work, done at the sender's invitation, and the reader's own
    first paragraph says an untrusted archive does not get to decide how much of
    it we do. This is the same defect as the one `MAX_ELEMENTS` closed, on the
    axis `MAX_ELEMENTS` does not see.
    """
    from vdi2770_validate.runner import MAX_TOTAL_ELEMENTS

    per = xmlread.MAX_ELEMENTS - 2
    spare = 6                                    # containers past the budget
    n = (MAX_TOTAL_ELEMENTS // per) + spare
    raw = _tree_of(n, per)
    assert len(raw) < 1_000_000, "the point is that the archive is small"

    # Counted, not timed. An earlier draft asserted `elapsed < 30` and flaked the
    # first time the machine was busy — the same mistake this project keeps
    # finding in its own gates. What the budget bounds is how many documents get
    # parsed, and that is a number.
    report = check_bytes(raw, "tree.zip")
    refused = [f for f in report.findings
               if f.rule.id == "X6" and "budget" in (f.detail or "")]
    assert len(refused) >= spare, (
        f"{n} containers, a budget of {MAX_TOTAL_ELEMENTS} elements and "
        f"{per} per document — at least {spare} should have gone unparsed, and "
        f"{len(refused)} say so")
    assert all(str(MAX_TOTAL_ELEMENTS) in (f.detail or "") for f in refused), (
        f"the finding does not say what the budget was: {refused[0].detail}")


def test_the_budget_is_generous_next_to_a_real_delivery():
    """A plant handover of nine hundred documents is a legitimate input, and its
    metadata is not `<a/>` repeated — the largest in this repository's corpus has
    53 elements. A limit that refuses a real delivery is its own defect."""
    from vdi2770_validate.runner import MAX_TOTAL_ELEMENTS

    assert MAX_TOTAL_ELEMENTS >= 900 * 500, MAX_TOTAL_ELEMENTS
