"""A layer that starts costing more than the rest of the run has to say so.

The PDF scan was quadratic once: 28 seconds on a delivery that now takes under
a second. Nothing failed -- it was still *correct*, only unusable -- so the
thing that caught it was a person waiting. This is the gate that would have.

The measurement cannot be absolute seconds. A baseline recorded on a laptop
means nothing on a CI runner, and a runner under load is slower than the same
runner idle, so an absolute ceiling is either useless or flaky. What travels is
a **ratio**: how much the whole corpus costs measured in units of one ordinary
container, both timed in the same process on the same machine in the same run.
A layer that blows up moves that ratio; a machine that is simply slower does
not.
"""
import importlib.util
import json

import pytest

from conftest import ROOT

# Loaded by path, the way this suite reaches every other tool: `tools/` is not a
# package and putting it on `sys.path` for one test would put all of it there.
_spec = importlib.util.spec_from_file_location(
    "time_budget", ROOT / "tools" / "time_budget.py")
time_budget = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(time_budget)


def test_a_ratio_inside_the_budget_passes():
    verdict = time_budget.judge(measured=10.0, baseline=10.0)
    assert verdict.ok and not verdict.warned, verdict


def test_noise_below_the_warning_line_is_not_a_finding():
    """Runners vary. A gate that fires on 5% is a gate people learn to ignore."""
    verdict = time_budget.judge(measured=11.0, baseline=10.0)
    assert verdict.ok and not verdict.warned, verdict


def test_half_again_as_expensive_warns_but_does_not_fail():
    verdict = time_budget.judge(measured=15.0, baseline=10.0)
    assert verdict.ok and verdict.warned, verdict


def test_twice_as_expensive_fails():
    verdict = time_budget.judge(measured=20.0, baseline=10.0)
    assert not verdict.ok, verdict


def test_getting_faster_never_fails():
    """A speed-up is not a regression, and a gate that pins a floor would make
    an optimisation look like a defect."""
    verdict = time_budget.judge(measured=1.0, baseline=10.0)
    assert verdict.ok and not verdict.warned, verdict


def test_a_missing_baseline_is_refused_rather_than_passed():
    """No baseline means nothing was compared. Passing would be a green light
    from a gate that did not look -- the shape this repository removes."""
    with pytest.raises(time_budget.NoBaseline):
        time_budget.judge(measured=10.0, baseline=None)


def test_the_recorded_baseline_is_a_ratio_and_not_seconds():
    """Seconds recorded on one machine would gate another, which is the thing
    the ratio exists to avoid. The file may *carry* seconds for a reader; what
    is compared has to be the ratio."""
    recorded = time_budget.load()
    assert set(recorded["budgets"]) == {"corpus_over_reference", "pdf_layer_over_reference"}
    for name, value in recorded["budgets"].items():
        assert isinstance(value, (int, float)) and value > 0, (name, value)
    assert "absolute_seconds" in recorded["recorded_on"], (
        "keep the seconds for a reader, clearly marked as not the thing compared")


def test_the_gate_run_as_a_command_fails_when_the_budget_is_exceeded(tmp_path, monkeypatch, capsys):
    """`judge()` being right is not the same as the gate saying so.

    A sibling gate in this repository once had a tested `judge()` and a `main()`
    that threw the judgement away, and everything stayed green. So this runs the
    command, against a budget small enough that this machine cannot meet it.
    """
    budget = tmp_path / "time-budget.json"
    budget.write_text(json.dumps({
        "budgets": {"corpus_over_reference": 1.0, "pdf_layer_over_reference": 1.0},
        "recorded_on": {"absolute_seconds": {}}}), encoding="utf-8")
    monkeypatch.setattr(time_budget, "BUDGET_FILE", budget)
    assert time_budget.main(["--check"]) == 1, "the budget was impossible and the gate passed"
    assert "got slower" in capsys.readouterr().err


def test_the_gate_run_as_a_command_passes_a_budget_it_meets(tmp_path, monkeypatch):
    """The other direction, so the test above cannot pass by the gate always
    failing -- which would be just as useless and much easier to miss."""
    budget = tmp_path / "time-budget.json"
    budget.write_text(json.dumps({
        "budgets": {"corpus_over_reference": 10 ** 9, "pdf_layer_over_reference": 10 ** 9},
        "recorded_on": {"absolute_seconds": {}}}), encoding="utf-8")
    monkeypatch.setattr(time_budget, "BUDGET_FILE", budget)
    assert time_budget.main(["--check"]) == 0
