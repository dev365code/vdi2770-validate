"""The rule catalogue is data, so it can be checked like data."""
import json
import re

from conftest import ROOT
from vdi2770_validate.catalog import document_classes, rules
from vdi2770_validate.model import Obligation

RULES_JSON = json.loads((ROOT / "src" / "vdi2770_validate" / "data" / "rules.json").read_text(encoding="utf-8"))


def test_ids_unique_and_shaped():
    ids = [r["id"] for r in RULES_JSON["rules"]]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[ZXFMP]\d+", i) for i in ids)


def test_every_rule_tells_the_user_what_to_do():
    for r in rules().values():
        assert len(r.remedy) > 30, f"{r.id} has no usable remedy"
        assert not r.remedy.endswith(("is invalid.", "is wrong.")), f"{r.id} restates the problem"


def test_our_own_judgements_say_why():
    for r in rules().values():
        if r.obligation is Obligation.OURS:
            assert r.why_ours, f"{r.id} claims its own authority without explaining it"


def test_rules_observed_in_the_reference_say_where():
    """`reference` means we saw the behaviour in someone else's implementation
    and did not check it against the standard. The evidence is the message key,
    so a rule may not claim it without naming one."""
    for r in rules().values():
        if r.obligation is Obligation.REFERENCE:
            assert r.ref_keys, f"{r.id} claims to follow the reference but names no message key"


def test_a_basis_can_actually_be_looked_up():
    """`basis` is the receipt for a rule. It must name either a file we ship or
    a published edition precise enough to find — "a space in the string" is not
    a check, which is what this used to be."""
    data = ROOT / "src" / "vdi2770_validate" / "data"
    for r in rules().values():
        if not r.basis:
            continue
        if (data / r.basis).exists():
            continue
        assert re.match(r"^IDTA \d{5} v\d+\.\d+(\.\d+)? Table \d+$", r.basis), (
            f"{r.id} basis {r.basis!r} names neither a bundled file nor a citable edition")


def test_every_published_table_citation_is_the_same_edition():
    """Two rules citing two different editions of the same table would mean one
    of them is stale."""
    cited = {r.basis for r in rules().values() if r.basis.startswith("IDTA")}
    assert len(cited) <= 1, f"rules cite more than one edition: {sorted(cited)}"


def test_class_table_is_keyed_on_what_the_sources_agree_about():
    classes = document_classes()
    assert len(classes) == 12
    for c in classes.values():
        assert c["nameDe"], "German name is the matching key and must be present"
        assert c["irdi"].startswith("0173-1#07-")
    disagreements = [c["classId"] for c in classes.values() if not c["nameEn"]["agree"]]
    assert disagreements == ["02-03", "02-04", "03-01", "03-04", "04-01"], (
        "the English disagreement set changed — re-verify against both sources before moving this pin")


def test_no_remedy_is_copied_from_the_reference_implementation():
    """Licensing gate. The reference's message strings are MIT and may be reused
    with attribution — but reusing them would make this tool a translation of
    someone else's reading rather than an independent one.

    The strings are vendored under tests/data so this runs everywhere, including
    on a fresh clone. A gate that silently skips is decoration."""
    oracle = ROOT / "tests" / "data" / "oracle-messages.json"
    assert oracle.exists(), "the licensing gate cannot run without tests/data/oracle-messages.json"
    theirs = {m.strip().lower() for m in json.loads(oracle.read_text(encoding="utf-8"))["messages"]}
    theirs.discard("")
    assert len(theirs) > 100, "the vendored message set looks truncated"
    for r in rules().values():
        mine = r.remedy.strip().lower()
        assert mine not in theirs, f"{r.id} remedy is copied verbatim from the reference"
        for t in theirs:
            if len(t) > 25:
                assert t not in mine, f"{r.id} remedy embeds the reference's message {t!r}"
        title = r.title.strip().lower()
        assert not (len(title) > 25 and title in theirs), (
            f"{r.id} title is copied verbatim; mark it or write your own")
