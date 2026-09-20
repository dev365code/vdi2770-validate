"""The same object identifier cannot be a type in one document and an
individual in another.

`ObjectId` carries an `ObjectType` saying which it is: `Type` names a product
model, `Individual` names the one machine on the floor with that serial. A
delivery that says `ABC1223` is both has contradicted itself, and a recipient's
system has to pick one -- there is no reading under which both are true.

The corpus has held that contradiction since the sweep began, in
`objectreferences.zip`, and nothing here could see it: `ObjectId` was in the
schema and nowhere in the model, so no rule could ask.

This is not the broad question. Whether a documentation container must share an
object with the documents it bundles is a question about what the guideline
requires, and the guideline is paid and unread here -- a plant-level bundle
carrying sub-component documents may differ legitimately. That rule is not
written, on purpose.
"""
import io
import zipfile

from vdi2770_validate.runner import check_file

from conftest import CLEAN_DOCUMENTATION, ROOT

DOCN = zipfile.ZipFile(CLEAN_DOCUMENTATION)
MAINXML = DOCN.read("VDI2770_Main.xml").decode()
MAINPDF = DOCN.read("VDI2770_Main.pdf")


def ids(path):
    return {f.rule.id for f in check_file(path).findings}


def detail_of(path, rule_id):
    return " ".join(f.detail or "" for f in check_file(path).findings
                    if f.rule.id == rule_id)


def test_the_corpus_container_that_says_both_is_told_so():
    """The real delivery, not a fixture shaped like it.

    `objectreferences.zip` declares `ABC1223` as a `Type` in `456-29201.zip`
    and as an `Individual` in `AB393.zip`. Both are in the same handover.
    """
    p = ROOT / "corpus" / "examples" / "container" / "objectreferences.zip"
    assert p.exists(), "the corpus container this rule is about is missing"
    assert "M13" in ids(str(p)), (
        f"a delivery calling one identifier both a type and an individual drew "
        f"nothing: {sorted(ids(str(p)))}")
    said = detail_of(str(p), "M13")
    assert "ABC1223" in said, f"the finding does not name the identifier: {said!r}"
    assert "Type" in said and "Individual" in said, (
        f"the finding does not say which two kinds were claimed: {said!r}")


def test_one_identifier_used_one_way_throughout_is_not_a_contradiction(tmp_path):
    """The precision pin. An identifier repeated across documents is ordinary
    -- it is how a delivery says these documents are about the same thing."""
    p = _delivery(tmp_path, "agree.zip",
                  [("Type", "ABC1223"), ("Type", "ABC1223")])
    assert "M13" not in ids(p), "the same kind twice was read as a disagreement"


def test_two_identifiers_that_merely_differ_are_not_a_contradiction(tmp_path):
    """Different identifiers may of course be different kinds."""
    p = _delivery(tmp_path, "distinct.zip",
                  [("Type", "ABC1223"), ("Individual", "XYZ999")])
    assert "M13" not in ids(p), "two different identifiers were compared to each other"


def test_the_contradiction_is_reported_without_reading_the_whole_delivery(tmp_path):
    """The guard the sibling rules in this layer need, and this one does not.

    `M11`/`M12` say nothing when a read was incomplete, because "no document
    declares this" cannot be established from half a delivery. A contradiction
    is the other shape: two declarations that disagree are a fact about what was
    actually read, and staying silent about it would be the tool hiding
    something it had already seen.
    """
    p = _delivery(tmp_path, "partial.zip",
                  [("Type", "ABC1223"), ("Individual", "ABC1223")],
                  unreadable=True)
    assert "M13" in ids(p), (
        "the contradiction was already in hand and went unreported because some "
        "other part of the delivery could not be read")


def _delivery(tmp_path, name, objects, unreadable=False):
    """A documentation container holding one document container per object."""
    inner = []
    for i, (object_type, object_id) in enumerate(objects):
        meta = MAINXML.replace("VDI2770_Main.pdf", "B.pdf")
        meta = _with_object(meta, object_type, object_id)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("VDI2770_Metadata.xml", meta)
            z.writestr("B.pdf", MAINPDF)
        inner.append((f"doc{i}.zip", buf.getvalue()))

    entries = [("VDI2770_Main.xml", MAINXML), ("VDI2770_Main.pdf", MAINPDF)] + inner
    if unreadable:
        entries.append(("broken.zip", b"not a zip at all"))
    p = tmp_path / name
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in entries:
            z.writestr(n, d)
    p.write_bytes(buf.getvalue())
    return str(p)


def _with_object(metadata_xml, object_type, object_id):
    """Replace the container's ReferencedObject ids with one of our own."""
    import re
    return re.sub(
        r"<ObjectId[^>]*>[^<]*</ObjectId>",
        f'<ObjectId ObjectType="{object_type}">{object_id}</ObjectId>',
        metadata_xml, count=1)
