"""The promises the README makes, asserted rather than believed.

A hostile review broke this project eleven ways and `make check` stayed green
every time: the reader could be made to write every member to disk, the tool
could open a socket, the PDF/A wording could be turned into a lie, and severities
could be flipped — all without a single test failing. These are those tests.
"""
import builtins
import socket

import pytest

from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION, FIXTURES
from vdi2770_validate import report as rendering
from vdi2770_validate.catalog import rules
from vdi2770_validate.model import Severity
from vdi2770_validate.runner import check_file


def test_nothing_is_written_to_disk(monkeypatch, tmp_path):
    """README: "Nothing is extracted to disk". Nothing asserted it."""
    real_open = builtins.open
    writes = []

    def watched(file, mode="r", *a, **k):
        if any(ch in str(mode) for ch in ("w", "a", "x", "+")):
            writes.append(str(file))
        return real_open(file, mode, *a, **k)

    monkeypatch.setattr(builtins, "open", watched)
    check_file(str(CLEAN_DOCUMENTATION))
    monkeypatch.undo()
    assert not writes, f"the tool opened these for writing: {writes}"


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
    from vdi2770_validate.readers.xmlread import UnsafeXml, parse
    internal_only = (b"<!DOCTYPE r [<!ENTITY a 'aaaaaaaaaa'>]>"
                     b"<r xmlns='http://www.vdi.de/schemas/vdi2770'>&a;</r>")
    with pytest.raises(UnsafeXml):
        parse(internal_only)
