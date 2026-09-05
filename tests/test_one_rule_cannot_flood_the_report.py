"""One rule can fire once per element. A crafted file makes that four hundred
thousand times, and the report used to hold every one of them: 923 MB of memory
and 107 MB of output for a 127 KB archive. The listing is now bounded; the
count is not, so the summary and the exit code still tell the truth."""
import json

from conftest import counts_line
from vdi2770_validate.model import (
    MAX_LISTED_PER_RULE,
    About,
    Finding,
    Location,
    Obligation,
    Report,
    Rule,
    Severity,
)
from vdi2770_validate.report import as_json, as_text


def a_rule(rid="M10", sev=Severity.ERROR):
    return Rule(id=rid, title="t", severity=sev, obligation=Obligation.PUBLISHED_TABLE,
                about=About.CONTAINER, layer="metadata",
                remedy="Do the thing that fixes it, in a full sentence.")


def flood(rep, n, rid="M10", sev=Severity.ERROR, container="x.zip"):
    r = a_rule(rid, sev)
    for i in range(n):
        rep.add(Finding(r, f"finding {i}", Location(container=container, line=i)))


N = MAX_LISTED_PER_RULE * 3


def test_the_listing_is_bounded_but_the_count_is_not():
    rep = Report(target="x.zip")
    flood(rep, N)
    assert len(rep.findings) == MAX_LISTED_PER_RULE
    assert rep.count(Severity.ERROR) == N          # every one still counted
    assert not rep.clean                           # so the exit code is still 1
    assert rep.suppressed == {("M10", "x.zip"): N - MAX_LISTED_PER_RULE}


def test_the_budget_is_per_rule_and_per_container():
    rep = Report(target="outer.zip")
    flood(rep, N, rid="M10", container="a.zip")
    flood(rep, N, rid="M10", container="b.zip")    # a second container, its own budget
    flood(rep, N, rid="M2", container="a.zip")     # a second rule, its own budget
    assert len(rep.findings) == MAX_LISTED_PER_RULE * 3
    assert rep.count(Severity.ERROR) == N * 3
    assert sorted(rep.suppressed) == [("M10", "a.zip"), ("M10", "b.zip"), ("M2", "a.zip")]


def test_the_text_says_what_it_did_not_list_and_agrees_with_its_own_summary():
    rep = Report(target="x.zip")
    flood(rep, N)
    out = as_text(rep)
    assert out.count("  error  M10  ") == MAX_LISTED_PER_RULE
    assert f"... {N - MAX_LISTED_PER_RULE} more M10 findings in x.zip" in out
    assert f"  {N} error(s)," in out               # the summary counts all of them


def test_a_quiet_run_does_not_announce_notes_it_is_not_printing():
    # --quiet hides notes. Announcing "... 200 more X2 findings" while printing
    # none of them, and then a note count of zero, is the report contradicting
    # itself twice over.
    rep = Report(target="x.zip")
    flood(rep, N, rid="X2", sev=Severity.INFO)
    out = as_text(rep, show_info=False)
    assert "more X2 findings" not in out
    assert f"({N} note(s) not shown)" in out       # not the capped 100
    assert f", {N} note(s)" in out
    assert "more X2 findings" in as_text(rep, show_info=True)


def test_the_json_carries_the_unlisted_count_next_to_the_summary():
    rep = Report(target="x.zip")
    flood(rep, N)
    doc = json.loads(as_json(rep))
    assert doc["summary"]["error"] == N
    assert len(doc["findings"]) == MAX_LISTED_PER_RULE
    assert doc["notListed"] == [
        {"rule": "M10", "container": "x.zip", "count": N - MAX_LISTED_PER_RULE}]


def test_a_report_under_the_budget_says_nothing_about_unlisted_findings():
    rep = Report(target="x.zip")
    flood(rep, MAX_LISTED_PER_RULE)                # exactly at the cap, none dropped
    assert rep.suppressed == {}
    assert "not listed" not in as_text(rep)
    assert json.loads(as_json(rep))["notListed"] == []


def _tool_rule():
    """The first `about: tool` error in the catalogue, whatever it is called."""
    import json

    from conftest import ROOT
    from vdi2770_validate.catalog import rule as by_id

    catalogue = json.loads(
        (ROOT / "src" / "vdi2770_validate" / "data" / "rules.json").read_text(encoding="utf-8"))
    for entry in catalogue["rules"]:
        if entry["about"] == "tool" and entry["severity"] == "error":
            return by_id(entry["id"])
    raise AssertionError("no about:tool error in the catalogue")


def test_the_axis_count_survives_the_listing_cap():
    """The summary counts every error and counted only the errors it printed.

    `count()` adds the findings the listing cap withheld — the comment above it
    says why: "the listing is capped, the count is not, and printing the capped
    number over an uncapped summary contradicts it". The sentence naming how
    many of those errors are this tool declining to look was written an hour
    later and walked `findings`, which is the capped list. So a container with
    150 tool-axis errors read `150 error(s) … 100 of the errors are this tool
    declining to look`, and a supplier took the other 50 as theirs.
    """
    from vdi2770_validate.model import About, Finding, Location, Report, Severity
    from vdi2770_validate.report import as_text

    rule = _tool_rule()
    report = Report(target="deep.zip")
    for _ in range(150):
        report.add(Finding(rule, rule.title, Location(container="deep.zip")))

    assert report.count(Severity.ERROR) == 150, report.count(Severity.ERROR)
    summary = counts_line(as_text(report, True))
    assert "150 error(s)" in summary, summary
    assert "150 of the errors" in summary, (
        f"the axis was counted over the listing, not the count: {summary}")
    assert About.TOOL is not None


def test_quiet_hides_the_same_notes_from_both_shapes():
    """`--quiet` hides notes. The text renderer asks `not_listed(show_info)` and
    the JSON one asked `not_listed()`, so a quiet run carried no findings and a
    machine-readable count of findings it had not listed — one document
    contradicting itself in two adjacent keys.

    `Report.not_listed` already takes the filter and says why: *"Honours the
    same INFO filter the listing does, so a quiet run does not announce notes it
    is not printing."* One of its two callers passed it.
    """
    rep = Report(target="x.zip")
    flood(rep, N, rid="P4", sev=Severity.INFO)

    loud = json.loads(as_json(rep, True))
    assert loud["notListed"], "the premise: this report must overflow the cap"

    quiet = json.loads(as_json(rep, False))
    assert quiet["findings"] == [], "the premise: --quiet leaves no notes listed"
    assert quiet["notListed"] == [], (
        f"a quiet run listed no findings and announced "
        f"{quiet['notListed']} it did not list")
    # And the two shapes agree, which is the whole of it.
    assert ("..." in as_text(rep, False)) is bool(quiet["notListed"])
