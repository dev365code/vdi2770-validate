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
        # A *folder*, not a broken archive. An unopenable nested zip contributes
        # nothing to either side of the read count -- it is invisible to the
        # completeness question -- so a fixture built that way reports a
        # complete read and pins nothing. A metadata file delivered in a folder
        # is listed and never opened (`Z13`), which is what actually makes
        # `read_everything` false. Measured: 3 of 4 metadata files read.
        entries.append(("sub/VDI2770_Metadata.xml", MAINXML))
        entries.append(("sub/B.pdf", MAINPDF))
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
    # Every one of them, not the first. The clean container declares two
    # objects -- a product type and a serial number -- and replacing one left
    # the other in every document, so the fixtures carried four declarations
    # where their own docstring said two and the pins were partly pinned by the
    # leftover rather than by the identifier under test.
    return re.sub(
        r"<ObjectId[^>]*>[^<]*</ObjectId>",
        f'<ObjectId ObjectType="{object_type}">{object_id}</ObjectId>',
        metadata_xml)


def test_two_registers_that_happen_to_agree_are_not_one_thing(tmp_path):
    """The false positive this rule was one line away from.

    An article number and a serial number are different registers. This corpus
    already pairs them inside a single document -- `Individual/serial number/
    U1-99999` beside `Type/article number/U1` -- so the day a manufacturer's
    article number equals somebody's serial, a rule comparing the bare string
    calls a correct delivery a contradiction.
    """
    p = _delivery_with_axes(tmp_path, "axes.zip", [
        ("Type", "article number", "4711"),
        ("Individual", "serial number", "4711"),
    ])
    assert "M13" not in ids(p), (
        "two identifiers on different registers were read as one identifier "
        "claimed two ways")


def test_one_register_claimed_two_ways_is_still_caught(tmp_path):
    """And the axis must not become a way to escape the rule: same register,
    two kinds, is the contradiction."""
    p = _delivery_with_axes(tmp_path, "same-axis.zip", [
        ("Type", "serial number", "4711"),
        ("Individual", "serial number", "4711"),
    ])
    assert "M13" in ids(p), "one register claiming both kinds went unreported"


def test_naming_a_register_on_one_side_only_does_not_silence_the_rule(tmp_path):
    """The evasion the first draft of this shipped.

    Grouped by `(identifier, RefType)`, a sender could switch this rule off by
    writing a register on one of two contradicting claims and leaving it off
    the other -- one attribute, one side. Measured against this project's own
    corpus container at the time: the finding disappeared. An unstated register
    has to match every register, or the rule is advisory.
    """
    p = _delivery_with_axes(tmp_path, "one-sided.zip", [
        ("Type", "", "4711"),
        ("Individual", "serial number", "4711"),
    ])
    assert "M13" in ids(p), (
        "naming a register on one side and not the other silenced a real "
        "contradiction")


def test_a_register_spelled_two_ways_is_one_register(tmp_path):
    """And the escape must not be reachable by spelling either.

    One register written with different spacing is one register, and a
    comparison that treats them as two lets a stray space do what the attribute
    above could not.
    """
    p = _delivery_with_axes(tmp_path, "spelled.zip", [
        ("Type", "serial  number", "4711"),
        ("Individual", "serial number", "4711"),
    ])
    assert "M13" in ids(p), (
        "the same register written with different spacing was read as two "
        "registers, which is an escape hatch a space wide")


def test_a_register_spelled_in_another_case_is_one_register(tmp_path):
    """The other half of the same escape, and it had no test.

    `different_registers` says in its own words that the rule could be switched
    off "by writing a RefType on one of two contradicting claims and not the
    other, or by spelling it `serialNumber` on one side". The spacing half is
    pinned above. The case half was not, and `_register` folds case for exactly
    this reason -- so removing `.casefold()` from it left every test in this
    file, in the cost file, in the evasion file and in the reference-corpus file
    green, fifty of them, while the escape it guards was open again.

    Every `RefType` literal in these fixtures was lower case, which is why no
    existing case could tell the difference.
    """
    p = _delivery_with_axes(tmp_path, "cased.zip", [
        ("Type", "serialNumber", "4711"),
        ("Individual", "serialnumber", "4711"),
    ])
    assert "M13" in ids(p), (
        "the same register written in two cases was read as two registers, so "
        "a contradiction was silenced by capitalising one side")


def _delivery_with_axes(tmp_path, name, triples):
    """One document container per (kind, register, identifier)."""
    import re
    inner = []
    for i, (object_type, ref_type, object_id) in enumerate(triples):
        meta = MAINXML.replace("VDI2770_Main.pdf", "B.pdf")
        meta = re.sub(
            r"<ObjectId[^>]*>[^<]*</ObjectId>",
            f'<ObjectId ObjectType="{object_type}" RefType="{ref_type}">'
            f'{object_id}</ObjectId>',
            meta)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("VDI2770_Metadata.xml", meta)
            z.writestr("B.pdf", MAINPDF)
        inner.append((f"doc{i}.zip", buf.getvalue()))
    p = tmp_path / name
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in [("VDI2770_Main.xml", MAINXML),
                     ("VDI2770_Main.pdf", MAINPDF)] + inner:
            z.writestr(n, d)
    p.write_bytes(buf.getvalue())
    return str(p)


def test_the_uniqueness_flag_keeps_absent_apart_from_false():
    """`IsGloballyBiUnique` is parsed and no rule consults it, which is exactly
    when a parser goes wrong unnoticed.

    Absent is not `False`. A sender who said nothing has not said the identifier
    is local, and a reader that collapses the two will one day act on a claim
    nobody made. The corpus carries real `false` values, so this is not
    hypothetical shape-checking.
    """
    from vdi2770.domain import _flag

    assert _flag(None) is None, "an absent attribute became a stated one"
    assert _flag("true") is True and _flag("1") is True
    assert _flag("false") is False and _flag("0") is False
    assert _flag(" TRUE ") is True, "xs:boolean is not case- or space-sensitive"
    assert _flag("perhaps") is None, "an unreadable value became a decision"


def test_the_corpus_uniqueness_flags_are_read_as_written():
    """And read through the real parse path off a real container.

    `vdi2770_excel.zip` states `IsGloballyBiUnique` both ways, so this is the
    difference between a parser that works and one that has only been reasoned
    about.
    """
    import glob
    import zipfile

    import pytest

    from vdi2770 import build_document
    from vdi2770.model import Location
    from vdi2770.xmlread import parse

    found = glob.glob("corpus/**/vdi2770_excel.zip", recursive=True)
    if not found:
        pytest.skip("the container that carries the flag is not here")

    stated = set()
    with zipfile.ZipFile(found[0]) as outer:
        for name in outer.namelist():
            if not name.endswith(".zip"):
                continue
            with zipfile.ZipFile(io.BytesIO(outer.read(name))) as inner:
                for member in inner.namelist():
                    if not member.endswith(".xml"):
                        continue
                    root = parse(inner.read(member))
                    doc = build_document(root, Location())
                    stated |= {o.globally_unique for o in doc.objects}

    assert stated, "premise: this container declares objects at all"
    assert False in stated, (
        f"the corpus states IsGloballyBiUnique=\"false\" and the parse never "
        f"produced False: {stated}")


def test_an_identifier_spelled_in_another_case_is_one_identifier(tmp_path):
    """The claims are grouped on the identifier folded for case, and nothing
    held that either.

    Drop the fold and `ABC1223` declared as a type no longer meets `abc1223`
    declared as an individual: they become two identifiers, neither of which
    contradicts anything, and the rule goes quiet. That is a rule a sender
    silences with one keystroke -- the shape `different_registers`' own
    docstring exists to warn about, on the other axis.
    """
    p = _delivery_with_axes(tmp_path, "cased-id.zip", [
        ("Type", "product type", "ABC1223"),
        ("Individual", "product type", "abc1223"),
    ])
    assert "M13" in ids(p), (
        "one identifier written in two cases was read as two identifiers, so "
        "the contradiction between them went unreported")
