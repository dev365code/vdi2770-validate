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


def test_schema_backed_rules_name_the_schema():
    for r in rules().values():
        if r.basis:
            assert (ROOT / "src" / "vdi2770_validate" / "data" / r.basis).exists() or " " in r.basis


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
