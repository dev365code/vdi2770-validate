"""`Document` is not a name. `{http://www.vdi.de/schemas/vdi2770}Document` is.

The model matched local names, so an element from any vocabulary at all was
read as a VDI 2770 one. Three things followed, and the first is the worst:

  * a `DocumentClassification` in someone else's namespace *satisfied* `M1`, so
    a document carrying no VDI 2770 classification was reported as carrying one;
  * `M2` and `M3` issued VDI 2770 verdicts about foreign elements, beside an
    `X2` saying those elements are not in the schema at all — two findings that
    cannot both be true;
  * `X2`'s line resolution counted children by local name while `xmlschema`
    counts them by expanded name, so one foreign sibling shifted every position
    after it and the finding named a line whose element does not have the
    defect.

And the repair has a cost that has to be paid rather than absorbed: a document
in the wrong namespace, or in none, loses every `M` finding it used to get. That
is right — the obligation layer must not run on a vocabulary that is not the
standard's — but only if something says so, which is what `M11` is for.
"""
from __future__ import annotations

import io
import re
import zipfile

import pytest

from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION
from vdi2770_validate.runner import check_bytes

FOREIGN = ('<x:DocumentClassification xmlns:x="urn:not-vdi" '
           'ClassificationSystem="VDI2770:2018">'
           '<x:ClassId>{cid}</x:ClassId>'
           '<x:ClassName Language="de">fremd</x:ClassName>'
           '</x:DocumentClassification>')


def _metadata() -> str:
    return zipfile.ZipFile(CLEAN_DOCUMENT).read(
        "VDI2770_Metadata.xml").decode("utf-8")


def _box(text: str) -> bytes:
    base = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in base.namelist():
            z.writestr(name, text if name == "VDI2770_Metadata.xml"
                       else base.read(name))
    return buf.getvalue()


def _classification(meta: str) -> str:
    return re.search(r"<DocumentClassification.*?</DocumentClassification>",
                     meta, re.S).group(0)


def _ids(report):
    return sorted({f.rule.id for f in report.findings})


def test_someone_elses_classification_does_not_satisfy_ours():
    meta = _metadata()
    report = check_bytes(
        _box(meta.replace(_classification(meta), FOREIGN.format(cid="02-01"), 1)),
        "foreign.zip")
    assert "M1" in _ids(report), (
        f"a document with no VDI 2770 classification was not told so: "
        f"{_ids(report)}")


def test_no_vdi_verdict_is_issued_about_someone_elses_element():
    meta = _metadata()
    report = check_bytes(
        _box(meta.replace(_classification(meta), FOREIGN.format(cid="02-01"), 1)),
        "foreign.zip")
    assert "M3" not in _ids(report), (
        "a German class name in another vocabulary was judged against VDI 2770")

    both = _classification(meta) + FOREIGN.format(cid="ZZ-99")
    report = check_bytes(_box(meta.replace(_classification(meta), both, 1)),
                         "both.zip")
    assert "M2" not in _ids(report), (
        "a class id in another vocabulary was judged against the published list")


def test_a_schema_complaint_counts_children_the_way_the_schema_does():
    """One foreign sibling shifted every position after it."""
    meta = _metadata()
    at = meta.index('<ClassName Language="de">')
    meta = (meta[:at]
            + '<x:ClassName xmlns:x="urn:not-vdi" Language="de">fremd</x:ClassName>\n    '
            + meta[at:])
    # And the real second name loses its Language, which is what X2 reports.
    meta = meta.replace('<ClassName Language="en">', "<ClassName>", 1)
    lines = meta.splitlines()
    want = next(i + 1 for i, ln in enumerate(lines) if "<ClassName>" in ln)

    report = check_bytes(_box(meta), "shifted.zip")
    said = [f for f in report.findings
            if f.rule.id == "X2" and "Language" in (f.detail or "")]
    assert said, [(f.rule.id, f.detail) for f in report.findings]
    assert said[0].where.line == want, (
        f"the finding names line {said[0].where.line}; the element without a "
        f"Language is on line {want}")


def test_metadata_in_another_namespace_is_told_so_once():
    meta = _metadata().replace('xmlns="http://www.vdi.de/schemas/vdi2770"',
                               'xmlns="urn:not-vdi"', 1)
    report = check_bytes(_box(meta), "typo.zip")
    said = [f for f in report.findings if f.rule.id == "M1"]
    assert len(said) == 1, _ids(report)
    # A namespace that is not a prefix of the real one. `vdi277` is a substring
    # of `vdi2770`, so asserting on it was satisfied by the half of the sentence
    # that names what was *expected* — true for every value of what was found.
    assert "urn:not-vdi" in (said[0].detail or ""), said[0].detail
    assert said[0].detail.index("urn:not-vdi") < said[0].detail.index(
        "http://www.vdi.de/schemas/vdi2770"), (
        "the namespace found and the one expected are the wrong way round: "
        + said[0].detail)
    # And it points at the element carrying the declaration, not at line 1,
    # which is the XML declaration.
    assert said[0].where.line == 1 + meta[:meta.index("<Document")].count("\n"), (
        said[0].where.line)
    assert 'xmlns="http://www.vdi.de/schemas/vdi2770"' in (said[0].remedy or ""), (
        said[0].remedy)
    # And nothing else runs on a vocabulary that is not ours: every other rule
    # in these two layers reads a model built from names this document has none
    # of, so `F2` said of every file in the archive that the metadata does not
    # name it — true, and pointing at the wrong thing.
    assert not [f for f in report.findings
                if f.rule.id.startswith(("M", "F")) and f.rule.id != "M1"], _ids(report)


def test_a_file_in_the_container_is_not_blamed_for_the_namespace():
    """The same, from the file rules' side, where it was a flood rather than a
    single line: one `F2` per member."""
    meta = _metadata().replace('xmlns="http://www.vdi.de/schemas/vdi2770"', "", 1)
    report = check_bytes(_box(meta), "none.zip")
    assert "F2" not in _ids(report), _ids(report)


def test_a_prefix_on_the_root_and_nowhere_else_is_still_the_wrong_vocabulary():
    """The root's own namespace is not the question; its children's is.

    `<vdi:Document xmlns:vdi="…">` with unprefixed children puts the root in the
    VDI 2770 namespace and everything under it in none — which the schema, whose
    elements are declared qualified, makes an error, and which reads to the
    layers below as a document with nothing in it. Deciding on the root alone
    let that document draw `M1`'s first sentence, *carries no classification*,
    for a file whose classification is written out in full.
    """
    meta = _metadata()
    meta = meta.replace('xmlns="http://www.vdi.de/schemas/vdi2770"',
                        'xmlns:vdi="http://www.vdi.de/schemas/vdi2770"', 1)
    meta = meta.replace("<Document ", "<vdi:Document ", 1)
    meta = meta.replace("</Document>", "</vdi:Document>", 1)
    assert "<vdi:Document " in meta and "xmlns:vdi=" in meta, "the premise"
    report = check_bytes(_box(meta), "prefix.zip")
    said = [f for f in report.findings if f.rule.id == "M1"]
    assert len(said) == 1, _ids(report)
    assert "no namespace at all" in (said[0].detail or ""), said[0].detail
    assert "F2" not in _ids(report), _ids(report)


def test_a_root_with_no_children_is_the_schemas_complaint_and_not_this_one():
    """"No children in our namespace" must not swallow "no children"."""
    report = check_bytes(
        _box('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<Document xmlns="http://www.vdi.de/schemas/vdi2770"/>\n'),
        "empty.zip")
    said = [f for f in report.findings if f.rule.id == "M1"]
    assert said, _ids(report)
    assert "namespace" not in (said[0].detail or ""), said[0].detail


def _declaring_a_payload(src, member: str, xmlns: str) -> bytes:
    """A container declaring `cad.zip`, with an ordinary `cad.zip` in it."""
    base = zipfile.ZipFile(src)
    meta = base.read(member).decode("utf-8").replace(
        "<DigitalFile",
        '<DigitalFile FileFormat="application/zip">cad.zip</DigitalFile>\n      '
        "<DigitalFile", 1)
    meta = meta.replace('xmlns="http://www.vdi.de/schemas/vdi2770"', xmlns, 1)
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as inner:
        inner.writestr("part.step", b"ISO-10303-21;\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in base.namelist():
            z.writestr(name, meta if name == member else base.read(name))
        z.writestr("cad.zip", payload.getvalue())
    return buf.getvalue()


@pytest.mark.parametrize("src,member,invented", [
    (CLEAN_DOCUMENTATION, "VDI2770_Main.xml", "Z3"),
    (CLEAN_DOCUMENT, "VDI2770_Metadata.xml", "Z11"),
])
def test_a_vocabulary_we_cannot_read_is_unknown_and_not_declares_nothing(
        src, member, invented):
    """The container rules read the same model, and an empty one is not silence.

    `declared` came out `frozenset()` for a document whose names are in another
    vocabulary, and the container layer reads that as *this container declares
    no files* — so a payload declared three lines from `B.pdf`'s own declaration
    was accused of not being declared. The runner already keeps "unknown" and
    "declares nothing" apart for three other ways of having no model; this was a
    fourth, and the comment beside them says what it costs.
    """
    ours = _ids(check_bytes(
        _declaring_a_payload(src, member,
                             'xmlns="http://www.vdi.de/schemas/vdi2770"'), "ok.zip"))
    assert invented not in ours, f"the premise: a declared payload is quiet: {ours}"

    theirs = _ids(check_bytes(
        _declaring_a_payload(src, member, 'xmlns="urn:not-vdi"'), "foreign.zip"))
    assert invented not in theirs, theirs
    assert "M1" in theirs, theirs


def test_the_two_namespaces_are_told_apart_when_they_print_the_same():
    """One Cyrillic letter and the finding holds two URIs a reader cannot tell
    apart, under a remedy telling them to write the one they appear to have
    written. `told_apart` is what the rest of this layer uses for that."""
    look_alike = "http://www.vdi.de/sch" + chr(0x435) + "mas/vdi2770"
    meta = _metadata().replace('xmlns="http://www.vdi.de/schemas/vdi2770"',
                               f'xmlns="{look_alike}"', 1)
    said = [f for f in check_bytes(_box(meta), "twin.zip").findings
            if f.rule.id == "M1"]
    assert said, _ids(check_bytes(_box(meta), "twin.zip"))
    assert chr(0x435) not in (said[0].detail or ""), said[0].detail
    assert "0435" in (said[0].detail or ""), said[0].detail


def test_a_root_outside_the_namespace_whose_children_are_inside_it_is_read():
    """The root's namespace is not the question either.

    `<Document>` in no namespace with `xmlns` on its children builds the whole
    model — the builder reads the root's children — so a report saying *nothing
    in it is a VDI 2770 element* said it beside findings drawn from those
    elements. The question is whether the model came out empty.
    """
    ns = ' xmlns="http://www.vdi.de/schemas/vdi2770"'
    meta = _metadata().replace(ns, "", 1)
    # The declaration moves off the root and onto each of its children, which is
    # where the builder looks. Two-space indent is a direct child of `Document`.
    meta = re.sub(r"^    <([A-Za-z]+)", lambda m: f"    <{m.group(1)}{ns}",
                  meta, flags=re.M)
    assert meta.count(ns) > 1, "the premise: several children carry it"
    report = check_bytes(_box(meta), "inside.zip")
    said = [f for f in report.findings if f.rule.id == "M1"]
    assert not said or "namespace" not in (said[0].detail or ""), (
        f"the model was built from these names: {said[0].detail if said else ''}")


def test_the_single_lookup_carries_the_namespace_too():
    """`find` and `find_all` are two halves of one decision.

    The model reads `ClassId` with `find`, so leaving that half unfiltered kept
    the headline case alive one level down: a foreign `ClassId` inside a VDI
    2770 classification drew *the class id is not one of the published classes*
    beside a schema complaint saying that element is not in the schema at all.
    Reverting `find` alone was green across the whole suite.
    """
    meta = _metadata()
    at = meta.index("<ClassId>")
    end = meta.index("</ClassId>", at) + len("</ClassId>")
    meta = (meta[:at]
            + '<x:ClassId xmlns:x="urn:not-vdi">ZZ-99</x:ClassId>'
            + meta[end:])
    fired = _ids(check_bytes(_box(meta), "inner.zip"))
    assert "M2" not in fired, fired
    assert "X2" in fired, fired


def test_one_element_in_another_vocabulary_is_not_the_whole_document():
    """A document can be part ours, and the predicate has to be about the model.

    Put the classification alone in another namespace and leave the rest right:
    the identifiers and the versions are read, so the model is not empty and
    saying *nothing in it is a VDI 2770 element* would be false about the very
    findings this report goes on to make from it. `M1` still fires — the
    document does carry no VDI 2770 classification — and it fires its first way,
    which is the true one.
    """
    meta = _metadata()
    at = meta.index("<DocumentClassification")
    end = meta.index("</DocumentClassification>", at) + len("</DocumentClassification>")
    block = meta[at:end].replace("DocumentClassification", "x:DocumentClassification")
    meta = (meta[:at] + block.replace("<x:DocumentClassification",
                                      '<x:DocumentClassification xmlns:x="urn:not-vdi"', 1)
            + meta[end:])
    report = check_bytes(_box(meta), "mixed.zip")
    said = [f for f in report.findings if f.rule.id == "M1"]
    assert said, _ids(report)
    assert "urn:not-vdi" not in (said[0].detail or ""), (
        f"the model was built from this document: {said[0].detail}")
    # And the file rules are not switched off for a document they can read.
    assert not [f for f in report.findings if f.rule.id == "M11"], _ids(report)
