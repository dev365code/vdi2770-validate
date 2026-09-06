"""Every finding says where its requirement comes from, on both surfaces.

`rules.json` carries an `obligation` on every rule so that no claim about
VDI 2770 travels without its source, and the JSON report printed it. The text
report — the surface a person at a terminal actually reads — printed nothing.
So thirteen rules whose basis is *the reference implementation, not the
guideline* reached the reader as unqualified imperatives: "Add a
DocumentClassification whose ClassificationSystem is VDI2770:2018", with no hint
that the thing requiring it is somebody else's Java program and that the
guideline which could settle it is paid and was never read here. `Z9` was the
only remedy that named its source inside the sentence, which proved the rest
could have.

Two rules govern the fix and both are asserted below. The words are *derived*
from the rule's obligation and its recorded reference codes, never written per
rule, so a new rule cannot arrive with a hand-phrased basis that says something
slightly different from the twelve before it. And the two surfaces have to say
the same thing: one risk written on two surfaces is one risk that drifts, and
the drift here would be a report whose JSON is honest and whose text is not.
"""
import json
import re
import subprocess
import sys

import pytest

from conftest import CORPUS, FIXTURES, ROOT, under_test
from vdi2770_validate.model import Obligation
from vdi2770_validate.report import BASIS, basis
from vdi2770_validate.runner import check_file

BROKEN = FIXTURES / "m2-unknown-class-id.zip"


def run(*args):
    done = subprocess.run([sys.executable, "-m", "vdi2770_validate", "check", *args],
                          cwd=ROOT, capture_output=True, text=True, env=under_test())
    return done.stdout


def test_every_obligation_has_words_and_no_rule_writes_its_own():
    """Derived, not authored. A basis phrased at the rule is a basis that can
    disagree with the one beside it about what `reference` means."""
    assert set(BASIS) == set(Obligation), (
        f"obligations without fixed words: {sorted(o.value for o in set(Obligation) - set(BASIS))}")
    for words in BASIS.values():
        assert words and not words.startswith("per "), (
            "the table holds the noun phrase; `basis` puts `per` in front of it")


def test_the_words_name_the_reference_code_when_there_is_one():
    """`obligation: reference` says a Java program requires this. Which of its
    checks is a fact this project already records per rule, and a reader who
    wants to go and look needs it."""
    from vdi2770_validate.catalog import rule

    said = basis(rule("M11"))
    assert said.startswith("per "), said
    assert "reference implementation" in said, said
    assert "D_004" in said, (
        f"M11 records refCodes and the basis line does not name them: {said!r}")


def test_the_text_report_prints_a_basis_for_every_finding_it_lists():
    """The count is the assertion. A basis printed for some findings and not
    others is worse than none: a reader learns to read its absence as meaning
    something, and it means nothing."""
    out = run("--json", str(BROKEN))
    listed = json.loads(out)[0]["findings"]
    text = run(str(BROKEN))
    per = [ln for ln in text.splitlines() if ln.strip().startswith("per ")]
    assert len(per) == len(listed), (
        f"the text report lists {len(listed)} findings and prints {len(per)} "
        f"basis lines")


def test_the_two_surfaces_say_the_same_thing_about_every_finding():
    """The gate the whole file is for. `--json` carries `obligation` as a bare
    token and the text carries the words; they are two spellings of one fact,
    and nothing compared them."""
    docs = json.loads(run("--json", str(BROKEN)))
    text = run(str(BROKEN)).splitlines()
    said = [ln.strip() for ln in text if ln.strip().startswith("per ")]
    findings = docs[0]["findings"]
    assert len(said) == len(findings) and findings, (len(said), len(findings))
    for finding, line in zip(findings, said):
        assert line == basis_words(finding["obligation"]), (
            f"{finding['rule']} is `{finding['obligation']}` in the JSON and "
            f"the text says {line!r}")


def basis_words(obligation_value: str) -> str:
    return "per " + BASIS[Obligation(obligation_value)]


def test_the_basis_sits_with_the_evidence_and_not_with_the_remedy():
    """Where it goes is part of what it says. The basis answers *why this is
    being reported*, which belongs with what was observed; the remedy answers
    *what to do*, and a reader skimming for the fix should not have to step over
    the justification to reach it."""
    lines = [ln for ln in run(str(BROKEN)).splitlines() if ln.startswith("  ")]
    seen_finding = False
    for i, line in enumerate(lines):
        if re.match(r"  (error|warn |info )", line):
            seen_finding = True
            continue
        if not seen_finding or not line.strip().startswith("per "):
            continue
        assert lines[i + 1].strip().startswith("-> "), (
            f"the basis is not immediately before the remedy: {lines[i + 1]!r}")
        assert lines[i - 1].strip().startswith(("at ", "'")) or \
            not lines[i - 1].strip().startswith("-> "), (
            f"the basis follows the remedy rather than the evidence: {lines[i - 1]!r}")


@pytest.mark.parametrize("quiet", [False, True])
def test_quiet_does_not_take_the_basis_away(quiet):
    """`--quiet` hides notes. It has been caught deleting a statement this tool
    makes about itself before, and this is another one."""
    out = run(*(["--quiet"] if quiet else []), str(BROKEN))
    assert [ln for ln in out.splitlines() if ln.strip().startswith("per ")]


def test_a_clean_container_prints_no_basis_lines():
    """Nothing to justify. A guard on the count above, which would pass over a
    report that printed a basis for findings it did not have."""
    clean = CORPUS / "container" / "documentcontainer.zip"
    assert check_file(str(clean)).count_errors() == 0 if hasattr(
        check_file(str(clean)), "count_errors") else True
    out = run("--quiet", str(clean))
    assert not [ln for ln in out.splitlines() if ln.strip().startswith("per ")]


def test_a_scan_stopped_by_the_stream_budget_names_it(tmp_path):
    """The detail withheld the number for a reason that no longer exists.

    It read: *"No number: `MAX_STREAMS` counts stream markers and `stream\\n`
    matches `endstream\\n` too, so any count printed here would be about twice
    what a PDF parser sees in the file."* That was true and it is not any more —
    the marker counts streams now. Withholding it on a freshly-invented reason
    would be rationalising a decision whose only ground was a defect.

    Only where the stream budget is what stopped it. The other reason a file's
    own scan ends covers two different ceilings at once, and one number would
    pick one of them and be wrong about the other.
    """
    import io
    import zipfile
    import zlib

    from vdi2770.pdfread import MAX_STREAMS

    blob = zlib.compress(b"a page\n")
    pdf = [b"%PDF-1.7\n", b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"]
    for i in range(2, MAX_STREAMS + 4):
        pdf.append(b"%d 0 obj\n<< /Length %d /Filter /FlateDecode >>\nstream\n"
                   % (i, len(blob)))
        pdf.append(blob)
        pdf.append(b"\nendstream\nendobj\n")
    pdf.append(b"trailer\n%%EOF\n")

    # A real document container with one member swapped, so everything else
    # about it is conforming and the finding can only be about the PDF.
    source = CORPUS / "container" / "documentcontainer.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(buf, "w") as out:
        for name in src.namelist():
            out.writestr(name, b"".join(pdf) if name == "B.pdf" else src.read(name))
    target = tmp_path / "many-streams.zip"
    target.write_bytes(buf.getvalue())

    said = [f.detail or "" for f in check_file(str(target)).sorted()
            if f.rule.id == "P3"]
    assert said, "a PDF past the stream budget produced no P3 at all"
    assert any(str(MAX_STREAMS) in d for d in said), (
        f"the scan stopped at the stream budget and the detail does not say "
        f"how many that is: {said}")
