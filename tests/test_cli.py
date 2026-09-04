"""The command line is the whole product for most users, and it had no tests at
all — which is how `classes` came to crash while `make check` stayed green.
"""
import json
import subprocess
import sys
import zipfile

import pytest

from conftest import CLEAN_DOCUMENT, CORPUS, FIXTURES, under_test
from vdi2770_validate.cli import main

capsys_holder = [None]


@pytest.fixture(autouse=True)
def _hold_capsys(capsys):
    capsys_holder[0] = capsys
    yield


def run(capsys, argv):
    code = main(argv)
    return code, capsys.readouterr().out


def test_check_on_a_clean_container_exits_zero(capsys):
    code, out = run(capsys, ["check", str(CLEAN_DOCUMENT)])
    assert code == 0
    assert "0 error(s)" in out


def test_check_on_a_broken_container_exits_one(capsys):
    code, out = run(capsys, ["check", str(FIXTURES / "m2-unknown-class-id.zip")])
    assert code == 1
    assert "M2" in out


def test_check_json_is_valid_json_and_says_pdfa_is_unverified(capsys):
    _, out = run(capsys, ["check", str(CLEAN_DOCUMENT), "--json"])
    # One document for the run, one entry per path given.
    payload = json.loads(out)[0]
    assert payload["pdfaVerified"] is False
    assert payload["target"].endswith(".zip")
    for f in payload["findings"]:
        assert f["remedy"], "every finding in JSON carries a remedy"


def test_every_finding_in_text_output_carries_a_remedy(capsys):
    """The text renderer used to print one remedy per rule, not per finding,
    while the docs promised per finding."""
    from conftest import CLEAN_DOCUMENTATION  # two P4 notes: the repeat is the point
    _, out = run(capsys, ["check", str(CLEAN_DOCUMENTATION)])
    findings = [ln for ln in out.splitlines() if ln.startswith(("  error", "  warn ", "  info "))]
    remedies = [ln for ln in out.splitlines() if ln.strip().startswith("-> ")]
    assert findings, "expected some findings"
    assert len(remedies) == len(findings), (
        f"{len(findings)} findings but {len(remedies)} remedies")


def test_rules_lists_every_rule(capsys):
    from vdi2770_validate.catalog import rules
    code, out = run(capsys, ["rules"])
    assert code == 0
    for rid in rules():
        assert rid in out
    assert f"{len(rules())} rules" in out


def test_classes_prints_twelve_and_shows_both_renderings(capsys):
    code, out = run(capsys, ["classes"])
    assert code == 0
    for cid in ("01-01", "02-03", "04-01"):
        assert cid in out
    assert "Assemblies" in out and "Components" in out, "both English renderings should be visible"


def test_a_missing_file_is_reported_not_a_traceback(capsys):
    assert main(["check", "no-such-file.zip"]) == 2
    assert "cannot read it" in capsys.readouterr().err


def test_one_unreadable_path_does_not_stop_the_rest(capsys):
    """A CI job sweeping a supplier drop folder must not stop at the first dud."""
    code = main(["check", "no-such-file.zip", str(CLEAN_DOCUMENT)])
    out = capsys.readouterr()
    assert code == 1                       # something was unreadable, but we kept going
    assert "cannot read it" in out.err
    assert "0 error(s)" in out.out         # the good one was still checked


def test_a_conforming_container_still_leaves_one_note(capsys):
    """The shape every happy user sees, and it is not "no findings".

    A conforming document container declares a PDF — `M6` requires one per
    version — and every PDF produces either `P3` (no PDF/A claim) or `P4` (a
    claim this tool will not verify). So a report with nothing at all in it is
    unreachable for a valid container, and pinning "no findings" against the
    clean corpus document is how a test came to assert that line printed above a
    summary reading "1 note(s)".
    """
    code, out = run(capsys, ["check", str(CLEAN_DOCUMENT)])
    assert code == 0
    assert "info   P4" in out, out
    assert "0 error(s), 0 warning(s), 1 note(s)" in out, out
    assert "no findings" not in out, out


def test_hidden_notes_are_not_reported_as_nothing(capsys):
    """`--quiet` drops the notes; it does not make them stop existing, and the
    summary line right underneath still counts them."""
    _, out = run(capsys, ["check", str(CLEAN_DOCUMENT), "--quiet"])
    assert "no findings" not in out, out
    assert "1 note(s) not shown" in out, out
    assert "0 error(s), 0 warning(s), 1 note(s)" in out, out


def test_the_module_entry_point_works():
    """`python -m vdi2770_validate` had no coverage at all."""
    import os
    import subprocess
    import sys

    from conftest import ROOT
    r = subprocess.run([sys.executable, "-m", "vdi2770_validate", "--version"],
                       capture_output=True, text=True,
                       env={"PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(ROOT / "packages" / "vdi2770" / "src")]),
                            "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()


def test_a_surprise_from_the_reader_does_not_stop_the_sweep(capsys, monkeypatch):
    """The handler written so one bad path cannot stop the rest was itself the
    thing that stopped the rest.

    `except Exception as e: ... {e.strerror or e}` — `strerror` exists on
    `OSError` and nowhere else, so anything else raised out of `check_file`
    became `AttributeError: 'ValueError' object has no attribute 'strerror'`,
    uncaught, killing a CI job sweeping a supplier drop folder at the first dud.
    Exactly the failure it was added to prevent, for exactly the class of
    surprise it was added for.
    """
    from vdi2770_validate import cli

    real = cli.check_file          # before patching: the patched name is `boom`

    def boom(path):
        if "boom" in path:
            raise ValueError("something a reader did not expect")
        return real(path)

    monkeypatch.setattr(cli, "check_file", boom)
    code = cli.main(["check", "boom.zip", str(CLEAN_DOCUMENT)])
    captured = capsys.readouterr()
    assert "something a reader did not expect" in captured.err, captured.err
    assert "0 error(s)" in captured.out, "the sweep stopped at the bad path"
    assert code == 1, "one unreadable path out of two is not a clean run"


def test_a_missing_file_still_says_what_the_os_said(capsys, monkeypatch):
    """The `strerror` was there for a reason — "No such file or directory" is
    more useful than the repr of an OSError. Fixing the crash must not lose it.
    """
    code = main(["check", "definitely-not-here.zip"])
    assert code == 2
    assert "No such file or directory" in capsys.readouterr().err


def test_the_listing_cap_does_not_soften_the_exit_code(capsys, tmp_path):
    """Everything holding the cap ran against `Report` objects built by hand.
    The claim in scope.md is about what a user sees, and the exit code is the
    half a CI job reads: a bounded listing must never become a quieter verdict.
    """
    import io
    import re
    import zipfile

    from vdi2770_validate.model import MAX_LISTED_PER_RULE

    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    meta = src.read("VDI2770_Metadata.xml").decode()
    n = MAX_LISTED_PER_RULE * 2 + 50
    one = '<DocumentId DomainId="d">x</DocumentId>'
    assert one in meta or "DocumentId" in meta, "the fixture no longer carries a DocumentId"
    flooded = re.sub(r"<DocumentId[^>]*>[^<]*</DocumentId>",
                     lambda m: m.group(0) + '<DocumentId DomainId="d"></DocumentId>' * n,
                     meta, count=1)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in src.namelist():
            z.writestr(name, flooded.encode() if name == "VDI2770_Metadata.xml" else src.read(name))
    path = tmp_path / "flood.zip"
    path.write_bytes(buf.getvalue())

    code, out = run(capsys, ["check", str(path)])
    listed = len(re.findall(r"^  error  M10 ", out, re.M))
    assert listed == MAX_LISTED_PER_RULE, f"listed {listed}"
    assert "counted below but not listed" in out
    summary = re.search(r"^  (\d+) error\(s\)", out, re.M)
    assert summary and int(summary.group(1)) > MAX_LISTED_PER_RULE, out[-400:]
    assert code == 1, "the cap must not turn errors into a clean exit"

    code, out = run(capsys, ["check", str(path), "--json"])
    payload = json.loads(out)[0]
    assert payload["summary"]["error"] > MAX_LISTED_PER_RULE
    assert len(payload["findings"]) <= MAX_LISTED_PER_RULE + 5
    assert payload["notListed"] and code == 1


def test_json_over_several_paths_is_one_document_a_parser_accepts():
    """`--json` is advertised as machine-readable and `paths` is `nargs="+"`.
    It printed one pretty-printed object per path with no separator, which is
    neither JSON nor NDJSON — and every `target` was the basename, so a sweep
    over `a/x.zip` and `b/x.zip` gave a consumer no way to tell them apart.

    `cli.py`'s own docstring names this case: "A CI job pointed at a supplier
    drop folder must come back with a verdict on every container it was given."
    """

    from conftest import CLEAN_DOCUMENT

    good = str(CLEAN_DOCUMENT)
    code, out = run(capsys_holder[0], ["check", "--json", good, good])
    doc = json.loads(out)
    assert isinstance(doc, list) and len(doc) == 2, type(doc)
    assert [d["path"] for d in doc] == [good, good], doc
    assert code == 0


def test_a_path_that_could_not_be_read_still_appears_in_the_json():
    """The unreadable one was skipped before the print, so a consumer got N-1
    documents for N paths and learned about the missing one from stderr prose."""
    from conftest import CLEAN_DOCUMENT

    good = str(CLEAN_DOCUMENT)
    code, out = run(capsys_holder[0], ["check", "--json", "no-such-file.zip", good])
    doc = json.loads(out)
    assert len(doc) == 2, doc
    missing = next(d for d in doc if d["path"] == "no-such-file.zip")
    assert missing.get("unreadable"), missing
    assert code == 1


@pytest.mark.parametrize("encoding", ["ascii", "latin-1", "cp850", "cp437"])
def test_a_console_that_is_not_utf8_still_gets_a_verdict(encoding):
    """The remedies contain an em dash, and the class names contain umlauts.

    On any console that cannot encode them -- `cp850` and `cp437` are the OEM
    defaults of Windows `cmd.exe` -- `print` raised `UnicodeEncodeError` from
    outside the handler that exists so "a CI job must come back with a verdict on
    every container it was given, not a traceback about the first one". A
    conformant container came back as a traceback and exit 1, which is this
    tool's code for *at least one error*.
    """
    done = subprocess.run(
        [sys.executable, "-m", "vdi2770_validate", "check", str(CLEAN_DOCUMENT)],
        capture_output=True, text=True, timeout=120,
        env={**under_test(), "PYTHONIOENCODING": encoding})
    assert "Traceback" not in done.stderr, done.stderr
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.parametrize("encoding", ["ascii", "cp932", "cp949", "koi8-r"])
def test_the_json_a_console_cannot_carry_is_still_json(encoding, tmp_path):
    """`--json` came back exit 0 with a payload no parser would read.

    The console handler puts `errors="backslashreplace"` on stdout, so a
    character the console cannot encode is written as `\\xNN`. For the text
    report that is the point -- it says something was there and says what. For
    `--json` it is not an escape JSON has: a member named `Prufbericht.pdf` with
    an umlaut, on a console that is not Latin-1, produced

        "member": "Pr\\xfcfbericht.pdf"

    and `json.load` stopped at *Invalid \\escape*. Exit was 0, so a CI job saw a
    clean run and a file it could not read. That is the shape this tool's own
    notes call "the interface advertised as machine-readable could not be read by
    a machine", and only U+0080-U+00FF does it: everything above gets `\\uXXXX`
    from the same handler, which JSON does accept.
    """
    src = zipfile.ZipFile(CLEAN_DOCUMENT)
    target = tmp_path / "umlaut.zip"
    with zipfile.ZipFile(target, "w") as z:
        for m in src.namelist():
            z.writestr(m, src.read(m))
        z.writestr("Pr\u00fcfbericht_\u00d6lk\u00fchler.pdf", b"%PDF-1.4\n")
    done = subprocess.run(
        [sys.executable, "-m", "vdi2770_validate", "check", "--json", str(target)],
        capture_output=True, text=True, timeout=120,
        env={**under_test(), "PYTHONIOENCODING": encoding})
    assert "Traceback" not in done.stderr, done.stderr
    doc = json.loads(done.stdout)          # the whole point
    # `ensure_ascii=False` on the way back: the escape is the wire form, and
    # what has to survive it is the name.
    assert "Pr\u00fcfbericht_\u00d6lk\u00fchler.pdf" in json.dumps(doc, ensure_ascii=False), (
        "the name did not survive the round trip")


def test_a_console_that_is_not_utf8_does_not_stop_the_sweep():
    """And the container after it is still reported. The first failure took the
    whole run down: three paths in, zero reports out."""
    done = subprocess.run(
        [sys.executable, "-m", "vdi2770_validate", "check",
         str(CLEAN_DOCUMENT), str(CLEAN_DOCUMENT), str(CLEAN_DOCUMENT)],
        capture_output=True, text=True, timeout=120,
        env={**under_test(), "PYTHONIOENCODING": "ascii"})
    assert done.stdout.count("error(s)") == 3, done.stdout + done.stderr


def test_a_reader_that_stops_reading_does_not_produce_a_traceback():
    """`vdi2770-validate check *.zip | head -1`.

    The pipe closes, `print` raises `BrokenPipeError` from outside the handler,
    and the interpreter prints two tracebacks on the way down. Exit was **120**,
    which appears in no documentation; with `--json` it was **1** -- *at least
    one error* -- for containers that had none.
    """
    import signal

    args = [sys.executable, "-m", "vdi2770_validate", "check"] + [str(CLEAN_DOCUMENT)] * 400
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=under_test())
    proc.stdout.readline()
    proc.stdout.close()
    proc.wait(timeout=120)
    err = proc.stderr.read().decode("utf-8", "replace")
    proc.stderr.close()

    assert "Traceback" not in err, err
    assert "BrokenPipeError" not in err, err
    # Killed by the signal the platform has for this, or the code a shell
    # reports for it. Never a verdict: the run did not finish, and saying 0 or 1
    # would be a claim about containers nobody looked at.
    assert proc.returncode in (-signal.SIGPIPE, 141), proc.returncode


def test_the_exit_codes_the_docstring_promises_are_the_ones_it_returns(tmp_path,
                                                                       capsys):
    """`cli`'s own first paragraph is where the exit codes are written down, and
    it said "0 nothing wrong" for a run that reports warnings and returns 0.

    A CI job reads the number, not the paragraph — but the paragraph is what a
    reader is given, and five fixtures whose whole purpose is to violate a rule
    come back 0 because the rule is a warning.
    """
    import re

    from vdi2770_validate import cli

    said = re.search(r"Exit codes: ([^.]*)\.", cli.__doc__).group(1)
    assert "0 nothing wrong" not in said, said
    assert "warning" in said, (
        f"the paragraph does not say what a warning does to the number: {said}")

    warned = FIXTURES / "f2-undeclared-file.zip"
    assert warned.exists(), "the premise"
    assert cli.main(["check", str(warned)]) == 0
    out = capsys.readouterr().out
    assert "warning(s)" in out and " 0 error(s)" in out, out


def test_quiet_hides_notes_in_both_shapes(tmp_path, capsys):
    """`--quiet` says "hide notes" and only the human shape obeyed it."""
    import json as _json

    from vdi2770_validate import cli

    box = CORPUS / "demo_vdi.zip"
    assert box.exists(), "the premise"
    cli.main(["check", "--json", "--quiet", str(box)])
    payload = _json.loads(capsys.readouterr().out)
    kinds = {f["severity"] for d in payload for f in d.get("findings", [])}
    assert "info" not in kinds, sorted(kinds)


def test_findings_are_ordered_the_way_a_reader_counts(tmp_path, capsys):
    """`Z10` sorted before `Z2` because the ids were compared as strings. The
    `rules` subcommand was fixed for exactly this and the report was not."""
    from vdi2770_validate.catalog import rule
    from vdi2770_validate.model import Finding, Location, Report, Severity

    rep = Report(target="x.zip")
    ids = ("Z2", "Z11", "Z13")
    for rid in ids:
        r = rule(rid)
        assert r.severity is Severity.ERROR, (
            f"{rid} changed severity; this test needs three of one kind")
        rep.add(Finding(r, r.title, Location(container="x.zip")))
    got = [f.rule.id for f in rep.sorted()]
    assert got == ["Z2", "Z11", "Z13"], got


def test_the_run_says_what_it_never_verifies_however_it_is_asked(capsys):
    """The one refusal this tool leads with is carried only by notes.

    `P4` and `P3` say *this tool cannot verify PDF/A conformance* on every file
    where it matters, and `--quiet` — the flag a CI log reaches for — removes
    every one of them. The README promises the tool says so on every line where
    it matters, and under that flag it says so nowhere: measured, zero mentions
    of PDF/A in the whole output.

    A statement about what this tool never does is not a finding about a
    container. It belongs to the run, said once however many paths were given,
    and it does not move a count or an exit code.
    """
    box = str(CORPUS / "demo_vdi.zip")
    for argv in (["check", box], ["check", "--quiet", box],
                 ["check", "--quiet", box, box]):
        code, out = run(capsys, argv)
        assert code == 0, out
        assert out.lower().count("pdf/a") >= 1, (
            f"{argv} says nothing about PDF/A:\n{out}")
    # Once for the run, not once per path.
    _, two = run(capsys, ["check", "--quiet", box, box])
    assert two.count("This tool does not verify PDF/A") == 1, two


def test_that_standing_line_is_not_a_finding(capsys):
    """It must not move a count, an exit code, or the JSON's finding list."""
    import json as _json

    box = str(CORPUS / "demo_vdi.zip")
    code, out = run(capsys, ["check", "--quiet", box])
    assert "0 error(s), 0 warning(s), 3 note(s)" in out, out
    assert code == 0

    code, raw = run(capsys, ["check", "--json", "--quiet", box])
    payload = _json.loads(raw)
    assert payload[0]["pdfaVerified"] is False
    assert all(f["rule"] != "PDFA" for f in payload[0]["findings"])


def test_the_standing_line_does_not_read_as_part_of_the_last_container(capsys):
    """In a sweep it printed hard against the last report's final line, where a
    reader takes it for something about that container. It is about the run."""
    box = str(CORPUS / "demo_vdi.zip")
    _, out = run(capsys, ["check", "--quiet", box, str(CORPUS / "empty.zip")])
    before = out.split("This tool does not verify")[0]
    assert before.endswith("\n\n"), repr(before[-60:])


def test_a_run_that_read_nothing_does_not_lead_with_what_it_did_not_verify(
        tmp_path, capsys):
    """Every path unreadable: the reports go to stderr and this was the only
    thing on stdout, so a log carried one sentence about PDF/A for a run that
    opened no container at all. The statement exists to stop a reader
    over-trusting a report; with no report there is nothing to over-trust."""
    code, out = run(capsys, ["check", str(tmp_path / "nope1.zip"),
                             str(tmp_path / "nope2.zip")])
    assert code == 2, out
    assert "PDF/A" not in out, out


def test_a_gate_can_choose_to_fail_on_warnings(capsys):
    """Nine rules are warnings and every one is about the container, not about
    this tool — a file the metadata does not name, a class name in a language
    this tool cannot check, an encrypted PDF. Eight containers in this
    repository come back `exit 0` carrying one.

    They are warnings on purpose: `P3` cannot be an error because this tool does
    not verify PDF/A, and `Z9` relays what the reference implementation says
    about folders. Making them errors would claim more than this tool knows. So
    the default does not move, and an intake gate that wants none of them says
    so.
    """
    warned = str(FIXTURES / "f2-undeclared-file.zip")
    clean = str(CLEAN_DOCUMENT)

    assert run(capsys, ["check", warned])[0] == 0
    assert run(capsys, ["check", "--fail-on", "warning", warned])[0] == 1
    # A container with nothing to say is still nothing to say.
    assert run(capsys, ["check", "--fail-on", "warning", clean])[0] == 0
    # And the flag does not invent an error where there is none to report.
    code, out = run(capsys, ["check", "--fail-on", "warning", warned])
    assert "1 error(s)" not in out, out
    assert "0 error(s), 1 warning(s)" in out, out


def test_the_default_is_the_one_the_page_documents(capsys):
    """`--fail-on` defaults to `error`, which is what the README says happens."""
    from conftest import ROOT

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "A warning does" in readme, "the README explains what a warning does"
    warned = str(FIXTURES / "f2-undeclared-file.zip")
    assert run(capsys, ["check", "--fail-on", "error", warned])[0] == 0
    assert run(capsys, ["check", warned])[0] == 0
