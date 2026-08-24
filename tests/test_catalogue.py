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


def test_the_german_agreement_is_recorded_not_just_asserted():
    """Keying classification on the German name is justified by the two published
    sources agreeing on all twelve. If only one rendering is stored, that
    justification leaves no evidence behind and the reader has to take our word."""
    for cid, c in sorted(document_classes().items()):
        de = c["nameDe"]
        assert isinstance(de, dict), (
            f"{cid} stores one German name; store both sources so the agreement is checkable")
        assert de["idta02004"] and de["ddcReference"]
        assert de["agree"] is (de["idta02004"] == de["ddcReference"])
    disagreeing = [cid for cid, c in document_classes().items() if not c["nameDe"]["agree"]]
    assert disagreeing == [], (
        f"the German names no longer agree for {disagreeing} — matching is keyed on them, "
        f"so this changes the design, not just the data")


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


def test_an_unknown_class_id_has_no_published_names():
    from vdi2770_validate.catalog import english_for, german_for
    assert english_for("99-99") == ()
    assert german_for("99-99") == ()


# The `container` obligation is the strongest thing this project claims: "true
# without knowing VDI 2770 at all". An audit found six rules wearing it that are
# entirely VDI conventions -- reserved filenames, the metadata model, a byte scan
# of a PDF. The tag had become the default for anything that was not obviously
# schema or table. Listing them here makes the claim a decision someone made.
CONTAINER_RULES = {
    "Z1": "a file that is not a readable ZIP is not one; zipfile decides, not VDI",
    "Z2": "an archive with no members has no members",
    "X1": "well-formedness is XML 1.0. The VDI schema cannot speak until this holds",
    "Z12": "a member whose CRC fails or that needs a password cannot be decompressed; zlib decides",
}


def test_the_container_obligation_is_never_a_default():
    from vdi2770_validate.catalog import rules
    from vdi2770_validate.model import Obligation

    actual = {rid for rid, r in rules().items() if r.obligation is Obligation.CONTAINER}
    assert actual == set(CONTAINER_RULES), (
        "`container` claims a rule holds without VDI 2770 at all. Adding one means "
        "writing down why here.\n"
        f"  claiming it but unlisted: {sorted(actual - set(CONTAINER_RULES))}\n"
        f"  listed but no longer claiming it: {sorted(set(CONTAINER_RULES) - actual)}")
    for rid, why in CONTAINER_RULES.items():
        assert len(why) > 20, f"{rid}: give an actual reason"


def test_a_container_rule_does_not_lean_on_a_vdi_reserved_name():
    """The mechanical half of the same claim: a rule that only fires because a
    file is called VDI2770_Main.xml is not describing ZIP mechanics."""
    from vdi2770_validate.catalog import rules
    from vdi2770_validate.model import Obligation

    reserved = ("VDI2770_Metadata.xml", "VDI2770_Main.xml", "VDI2770_Main.pdf")
    for rid, r in rules().items():
        if r.obligation is not Obligation.CONTAINER:
            continue
        text = " ".join((r.title, r.remedy, r.basis, r.why_ours))
        found = [n for n in reserved if n in text]
        assert not found, f"{rid} claims `container` but names {found}"


def test_every_defect_the_reader_can_emit_maps_to_a_rule():
    """`DEFECT_TO_RULE` is the reader-to-rules interface and nothing checked it.

    The lookup is `.get(kind)` followed by `continue`, so a defect kind the reader
    grows is dropped in silence and the container passes with nothing said about
    it. The SDK already gates its kinds against its README; this is the same
    gate pointed the other way.
    """
    import re

    from conftest import ROOT
    from vdi2770_validate.catalog import rules
    from vdi2770_validate.rules.container import DEFECT_TO_RULE

    source = (ROOT / "packages" / "vdi2770" / "src" / "vdi2770" / "zipread.py")
    emitted = set(re.findall(r'Defect\(\s*\n?\s*"([a-z-]+)"', source.read_text(encoding="utf-8")))
    assert len(emitted) >= 10, f"only found {sorted(emitted)}; has the reader moved?"

    unmapped = sorted(emitted - set(DEFECT_TO_RULE))
    assert not unmapped, f"the reader emits {unmapped} and no rule reports them"

    stale = sorted(set(DEFECT_TO_RULE) - emitted)
    assert not stale, f"DEFECT_TO_RULE maps {stale}, which the reader no longer emits"

    known = set(rules())
    wrong = sorted({r for r in DEFECT_TO_RULE.values() if r not in known})
    assert not wrong, f"mapped to rule ids that do not exist: {wrong}"
