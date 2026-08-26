"""Numbers in prose drift silently. Each of these was written true and became
false when the thing it counted changed — and nothing failed, because no test
reads prose.

The rule this file applies: if a document states a count of something this
repository holds, the count is derived here and compared.
"""
import json
import re

from conftest import CORPUS, FIXTURES, ROOT, newest_changelog_section, spelled


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
    total = re.search(r"(\d+) containers in `corpus/` and\s+`tests/fixtures/`", prose)
    assert total, "the sentence naming how many containers exist has been reworded"
    assert int(total.group(1)) == len(here), (
        f"divergences.md says {total.group(1)} containers; there are {len(here)}")

    # And how many of them were actually put through the reference. Two numbers,
    # because one was doing the work of both and a container the reference has
    # never seen was being counted as disagreeing with it.
    measured = len(here) - len(unswept)
    if unswept:
        assert f"{measured} of the {len(here)} containers" in prose, (
            f"{measured} of {len(here)} were swept and divergences.md does not say so")
        for n in unswept:
            assert n in prose or "_unswept" in prose, (
                f"{n} was not swept and the page does not point a reader at which ones")
    else:
        assert f"All {len(here)} containers" in prose, (
            "nothing is outstanding and the page does not say the sweep is complete")


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
    from vdi2770 import pdfread, xmlread, zipread
    from vdi2770_validate.model import MAX_LISTED_PER_RULE

    prose = (ROOT / "docs" / "scope.md").read_text(encoding="utf-8")
    # How many times one rule can be true. This sentence said "two hundred
    # thousand" and had gone stale: `MAX_ELEMENTS` bounds one metadata document,
    # so the real ceiling is just under a hundred thousand and the document is
    # refused past it. Six of this page's numbers were derived here and this was
    # not one of them -- which is the one that drifted.
    assert xmlread.MAX_ELEMENTS == 100_000, (
        "the element budget moved; the sentence about how many times one rule "
        "can be true is derived from it")
    assert "nearly a hundred thousand" in prose, (
        "docs/scope.md no longer says how many times one rule can be true, or "
        f"says it in words this cannot check; the budget is {xmlread.MAX_ELEMENTS}")
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
    was written at the time and was not true.

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
    # the whole point of `docs/divergences.md` §3: a crash is not a finding.
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

    unreleased = newest_changelog_section()
    # `[a-z-]+` could not match a count past twenty-nine, where `spelled` starts
    # returning digits — so at thirty rows this gate reported "the sentence has
    # been reworded" and no wording could satisfy it.
    m = re.search(r"([a-z0-9-]+) rows, each\s*\n?\s*naming the pytest selection", unreleased)
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

    texts = {d: (ROOT / d).read_text(encoding="utf-8") for d in docs if (ROOT / d).exists()}
    texts["CHANGELOG.md (newest section)"] = newest_changelog_section()

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
    assert seen == 23, (
        f"{seen} citations found, not 23. If you added or removed one, say so here; "
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

    unreleased = newest_changelog_section()
    m = re.search(r"([A-Za-z0-9-]+) rules fire because the validator declined", unreleased)
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

    unreleased = newest_changelog_section()
    m = re.search(r"runs each of the (\d+) test files on its own", unreleased)
    assert m, "the CHANGELOG sentence this test pins has been reworded"
    assert int(m.group(1)) == len(files), (
        f"`make standalone` runs {len(files)} files; the CHANGELOG says {m.group(1)}")


def test_the_changelog_counts_the_trailer_shapes_it_claims_are_pinned():
    """The entry said seventeen, then twenty-three; it was twenty-two.

    I wrote the second number without counting, in a section whose subject is a
    scan that has now been repaired five times. A count in prose is a claim
    nobody re-checks, which is why the sibling test above exists for the mutation
    table -- so this one exists for the other number in the same section.
    """
    import ast
    import re

    unreleased = newest_changelog_section()
    m = re.search(r"([A-Za-z-]+) shapes are pinned", unreleased)
    assert m, "the sentence counting the pinned trailer shapes has been reworded"
    words = {"Seventeen": 17, "Eighteen": 18, "Nineteen": 19, "Twenty": 20,
             "Twenty-one": 21, "Twenty-two": 22, "Twenty-three": 23,
             "Twenty-four": 24, "Twenty-five": 25, "Twenty-six": 26}
    said = words.get(m.group(1))
    assert said is not None, f"unknown number word {m.group(1)!r}"

    src = (ROOT / "packages/vdi2770/tests/test_the_public_api.py").read_text(
        encoding="utf-8")
    tree = ast.parse(src)
    named = {t.id: len(n.value.elts)
             for n in tree.body if isinstance(n, ast.Assign)
             and isinstance(n.value, (ast.List, ast.Tuple))
             for t in n.targets if isinstance(t, ast.Name)}
    shapes = {"test_encryption_is_read_from_the_trailer_and_nowhere_else",
              "test_the_trailer_scan_reads_pdf_structure",
              "test_the_trailer_scan_reads_the_whole_file_and_only_keys"}
    seen, real = set(), 0
    for n in ast.walk(tree):
        if not isinstance(n, ast.FunctionDef) or n.name not in shapes:
            continue
        seen.add(n.name)
        for d in n.decorator_list:
            if isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "parametrize":
                a = d.args[1]
                real += (len(a.elts) if isinstance(a, (ast.List, ast.Tuple))
                         else named.get(getattr(a, "id", ""), 0))
    assert seen == shapes, f"a parametrised trailer test was renamed: {shapes - seen}"
    # Plus one: the sentence says "including the real encrypted PDF in the
    # corpus", which is a fixture rather than a parameter.
    assert said == real + 1, f"the CHANGELOG says {said}; there are {real} + 1"


def test_contributing_is_right_about_who_signed_off():
    """`CONTRIBUTING.md` said every commit carries a `Signed-off-by` line.

    Thirty-two do not. The practice was in place, lapsed for one afternoon, and
    resumed the next day — and nothing noticed, because `.github/dco.yml` checks
    pull requests and every one of those commits arrived by a direct push. A
    public file stating something about this repository that `git log` refutes
    is the defect this suite exists for.

    History is not being rewritten to make the sentence true, so the sentence
    says what happened instead. Two halves are held here: the count in the prose
    matches the log, and the lapse stays closed — nothing newer than it is
    unsigned.
    """
    import subprocess

    import pytest

    got = subprocess.run(
        ["git", "log", "--reverse", "--format=%H%x01%(trailers:key=Signed-off-by)"],
        cwd=ROOT, capture_output=True, text=True)
    if got.returncode != 0:
        pytest.skip("not a git checkout; the log is not available here")
    signed = [("Signed-off-by" in line.split("\x01", 1)[1])
              for line in got.stdout.splitlines() if "\x01" in line]
    assert signed, "no commits found; this test is looking in the wrong place"

    unsigned = [i for i, ok in enumerate(signed) if not ok]
    prose = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")

    if not unsigned:
        assert "do not carry it" not in prose, (
            "every commit is signed now; the paragraph about the lapse is stale")
        return

    # Whole words. `str(2) in prose` is satisfied by the `32` already written
    # there, and `"two" in prose.lower()` by `thirty-two` — so the count could
    # fall by thirty and this would still agree with the page. Both spellings of
    # the number are looked for the same way.
    import re as _re

    said = _re.search(rf"\b({_re.escape(spelled(len(unsigned)))}|{len(unsigned)})\b",
                      prose, _re.IGNORECASE)
    assert said, (
        f"{len(unsigned)} commits carry no Signed-off-by line and CONTRIBUTING.md "
        f"does not say so")
    assert all(signed[i] for i in range(unsigned[-1] + 1, len(signed))), (
        "a commit newer than the lapse is unsigned; the lapse has reopened")


def test_the_upgrade_warning_names_only_rules_a_container_can_ask_for():
    """The first sentence of the release named a rule no delivery can trigger.

    The warning exists to tell an upgrading CI job which ids will turn its green
    run red. It opened with `X5`, which `tools/rule_coverage.py` excuses from
    coverage precisely because it "only fires when a rule in this tool raises,
    which is a bug here rather than anything a container can ask for" -- so the
    repository already held the evidence, one file away, and the sentence a
    reader sees first was written without it.
    """
    import re
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    from rule_coverage import CANNOT_FIRE

    # The paragraph, found by what it says rather than by its position: the
    # section opens with its own heading, and counting paragraphs made this gate
    # read the date line and pass on an empty set of ids.
    paragraphs = [t for t in newest_changelog_section().split("\n\n")
                  if "Upgrading from" in t]
    assert len(paragraphs) == 1, "the release no longer opens with one upgrade warning"
    warning = paragraphs[0]
    named = set(re.findall(r"`([A-Z][0-9]+)`", warning))
    assert named, "the upgrade warning no longer names any rule ids"
    # Named as one this tool can raise itself is fine -- the paragraph says so
    # about `X5` in as many words. Named among the ids that will turn a run red
    # is not.
    turns_red = set(re.findall(r"`([A-Z][0-9]+)`", warning.split("(")[0]))
    assert not (turns_red & set(CANNOT_FIRE)), (
        "the upgrade warning tells a reader to expect ids that no container can "
        f"cause: {sorted(turns_red & set(CANNOT_FIRE))}")


def test_the_readme_describes_the_json_entries_the_tool_actually_emits():
    """The README promised a key that half the entries do not have.

    *"a list with an entry per path you gave, each carrying that path and
    `pdfaVerified: false`"* -- true of a container that was checked, and not of a
    path that could not be opened, which carries `path` and `unreadable` and
    stops there. The heterogeneous shape is deliberate: there is no PDF/A verdict
    to give about a file nobody read. What was wrong was the sentence, and a
    consumer that believed it raised `KeyError` on exactly the path the sweep
    exists to keep going past.
    """
    import json
    import subprocess
    import sys

    from conftest import CLEAN_DOCUMENT, under_test

    done = subprocess.run(
        [sys.executable, "-m", "vdi2770_validate", "check", "--json",
         str(CLEAN_DOCUMENT), "no-such-container.zip"],
        capture_output=True, text=True, timeout=120, env=under_test())
    checked, unread = json.loads(done.stdout)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "pdfaVerified" in checked and "path" in checked, sorted(checked)
    assert "pdfaVerified" not in unread, (
        "an unreadable path now carries a PDF/A verdict; the README says it does not")
    assert "unreadable" in unread, sorted(unread)
    assert '`"unreadable"`' in readme, (
        "the README no longer says what an entry for an unopenable path carries")


def test_the_changelog_multiplies_the_attribute_caps_the_same_way_twice():
    """One release section said `2,000×` in one entry and `1,900×` in another.

    Both are the same division — `MAX_ATTRIBUTES` over the worst document the
    corpus holds, which the entry beside them says is 49. `100000 / 49` is
    2,040.8, so one of the two was rounded and the other was wrong, and nothing
    noticed because the two sentences are two hundred lines apart. A figure
    stated twice is a figure that will be stated two ways.
    """
    import re

    from vdi2770.xmlread import MAX_ATTRIBUTES

    unreleased = newest_changelog_section()
    # `\*{0,2}` because one of the two is bold and the other is not. A pattern
    # that matched only the plain one found a single value, agreed with itself,
    # and could not have failed -- which is the shape of defect this gate exists
    # to catch, so the count of matches is asserted before their agreement is.
    said = re.findall(r"([\d,]+)×\*{0,2} (?:above )?the worst document", unreleased)
    assert len(said) >= 2, (
        f"this gate compares two sentences and found {len(said)}; the CHANGELOG "
        f"has been reworded: {said}")
    assert len(set(said)) == 1, (
        f"the same multiple is written two ways: {sorted(set(said))}")

    # `\s*` because the sentence wraps: the count sits on the next line.
    worst = re.search(r"the worst document\s*\*\*(\d+)\*\*", unreleased)
    assert worst, "the CHANGELOG no longer states the worst document's attribute count"
    derived = round(MAX_ATTRIBUTES / int(worst.group(1)), -2)
    assert int(said.pop().replace(",", "")) == derived, (
        f"{MAX_ATTRIBUTES} over {worst.group(1)} rounds to {derived:,.0f}")


def test_the_changelog_states_the_per_rule_ceiling_the_budget_allows():
    """It said `99,997`, and the ceiling is `99,999`.

    A rule that fires once per element can fire once for every element the budget
    admits, less the root — which is an element too. `M10` reaches exactly that
    on a document of nothing but `<DocumentId/>`; `M9` stops one short because
    its own shape costs a child. The figure is derived here rather than measured,
    because measuring it means building a hundred thousand elements and this
    gate should cost nothing.

    The same entry also said the page "now says so" of a page that says *nearly
    a hundred thousand* — which is the right thing for the page to say, since
    which rule the file provokes moves the exact number.
    """
    import re

    from vdi2770.xmlread import MAX_ELEMENTS

    unreleased = newest_changelog_section()
    m = re.search(r"real ceiling is \*\*([\d,]+)\*\*", unreleased)
    assert m, "the CHANGELOG sentence this test pins has been reworded"
    assert int(m.group(1).replace(",", "")) == MAX_ELEMENTS - 1, (
        f"the budget admits {MAX_ELEMENTS} elements, so one rule can fire "
        f"{MAX_ELEMENTS - 1} times; the CHANGELOG says {m.group(1)}")


def test_scope_md_divides_the_ceilings_by_the_rate_it_publishes():
    """The seconds were prose beside a number nobody divided by.

    `docs/scope.md` gives a decompression rate and then says what the two
    whole-read ceilings cost at it. The rate is a measurement and stays one —
    it is the machine's, and the page says so. The seconds are not a
    measurement; they are that division, and they were written as *a few* and *a
    few more* beside a rate that has now been wrong twice (1.1 GB/s, then 0.6).
    Wrong by enough and *a few more* stops being true, with nothing to notice.

    So the ceilings come from the reader's own constants and the arithmetic is
    checked here. A machine half this speed takes twice as long, which is what
    the page tells its reader to do with the figure.
    """
    import re

    from vdi2770 import zipread

    page = (ROOT / "docs" / "scope.md").read_text(encoding="utf-8")
    rate = re.search(r"measured here at \*\*([\d.]+) GB/s\*\*", page)
    assert rate, "scope.md no longer publishes a decompression rate"
    per_second = float(rate.group(1)) * 1e9

    for ceiling, pattern in (
            (zipread.MAX_TOTAL_BYTES, r"2 GiB ceiling costs about \*\*(\d+) seconds?\*\*"),
            (zipread.MAX_TOTAL_DECOMPRESSED, r"ceiling of 4 GiB\s*\n?\s*about \*\*(\d+)\*\*")):
        m = re.search(pattern, page)
        assert m, f"scope.md no longer says what {ceiling} bytes costs at that rate"
        assert int(m.group(1)) == round(ceiling / per_second), (
            f"{ceiling} bytes at {rate.group(1)} GB/s is "
            f"{ceiling / per_second:.1f} s; scope.md says {m.group(1)}")
