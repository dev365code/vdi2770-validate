"""When the tool cannot do its job, it must say so — not blame the container.

The class: a limitation of this program reported as a finding about someone
else's document, at error severity, which exits 1 in their CI. A missing
dependency was being reported as "your metadata does not conform to the schema",
with a remedy telling the reader to go and edit a line that is perfectly fine.
"""
import pytest

from conftest import CLEAN_DOCUMENT
from vdi2770_validate.catalog import rules
from vdi2770_validate.model import Obligation, Severity
from vdi2770_validate.runner import check_file


def test_a_broken_installation_is_not_a_schema_violation(monkeypatch):
    from vdi2770_validate import xsdvalidate

    def no_schema():
        raise ImportError("No module named 'xmlschema'")

    monkeypatch.setattr(xsdvalidate, "_schema", no_schema)
    ids = {f.rule.id for f in check_file(str(CLEAN_DOCUMENT)).findings}
    assert "X2" not in ids, "a missing dependency was reported as a schema violation"
    assert "X0" in ids, f"and nothing said the check could not run: {sorted(ids)}"


def test_the_could_not_run_finding_points_at_the_tool_not_the_document(monkeypatch):
    from vdi2770_validate import xsdvalidate

    monkeypatch.setattr(xsdvalidate, "_schema",
                        lambda: (_ for _ in ()).throw(ImportError("no xmlschema")))
    found = [f for f in check_file(str(CLEAN_DOCUMENT)).findings if f.rule.id == "X0"]
    assert found
    remedy = found[0].remedy.lower()
    assert "install" in remedy or "environment" in remedy, remedy
    assert "correct the element" not in remedy


@pytest.mark.parametrize("rule_id", ["P2", "P3", "X0", "Z5", "Z6"])
def test_a_rule_about_our_own_limits_says_so(rule_id):
    """`container` means "mechanics of ZIP and XML that hold without knowing
    VDI 2770 at all". A byte scan for /Encrypt is neither."""
    r = rules()[rule_id]
    assert r.obligation is not Obligation.CONTAINER, (
        f"{rule_id} is tagged `container`, which its own definition does not cover")
    if r.obligation is Obligation.OURS:
        assert r.why_ours


@pytest.mark.parametrize("rule_id", ["P2", "P3"])
def test_a_pattern_match_does_not_carry_error_severity(rule_id):
    """scope.md admits both of these can be wrong. A finding that can be wrong
    in both directions should not fail someone's build on its own."""
    assert rules()[rule_id].severity is Severity.WARNING
