"""The command line is the whole product for most users, and it had no tests at
all — which is how `classes` came to crash while `make check` stayed green.
"""
import json

from conftest import CLEAN_DOCUMENT, FIXTURES
from vdi2770_validate.cli import main


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
    payload = json.loads(out)
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
