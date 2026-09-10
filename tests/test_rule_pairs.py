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
    """Every rule that fired on `path`, or a refusal to answer if a check
    crashed and said so.

    X5 is this tool saying that a check of its own raised and did not finish. A
    set with X5 in it still holds the rule a fixture was built for, so a case
    below could pass while some check it exercised was dying on it -- the pair
    reading green over a crash. A crash reported some other way is not seen here.
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
    whether one rule is in the set. A crash in one layer leaves every other
    layer's rules in it: here the pdf checks raise under a fixture built for a
    metadata rule, and that rule still fires beside X5.

    The first version crashed the read of the whole container, which leaves X5
    alone in the set -- a case most of the tests here already fail, and one a
    guard refusing only a run that found nothing else would pass too.
    """
    from vdi2770_validate import runner

    def explodes(*a, **kw):
        raise RuntimeError("a check fell over")
        yield                     # never reached: it makes this a generator, as the checks are

    monkeypatch.setattr(runner.r_pdf, "check", explodes)
    name = "m1-no-vdi-classification.zip"
    ids = {f.rule.id for f in check_file(str(FIXTURES / name)).findings}
    assert {"M1", "X5"} <= ids, f"the premise, the rule firing beside the crash: {sorted(ids)}"
    with pytest.raises(AssertionError, match="a check crashed on it"):
        fired(FIXTURES / name)
    # And through the case itself. A guard that moved to where the cases call
    # `fired` -- or a case that stopped calling it -- passes the helper above
    # and lets this one read green over the crash.
    with pytest.raises(AssertionError, match="a check crashed on it"):
        test_fixture_fires_its_rule(name, MANIFEST[name])
