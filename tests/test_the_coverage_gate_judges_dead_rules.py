"""README: "A rule that fires nowhere fails the build."

It did not. `rule_coverage --check` computed `unexercised` and never looked at
it, so `--write` followed by `--check` reported "ok ... 1 unexercised", exit 0 —
the baseline blessing exactly the thing the tool exists to catch.
"""
import pytest

from conftest import ROOT
from vdi2770_validate.catalog import rules


@pytest.fixture
def rule_coverage(monkeypatch):
    # syspath_prepend puts it back afterwards; the module itself stays cached in
    # sys.modules, so this costs one import for the whole file.
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    import rule_coverage as mod
    return mod

ALL = {"Z1", "Z2", "Z3"}
EXCUSED = {"Z3": "only fires when the installation is broken"}


def baseline(**over):
    b = {"rules": 3, "fired": ["Z1", "Z2"], "cannotFire": EXCUSED}
    b.update(over)
    return b


def judge(rule_coverage, fired, base=None, excused=EXCUSED, about_the_tool=None):
    # The synthetic catalogue's Z3 is not the real Z3; an excused rule in these
    # tests is a stand-in for a tool-failure rule, so say so rather than let the
    # real catalogue answer a question about a made-up one.
    return rule_coverage.judge(ALL, fired, base or baseline(), cannot_fire=excused,
                               about_the_tool=about_the_tool or (lambda rid: True))


def test_a_rule_that_fires_nowhere_fails_the_build(rule_coverage):
    problems = judge(rule_coverage, {"Z1"}, baseline(fired=["Z1"]))
    assert any("Z2" in p and "fire nowhere" in p for p in problems), problems


def test_the_baseline_cannot_bless_a_dead_rule(rule_coverage):
    # This is the exact escape that existed: record it and it goes quiet.
    problems = judge(rule_coverage, {"Z1"}, baseline(fired=["Z1"], unexercised=["Z2"]))
    assert any("fire nowhere" in p for p in problems), problems


def test_an_excused_rule_is_not_a_dead_rule(rule_coverage):
    assert judge(rule_coverage, {"Z1", "Z2"}) == []


def test_the_excuse_has_to_be_the_one_the_baseline_recorded(rule_coverage):
    """The reason *is* the excuse, and only the keys were compared.

    The version of this test that passed here passed because it also added a
    key: `{"Z3": "different reason", "Z9": "new"}` goes red on `Z9` whether or
    not the reason is looked at. Isolating the variable is the whole job —
    rewriting X0's excuse from "no container can cause it" to "nobody has got
    round to it" left the build green.
    """
    same_keys = judge(rule_coverage, {"Z1", "Z2"},
                      excused={"Z3": "nobody has got round to writing a fixture"})
    assert any("excused set moved" in p for p in same_keys), same_keys
    assert any("reasons rewritten for ['Z3']" in p for p in same_keys), same_keys


def test_an_added_excuse_is_caught_too(rule_coverage):
    problems = judge(rule_coverage, {"Z1", "Z2"},
                     excused={"Z3": EXCUSED["Z3"], "Z9": "new"})
    assert any("excused set moved" in p and "Z9" in p for p in problems), problems


def test_a_rule_that_stops_firing_is_a_regression(rule_coverage):
    problems = judge(rule_coverage, {"Z1"}, baseline(fired=["Z1", "Z2"]), excused={"Z2": "x", "Z3": "y"})
    assert any("no longer do" in p and "Z2" in p for p in problems), problems


def test_a_new_rule_makes_the_count_disagree(rule_coverage):
    problems = judge(rule_coverage, {"Z1", "Z2"}, baseline(rules=2))
    assert any("the catalogue has 3 rules" in p for p in problems), problems


def test_the_checked_in_baseline_holds_no_dead_rules():
    """The gate above is worth nothing if the artifact it guards already carries
    what it forbids. This is the state the repository is actually in."""
    import json
    baseline = json.loads((ROOT / "docs" / "rule-coverage.json").read_text(encoding="utf-8"))
    assert baseline["unexercised"] == [], baseline["unexercised"]
    assert set(baseline["fired"]) | set(baseline["cannotFire"]) == set(rules())


def test_the_gate_run_as_a_command_uses_its_own_judgement(tmp_path):
    """Every test above calls `judge()` directly. Nothing ran the tool.

    So `main()` could compute the judgement and drop it — one line, `problems =
    []` — and the command exited 0, the whole suite passed, and the mutation
    table reported everything caught. A gate is what it does when you run it.

    And a subprocess has to be *able* to run it. This spawned the copy with
    whatever `sys.path` the ambient installation gave it; on a machine where
    this package is not installed the copy died on its own import, exited 1 for
    that reason, and printed a traceback whose source line reads `import rules`
    — which satisfied both assertions. The gate never ran, the mutation that
    blanks the judgement survived, and the table reported it. So the path is
    handed over explicitly now, and the sentence asserted is one only the
    judgement produces.
    """
    import json
    import shutil
    import subprocess
    import sys

    from conftest import ROOT, under_test

    tool = tmp_path / "rule_coverage.py"
    shutil.copy(ROOT / "tools" / "rule_coverage.py", tool)
    text = tool.read_text(encoding="utf-8")

    # A baseline that the real catalogue cannot satisfy: it claims a rule count
    # that is wrong, which `judge()` reports and `main()` must act on.
    baseline = json.loads((ROOT / "docs" / "rule-coverage.json").read_text(encoding="utf-8"))
    baseline["rules"] = baseline["rules"] + 7
    bad = tmp_path / "rule-coverage.json"
    bad.write_text(json.dumps(baseline), encoding="utf-8")
    swapped = text.replace('BASELINE = ROOT / "docs" / "rule-coverage.json"',
                           f'BASELINE = Path({str(bad)!r})')
    assert swapped != text, "the gate no longer names its baseline that way"
    tool.write_text(swapped, encoding="utf-8")

    # The copy's own `ROOT` would be `tmp_path`'s parent, where there is no
    # corpus to observe; point it back so the gate looks at the real tree. Both
    # substitutions are asserted, because `str.replace` on a miss is a silent
    # no-op and this test's whole subject is a check that passed without
    # running — the discipline the mutation table applies to its own anchors.
    anchored = tool.read_text(encoding="utf-8").replace(
        "ROOT = Path(__file__).resolve().parent.parent",
        f"ROOT = Path({str(ROOT)!r})")
    assert "ROOT = Path(__file__)" not in anchored, "the gate no longer sets ROOT that way"
    tool.write_text(anchored, encoding="utf-8")
    env = under_test()
    done = subprocess.run([sys.executable, str(tool), "--check"],
                          cwd=ROOT, capture_output=True, text=True, env=env)
    assert done.returncode == 1, (
        f"the gate ran with a baseline it disagrees with and exited "
        f"{done.returncode}: {done.stdout} {done.stderr}")
    # `judge()`'s own sentence, which an import error cannot counterfeit.
    assert "the catalogue has" in (done.stderr or ""), done.stderr


def test_an_excuse_is_only_available_to_a_rule_about_this_tool(rule_coverage):
    """`CANNOT_FIRE` was both the requirement and the exemption: one sentence in
    the tool removed a rule from its own gate, and the only quality check was
    that the sentence was long. Reproduced — deleting `M9`'s fixture and adding
    "nobody has got round to it" left every gate green.

    The claim a row makes is "no container can cause this". That is coherent only
    for a rule that is about this tool rather than about a container, and
    `rules.json` already records which is which.
    """
    from vdi2770_validate.catalog import rules
    from vdi2770_validate.model import About

    for rid in rule_coverage.CANNOT_FIRE:
        assert rules()[rid].about is About.TOOL, (
            f"{rid} is about the container and is excused from firing anywhere")

    problems = rule_coverage.judge(
        {"Z1", "M9"}, {"Z1"}, {"rules": 2, "fired": ["Z1"], "cannotFire": {"M9": "x" * 50}},
        cannot_fire={"M9": "x" * 50}, about_the_tool=lambda rid: False)
    assert any("about the container" in p for p in problems), problems


def test_the_observer_actually_runs_the_tool(rule_coverage):
    """`judge()` is tested eight ways. `observe()` — the half that runs this tool
    over every corpus and fixture container — had no test at all, so it could be

        return Counter(json.loads(BASELINE.read_text())["fired"])

    and the gate would compare the baseline to itself, forever green. That is the
    same shape as the bug this file commemorates, one function upstream.

    Checked against facts the baseline does not carry: how many times each rule
    fired, and on a container the baseline never mentions.
    """
    import json

    fired = rule_coverage.observe()
    assert fired, "the observer saw nothing"

    baseline = json.loads((ROOT / "docs" / "rule-coverage.json").read_text(encoding="utf-8"))
    # The baseline stores a sorted list of ids and no counts. A parrot can only
    # ever produce one each.
    assert any(n > 1 for n in fired.values()), (
        "every rule fired exactly once, which is what reading the baseline back "
        "would produce — the observer is not running anything")
    assert set(fired) == set(baseline["fired"]), sorted(set(fired) ^ set(baseline["fired"]))

    # And it must see a container, not a file of names: P4 fires once per PDF
    # that claims a level, which is a count only a real run knows.
    from conftest import CORPUS
    from vdi2770_validate.runner import check_file
    live = sum(1 for f in check_file(str(CORPUS / "container" / "documentcontainer.zip")).findings
               if f.rule.id == "P4")
    assert live >= 1 and fired.get("P4", 0) >= live, (
        f"the observer reports {fired.get('P4', 0)} P4 findings; one container alone has {live}")
