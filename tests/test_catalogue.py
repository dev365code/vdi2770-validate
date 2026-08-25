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
    from vdi2770 import DEFECT_KINDS
    from vdi2770_validate.catalog import rules
    from vdi2770_validate.rules.container import DEFECT_TO_RULE

    # The reader's own vocabulary, not a regex over its source. The regex broke
    # the third time a call site changed shape, and a broken scrape reports
    # "nothing unmapped" rather than failing.
    emitted = set(DEFECT_KINDS)
    assert len(emitted) >= 10, f"only found {sorted(emitted)}; has the reader moved?"

    unmapped = sorted(emitted - set(DEFECT_TO_RULE))
    assert not unmapped, f"the reader emits {unmapped} and no rule reports them"

    stale = sorted(set(DEFECT_TO_RULE) - emitted)
    assert not stale, f"DEFECT_TO_RULE maps {stale}, which the reader no longer emits"

    known = set(rules())
    wrong = sorted({r for r in DEFECT_TO_RULE.values() if r not in known})
    assert not wrong, f"mapped to rule ids that do not exist: {wrong}"


# Rules that fire because *this tool* stopped. Nothing in one of these is a
# statement about the archive somebody sent, and until `about` existed a consumer
# reading the JSON had no field that said so.
TOOL_RULES = {
    "X0": "the bundled schema would not load — a broken installation of ours",
    "X4": "the schema checker would not follow this document to the end",
    "X5": "a check in this tool raised and did not finish — a bug of ours, not a container",
    "Z13": "documents delivered as folders, which this tool does not open — its limit,\n           not the delivery's fault",
    "Z5": "the archive is over a budget this tool sets for untrusted input",
    "Z6": "the tree is deeper than this tool opens",
}


def test_a_rule_about_this_tool_says_so():
    from vdi2770_validate.catalog import rules
    from vdi2770_validate.model import About

    actual = {rid for rid, r in rules().items() if r.about is About.TOOL}
    assert actual == set(TOOL_RULES), (
        "`about: tool` means the finding exists because this tool stopped.\n"
        f"  claiming it but unlisted: {sorted(actual - set(TOOL_RULES))}\n"
        f"  listed but not claiming it: {sorted(set(TOOL_RULES) - actual)}")


def test_every_rule_about_this_tool_is_an_error():
    """One policy, not four arguments. `X0` and `X4` argued error — "a report
    that silently skipped the check would be worse than no report" — while `Z6`
    argued warning for the same situation: "a budget, not a claim about the
    standard". Both are good arguments and only one can be the policy. If we did
    not look, exit 0 would be telling somebody we did."""
    from vdi2770_validate.catalog import rules
    from vdi2770_validate.model import About, Severity

    for rid, r in sorted(rules().items()):
        if r.about is About.TOOL:
            assert r.severity is Severity.ERROR, (
                f"{rid} says this tool stopped and reports it as {r.severity.value}")


def test_a_rule_about_this_tool_explains_itself():
    from vdi2770_validate.catalog import rules
    from vdi2770_validate.model import About

    for rid, r in sorted(rules().items()):
        if r.about is About.TOOL:
            assert r.why_ours, f"{rid} is about us and does not say why"
            assert "this tool" in (r.title + r.remedy + r.why_ours).lower(), (
                f"{rid} never tells the reader the limit is ours")


def test_every_defect_that_maps_to_z5_carries_its_own_remedy():
    """Z5 is reached seven ways and its own remedy fits none of them: "split the
    delivery into several containers" does nothing for one member that expands
    past the ratio floor, and `test_a_member_we_cannot_read_is_not_a_pass.py`
    says so in as many words. A Finding may carry its own."""
    from vdi2770_validate.rules.container import DEFECT_TO_RULE, REMEDY_FOR_DEFECT

    to_z5 = {k for k, v in DEFECT_TO_RULE.items() if v == "Z5"}
    missing = sorted(to_z5 - set(REMEDY_FOR_DEFECT))
    assert not missing, f"these reach Z5 with only its general remedy: {missing}"

    stale = sorted(set(REMEDY_FOR_DEFECT) - set(DEFECT_TO_RULE))
    assert not stale, f"remedies for defects nothing emits: {stale}"

    for kind, remedy in sorted(REMEDY_FOR_DEFECT.items()):
        assert remedy.endswith("."), f"{kind}: a remedy is a sentence"
        assert kind.replace("-", " ") not in remedy.lower(), (
            f"{kind}: the remedy restates the problem instead of saying what to do")


def test_a_rule_that_speaks_about_this_tool_owns_its_claim():
    """`obligation` says where the requirement came from. A title that talks
    about *our* scan is not reporting somebody else's requirement — it is our own
    judgement about what we managed to look at, and `ours` is the value that
    forces a `whyOurs` sentence saying so.

    `P3` — *"This scan found no PDF/A claim in the file"* — was `reference`,
    while `P4` one row below, with the same shape (*"...this tool did not verify
    the claim"*), was `ours`. Two rules asserting the reach of the same scan
    cannot trace to two different places.
    """
    import re

    from vdi2770_validate.catalog import rules
    from vdi2770_validate.model import Obligation

    speaks_of_us = re.compile(r"\bthis (tool|scan)\b", re.I)
    wrong = sorted(rid for rid, r in rules().items()
                   if speaks_of_us.search(r.title) and r.obligation is not Obligation.OURS)
    assert not wrong, (
        f"these titles claim something about this tool while sourcing the requirement "
        f"elsewhere: {wrong}")


def test_the_docs_say_that_citing_a_key_is_not_borrowing_its_claim():
    """Five rules are `ours` and cite a reference message key. Nothing said the
    two fields were independent, so the natural reading of a cited key — "this is
    what the standard requires" — was left available, which is the one reading
    this vocabulary exists to prevent."""
    from conftest import ROOT
    from vdi2770_validate.catalog import rules
    from vdi2770_validate.model import Obligation

    both = sorted(rid for rid, r in rules().items()
                  if r.obligation is Obligation.OURS and r.ref_keys)
    prose = (ROOT / "docs" / "licensing.md").read_text(encoding="utf-8")
    if both:
        assert "independent" in prose and "`refKeys`" in prose, (
            f"{len(both)} rules are `ours` and cite a reference key ({both}); "
            f"docs/licensing.md does not say the two fields are independent")


def test_every_field_a_rule_carries_reaches_a_reader():
    """`Rule.basis` is loaded from `rules.json`, three rules fill it in — the
    IDTA table, the bundled XSD — and no document or code path rendered it. A
    field nobody reads is either a claim nobody can check or dead weight; this
    says which by making the generated page show it.
    """
    from conftest import ROOT
    from vdi2770_validate.catalog import rules

    page = (ROOT / "docs" / "rules.md").read_text(encoding="utf-8")
    for rid, r in rules().items():
        if r.basis:
            assert f"`{r.basis}`" in page, f"{rid} carries basis {r.basis!r} and nothing shows it"
        for key in r.ref_keys:
            assert f"`{key}`" in page, (
                f"{rid} cites {key} and the page shows only the ambiguous display code")
