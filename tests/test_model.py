"""The value types carry the things a report needs a year later."""
from vdi2770_validate.model import About, Finding, Location, Obligation, Report, Rule, Severity


def a_rule(rid="Z1", sev=Severity.ERROR):
    return Rule(id=rid, title="t", severity=sev, obligation=Obligation.CONTAINER,
                about=About.CONTAINER,
                layer="container", remedy="Do the thing that fixes it, in a full sentence.")


def test_location_reads_like_a_jar_path():
    loc = Location(container="outer.zip!/inner.zip", member="VDI2770_Metadata.xml", line=42, column=7)
    assert str(loc) == "outer.zip!/inner.zip!/VDI2770_Metadata.xml:42:7"


def test_location_without_a_position_is_still_readable():
    assert str(Location(container="a.zip")) == "a.zip"


def test_a_finding_falls_back_to_its_rule_remedy():
    r = a_rule()
    assert Finding(r, "m", Location()).remedy == r.remedy
    assert Finding(r, "m", Location(), fix="something specific").remedy == "something specific"


def test_severity_orders_errors_first():
    assert Severity.ERROR.rank < Severity.WARNING.rank < Severity.INFO.rank


def test_report_sorts_errors_before_warnings_and_counts_them():
    rep = Report(target="x.zip")
    rep.add(Finding(a_rule("Z9", Severity.WARNING), "w", Location(container="x.zip")))
    rep.add(Finding(a_rule("Z1", Severity.ERROR), "e", Location(container="x.zip")))
    assert [f.rule.id for f in rep.sorted()] == ["Z1", "Z9"]
    assert rep.count(Severity.ERROR) == 1
    assert not rep.clean
