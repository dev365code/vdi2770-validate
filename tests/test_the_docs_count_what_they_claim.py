"""Numbers in prose drift silently. Each of these was written true and became
false when the thing it counted changed — and nothing failed, because no test
reads prose.

The rule this file applies: if a document states a count of something this
repository holds, the count is derived here and compared.
"""
import json
import re

from conftest import (
    CORPUS,
    FIXTURES,
    ROOT,
    changelog_sections,
    latest_changelog_claim,
    newest_changelog_section,
    spelled,
)


def containers():
    return sorted(CORPUS.rglob("*.zip")) + sorted(FIXTURES.rglob("*.zip"))


def worst_document_attributes() -> int:
    """The most attributes any `VDI2770_*.xml` in the corpus carries, counted the
    way the budget counts them: with expat and a namespace separator, so
    namespace declarations are not attributes.

    Nested containers included, because the worst one is inside one.
    """
    import contextlib
    import xml.parsers.expat
    import zipfile

    worst = 0

    def count(data: bytes) -> int:
        seen = 0

        def start(_name, attrs):
            nonlocal seen
            seen += len(attrs)

        parser = xml.parsers.expat.ParserCreate(namespace_separator="|")
        parser.StartElementHandler = start
        # Some fixtures are malformed on purpose. What they carry up to the point
        # they break still counts; what they do not is not this gate's business.
        with contextlib.suppress(xml.parsers.expat.ExpatError):
            parser.Parse(data, True)
        return seen

    def walk(archive: zipfile.ZipFile):
        nonlocal worst
        for name in archive.namelist():
            leaf = name.rsplit("/", 1)[-1]
            if leaf.startswith("VDI2770_") and leaf.endswith(".xml"):
                worst = max(worst, count(archive.read(name)))
            elif leaf.lower().endswith(".zip"):
                import io
                try:
                    with zipfile.ZipFile(io.BytesIO(archive.read(name))) as inner:
                        walk(inner)
                except (zipfile.BadZipFile, RuntimeError, OSError):
                    continue          # a fixture that is not a readable archive

    for path in containers():
        try:
            with zipfile.ZipFile(path) as archive:
                walk(archive)
        except (zipfile.BadZipFile, RuntimeError, OSError):
            continue              # a fixture that is deliberately not an archive
    return worst


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
    from vdi2770_validate.model import MAX_LISTED_PER_RULE

    from vdi2770 import pdfread, xmlread, zipread

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

    # Digits *and* words, because the page writes numbers out. This matched
    # `4 prefix` and never `four tries`, so the page said the cap three times
    # over in words while the check that forbids restating it stayed green --
    # the gate's own reason ("two places to change and only one of them
    # gated") was live the whole time it was passing. Scoped to the bullet
    # that describes the scan, because "four" is an ordinary word elsewhere.
    scan = next(b for b in prose.split("\n- ") if "PDF/A claim can be missed" in b)
    flat = " ".join(scan.split())
    for name, unit in (("MAX_STREAMS", "stream"), ("MAX_XMP_PACKETS", "packet"),
                       ("MAX_PDFA_PREFIXES", "prefix")):
        value = getattr(pdfread, name)
        assert not re.search(rf"\b{value}\s+{unit}", prose), (
            f"scope.md restates {name} = {value}; that number belongs to the "
            f"reader's README, which has a gate for it")
        # `spelled` is rebound to a string earlier in this function, so the
        # helper is taken under its own name rather than the shadowed one.
        from conftest import spelled as in_words

        word = in_words(value) if value < 100 else None
        assert not (word and re.search(rf"\b{word}\b", flat)), (
            f"scope.md writes {name} = {value} out as {word!r} in the bullet "
            f"about the scan; that number belongs to the reader's README, and "
            f"a check that reads only digits does not see it")


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
        (ROOT / "packages" / "vdi2770" / "src" / "vdi2770" / "validate" / "data" / "rules.json").read_text(encoding="utf-8"))
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

    # `.get`: a rule may honestly cite nothing -- `M13` is our own reading of
    # a contradiction, with no observed key behind it -- and a docs gate that
    # raises KeyError instead of reporting is a gate nobody can read.
    citations = sum(len(r.get("refKeys", ())) for r in catalogue["rules"])
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
    words = {6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
             11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen"}
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

    from vdi2770_validate.runner import check_file

    from vdi2770_validate import report as rendering

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
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    from mutation_table import TABLE

    # `[a-z-]+` could not match a count past twenty-nine, where `spelled` starts
    # returning digits — so at thirty rows this gate reported "the sentence has
    # been reworded" and no wording could satisfy it.
    # Read from CONTRIBUTING rather than the CHANGELOG. A release note is for
    # people outside this repository, and how many rows a harness holds is not
    # something they can act on; it moved to the page that tells a contributor
    # to run the harness. The number stays checked because it is still written
    # down somewhere, and `tools/mutation_table.py` prints it on demand -- so
    # this is a number a reader can verify, not one they have to trust.
    m = re.search(r"it holds ([a-z0-9-]+) rows, each naming the pytest",
                  (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8"))
    assert m, "the CONTRIBUTING sentence this test pins has been reworded"
    said = m.group(1)
    expected = spelled(len(TABLE))
    assert said == expected, (
        f"CONTRIBUTING says {said} mutation rows and the table has {len(TABLE)}")


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
    # And the files that ship inside both wheels as the licence notice. NOTICE
    # names, for each third-party file, where it came from and what may be done
    # with it -- and it named two of them at the paths they had before the
    # merge, so a legal notice inside a published wheel pointed at files that
    # are not there. It was outside every gate because it is not a `.md`.
    docs += ["NOTICE", "THIRD_PARTY.md"]

    texts = {d: (ROOT / d).read_text(encoding="utf-8") for d in docs if (ROOT / d).exists()}
    texts["CHANGELOG.md (newest section)"] = newest_changelog_section()

    pattern = re.compile(
        r"`((?:tests|tools|src|packages|docs|corpus)/[\w./-]+\.(?:py|json|md|xsd|java))"
        r"(?:::(\w+))?`")
    # NOTICE is plain text and writes its paths bare, so the backtick pattern
    # walked straight past both of the ones that had moved. Anchored to a known
    # top-level directory and not preceded by a `/`, which is what keeps the
    # retrieval URLs in that same file from matching.
    bare = re.compile(
        r"(?<![/\w.-])((?:tests|tools|src|packages|docs|corpus)/[\w./-]+"
        r"\.(?:py|json|md|xsd|java))")

    seen = 0
    for doc, prose in texts.items():
        for path in bare.findall(prose) if doc in ("NOTICE",) else []:
            seen += 1
            assert (ROOT / path).exists(), (
                f"{doc} cites {path}, which is not in this repository. This "
                f"file ships inside both wheels as the licence notice, so a "
                f"path that has moved is a legal notice pointing at nothing.")
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
    #
    # 23 to 17 when 0.7.0 was cut and work continued above it: six of the 23 were
    # cited by that release's own section, and the newest section is a new one
    # that does not repeat them. Nothing stopped being checked -- the released
    # section is history and out of scope by design -- but the number moving for
    # that reason is worth writing down, because it will move again at every
    # release and "the count dropped" must not become a thing anyone waves past.
    #
    # 19 to 35 when NOTICE and THIRD_PARTY.md came into scope. They were outside
    # every gate because one is not a `.md` and the other was simply never
    # listed -- and NOTICE, which ships inside both wheels as the licence
    # notice, was naming two bundled files at the paths they had before the
    # merge. Sixteen citations were being made and none of them checked.
    # 35 to 31 when the two notices were made true about the wheels they travel
    # in: the root one stopped listing files it does not carry, and the engine's
    # names its two by the path they have *inside the wheel*, which is not a
    # repository path and is not this pattern's business.
    # 31 to 28 when 0.8.0 was cut and work continued above it, the same way as
    # at 0.7.0: three of the 31 were cited by that release's own section, and
    # the newest section is a new one that does not repeat them.
    # 28 to 29 when SECURITY.md's row on amplification after a member is
    # accepted came to cover reading that member a second time, and named the
    # test that holds it to that.
    # 29 to 30 when the GitHub Action arrived: SECURITY.md now discloses that the
    # action downloads the file it runs -- which the checker never does -- and
    # cites the test that holds the action to admitting it.
    # 30 to 31 when `docs/report-schema.md` arrived: the JSON report's contract
    # page points a reader at `docs/rules.md` for the sentence behind a rule id,
    # which is a repository path and so is checked like the rest.
    # 31 to 32 when the section being written started naming the generated page
    # a rule's prose lives on, so the reader of the entry can go and read it.
    # 32 to 33 when the report's contract page started naming the stored report
    # it is checked against, so a reader can see what the tool actually said
    # beside what the page promises.
    # 33 to 35 when the entry for this release named both halves of the report
    # contract -- the page that states it and the stored report it is checked
    # against -- so a reader of the changelog can go and read either.
    # 35 to 36 when the entry correcting the page-count sentence named the page
    # it corrects, `docs/divergences.md`: the claim is about what that page says,
    # so a reader who cannot reach the page cannot check the claim.
    # 36 to 37 when the entry about the widened media-type table named the page
    # that had gone on describing the narrow one, `docs/scope.md`, so a reader
    # of the entry can go and see what the page says now.
    # 37 to 38 when a figure was corrected by naming the harness that produces
    # it. A number published without the thing that makes it is a number nobody
    # can check, which is how "thirty-three bytes" survived into a released
    # section and an advisory when the pair rebuilds eleven bytes apart. Both
    # the correction and the entry that carries the figure now cite the test.
    # 38 to 39 when the entry about the bounded listing named the harness that
    # produces its figures. It had to: the numbers first published there were
    # measured with an ad-hoc script whose kind names were six characters, and
    # the repository's own fixture spells them `Kind{i:04d}` -- eight characters
    # below ten thousand and nine above -- so the same measurement gives 4,096
    # and 430,096 rather than 3,296 and 320,096. Naming the harness is what made
    # the two disagree out loud.
    assert seen == 39, (
        f"{seen} citations found, not 39. If you added or removed one, say so "
        f"here; if you did not, some of them just stopped being checked.")


def test_the_changelog_counts_the_rules_that_fire_because_we_declined():
    """`test_catalogue.py::TOOL_RULES` gates the *set* of `about: tool` rules and
    made anyone adding one write down why. Nothing tied the prose count to it, so
    the bullet describing the policy went stale inside the same release section
    that made it stale: it said four while this release shipped seven.
    """
    import json

    catalogue = json.loads(
        (ROOT / "packages" / "vdi2770" / "src" / "vdi2770" / "validate" / "data" / "rules.json").read_text(encoding="utf-8"))
    declined = [r["id"] for r in catalogue["rules"] if r["about"] == "tool"]

    _, m = latest_changelog_claim(
        r"([A-Za-z0-9-]+) rules fire because the validator declined")
    assert m, "the CHANGELOG sentence this test pins has been reworded"
    assert m.group(1).lower() == spelled(len(declined)), (
        f"{len(declined)} rules are `about: tool` ({sorted(declined)}); the "
        f"CHANGELOG says {m.group(1)}")


def test_contributing_counts_the_files_make_standalone_runs():
    """It said 48 — the root suite only, forgetting the reader's seven — while
    the target ran 55, and then 56 the moment another file was added. A number
    in prose about a directory listing drifts the first time anyone adds a file.

    Read from CONTRIBUTING, like the count of mutation rows and for the same
    reason: how many files a target runs is a contributor's number, not a
    release note's. The changelog used to carry it, and the first file added
    after a release left that released sentence stale -- and it was edited to
    match, which is exactly what a released section must not be.
    """

    files = sorted((ROOT / "tests").glob("test_*.py"))
    files += sorted((ROOT / "packages" / "vdi2770" / "tests").glob("test_*.py"))

    m = re.search(r"runs each of the (\d+) test files on its own",
                  (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8"))
    assert m, "the CONTRIBUTING sentence this test pins has been reworded"
    assert int(m.group(1)) == len(files), (
        f"`make standalone` runs {len(files)} files; CONTRIBUTING says {m.group(1)}")


def test_the_changelog_counts_the_trailer_shapes_it_claims_are_pinned():
    """The entry said seventeen, then twenty-three; it was twenty-two.

    I wrote the second number without counting, in a section whose subject is a
    scan that has now been repaired five times. A count in prose is a claim
    nobody re-checks, which is why the sibling test above exists for the mutation
    table -- so this one exists for the other number in the same section.
    """
    import ast

    _, m = latest_changelog_claim(r"([A-Za-z-]+) shapes are pinned")
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


#: Every commit here that carries no `Signed-off-by`, by name.
#:
#: A count was not enough, twice over. It is satisfied by any set of the same
#: size, so a total can be raised to match reality by whoever notices it going
#: red -- which absorbs a new unsigned commit into a paragraph about an old
#: lapse instead of naming it. And the assertion meant to catch a reopened lapse
#: compared positions: `git log --reverse` is oldest-first, so it read the
#: commits *after* the newest unsigned one, and when the unsigned commit is the
#: tip -- exactly when a lapse reopens -- that range is empty and it passes
#: having read nothing. It did, on `d4d647d`.
#:
#: Names depend on neither position nor arithmetic. A commit that is not on this
#: list and carries no trailer fails on arrival, and putting one here is a
#: deliberate act that has to say which commit, and why, on the page.
UNSIGNED = (
    "501d6c3bd1c66449e1ba1024e168953d44c972d2",
    "d65421977c615414e5a326d4734f4039f2365511",
    "59dd67f496b6376a73697f95faa294c0716722ee",
    "d8828631fa4570f1b4e980f94b4814d81a674248",
    "4d00dd176f5851e54b3f259dce121f406ea4a41d",
    "f354c4254d0f6e4fc982f305c15c00095382a470",
    "2dd35b4a13d37112c8e2c4cf5cd4dd2b9ad1b942",
    "87b3e7a2374f1a14464e4b05b4f52867ecbe75bb",
    "03292e534a47341d741615321cab17e7de32b257",
    "e2eac7299dc9b2e1c80c80a293971bc35f59c97f",
    "624500a9c659a48d5de9b00bd074ce6067eabd20",
    "c7485f049f00a2b5b3a73867cb83a550a88ee36c",
    "06aebd295547b215b68b63d4b39a72168d64ee8b",
    "6b81c4e03b204805101d1bd501244122f44a0d48",
    "aca780971479d67feae4853e9e0b7488f4a90c08",
    "c4e920e5e4175be6ffff22ba2d5ef0e50f00d1fc",
    "3e064cedb96074f6cf41d39068f5f92796875aa2",
    "7db1abfc3e588f73452ee48531e4b9cc8a66a1dd",
    "c03ba036dab13fe8615974c630d38a3b05f6777e",
    "a56842b14626077673c158d0204f0e573da358af",
    "e37b135218dda5886acdecef28a4e055bdc5401f",
    "8891ff8e0eb811ea22b7f650237876ca34bb2162",
    "f31cdad8c92949c67bb5ff0d0fbced524d09d05f",
    "961576e25cb05db3a94bc8369504f5a1e4f4b670",
    "ba3ec91884c18641d0d50409d2d508dbe51bee8d",
    "b50cc412ae06dc5f4cf794c48e62ed5198d7ba98",
    "92ea1f4c615f0ab944a94a4360a696ee337c256e",
    "eb6f1cc596a717eebc57e2b8690042629a640739",
    "9bc2d597c92bb60ef46dfc1e5868f3bfbbf57227",
    "f41016a145a9025796ce1cc3cf227f8d25b9b16b",
    "16ebebe751ebc5cf37b3f135a62620624ed783c6",
    "cb1cfa45d1f5cb425dc75c621a78b52abfe759a1",
    "d4d647d17327c72ef00d2b417b4a2d9d63cf83da",
)


def test_contributing_is_right_about_who_signed_off():
    """`CONTRIBUTING.md` said every commit carries a `Signed-off-by` line.

    Thirty-two do not. The practice was in place, lapsed for a run of commits,
    and resumed — and nothing noticed, because `.github/dco.yml` checks
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
    rows = [line.split("\x01", 1) for line in got.stdout.splitlines() if "\x01" in line]
    hashes = [h for h, _ in rows]
    signed = [("Signed-off-by" in trailers) for _, trailers in rows]
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

    # And which, not merely how many. This is the assertion that fails on a new
    # unsigned commit whatever its position, including the tip -- where the
    # positional check below reads an empty range and says nothing.
    here = [h for h, ok in zip(hashes, signed) if not ok]
    arrived = [h for h in here if h not in UNSIGNED]
    assert not arrived, (
        "these commits carry no Signed-off-by line and are not among the ones "
        "this repository has written down:\n  " + "\n  ".join(arrived)
        + "\nSign them, or -- if history cannot be rewound -- add them to "
          "UNSIGNED and say on the page which commit and why.")
    gone = [h for h in UNSIGNED if h not in here]
    assert not gone, (
        "UNSIGNED names commits that are signed or absent, so the list has "
        "stopped describing this repository:\n  " + "\n  ".join(gone))

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
    stating = next((text for _heading, text in changelog_sections()
                    if "Upgrading from" in text), "")
    paragraphs = [t for t in stating.split("\n\n") if "Upgrading from" in t]
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
    path that could not be opened. The heterogeneous shape is deliberate: there
    is no PDF/A verdict to give about a file nobody read. What was wrong was the
    sentence, and a consumer that believed it raised `KeyError` on exactly the
    path the sweep exists to keep going past.

    The README also says what that entry does *not* carry, and nothing counted
    it: three fields saying what produced the run were added to that branch and
    the sentence stayed as it was, which is the same defect in the other
    direction. So the whole key set is asserted here.
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
    # And nothing else beyond what says who produced the run. A key added here
    # is a promise the README has to make or the branch has to drop.
    assert set(unread) == {"path", "unreadable", "schemaVersion", "toolVersion",
                           "vdiSchema"}, (
        f"an entry for a path nobody read carries {sorted(unread)}; the README "
        f"says what it carries and this is not that")
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

    unreleased = next((text for _heading, text in changelog_sections()
                       if re.search(r"×\*{0,2} (?:above )?the worst document", text)),
                      "")
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

    # Counted out of the corpus, not read back out of the prose. Taking the
    # divisor from the same paragraph as the quotient meant the two always
    # agreed: move the corpus to sixty attributes on one element and this stayed
    # green about a multiple that had become wrong.
    assert int(worst.group(1)) == worst_document_attributes(), (
        f"the CHANGELOG says the worst document carries {worst.group(1)} "
        f"attributes; the corpus's worst carries {worst_document_attributes()}")

    derived = round(MAX_ATTRIBUTES / worst_document_attributes(), -2)
    assert int(said[0].replace(",", "")) == derived, (
        f"{MAX_ATTRIBUTES} over {worst_document_attributes()} rounds to {derived:,.0f}")


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

    from vdi2770.xmlread import MAX_ELEMENTS

    _, m = latest_changelog_claim(r"real ceiling is \*\*([\d,]+)\*\*")
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


def test_the_scope_page_quotes_what_the_tool_prints():
    """It shows two sentences the report carries. A page that quotes output is a
    page that goes stale — the README's sample lost its ending twice before a
    gate ran the command instead of the renderer, and this quotes the same run's
    closing statement one file along."""
    import subprocess
    import sys

    from conftest import under_test

    page = (ROOT / "docs" / "scope.md").read_text(encoding="utf-8")
    done = subprocess.run(
        [sys.executable, "-m", "vdi2770_validate", "check",
         "corpus/examples/missingdocuments/folders.zip"],
        cwd=ROOT, capture_output=True, text=True, env=under_test())
    printed = done.stdout

    said = ("This tool does not verify PDF/A conformance. It reports the claim a "
            "file makes\nabout itself where it finds one; only a PDF/A validator "
            "can say whether that\nclaim is true.")
    assert said in printed, printed[-400:]
    assert said in page, "the page quotes a refusal the tool does not print"

    shape = "  read 1 of 1 archives, 1 of 3 metadata files"
    assert shape in printed, printed[-400:]
    assert shape.strip() in page, "the page quotes a figure the tool does not print"


def test_the_upgrade_warning_counts_the_rules_it_names():
    """The sentence an upgrading reader sees first says how many ids can turn
    their green run red, and then names them. The number was written once and
    the list grew under it.

    This does not check the list is complete — nothing here can, because a rule
    can turn a run red through a path that is new while its id is not, which is
    what happened: `Z5` existed in 0.6.0 and could not be reached from the PDF
    layer. It checks the two halves of one sentence agree.
    """
    import re

    from conftest import spelled

    _, said = latest_changelog_claim(
        r"\*\*Upgrading from [\d.]+ will turn some green runs red\.\*\*\s+"
        r"(\w+) rules? can do it:(.*?)\n\n", re.S)
    assert said, "the upgrade warning has been reworded; this counts its ids"
    # The list is the sentence after the colon, and only that. What follows it
    # explains one of the ids and names others in passing -- `F2`, for what
    # 0.6.0 used to say -- and those are not ids that turn a run red. The
    # parenthetical goes too: it exists to name an id and then take it back out.
    listed = re.sub(r"\([^)]*\)", "", said.group(2)).split(". ")[0]
    named = sorted(set(re.findall(r"`([A-Z]\d+)`", listed)))
    assert named, said.group(2)
    assert said.group(1).lower() == spelled(len(named)), (
        f"the warning says {said.group(1)!r} and names {len(named)}: {named}")


def test_the_readme_names_the_classes_the_two_sources_actually_disagree_on():
    """The front page tells a reader which rows to distrust, by id.

    Nothing derived it. The list and the two counts were typed once and would
    have gone on reading true after a name was corrected, a class was added, or
    a source was re-transcribed — and the reader most likely to check them is
    the one deciding whether to trust this tool's verdicts on their own
    containers.

    Read from `document-classes.json`, which is also what the rules match on,
    so the page and the behaviour cannot drift apart.
    """
    import json

    classes = json.loads(
        (ROOT / "packages" / "vdi2770" / "src" / "vdi2770" / "validate" / "data" / "document-classes.json")
        .read_text(encoding="utf-8"))["classes"]
    # Whitespace collapsed: these sentences wrap, and a line break between
    # "twelve" and "German" is not a change of claim. The first version of this
    # test read the raw text and failed on the wrapping rather than on the fact.
    raw = (ROOT / "README.md").read_text(encoding="utf-8")
    readme = re.sub(r"\s+", " ", raw)

    agree_de = [c["classId"] for c in classes if c["nameDe"]["agree"]]
    differ_en = [c["classId"] for c in classes if not c["nameEn"]["agree"]]

    assert len(agree_de) == len(classes), (
        f"the sources no longer agree on every German name ({len(agree_de)} of "
        f"{len(classes)}), and the page says they do")
    assert f"all {spelled(len(classes))} German names" in readme, (
        f"the sources agree on {len(classes)} German names and the page says "
        f"otherwise")
    assert f"disagree on {spelled(len(differ_en))} English ones" in readme, (
        f"they disagree on {len(differ_en)} English names and the page says "
        f"otherwise")
    for cid in differ_en:
        assert cid in readme, (
            f"{cid} is a class the two sources render differently and the page "
            f"does not name it")
    named = set(re.findall(r"\b(0[1-4]-0[0-9])\b", raw))
    assert not (named - set(differ_en)), (
        f"the page names {sorted(named - set(differ_en))} as disputed and the "
        f"sources agree on them")


def test_a_claim_is_held_where_it_was_last_made():
    """The gates in this file pin sentences, and they looked for them in the
    newest changelog section only — on the reasoning that work lands above the
    releases, so the top section is the one whose claims must still be true.

    Half of that is right. The other half is not: a new section does not restate
    what a release already said, so the first change made *after* a release is
    cut turns seven gates red on prose that is entirely correct. And the repair
    that suggests itself then is editing the released section to match today,
    which is the one thing this project's changelog rule forbids — that is
    falsifying the record, not fixing a number.

    So a claim stands until it is restated: the sections are read newest first
    and the first one that makes the claim is the one held to it. Proved here on
    both halves, because a helper that finds a sentence is worthless without the
    guarantee that it stops at the *newest* one — a stale duplicate below would
    otherwise answer for a claim that has since changed.
    """
    from conftest import latest_changelog_claim

    heading, match = latest_changelog_claim(r"real ceiling is \*\*([\d,]+)\*\*")
    assert match, "no changelog section states the per-rule ceiling"
    assert heading.startswith("## "), heading

    # And it says so rather than answering with something: a gate whose helper
    # invents a match for a sentence nobody wrote is a gate that cannot fail.
    assert latest_changelog_claim(r"\bzzz-no-section-says-this\b") == (None, None)


def test_the_claim_reader_prefers_the_newer_of_two_statements(tmp_path,
                                                              monkeypatch):
    """The ordering, on a changelog built for it. Reading the real file cannot
    prove this: it proves whatever that file happens to hold today."""
    import conftest

    page = tmp_path / "CHANGELOG.md"
    page.write_text("# Changelog\n\n"
                    "## Unreleased\n\nit runs 9 files\n\n"
                    "## 0.1.0 — 2020-01-01\n\nit runs 4 files\n",
                    encoding="utf-8")
    monkeypatch.setattr(conftest, "ROOT", tmp_path)
    heading, match = conftest.latest_changelog_claim(r"it runs (\d+) files")
    assert heading.startswith("## Unreleased"), heading
    assert match.group(1) == "9", match.group(1)

    # And it reaches past the top section when the top does not restate it.
    page.write_text("# Changelog\n\n"
                    "## Unreleased\n\nsomething else entirely\n\n"
                    "## 0.1.0 — 2020-01-01\n\nit runs 4 files\n",
                    encoding="utf-8")
    heading, match = conftest.latest_changelog_claim(r"it runs (\d+) files")
    assert heading.startswith("## 0.1.0"), heading
    assert match.group(1) == "4", match.group(1)


def test_the_scope_page_counts_the_media_types_the_rule_knows():
    """The page tells a reader which declared types `F3` judges, and the number
    is the whole of the answer: a type outside the table is not checked at all,
    and this page is where somebody looks to find that out.

    It said two while the table grew to fifteen -- in the tree of the release
    that grew it, so the section announcing the change and the page describing
    the limit disagreed about one rule at the same commit. Derived from the
    table now, because a number written beside a table is right on the day it
    is written.
    """
    import re

    from vdi2770.validate.rules.files import EXTENSION_FOR

    prose = " ".join((ROOT / "docs" / "scope.md").read_text(encoding="utf-8").split())
    m = re.search(r"extension agreement is checked against a table of "
                  r"([a-z-]+) media types", prose)
    assert m, "the scope page's sentence about media types has been reworded"
    assert m.group(1) == spelled(len(EXTENSION_FOR)), (
        f"scope.md says {m.group(1)} media types and the table has "
        f"{len(EXTENSION_FOR)}")


def test_the_cli_counts_the_warnings_the_catalogue_holds():
    """The comment beside the exit-code decision said nine, and there are ten.

    `M13` made it ten in the release that added it, and the same sentence also
    said every warning is about the container -- which `M13` is not, because it
    is about the delivery. A number written beside the code that acts on it is
    the kind that goes stale quietly: nothing reads it, so nothing contradicts
    it. This derives it from the catalogue instead.
    """
    import json

    catalogue = json.loads(
        (ROOT / "packages" / "vdi2770" / "src" / "vdi2770" / "validate"
         / "data" / "rules.json").read_text(encoding="utf-8"))
    rules = catalogue["rules"] if isinstance(catalogue, dict) else catalogue
    warnings = [r["id"] for r in rules if r["severity"] == "warning"]

    source = (ROOT / "packages" / "vdi2770" / "src" / "vdi2770" / "validate"
              / "cli.py").read_text(encoding="utf-8")
    want = spelled(len(warnings)).capitalize()
    assert f"{want} rules are warnings" in source, (
        f"the catalogue holds {len(warnings)} warnings ({', '.join(sorted(warnings))}) "
        f"and cli.py does not say {want.lower()}")


def test_the_changelog_quotes_the_report_string_the_tool_prints():
    """The entry shows what a bounded listing looks like, so a reader can find
    it in their own report. It quoted *five of 40001 shown* while the tool
    prints `-- 5 of 40001 shown` -- a word where there is a digit, and without
    the dashes that begin it. Somebody grepping their report for the phrase in
    the release note finds nothing, which is the one thing the quotation is for.
    """
    from vdi2770.validate.rules.delivery import MOST_LISTED, _first_few

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    _shown, in_all = _first_few([f"K{i}" for i in range(40001)], "kinds")
    assert in_all.strip().rstrip(";") in changelog, (
        f"the entry does not quote what the tool prints. It prints "
        f"{in_all.strip()!r} for 40001 items with MOST_LISTED = {MOST_LISTED}")
