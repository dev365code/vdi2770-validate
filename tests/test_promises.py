"""The promises the README makes, asserted rather than believed.

Eleven ways to break this project with `make check` staying green every time: the reader could be made to write every member to disk, the tool
could open a socket, the PDF/A wording could be turned into a lie, and severities
could be flipped — all without a single test failing. These are those tests.
"""
import socket

import pytest

from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION, FIXTURES
from vdi2770_validate import report as rendering
from vdi2770_validate.catalog import rules
from vdi2770_validate.model import Severity
from vdi2770_validate.runner import check_file


def test_nothing_is_written_to_disk(monkeypatch, tmp_path):
    """README, SECURITY.md and both package READMEs: nothing is extracted to disk.

    This watched `builtins.open`. `io.open` is a second name bound to the same
    function, so a reader using it wrote sixty-four bytes for every container it
    read and the entire suite stayed green — a headline promise with a guard that
    could be stepped around by spelling. `sys.addaudithook` sees the `open` event
    whichever name reached it, and the `os.*` events that move bytes without
    opening anything at all.
    """
    from nodisk import hook_is_working, no_disk_writes

    assert hook_is_working(), "the watcher cannot see a write; it is proving nothing"

    monkeypatch.chdir(tmp_path)
    with no_disk_writes():
        check_file(str(CLEAN_DOCUMENTATION))
        check_file(str(FIXTURES / "z12-unreadable-member.zip"))
    assert not list(tmp_path.iterdir()), f"left behind: {list(tmp_path.iterdir())}"


def test_nothing_reaches_for_the_network():
    """At the interpreter's boundary, not at a name.

    The test below patches three names on the `socket` module. A caller that
    binds the constructor at import time — `from socket import socket as _sock` —
    reaches a different object, and connecting to a literal IP never consults
    `getaddrinfo`. Proved: a real `connect()` to 192.0.2.1 inside `check_bytes`
    left the whole suite green while `sys.addaudithook` recorded
    `socket.__new__` and `socket.connect`.

    This is the `io.open` lesson, which the disk promise learned and this one had
    not. Both now watch the same boundary.
    """
    from nonetwork import hook_is_working, no_network

    assert hook_is_working(), "the audit hook is not seeing sockets; nothing below means anything"
    with no_network():
        check_file(str(CLEAN_DOCUMENTATION))


def test_no_socket_is_even_attempted(monkeypatch):
    """Patching sockets to *raise* only catches a failure that escapes. A tool
    that tries the network and falls back to the bundle would pass that and fail
    this one."""
    attempts = []
    for name in ("socket", "create_connection", "getaddrinfo"):
        monkeypatch.setattr(socket, name,
                            lambda *a, _n=name, **k: attempts.append(_n))
    check_file(str(CLEAN_DOCUMENTATION))
    assert not attempts, f"the tool reached for the network: {attempts}"


PDFA_HONESTY = "this tool cannot verify PDF/A conformance"


def test_the_pdfa_wording_cannot_quietly_become_a_verdict():
    """scope.md: "Reporting a claim as a verdict would be a lie." Pin the words."""
    from vdi2770_validate.rules.pdf import UNVERIFIED
    assert UNVERIFIED == PDFA_HONESTY
    out = rendering.as_text(check_file(str(CLEAN_DOCUMENT)))
    assert PDFA_HONESTY in out
    assert "claims PDF/A" in out
    import re
    assert not re.search(r"PDF/A.{0,30}\b(valid|verified|conformant|compliant|passes)\b", out, re.I)


def test_the_json_always_says_the_claim_was_not_verified():
    import json
    for path in (CLEAN_DOCUMENT, FIXTURES / "p3-no-pdfa-claim.zip"):
        payload = json.loads(rendering.as_json(check_file(str(path))))
        assert payload["pdfaVerified"] is False
        assert "does not verify" in payload["pdfaNote"]


# Severities that carry a promise made somewhere in the documentation.
PROMISED_SEVERITY = {
    "M4": Severity.INFO,      # README: an English class name never fails a document
    "P4": Severity.INFO,      # scope.md: a claim is never a verdict
    "X3": Severity.ERROR,     # SECURITY.md: entity expansion is refused
    "Z4": Severity.ERROR,     # SECURITY.md: path traversal is refused
    "Z5": Severity.ERROR,     # SECURITY.md: over the budget is refused
    "F1": Severity.ERROR,     # a declared document that is not there
}


@pytest.mark.parametrize("rule_id,expected", sorted(PROMISED_SEVERITY.items()))
def test_a_promised_severity_cannot_be_changed_quietly(rule_id, expected):
    assert rules()[rule_id].severity is expected, (
        f"{rule_id} is documented as {expected.value}; changing it changes what the docs mean")


def test_an_entity_declaration_is_refused_even_without_an_external_reference():
    """The fixture uses an external entity, so the declaration handler — the
    thing SECURITY.md actually describes — had no coverage."""
    from vdi2770.xmlread import UnsafeXml, parse
    internal_only = (b"<!DOCTYPE r [<!ENTITY a 'aaaaaaaaaa'>]>"
                     b"<r xmlns='http://www.vdi.de/schemas/vdi2770'>&a;</r>")
    with pytest.raises(UnsafeXml):
        parse(internal_only)


def test_every_rule_count_in_prose_is_the_real_one():
    """0.1.0 shipped a changelog that said 32 rules in one line and 33 in another.

    Two things this has to get right. It must read *every* document, not three
    named ones -- the first version missed the changelog, which said "32 of
    32" for a catalogue of 33. And it must leave released changelog sections
    alone: "33 rules" under `## 0.1.0` is what was true then, and rewriting it to
    match today would be falsifying the record rather than fixing a number.
    """
    import re

    from conftest import ROOT
    from vdi2770_validate.catalog import rules

    real = len(rules())
    docs = [ROOT / "README.md", ROOT / "THIRD_PARTY.md", *sorted((ROOT / "docs").glob("*.md")),
            ROOT / "packages" / "vdi2770" / "README.md"]
    assert len(docs) >= 6, f"only found {len(docs)} documents to check"

    def current_section(text):
        heads = [m.start() for m in re.finditer(r"^## ", text, re.M)]
        return text[:heads[1]] if len(heads) > 1 else text

    changelog = ROOT / "CHANGELOG.md"
    targets = [(d, d.read_text(encoding="utf-8")) for d in docs if d.exists()]
    targets.append((changelog, current_section(changelog.read_text(encoding="utf-8"))))

    for path, text in targets:
        # A quoted count is someone being quoted -- usually this changelog quoting
        # the wrong number it once printed. Only unquoted claims are claims.
        for n in re.findall(r'(?<!")\b(\d+) rules?\b(?!")', text):
            assert int(n) == real, f"{path.name} says {n} rules; the catalogue has {real}"


def test_the_json_says_who_each_finding_is_about():
    """A machine reading the report has to be able to separate "your container is
    wrong" from "the validator declined to look". Both are errors, deliberately,
    so severity cannot carry that and the field has to."""
    import json

    from conftest import FIXTURES
    from vdi2770_validate import report as rendering
    from vdi2770_validate.runner import check_file

    payload = json.loads(rendering.as_json(check_file(str(FIXTURES / "z6-nesting-too-deep.zip"))))
    findings = payload["findings"]
    assert findings, "the fixture stopped producing findings"
    for f in findings:
        assert f["about"] in ("container", "tool"), f
    kinds = {f["rule"]: f["about"] for f in findings}
    assert kinds.get("Z6") == "tool", kinds
    assert any(v == "container" for v in kinds.values()), kinds


def test_security_md_cites_a_test_that_would_actually_notice():
    """SECURITY.md pointed at `tests/test_offline.py` for "no network access at
    all". That file patches sockets to raise, so it proves a socket failure
    escapes — not that no socket is opened. A `create_connection` wrapped in
    `except Exception: pass` inside `check_bytes` passes every test in it, and
    only `test_no_socket_is_even_attempted` goes red. A table that cites the
    weaker of two guards teaches a reader to trust the wrong one.
    """
    from conftest import ROOT

    row = [ln for ln in (ROOT / "SECURITY.md").read_text(encoding="utf-8").splitlines()
           if "Any network access at all" in ln]
    assert len(row) == 1, row
    # The strongest guard, not merely a guard. `test_offline.py` proves a socket
    # failure escapes; `test_no_socket_is_even_attempted` counts attempts at three
    # names; only the audit-hook test sees a caller that bound the constructor
    # before the patch, which was a real evasion.
    assert "test_nothing_reaches_for_the_network" in row[0], row[0]
    assert "addaudithook" in row[0], "the row should say why this guard and not the weaker one"


def test_every_test_security_md_cites_exists():
    """The table's whole value is the "where the proof is" column, and one row
    pointed at `tests/test_readers.py`, deleted when its contents moved
    into the SDK's suite. A citation to a file that is not there is worse than
    no citation: it reads as evidence.

    The row above this one is guarded by name because *which* test matters
    there. This guards every row, because whether the test exists at all is a
    question nobody was asking.
    """
    import re

    from conftest import ROOT

    prose = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    cited = re.findall(r"`((?:tests|packages)/[\w/]+\.py)(?:::(\w+))?`", prose)
    assert len(cited) >= 5, f"only found {cited}; has the table been reworded?"
    for path, func in cited:
        f = ROOT / path
        assert f.exists(), f"SECURITY.md cites {path}, which is not in this repository"
        if func:
            assert f"def {func}(" in f.read_text(encoding="utf-8"), (
                f"SECURITY.md cites {path}::{func}, which that file does not define")

    fixtures = re.findall(r"fixtures? `([\w.-]+\.zip)`", prose)
    assert fixtures, "the table cites no fixtures"
    import json
    manifest = json.loads(
        (ROOT / "tests" / "fixtures" / "MANIFEST.json").read_text(encoding="utf-8"))["fixtures"]
    for name in fixtures:
        assert name in manifest, f"SECURITY.md cites fixture {name}, which is not generated"
