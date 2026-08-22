"""Gate 1 — every rule has a violating example and a conforming one.

A rule with no failing fixture has never been seen to work. A rule that also
fires on the conforming container is not about what it claims to be about.
"""
import json

import pytest

from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION, FIXTURES
from vdi2770_validate.catalog import rules
from vdi2770_validate.runner import check_file

MANIFEST = json.loads((FIXTURES / "MANIFEST.json").read_text(encoding="utf-8"))["fixtures"]
CLEAN = {"documentcontainer.zip": CLEAN_DOCUMENT, "documentationcontainer.zip": CLEAN_DOCUMENTATION}


def fired(path):
    return {f.rule.id for f in check_file(str(path)).findings}


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


def test_every_rule_has_a_fixture_or_a_reason():
    covered = {m["rule"] for m in MANIFEST.values()}
    from tools_shim import corpus_fired
    missing = sorted(set(rules()) - covered - corpus_fired())
    assert not missing, f"rules with neither a fixture nor a corpus example: {missing}"
