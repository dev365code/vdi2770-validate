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

from conftest import CLEAN_DOCUMENT
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
                               'xmlns="http://www.vdi.de/schemas/vdi277"', 1)
    report = check_bytes(_box(meta), "typo.zip")
    said = [f for f in report.findings if f.rule.id == "M1"]
    assert len(said) == 1, _ids(report)
    assert "vdi277" in (said[0].detail or ""), said[0].detail
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
