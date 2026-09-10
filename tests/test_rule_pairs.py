"""Gate 1 — every rule has a violating example and a conforming one.

A rule with no failing fixture has never been seen to work. A rule that also
fires on the conforming container is not about what it claims to be about.
"""
import json

import pytest
from vdi2770_validate.catalog import rules
from vdi2770_validate.runner import check_file

from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION, FIXTURES, ROOT

MANIFEST = json.loads((FIXTURES / "MANIFEST.json").read_text(encoding="utf-8"))["fixtures"]
CLEAN = {"documentcontainer.zip": CLEAN_DOCUMENT, "documentationcontainer.zip": CLEAN_DOCUMENTATION}


def fired(path):
    """Every rule that fired on `path`, or a refusal to answer if a check crashed.

    X5 is this tool saying that a check of its own raised and did not finish. A
    set with X5 in it still holds the rule a fixture was built for, so every
    case below passed while some check it exercised was dying on it -- the pair
    read green over a crash.
    """
    ids = {f.rule.id for f in check_file(str(path)).findings}
    assert "X5" not in ids, (
        f"{path.name}: a check crashed on it (X5), so what fired is not a verdict: "
        f"{sorted(ids)}")
    return ids


@pytest.mark.parametrize("name,meta", sorted(MANIFEST.items()))
def test_fixture_fires_its_rule(name, meta):
    ids = fired(FIXTURES / name)
    assert meta["rule"] in ids, f"{name} was built to trigger {meta['rule']} but fired {sorted(ids)}"


@pytest.mark.parametrize("name,meta", sorted(MANIFEST.items()))
def test_conforming_container_does_not_fire_it(name, meta):
    if meta["basedOn"] is None:
        pytest.skip("not derived from a corpus container")
    ids = fired(CLEAN[meta["basedOn"]])
    assert meta["rule"] not in ids, (
        f"{meta['rule']} also fires on the conforming {meta['basedOn']}, so the fixture "
        f"does not isolate it")


def test_clean_containers_have_no_errors():
    from vdi2770_validate.model import Severity
    for p in CLEAN.values():
        rep = check_file(str(p))
        errs = [f for f in rep.findings if f.severity is Severity.ERROR]
        assert not errs, f"{p.name} should be clean, got {[(f.rule.id, f.detail) for f in errs]}"


def test_every_rule_has_a_fixture_or_a_reason(monkeypatch):
    """A rule needs a violating container, or a corpus example, or a written
    reason why no container can cause it."""
    # syspath_prepend, not sys.path.insert: a test that leaves the import path
    # altered decides what later tests can import.
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    from rule_coverage import CANNOT_FIRE
    from tools_shim import corpus_fired
    covered = {m["rule"] for m in MANIFEST.values()}
    missing = sorted(set(rules()) - covered - corpus_fired() - set(CANNOT_FIRE))
    assert not missing, f"rules with neither a fixture nor a corpus example: {missing}"
    for rule_id, why in CANNOT_FIRE.items():
        assert rule_id in rules(), f"{rule_id} is excused but does not exist"
        assert len(why) > 40, f"{rule_id} is excused without a real reason"



def test_a_crash_is_not_read_as_a_verdict(monkeypatch):
    """`fired` answers for every fixture in this file, and each case asks only
    whether one rule is in the set. A crash elsewhere in the run does not take
    that rule out of it, so nothing here would notice one unless `fired`
    refuses to answer."""
    from vdi2770_validate import runner

    def explodes(*a, **kw):
        raise RuntimeError("a check fell over")

    monkeypatch.setattr(runner.zipread, "read", explodes)
    with pytest.raises(AssertionError, match="X5"):
        fired(CLEAN_DOCUMENT)
