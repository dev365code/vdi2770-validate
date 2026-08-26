"""One rule's exception must not kill the run — it is demoted to that rule's
finding.

It killed the run. A batch over a supplier's delivery died on one archive with a
traceback naming this tool's internals, and every container after it went
unchecked. A validator that stops at the first surprise has the failure mode it
exists to prevent.
"""
import pytest

from conftest import CLEAN_DOCUMENT, CLEAN_DOCUMENTATION
from vdi2770_validate import runner
from vdi2770_validate.model import About, Severity


class Surprise(Exception):
    """Deliberately not a builtin, and in no hierarchy a guard might name.

    These tests first raised a builtin arithmetic error, so narrowing
    `except Exception` to `except ArithmeticError` still passed them: they could
    not tell "catches anything" from "catches arithmetic". The claim being made
    is *anything*, so the exception has to be something nobody anticipated.
    """


MODULES = ["r_container", "r_schema", "r_files", "r_metadata", "r_pdf"]

# The three steps that run *before* the rules, and were outside every guard when
# the guard was written: the rules were wrapped and the things feeding them were
# not. `xmlread.parse` was half-guarded — the runner caught `XmlError` and
# nothing else, so any other surprise from expat escaped.
STEPS = [
    ("xmlread parse", "vdi2770_validate.runner", "xmlread", "parse"),
    ("domain build", "vdi2770_validate.runner", None, "build"),
    ("schema validate", "vdi2770_validate.xsdvalidate", None, "validate"),
]


def exploding(*a, **k):
    raise Surprise("an input its author did not imagine")
    yield                                    # noqa: unreachable — makes it a generator


def partial(*a, **k):
    from vdi2770_validate.catalog import rule
    from vdi2770_validate.model import Finding, Location
    yield Finding(rule("Z9"), "first", Location(container="x.zip"))
    raise Surprise("after yielding one")


@pytest.mark.parametrize("mod", MODULES)
def test_every_rule_module_is_guarded(monkeypatch, mod):
    monkeypatch.setattr(runner, mod, type("M", (), {"check": staticmethod(exploding)}))
    report = runner.check_file(str(CLEAN_DOCUMENTATION))
    crashes = [f for f in report.findings if f.rule.about is About.TOOL
               and "Surprise" in (f.detail or "")]
    assert crashes, f"{mod} crashed and the report does not say so: {sorted(f.rule.id for f in report.findings)}"
    assert crashes[0].severity is Severity.ERROR, "we did not finish; exit 0 would be a lie"
    assert mod.replace("r_", "") in (crashes[0].detail or ""), crashes[0].detail


def test_the_other_rules_still_run(monkeypatch):
    monkeypatch.setattr(runner, "r_metadata",
                        type("M", (), {"check": staticmethod(exploding)}))
    fired = {f.rule.id for f in runner.check_file(str(CLEAN_DOCUMENT)).findings}
    assert "P4" in fired, f"a crash in one module silenced the others: {sorted(fired)}"


def test_what_the_rule_managed_to_say_is_kept(monkeypatch):
    monkeypatch.setattr(runner, "r_container",
                        type("M", (), {"check": staticmethod(partial)}))
    report = runner.check_file(str(CLEAN_DOCUMENT))
    ids = [f.rule.id for f in report.findings]
    assert "Z9" in ids, f"the finding it produced before crashing was thrown away: {ids}"
    assert not report.clean, "a crashed rule cannot leave the verdict clean"


@pytest.mark.parametrize("what,module,attr,name", STEPS,
                         ids=[c[0] for c in STEPS])
def test_every_step_before_the_rules_is_guarded_too(monkeypatch, what, module, attr, name):
    """A crash here killed the run just as dead as a crash in a rule, and the
    parametrize list above covered only the rules."""
    import importlib

    target = importlib.import_module(module)
    if attr:
        target = getattr(target, attr)
    monkeypatch.setattr(target, name, exploding_call)

    report = runner.check_file(str(CLEAN_DOCUMENT))
    crashes = [f for f in report.findings
               if f.rule.about is About.TOOL and "Surprise" in (f.detail or "")]
    assert crashes, (
        f"{what} crashed and the report does not say so: "
        f"{sorted(f.rule.id for f in report.findings)}")
    assert crashes[0].severity is Severity.ERROR
    assert not report.clean


def exploding_call(*a, **k):
    raise Surprise("an input its author did not imagine")


def test_the_reader_crashing_is_a_finding_too(monkeypatch):
    """`_into` guards the rules and `_step` guards what feeds them. Three calls
    into the reader sat outside both: `zipread.read`, `zipread.member_bytes` and
    `nfc`.

    The reader's contract is that it records a `Defect` rather than raising, and
    it is tested against that — but it is a *separately versioned package*, and
    the validator's pin admits releases nobody here has run. The failure mode is
    the exact one `_into` exists to prevent: a traceback naming this tool's
    internals, and every container after it in the batch unchecked.
    """
    def explodes(*a, **kw):
        raise Surprise("the reader fell over")

    monkeypatch.setattr(runner.zipread, "read", explodes)
    report = runner.check_bytes(CLEAN_DOCUMENT.read_bytes(), "boom.zip")

    fired = [f for f in report.findings if f.rule.id == "X5"]
    assert fired, f"the reader raised and the report says {[f.rule.id for f in report.findings]}"
    assert "Surprise" in (fired[0].detail or ""), fired[0].detail
    assert report.count(Severity.ERROR), "a run that checked nothing must not exit 0"


def test_reading_a_member_crashing_does_not_kill_the_walk(monkeypatch):
    """The same door, one level in: `member_bytes` is called for every nested
    container and for every PDF, and neither call was wrapped.

    Written first against `CLEAN_DOCUMENT`, which has **no inner containers** —
    so the line under test never ran, and the X5 it asserted on came from the
    PDF facts, caught by `_into`. Deleting the guard left the whole suite green
    while a real crash escaped `check_bytes` as a traceback. Two things fix it:
    a container that actually nests, and matching the finding by what it says
    rather than by its rule id.
    """
    def explodes(*a, **kw):
        raise Surprise("the reader fell over")

    monkeypatch.setattr(runner.zipread, "member_bytes", explodes)
    # documentationcontainer.zip carries documentcontainer.zip inside it.
    report = runner.check_bytes(CLEAN_DOCUMENTATION.read_bytes(), "boom.zip")

    said = [f.detail or "" for f in report.findings if f.rule.id == "X5"]
    assert any("the member read step:" in d for d in said), (
        f"nothing reports the member read; the X5s say {said}")
    assert any("Surprise" in d for d in said), said


def test_when_nothing_was_checked_the_remedy_does_not_say_the_rest_stands(monkeypatch):
    """X5's remedy ends *"Every other finding in this report still stands; only
    the named check did not run."* That is true of a rule that crashed among
    thirty that did not. It is false of the container read, which is the step
    every other check is downstream of: when it raises there are no other
    findings, nothing ran, and the report a user gets is one X5 saying the rest
    of it holds.

    A validator that reports "checked, and here is what stands" for an archive it
    never opened has the failure mode it exists to prevent.
    """
    def explodes(*a, **kw):
        raise Surprise("the reader fell over")

    monkeypatch.setattr(runner.zipread, "read", explodes)
    report = runner.check_bytes(CLEAN_DOCUMENT.read_bytes(), "boom.zip")

    only = [f for f in report.findings if f.rule.id == "X5"]
    assert len(only) == 1 and len(report.findings) == 1, [f.rule.id for f in report.findings]
    assert "still stands" not in only[0].remedy, (
        f"nothing else was checked, and the remedy says otherwise: {only[0].remedy!r}")
    assert "nothing in it was checked" in only[0].remedy.lower(), only[0].remedy
