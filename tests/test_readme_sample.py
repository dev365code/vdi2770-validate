"""The README's sample session must be output the tool can actually produce.

The first one was hand-written: it showed one remedy for three findings, wrapped
a line the renderer never wraps, and quoted a column number that cannot occur.
A fabricated sample is a screenshot of a program that does not exist.
"""
import contextlib
import io
import re

from conftest import ROOT, ordinal, under_test
from vdi2770_validate.model import Severity
from vdi2770_validate.runner import check_file

README = (ROOT / "README.md").read_text(encoding="utf-8")
BLOCK = re.search(r"```\n\$ vdi2770-validate check (\S+)\n(.*?)```", README, re.S)


def test_the_readme_shows_a_command_that_exists():
    assert BLOCK, "no sample session found in README.md"
    assert (ROOT / BLOCK.group(1)).exists(), f"the sample runs on {BLOCK.group(1)}, which is not here"


def _command_output(target: str) -> list:
    """What `vdi2770-validate check <target>` actually prints.

    The renderer is a layer below the command, and the run's closing statement
    lives in the command. A gate that reads the renderer sees a line the tool
    does produce as absent -- which is how this sample's ending went missing
    twice, the second time under the test written to forbid it.
    """
    import subprocess
    import sys

    done = subprocess.run([sys.executable, "-m", "vdi2770_validate", "check", target],
                          cwd=ROOT, capture_output=True, text=True, env=under_test())
    return done.stdout.splitlines()


def test_every_line_of_the_sample_is_really_produced_in_that_order():
    """Membership was the whole check, and a sample can hold every line the tool
    prints and still show a session it never had.

    It did: the findings were shown `F1`, `Z13`, `Z7` and the tool prints `F1`,
    `Z7`, `Z13`. Order is not decoration here — the report sorts by severity and
    then by rule, and a reader scrolling a CI log for the first error is reading
    that order. Checked by walking one cursor forward through the real output,
    so a line that appears before the one above it is as much a failure as a
    line that never appears.
    """
    target, shown = BLOCK.group(1), BLOCK.group(2)
    real = _command_output(target)
    at, previous = 0, None
    for line in shown.splitlines():
        if not line.strip() or line.strip().startswith("…"):
            continue          # checked by the test below, not skipped
        assert line in real, f"the README shows a line the tool never prints:\n  {line}"
        try:
            at = real.index(line, at) + 1
        except ValueError:
            raise AssertionError(
                f"the README shows this line after {previous!r}, and the tool "
                f"prints it before:\n  {line}") from None
        previous = line


def test_the_elision_says_what_it_elided():
    """The elision was the one line nothing checked, and it was wrong twice over:
    *"6 more warnings of the same kind"* stood for four F2 warnings and two of a
    different kind. A marked gap in a sample is still a claim about the output.
    """
    target, shown = BLOCK.group(1), BLOCK.group(2)
    report = check_file(str(ROOT / target))
    findings = report.sorted()

    # The "then ..." clause only exists when something of another rule follows.
    m = re.search(r"…\s*(\d+) more (\w+) warnings?(?:, then (.+))?", shown)
    assert m, "the sample's elision line has been reworded"
    listed = [ln for ln in shown.splitlines() if ln.startswith("  error") or ln.startswith("  warn")]
    rest = findings[len(listed):]
    assert rest, "the sample elides nothing, so it should not claim to"

    same = m.group(2)
    assert sum(1 for f in rest if f.rule.id == same) == int(m.group(1)), (
        f"the elision claims {m.group(1)} more {same}; the tool prints "
        f"{sum(1 for f in rest if f.rule.id == same)}")
    named = [w for w in re.split(r"[,\s]+|and", m.group(3) or "") if w]
    assert named == [f.rule.id for f in rest if f.rule.id != same], (
        f"the elision names {named}; what follows is "
        f"{[f.rule.id for f in rest if f.rule.id != same]}")

    counts = f"  {report.count(Severity.ERROR)} error(s), {report.count(Severity.WARNING)} warning(s)"
    assert counts in shown, f"the sample's summary line does not match: expected {counts!r}"


def test_the_sample_does_not_claim_a_pdfa_verdict():
    assert not re.search(r"PDF/A.{0,24}\b(valid|conformant|compliant)\b", README, re.I)


def test_the_readme_counts_its_own_fixture_pairs():
    """A number in prose drifts the moment the thing it counts changes. This one
    said 24 while one of those 24 had no conforming counterpart — the pair test
    skips it — so the sentence claimed a guarantee that did not exist for it.
    """
    import json
    import re

    from conftest import FIXTURES
    from vdi2770_validate.catalog import rules

    fixtures = json.loads((FIXTURES / "MANIFEST.json").read_text(encoding="utf-8"))["fixtures"]
    paired = {m["rule"] for m in fixtures.values() if m["basedOn"] is not None}
    lone = {m["rule"] for m in fixtures.values()} - paired
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    m = re.search(r"\*\*(\d+) of (\d+) rules have a minimal fixture pair\*\*", readme)
    assert m, "the README sentence this test pins has been reworded"
    assert (int(m.group(1)), int(m.group(2))) == (len(paired), len(set(rules()))), (
        f"README says {m.group(1)} of {m.group(2)}; the manifest and catalogue say "
        f"{len(paired)} of {len(set(rules()))}")
    # Derived, and it was not: a hand-written `{1: "24th", 2: "25th"}` was off by
    # one in both entries, so the README's "A 24th" — which contradicted its own
    # "24 of 37" — was the sentence this test *required*. Writing the true one
    # turned the build red.
    assert len(lone) == 1, (
        f"{len(lone)} rules have a fixture with no counterpart: {sorted(lone)}; "
        f"the README describes exactly one and has to be rewritten")
    n = len(paired) + 1
    assert f"A {ordinal(n)}" in readme, (
        f"{len(paired)} rules have a pair and one more has a lone fixture, so the "
        f"lone one is the {ordinal(n)}; the README says otherwise")


def test_the_classes_transcript_is_output_the_tool_produces():
    """The `check` transcript above is pinned line by line; the `classes` one was
    not, and it had drifted: the second line dropped the `English — ` that says
    *which* of the two names the sources disagree about, and the columns were
    hand-narrowed. Two transcripts in one README, one of them checked.
    """
    import subprocess
    import sys

    block = re.search(r"```\n\$ vdi2770-validate classes\n(.*?)```", README, re.S)
    assert block, "the README no longer shows a `classes` session"
    run = subprocess.run([sys.executable, "-m", "vdi2770_validate", "classes"],
                         cwd=ROOT, capture_output=True, text=True, env=under_test())
    assert run.returncode == 0, run.stderr
    real = run.stdout.splitlines()
    for line in block.group(1).splitlines():
        if not line.strip() or line.strip().startswith("…"):
            continue
        assert line in real, f"the README shows a line `classes` never prints:\n  {line}"


def test_the_reader_readmes_snippet_prints_what_it_says_it_prints():
    """The root README's two transcripts are pinned line by line, and the reader
    README's defect-kind list and budget constants both have gates. The one thing
    left unchecked was the snippet at the very top of it — the first code a
    prospective user reads — and it was wrong: the code prints
    `[(i.domain_id, i.id) for i in doc.identifiers]`, a *list of pairs*, and the
    output block showed a bare one-tuple with the domain id dropped.

    An identifier is (domain, value) — the rest of this project has a rule, a
    test file and a CHANGELOG entry about exactly that, and the reader's own
    front page rendered it as a bare string.

    The snippet is run against a corpus container rather than the `handover.zip`
    it names, so what is checked is the *shape* of each line: the container path,
    then a list of pairs, then a list of class ids. `test_layering.py` forbids
    the reader's own suite from reaching the corpus, which is why this lives
    here.
    """
    import ast

    import vdi2770
    from conftest import CLEAN_DOCUMENTATION

    readme = (ROOT / "packages" / "vdi2770" / "README.md").read_text(encoding="utf-8")
    shown = re.search(r"```\n(handover\.zip .*?)```", readme, re.S)
    assert shown, "the reader README no longer shows an output block"

    produced = []
    box = vdi2770.read_container_file(str(CLEAN_DOCUMENTATION))
    for c in box.walk():
        if c.metadata_bytes is None:
            continue
        doc = vdi2770.build_document(vdi2770.parse_xml(c.metadata_bytes), c.where)
        produced.append((c.path, [(i.domain_id, i.id) for i in doc.identifiers],
                         [k.class_id for k in doc.classifications]))
    assert len(produced) >= 2, "the sample walks a nested container; so must this"

    lines = [ln for ln in shown.group(1).splitlines() if ln.strip()]
    assert len(lines) == len(produced), (
        f"the README shows {len(lines)} containers; the snippet produces {len(produced)}")
    for line in lines:
        head, rest = line.split(" ", 1)
        assert head.endswith(".zip"), line
        shown_ids, shown_classes = ast.literal_eval(f"[{rest.replace('] [', '], [')}]")
        assert isinstance(shown_ids, list) and shown_ids, f"identifiers is a list: {line}"
        for pair in shown_ids:
            assert isinstance(pair, tuple) and len(pair) == 2, (
                f"an identifier is (domain, value) and the README shows {pair!r}")
        assert isinstance(shown_classes, list) and shown_classes, line
        assert all(isinstance(k, str) and "-" in k for k in shown_classes), line


def test_a_reader_who_has_only_installed_it_can_run_the_first_command():
    """The first command a stranger runs must not need a file they do not have.

    `pip install` was followed straight away by a check on `corpus/…`, which the
    wheel does not carry — so the first thing the README asks for produced
    `cannot read it — No such file or directory`. The sentence that mentions a
    clone came *after* the command, and no `git clone` line appeared anywhere.
    """
    text = README
    # Either spelling of the command: `vdi2770-validate` is the name this
    # project published under until 0.6.0 and it is still installed, so a
    # page that used it would have the same problem.
    first = re.search(r"vdi2770(-validate)? check (corpus|tests)/", text)
    if first is None:
        return                    # no repo-relative example to get wrong
    clone = text.find("git clone")
    assert clone >= 0, (
        "the README runs commands against paths inside this repository and "
        "never says how to get them")
    assert clone < first.start(), (
        "the README asks for a file from this repository before it says how to "
        "obtain one")


def test_the_readme_states_the_exit_codes_the_tool_really_returns(tmp_path):
    """It is sold as something to drop into a CI job, and the numbers a CI job
    reads were written down in one source docstring and nowhere a user looks."""
    from conftest import CLEAN_DOCUMENT, FIXTURES
    from vdi2770_validate.cli import main

    text = README
    measured = {}
    for label, path in (("clean", str(CLEAN_DOCUMENT)),
                        ("error", str(FIXTURES / "m2-unknown-class-id.zip")),
                        ("unreadable", str(tmp_path / "nope.zip"))):
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            measured[label] = main(["check", path])
    assert sorted(measured.values()) == [0, 1, 2], measured

    where = text.lower()
    assert "exit" in where, "the README never mentions the exit codes"
    for code in sorted(set(measured.values())):
        assert f"`{code}`" in text or f" {code} " in text, (
            f"exit code {code} is returned and not written down")


def test_the_sample_does_not_stop_before_the_tool_does():
    """`line in real` is one-directional: it catches a line the tool never
    prints and cannot catch one the tool prints and the page leaves out. The
    page then shows a real session with its ending removed, which is the kind of
    sample this file exists to forbid — and it happened the moment the report
    grew a line after the counts.
    """
    target, shown = BLOCK.group(1), BLOCK.group(2)
    real = _command_output(target)
    last = next(line for line in reversed(real) if line.strip())
    assert last.strip() in shown, (
        f"the command ends with {last.strip()!r} and the sample stops before it")
