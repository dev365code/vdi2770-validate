"""The command line is the whole product for most users, and it had no tests at
all — which is how `classes` came to crash while `make check` stayed green.
"""
import json

import pytest

from conftest import CLEAN_DOCUMENT, FIXTURES
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
