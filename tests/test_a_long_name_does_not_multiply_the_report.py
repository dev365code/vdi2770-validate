"""A finding carries the path of the container it is in, and the listing keeps a
hundred findings per rule *per container*. A member name may be 65,535 bytes
long, and a container that holds others repeats its name in every one of their
paths -- so what a report printed grew with the number of containers, times a
hundred, times the length of a name the sender chose. `MAX_CONTAINERS` bounds
the first factor; nothing bounded the product.

Each rule's listing now stops at a size budget, applied where findings are
collected rather than where they are printed, so a report that will not be
printed does not hold them either. What the budget turns away is counted, not
kept: the summary and the exit code are the same with it and without it, and
both shapes of the report say how many there were and how many are listed.
"""
import io
import json
import zipfile

import pytest
from vdi2770_validate.model import (
    LISTING_BUDGET_PER_RULE,
    About,
    Finding,
    Location,
    Obligation,
    Report,
    Rule,
    Severity,
    listed_size,
)
from vdi2770_validate.report import as_json, as_text
from vdi2770_validate.runner import check_file

import vdi2770.validate.model as model
from conftest import CORPUS, FIXTURES, ROOT, counts_line

#: As long as a member name can be, less the `.zip` it ends in.
LONG = 65_531

#: What the tests use. The report grows with the name the same way at any
#: length, and at this one an unbounded run takes seconds rather than minutes:
#: printing the text shape walks the name once per finding.
NAME = 8_000

ANCHOR = '<DocumentId DomainId="BSP-OEM">data-sheet-br-01-26</DocumentId>'


def _under_a_long_name(directory, containers, name_len, empties, char="M"):
    """`containers` document containers inside one container whose name is
    `name_len` characters long, each declaring `empties` empty `DocumentId`s.

    Every one of those is an `M10`, every `M10` carries its container's path,
    and every path begins with the long name. The archive holds that name once.
    """
    with zipfile.ZipFile(CORPUS / "container" / "documentcontainer.zip") as z:
        meta = next(n for n in z.namelist() if n.endswith("VDI2770_Metadata.xml"))
        text = z.read(meta).decode("utf-8")
    assert text.count(ANCHOR) == 1, "the sample no longer declares the anchor once"
    declared = text.replace(
        ANCHOR, ANCHOR + '<DocumentId DomainId="BSP-OEM"></DocumentId>' * empties)
    assert declared != text

    def child():
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(meta, declared.encode("utf-8"))
        return b.getvalue()

    one = child()
    middle = io.BytesIO()
    with zipfile.ZipFile(middle, "w", zipfile.ZIP_STORED) as z:
        for i in range(containers):
            z.writestr(f"c{i:04d}.zip", one)
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w", zipfile.ZIP_STORED) as z:
        z.writestr(char * name_len + ".zip", middle.getvalue())
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"long-{containers}.zip"
    path.write_bytes(outer.getvalue())
    return str(path)


def _printed(report):
    """Bytes of both shapes, as the command writes them."""
    return (len(as_json(report).encode("utf-8")),
            len(as_text(report).encode("utf-8")))


@pytest.mark.parametrize("char, name_len", [("M", NAME), ("\x01", NAME),
                                            ("\U000E0041", NAME // 4)],
                         ids=["plain", "control", "invisible"])
def test_what_a_report_prints_is_bounded_by_the_budget(tmp_path, char, name_len):
    """Twice the budget for each rule that lists anything. The budget charges
    each finding the bytes it prints in whichever shape prints more, so this is
    margin, not slack. The name is spelled three ways: a control character
    prints as six in JSON and on the page, an invisible symbol as ten on the
    page, and a budget that counted characters as stored let either print six
    to thirteen times what it held. Unbounded, the plain name prints seventeen
    times the budget for one rule."""
    report = check_file(_under_a_long_name(tmp_path, 20, name_len, 150, char))
    rules = {f.rule.id for f in report.findings} | {r for r, _n, _k in report.stopped()}
    bound = 2 * LISTING_BUDGET_PER_RULE * len(rules)
    for shape, size in zip(("JSON", "text"), _printed(report)):
        assert size < bound, (
            f"the {shape} report is {size:,} bytes for {len(rules)} rules, over "
            f"{bound:,}: the long name is being printed once per finding with "
            f"nothing bounding how many")


def test_what_a_report_keeps_is_within_the_budget_for_every_rule(tmp_path):
    """Measured on what the report holds, not on what it prints: a budget
    applied while printing would leave every finding held until then."""
    report = check_file(_under_a_long_name(tmp_path, 10, NAME, 150))
    spent = {}
    for f in report.findings:
        spent[f.rule.id] = spent.get(f.rule.id, 0) + listed_size(f)
    over = {rid: n for rid, n in spent.items() if n > LISTING_BUDGET_PER_RULE}
    assert not over, f"rules holding more than the budget: {over}"
    assert report.stopped(), "the premise: this report must reach the budget"


def _peak_bytes(path, runs=3):
    """Median peak allocation for checking `path` and printing both shapes."""
    import statistics
    import tracemalloc

    seen = []
    for _ in range(runs):
        tracemalloc.start()
        _printed(check_file(path))
        seen.append(tracemalloc.get_traced_memory()[1])
        tracemalloc.stop()
    return statistics.median(seen)


def test_the_peak_does_not_grow_with_the_length_of_the_name(tmp_path):
    """The name's length rather than the number of containers, because reading
    twice the containers legitimately costs more, and a name twice as long is
    stored once and costs the reading nothing.

    What this does not catch: the budget applied where the report is printed
    rather than where findings are collected. The findings here share their
    container's path, so holding every one of them costs little and the peak is
    the printing. The test that sees what is held is the one above.
    """
    small = _peak_bytes(_under_a_long_name(tmp_path / "a", 10, NAME, 150))
    large = _peak_bytes(_under_a_long_name(tmp_path / "b", 10, 2 * NAME, 150))
    assert large < small * 1.25, (
        f"a name twice as long cost {large / small:.1f}x the allocation "
        f"({small:,} -> {large:,} bytes): it is being printed once per finding")


def test_the_budget_changes_the_listing_and_nothing_else(tmp_path, monkeypatch):
    """The summary and the exit code are the same with the budget and without
    it. Only the listing is shorter."""
    path = _under_a_long_name(tmp_path, 10, NAME, 150)
    bounded = check_file(path)
    monkeypatch.setattr(model, "LISTING_BUDGET_PER_RULE", 10 ** 12)
    unbounded = check_file(path)
    assert bounded.stopped() and not unbounded.stopped(), "the premise"
    for sev in Severity:
        assert bounded.count(sev) == unbounded.count(sev), sev
        for about in About:
            assert bounded.count_about(sev, about) == unbounded.count_about(sev, about)
    assert bounded.clean == unbounded.clean


def _rule(rid="M10", sev=Severity.ERROR):
    return Rule(id=rid, title="t", severity=sev, obligation=Obligation.PUBLISHED_TABLE,
                about=About.CONTAINER, layer="metadata",
                remedy="Do the thing that fixes it, in a full sentence.")


def _flood(report, n, rid="M10", sev=Severity.ERROR, name_len=200_000):
    """`n` findings, each in a container whose path is `name_len` long, so the
    budget is reached after a handful."""
    r = _rule(rid, sev)
    for i in range(n):
        report.add(Finding(r, f"finding {i}", Location(container="x" * name_len, line=i)))


def test_both_shapes_say_how_many_there_were_and_how_many_are_listed():
    report = Report(target="x.zip")
    _flood(report, 40)
    listed = sum(1 for f in report.findings if f.rule.id == "M10")
    assert 0 < listed < 40, "the premise: the budget stops this listing part way"
    said = f"40 M10 findings in all, {listed} listed"
    text = as_text(report)
    assert said in text and "size budget" in text, text[-400:]
    doc = json.loads(as_json(report))
    assert doc["listingStopped"] == [
        {"rule": "M10", "inAll": 40, "listed": listed,
         "said": doc["listingStopped"][0]["said"]}], doc["listingStopped"]
    assert said in doc["listingStopped"][0]["said"]
    assert len([f for f in doc["findings"] if f["rule"] == "M10"]) == listed
    assert doc["summary"]["error"] == 40


def test_the_listing_stops_rather_than_skipping():
    """Once a rule's budget turns one finding away, it turns away the rest:
    "stopped" is a statement about everything after that point."""
    report = Report(target="x.zip")
    r = _rule()
    report.add(Finding(r, "large", Location(container="x" * (LISTING_BUDGET_PER_RULE + 1))))
    report.add(Finding(r, "small", Location(container="y.zip")))
    assert report.findings == []
    assert report.stopped() == [("M10", 2, 0)]


def test_a_rule_with_nothing_listed_does_not_read_as_no_findings():
    report = Report(target="x.zip")
    r = _rule()
    report.add(Finding(r, "large", Location(container="x" * (LISTING_BUDGET_PER_RULE + 1))))
    text = as_text(report)
    assert "no findings" not in text and "no errors or warnings" not in text, text[-300:]
    assert "1 M10 finding in all, 0 listed" in text
    assert "1 error(s)" in counts_line(text)


def test_a_quiet_run_does_not_announce_notes_the_budget_held_back():
    report = Report(target="x.zip")
    _flood(report, 40, rid="P4", sev=Severity.INFO)
    assert "P4 findings in all" in as_text(report, True), "the premise"
    assert "P4 findings in all" not in as_text(report, False)
    assert json.loads(as_json(report, False))["listingStopped"] == []
    assert json.loads(as_json(report, True))["listingStopped"] != []


HOSTILE = {
    "plain": "report.pdf",
    "controls": "\x01\x02\n\t" * 40,
    "invisible": "\U000E0041\u200b" * 40,
    "quoted": '"\\' * 60,
    "wide": "설명서_Prüfbericht" * 20,
    "long": "M" * 4_000,
}


@pytest.mark.parametrize("kind", sorted(HOSTILE))
def test_the_budget_charges_at_least_what_either_shape_prints(kind):
    """The budget is a bound only if it charges what is printed. It charged
    characters as stored, and both shapes spell some out -- a control character
    as six in JSON, an invisible symbol as ten on the page -- so a name made of
    them printed six to thirteen times what the listing held. For every rule in
    the catalogue, one finding whose every string is `kind` takes no more bytes
    in either shape than the budget charges for it: its strings as printed, and
    the allowance for the keys, the rule's fields and the basis line."""
    import json as _json

    from vdi2770_validate.catalog import rule

    catalogue = _json.loads((ROOT / "packages" / "vdi2770" / "src" / "vdi2770" / "validate"
                             / "data" / "rules.json").read_text(encoding="utf-8"))
    s = HOSTILE[kind]
    over = []
    for entry in catalogue["rules"]:
        r = rule(entry["id"])
        # Every string the finding carries, and then only its location, which is
        # what a long container name is: printed once per finding, and spelled
        # out on the page where JSON prints it as it is.
        for where, f in (("every field", Finding(r, s, Location(container=s, member=s, xpath=s,
                                                                   subject=s), detail=s, fix=s)),
                         ("the location", Finding(r, "m", Location(container=s * 10,
                                                                   member=s * 10)))):
            empty, one = Report(target="t.zip"), Report(target="t.zip")
            one.add(f)
            for shape, render in (("JSON", as_json), ("text", as_text)):
                printed = len(render(one).encode("utf-8")) - len(render(empty).encode("utf-8"))
                if printed > listed_size(f):
                    over.append(f"{entry['id']}, {kind} in {where}, {shape}: {printed:,} "
                                f"printed, {listed_size(f):,} charged")
    assert not over, over[:5]


def _every_input_the_repository_holds():
    return sorted(FIXTURES.glob("*.zip")) + sorted(CORPUS.rglob("*.zip"))


@pytest.mark.parametrize("path", _every_input_the_repository_holds(),
                         ids=lambda p: p.name)
def test_no_input_the_repository_holds_reaches_the_budget(path):
    """The lower bound. A budget that engaged on an ordinary delivery would be
    taking findings out of reports nobody needed shortened."""
    report = check_file(str(path))
    assert report.stopped() == [], (
        f"{path.name}: the listing stopped at the budget for {report.stopped()}")
