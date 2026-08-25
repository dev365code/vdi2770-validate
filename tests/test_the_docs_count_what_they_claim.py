"""Numbers in prose drift silently. Each of these was written true and became
false when the thing it counted changed — and nothing failed, because no test
reads prose.

The rule this file applies: if a document states a count of something this
repository holds, the count is derived here and compared.
"""
import json
import re

from conftest import CORPUS, FIXTURES, ROOT, spelled


def containers():
    return sorted(CORPUS.rglob("*.zip")) + sorted(FIXTURES.rglob("*.zip"))


def test_the_oracle_sweep_covers_every_container_and_says_how_many():
    """`docs/divergences.md` said 43 while the sweep held 44 — the sweep was
    right and the sentence describing it was a version behind.

    Two numbers now, because one was doing the work of two: how many containers
    exist, and how many were actually put through the reference implementation.
    A container added after the recorded run carries `reference: {}`, and the
    page derived every disagreement from the total — so a container the
    reference has never seen was counted as disagreeing with it.
    """
    swept = json.loads((ROOT / "docs" / "oracle-sweep.json").read_text(encoding="utf-8"))
    names = set(swept["containers"])
    here = {p.name for p in containers()}
    assert names == here, (
        f"the sweep and the repository disagree about which containers exist: "
        f"only swept {sorted(names - here)}, only here {sorted(here - names)}")

    # A container may be recorded with our half only — the reference half needs a
    # JDK and the pinned checkout, so a fixture added afterwards waits for the
    # next full sweep. It has to say so rather than look swept.
    unswept = [n for n, e in swept["containers"].items() if not e["reference"]]
    for n in unswept:
        assert n in swept.get("_unswept", {}), (
            f"{n} has no reference verdict and the file does not say why")
    assert not (set(swept.get("_unswept", {})) - set(unswept)), (
        "the file excuses a container that does have a reference verdict: "
        f"{sorted(set(swept['_unswept']) - set(unswept))}")

    prose = (ROOT / "docs" / "divergences.md").read_text(encoding="utf-8")
    m = re.search(r"([A-Za-z0-9-]+) of the (\d+) containers in `corpus/` and\s+`tests/fixtures/`",
                  prose)
    assert m, "the sentence this test pins has been reworded"
    assert int(m.group(2)) == len(here), (
        f"divergences.md says {m.group(2)} containers; there are {len(here)}")
    assert m.group(1).lower() == spelled(len(here) - len(unswept)), (
        f"{len(here) - len(unswept)} of them were swept and divergences.md "
        f"says {m.group(1)}")


def test_contributing_names_every_obligation_the_catalogue_uses():
    """`reference` carries 14 of 35 rules and CONTRIBUTING did not mention it,
    so a contributor reading the only document that explains the vocabulary
    would have picked one of the four it did list."""
    from vdi2770_validate.catalog import rules
    from vdi2770_validate.model import Obligation

    prose = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    # One assertion, not two. The second one asked the same question about the
    # obligations actually in use, which is a subset of the enum -- so it could
    # not fail unless the first already had, and it computed `used` only to feed
    # itself. That is the "computed and never judged" shape this changeset
    # removed from `rule_coverage.judge`; leaving a copy of it in the gate that
    # checks the docs would be funny in the wrong way.
    missing = sorted(o.value for o in Obligation if f"`{o.value}`" not in prose)
    assert not missing, f"CONTRIBUTING does not explain these obligations: {missing}"
    # The other direction: an obligation the catalogue no longer uses should not
    # linger in the enum unexplained, and every value in use must be a real one.
    # `r.obligation` is built as `Obligation(...)`, so "used is a subset of the
    # enum" is true by construction — the shape this changeset removed from
    # `rule_coverage.judge`, reproduced here. The live question is the other
    # direction: a value in the vocabulary that no rule uses any more.
    used = {r.obligation for r in rules().values()}
    unused = sorted(o.value for o in set(Obligation) - used)
    assert not unused, f"the vocabulary carries values no rule uses: {unused}"


def test_scope_md_states_the_limits_the_code_enforces():
    """The reader's README names every budget constant and a gate holds it.
    `docs/scope.md` describes the same limits in words — "a thousand containers,
    64 MiB of metadata, 4 GiB inflated", "three levels", "a hundred times per
    container" — and nothing derived any of them. It is the page a buyer reads
    to decide whether this tool will cope with their delivery.
    """
    from vdi2770 import pdfread, zipread
    from vdi2770_validate.model import MAX_LISTED_PER_RULE

    prose = (ROOT / "docs" / "scope.md").read_text(encoding="utf-8")
    mib, gib = 1 << 20, 1 << 30
    stated = {
        "containers in one read": (zipread.MAX_CONTAINERS, "a thousand containers"),
        "metadata across the tree": (zipread.MAX_TOTAL_METADATA_BYTES // mib, "64 MiB"),
        "inflated across the tree": (zipread.MAX_TOTAL_DECOMPRESSED // gib, "4 GiB"),
        "one archive": (zipread.MAX_TOTAL_BYTES // gib, "2 GiB"),
        "container levels": (zipread.MAX_CONTAINER_LEVELS, "three levels"),
        "findings listed per rule": (MAX_LISTED_PER_RULE, "a hundred times"),
    }
    words = {1000: "a thousand", 3: "three", 100: "a hundred"}
    for what, (value, phrase) in stated.items():
        assert phrase in prose, f"scope.md no longer says {phrase!r} for {what}"
        spelled = words.get(value)
        assert (str(value) in phrase or (spelled and phrase.startswith(spelled))), (
            f"{what} is {value} and scope.md says {phrase!r}")
    # The PDF budgets are the reader's to describe. scope.md may mention streams
    # in words; what it must not do is restate one of those numbers, because
    # then there would be two places to change and only one of them gated.
    # Matching bare digits finds "4" inside "4 GiB" and "64" inside "64 MiB",
    # which are the tree budgets this page does own. What would be a restatement
    # is the number next to the word it bounds.
    import re

    for name, unit in (("MAX_STREAMS", "stream"), ("MAX_XMP_PACKETS", "packet"),
                       ("MAX_PDFA_PREFIXES", "prefix")):
        value = getattr(pdfread, name)
        assert not re.search(rf"\b{value}\s+{unit}", prose), (
            f"scope.md restates {name} = {value}; that number belongs to the "
            f"reader's README, which has a gate for it")


def test_the_divergence_numbers_are_derived_from_the_sweep_and_the_catalogue():
    """`divergences.md` states five counts and none of them was checked — one of
    the sentences even says "the count of citations is derived and gated", which
    was written the same day and was not true.

    They are derived here: the citation count from `rules.json`, the two
    divergence counts and the throws count from `oracle-sweep.json`.
    """
    import json
    import re

    prose = (ROOT / "docs" / "divergences.md").read_text(encoding="utf-8")
    catalogue = json.loads(
        (ROOT / "src" / "vdi2770_validate" / "data" / "rules.json").read_text(encoding="utf-8"))
    recorded = json.loads(
        (ROOT / "docs" / "oracle-sweep.json").read_text(encoding="utf-8"))
    # Only what was actually put through the reference implementation. A
    # container added after the recorded run carries `reference: {}`, and every
    # count below reads that as "the reference reported nothing" when it means
    # "we never asked it". `x6-too-many-elements.zip` errors on our side, so it
    # was counted as a disagreement with a tool that has never seen it — the
    # exact mistake this project exists to prevent, in its own evidence.
    sweep = {n: e for n, e in recorded["containers"].items()
             if n not in recorded.get("_unswept", {})}
    assert sweep, "every container is unswept; there is nothing to derive from"

    words = {6: "Six", 13: "thirteen", 28: "Twenty-eight", 2: "two"}

    citations = sum(len(r["refKeys"]) for r in catalogue["rules"])
    assert f"{words[28] if citations == 28 else citations} citations" in prose, (
        f"the rules cite {citations} keys; divergences.md says otherwise")

    def errs(entry, side):
        block = entry.get(side, {})
        return {k for k, v in block.items() if k.upper().startswith("ERROR") for _ in v} or set()

    theirs_only = sum(1 for e in sweep.values()
                      if e["reference"].get("ERROR") and not e["ours"].get("error"))
    ours_only = sum(1 for e in sweep.values()
                    if e["ours"].get("error") and not e["reference"].get("ERROR"))
    assert f"**{words.get(theirs_only, theirs_only)} containers where it reports an error" in prose, (
        f"the sweep has {theirs_only} where only the reference errors")
    assert f"**{spelled(ours_only)} where we" in prose, (
        f"the sweep has {ours_only} where only we error")

    # The sweep records a thrown exception as its own severity block, which is
    # the whole point of §3: a crash is not a finding.
    threw = sum(1 for e in sweep.values() if e["reference"].get("EXCEPTION"))
    assert re.search(rf"\b{words.get(threw, threw)}\b of our fixtures", prose), (
        f"the reference threw on {threw} fixtures")


def test_licensing_md_counts_the_rules_that_cite_a_key_while_owning_the_claim():
    from vdi2770_validate.catalog import rules
    from vdi2770_validate.model import Obligation

    both = [rid for rid, r in rules().items()
            if r.obligation is Obligation.OURS and r.ref_keys]
    prose = (ROOT / "docs" / "licensing.md").read_text(encoding="utf-8")
    words = {4: "four", 5: "five", 6: "six", 7: "seven"}
    assert f"and {words[len(both)]} do" in prose, (
        f"{len(both)} rules are `ours` and cite a key ({sorted(both)}); licensing.md disagrees")


def test_contributing_counts_the_targets_it_lists():
    import re

    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    prereqs = re.search(r"^check:\s*(.*)$", makefile, re.M).group(1).split()
    prose = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    words = {6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven"}
    assert f"It is {words[len(prereqs)]} targets" in prose, (
        f"`make check` has {len(prereqs)} prerequisites and CONTRIBUTING says otherwise")
    # One of them is a build step, not a gate, and the prose says so. If that
    # ever stops being one short of the total, somebody has miscounted.
    judging = len(prereqs) - 1
    assert f"other {words[judging]} judge something" in prose, (
        f"{len(prereqs)} targets, one of them a build step, so {words[judging]} judge; "
        f"CONTRIBUTING disagrees")


def test_the_audit_log_does_not_contradict_its_own_headings():
    """the audit record said "thirteen defects, six fixed" over a list where every
    item was struck through and marked **Fixed**, and a subheading said "None is
    fixed yet" directly above them. A dated tracker rots exactly here: the items
    get updated and the sentence introducing them does not.
    """
    import re

    text = (ROOT / "docs" / "the audit record").read_text(encoding="utf-8")
    assert "None is fixed yet" not in text or not re.search(r"~~.*~~", text), (
        "a section says nothing is fixed and the items below it are struck through")
    for head in re.finditer(r"^## (.+)$", text, re.M):
        rest = text[head.end():]
        nxt = rest.find("\n## ")
        body = rest if nxt < 0 else rest[:nxt]
        # A heading may state how many of its own items are fixed, or say
        # nothing. What it may not do is state a number this file cannot show:
        # the first one claimed thirteen, six of which are recorded in the
        # changelog and not here, so the count was unprovable from the document
        # making it.
        claimed = re.search(r"(\w+) fixed", head.group(1))
        if not claimed:
            continue
        words = {"none": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                 "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
                 "thirteen": 13}
        want = words.get(claimed.group(1).lower())
        if want is None:
            continue
        assert len(re.findall(r"\*\*Fixed", body)) == want, (
            f"the heading {head.group(1)!r} claims {want} fixed; the section marks "
            f"{len(re.findall(r'[*][*]Fixed', body))}")


def test_the_json_report_carries_what_each_finding_actually_says():
    """`--json` is sold as the machine-readable interface, and eight of its
    fields could be a constant with the whole suite green — `severity` reported
    as `"error"` for every note, `message` empty, `where` blank, `refCodes`
    empty. A CI consumer keying on `severity` would have seen errors for notes
    and nothing would have turned red.

    Every field is compared against the `Finding` it came from, on a container
    that produces several severities and several rules.
    """
    import json

    from vdi2770_validate import report as rendering
    from vdi2770_validate.runner import check_file

    target = ROOT / "corpus" / "examples" / "missingdocuments" / "folders.zip"
    rep = check_file(str(target))
    doc = json.loads(rendering.as_json(rep))

    assert len({f["severity"] for f in doc["findings"]}) > 1, (
        "this container should produce more than one severity, or the check below "
        "cannot see a constant")
    assert len({f["rule"] for f in doc["findings"]}) > 1, "and more than one rule"

    by_key = {}
    for f in rep.sorted():
        by_key.setdefault((f.rule.id, f.where.container, f.where.member, f.message), f)

    for row in doc["findings"]:
        f = by_key.get((row["rule"], row["where"]["container"],
                        row["where"]["member"], row["message"]))
        assert f is not None, f"the JSON carries a finding the report does not: {row}"
        assert row["severity"] == f.severity.value
        assert row["message"] == f.message
        assert row["remedy"] == f.remedy
        assert row["detail"] == f.detail
        assert row["where"]["line"] == f.where.line
        assert row["where"]["column"] == f.where.column
        assert row["where"]["xpath"] == f.where.xpath
        assert row["where"]["subject"] == f.where.subject
        assert row["about"] == f.rule.about.value
        assert row["layer"] == f.rule.layer
        assert row["obligation"] == f.rule.obligation.value
        assert row["refCodes"] == list(f.rule.ref_codes)


def test_the_changelog_counts_the_mutation_rows_it_describes():
    """The entry said "fifteen rows" for a table that had grown to twenty. Every
    number in prose about a checked-in list is a number that drifts the first
    time the list grows, and this one describes the gate that checks the gates.
    """
    import re
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    from mutation_table import TABLE

    prose = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    unreleased = prose[:prose.index("\n## 0.6.0")]
    m = re.search(r"([a-z-]+) rows, each\s*\n?\s*naming the pytest selection", unreleased)
    assert m, "the CHANGELOG sentence this test pins has been reworded"
    said = m.group(1)
    expected = spelled(len(TABLE))
    assert said == expected, (
        f"the CHANGELOG says {said} mutation rows and the table has {len(TABLE)}")


def test_no_document_cites_a_file_that_is_not_here():
    """SECURITY.md's citations were checked and nobody else's were.

    A pointer to `tests/test_offline.py::test_x` is the evidence a reader is
    offered instead of trusting the sentence, and it is worth exactly as much in
    CONTRIBUTING or docs/licensing.md as in SECURITY.md. The narrow gate was
    written the day a SECURITY.md row pointed at a renamed file; the rename could
    equally have been cited three other places.

    The released CHANGELOG sections are deliberately out of scope: an entry about
    a file that has since been renamed is history, not a broken pointer. Its
    Unreleased section is in scope, because that is prose being written now.
    """
    import re

    docs = ["README.md", "CONTRIBUTING.md", "SECURITY.md", "packages/vdi2770/README.md"]
    docs += [str(p.relative_to(ROOT)) for p in sorted((ROOT / "docs").glob("*.md"))]

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    texts = {d: (ROOT / d).read_text(encoding="utf-8") for d in docs if (ROOT / d).exists()}
    texts["CHANGELOG.md (Unreleased)"] = changelog[:changelog.index("\n## 0.")]

    pattern = re.compile(
        r"`((?:tests|tools|src|packages|docs|corpus)/[\w./-]+\.(?:py|json|md|xsd|java))"
        r"(?:::(\w+))?`")
    seen = 0
    for doc, prose in texts.items():
        for path, func in pattern.findall(prose):
            seen += 1
            f = ROOT / path
            assert f.exists(), f"{doc} cites {path}, which is not in this repository"
            if func:
                assert f"def {func}(" in f.read_text(encoding="utf-8", errors="replace"), (
                    f"{doc} cites {path}::{func}, which that file does not define")
    # A floor of 12 against a real count in the twenties lets ten citations vanish in
    # silence, which is the failure this whole file is about. Exact, and updated
    # when a citation is added or removed -- that is the point of it.
    assert seen == 24, (
        f"{seen} citations found, not 24. If you added or removed one, say so here; "
        f"if you did not, ten of them just stopped being checked.")


def test_the_changelog_counts_the_rules_that_fire_because_we_declined():
    """`test_catalogue.py::TOOL_RULES` gates the *set* of `about: tool` rules and
    made anyone adding one write down why. Nothing tied the prose count to it, so
    the bullet describing the policy went stale inside the same release section
    that made it stale: it said four while this release shipped seven.
    """
    import json
    import re

    catalogue = json.loads(
        (ROOT / "src" / "vdi2770_validate" / "data" / "rules.json").read_text(encoding="utf-8"))
    declined = [r["id"] for r in catalogue["rules"] if r["about"] == "tool"]

    prose = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    unreleased = prose[:prose.index("\n## 0.")]
    m = re.search(r"([A-Za-z-]+) rules fire because the validator declined", unreleased)
    assert m, "the CHANGELOG sentence this test pins has been reworded"
    assert m.group(1).lower() == spelled(len(declined)), (
        f"{len(declined)} rules are `about: tool` ({sorted(declined)}); the "
        f"CHANGELOG says {m.group(1)}")


def test_the_changelog_counts_the_files_make_standalone_runs():
    """It said 48 — the root suite only, forgetting the reader's seven — while
    the target ran 55, and then 56 the moment another file was added. A number
    in prose about a directory listing drifts the first time anyone adds a file,
    which is every day this project is worked on.
    """
    import re

    files = sorted((ROOT / "tests").glob("test_*.py"))
    files += sorted((ROOT / "packages" / "vdi2770" / "tests").glob("test_*.py"))

    prose = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    unreleased = prose[:prose.index("\n## 0.")]
    m = re.search(r"runs each of the (\d+) test files on its own", unreleased)
    assert m, "the CHANGELOG sentence this test pins has been reworded"
    assert int(m.group(1)) == len(files), (
        f"`make standalone` runs {len(files)} files; the CHANGELOG says {m.group(1)}")
