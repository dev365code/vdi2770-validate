"""The licensing claims are pinned, because they are the ones that matter if wrong.

This project bundles someone else's schema, a table extracted from someone
else's publication, and a corpus from an MIT project. Getting the notices wrong
is not a style problem.
"""
import hashlib
import json
import re

from conftest import ROOT

THIRD_PARTY = (ROOT / "THIRD_PARTY.md").read_text(encoding="utf-8")
NOTICE = (ROOT / "NOTICE").read_text(encoding="utf-8")
DATA = ROOT / "src" / "vdi2770_validate" / "data"


def license_files():
    """Read the packaged licence list without a TOML parser — the tool supports
    Python 3.9, where tomllib does not exist, and plant systems run 3.9."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r"^license-files\s*=\s*\[(.*?)\]", text, re.M | re.S)
    assert m, "pyproject.toml declares no license-files"
    return re.findall(r'"([^"]+)"', m.group(1))


def test_the_notices_travel_with_the_wheel():
    """Apache-2.0 requires the NOTICE to be distributed; the bundled schema and
    table make THIRD_PARTY.md carry the MIT and CC BY texts."""
    files = license_files()
    for wanted in ("LICENSE", "NOTICE", "THIRD_PARTY.md"):
        assert wanted in files, f"{wanted} would not be packaged"
        assert (ROOT / wanted).exists()


def test_the_notice_of_the_half_that_used_to_ship_alone_travels_too():
    """The reader carried its own NOTICE while it was published as its own
    distribution, and that NOTICE says something the root one cannot: that this
    half bundles nothing of anybody else's. One distribution now, so the list
    that has to name it is this one -- and a file that stops being packaged the
    moment its own `pyproject.toml` is deleted is exactly the loss a rename is
    likely to make quietly."""
    reader = "packages/vdi2770/NOTICE"
    assert reader in license_files(), f"{reader} would not be packaged"
    assert (ROOT / reader).exists()


def test_the_readers_notice_sends_people_where_the_material_actually_is():
    """A NOTICE is read by whoever has to clear the package for use, and it was
    written when this repository published two distributions: it told them the
    schema, the class table and the corpus were accounted for "in the sibling
    package `vdi2770-validate`".

    That name still resolves, and after the rename it resolves to a redirect
    that contains no notices, no THIRD_PARTY.md and no code — so the sentence
    now sends the one reader who follows it to an empty package. The material
    did not move; the distribution boundary the sentence described did.
    """
    reader = (ROOT / "packages" / "vdi2770" / "NOTICE").read_text(encoding="utf-8")
    assert "THIRD_PARTY.md" in reader, (
        "the reader's NOTICE no longer says where the bundled material is "
        "accounted for")
    assert "vdi2770-validate" not in reader, (
        "the reader's NOTICE points at `vdi2770-validate` for the third-party "
        "accounting, and that distribution is now a redirect carrying none of "
        "it. Point at this distribution's own THIRD_PARTY.md.")


def test_mit_permission_notice_is_reproduced_in_full():
    """MIT: 'the above copyright notice AND THIS PERMISSION NOTICE shall be
    included'. A copyright line on its own does not satisfy it."""
    for where in (THIRD_PARTY, (ROOT / "corpus" / "NOTICE").read_text(encoding="utf-8")):
        assert "Permission is hereby granted, free of charge" in where
        assert "THE SOFTWARE IS PROVIDED \"AS IS\"" in where
        assert "Copyright (C) 2021 Johannes Schmidt" in where


def test_cc_by_attribution_states_the_modification():
    """CC BY 4.0 requires the licence, the creator, a link, and an indication
    that the material was changed. We reformatted a table, so we say so."""
    assert "CC BY 4.0" in THIRD_PARTY
    assert "creativecommons.org/licenses/by/4.0" in THIRD_PARTY
    assert "Industrial Digital Twin Association" in THIRD_PARTY
    assert re.search(r"extracted and reformatted", THIRD_PARTY)
    # Reformatting was not the only change, and "indicate if You modified" is not
    # satisfied by naming the change that is easy to admit. One cell of the table
    # is stored differently from how the source prints it.
    assert "Commissioning, de-" in THIRD_PARTY, (
        "the one transcription that departs from the printed table is no longer "
        "disclosed, so the CC BY modification statement is now incomplete")
    classes = json.loads((DATA / "document-classes.json").read_text(encoding="utf-8"))
    assert "Commissioning, de-" in classes["_sources"]["german_and_irdi"]["modification"], (
        "the data file has to carry the same disclosure: it ships in the wheel "
        "and THIRD_PARTY.md is what a reader finds only if they go looking")


def test_every_bundled_data_file_is_accounted_for():
    for f in sorted(DATA.iterdir()):
        if f.name.endswith(".py"):
            continue
        assert f.name in THIRD_PARTY, f"{f.name} is shipped but not listed in THIRD_PARTY.md"


def test_the_vendored_schema_is_the_bytes_vdi_published():
    """We claim byte-for-byte verbatim and print a hash to prove it. If the file
    is ever touched, this fails before anyone can repeat the claim."""
    xsd = DATA / "VDI2770_Schema_2019-08-23.xsd"
    digest = hashlib.sha256(xsd.read_bytes()).hexdigest()
    assert digest in THIRD_PARTY, "the hash in THIRD_PARTY.md no longer matches the shipped file"
    assert digest == "f7a704fe4bba095eaa4e95be0b9853205412301ad09c4bcffb4c5f0f666cb805"


def test_the_paid_guideline_is_not_claimed_as_a_source():
    """Every rule must trace to something free. `ours` is allowed, but it has to
    explain itself; nothing may cite the guideline text."""
    rules = json.loads((DATA / "rules.json").read_text(encoding="utf-8"))["rules"]
    for r in rules:
        basis = (r.get("basis") or "").lower()
        assert "blatt" not in basis, f"{r['id']} cites the paywalled guideline as its basis"
    assert "was not consulted" in THIRD_PARTY or "not read" in THIRD_PARTY


def test_unofficial_is_stated_where_a_reader_will_see_it():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Unofficial" in readme or "unofficial" in readme
    assert "not affiliated" in readme.lower()
    assert "not affiliated" in THIRD_PARTY.lower()


def test_the_oracle_evidence_records_identifiers_and_not_their_prose():
    """`docs/oracle-sweep.json` is produced by running someone else's MIT-licensed
    software over our containers. Codes are identifiers; their message strings are
    their prose, and this project vendors exactly one bounded list of those with
    the licence attached. A change to the capture that started recording `text`
    would quietly widen what we redistribute, so the shape is asserted rather
    than trusted."""
    import json
    import re

    path = ROOT / "docs" / "oracle-sweep.json"
    assert path.name in THIRD_PARTY, "the evidence file is not listed in THIRD_PARTY.md"

    strings = []

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            strings.append(node)

    walk(json.loads(path.read_text(encoding="utf-8"))["containers"])
    assert strings, "the evidence file recorded nothing"
    allowed = re.compile(r"^(?:[A-Z]{1,4}_\d{3}|[A-Z]\d{1,2}|«uncoded»)$")
    strays = sorted({s for s in strings if not allowed.match(s)})
    assert not strays, f"not identifiers: {strays[:5]}"


def test_the_oracle_harness_is_accounted_for():
    assert "Sweep.java" in THIRD_PARTY
    harness = (ROOT / "tools" / "oracle" / "Sweep.java").read_text(encoding="utf-8")
    assert "de.vdi.vdi2770" in harness, "the harness no longer imports theirs; update the note"
    assert "Copyright (C) 2021" not in harness, "their source must not be pasted into ours"


def test_no_foreign_log_or_build_output_is_tracked():
    """Running the differential oracle drops the reference implementation's log4j
    output into the working directory, and `git add -A` committed one: 59 KB of
    somebody else's log, with absolute paths from the machine that ran it, in a
    repository that accounts for every other byte it carries from them.

    It never reached a published artifact — MANIFEST.in lists what ships — but it
    was in the repository, and this is cheaper than remembering."""
    import subprocess

    # Inside an sdist there is no repository, and the question is the same one:
    # does this distribution carry a stray. Asking git when git is there keeps
    # ignored files out of the answer; walking the tree covers the sdist, where
    # only shipped files exist anyway. (A `git ls-files` with no fallback is what
    # broke the sdist gate the first time this test was written.)
    found = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if found.returncode == 0:
        names = found.stdout.split()
    else:
        skip = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", "build", "dist"}
        names = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*")
                 if p.is_file() and not skip & set(p.relative_to(ROOT).parts)]
    assert names, "nothing to inspect"

    strays = [f for f in names
              if f.endswith((".log", ".jar", ".class", ".orig", ".rej"))
              or f.split("/")[0] == "target"]
    assert not strays, f"build or log output is carried: {strays}"


def test_the_vendored_message_set_is_the_bytes_that_were_extracted():
    """`tests/data/oracle-messages.json` is what proves no remedy of ours is a
    translation of somebody else's. Weakening it weakens that proof, and the
    only floor was "more than a hundred strings".

    Its provenance has two halves. The half that needs the reference checkout —
    are these really that project's messages at that commit — is
    `tools/capture_oracle.py --check-messages`, outside `make check` for the same
    reason the sweep is. The half that does not is here: the bytes have not moved
    and the file agrees with itself.
    """
    oracle = ROOT / "tests" / "data" / "oracle-messages.json"
    digest = hashlib.sha256(oracle.read_bytes()).hexdigest()
    assert digest == "24b0121f4a3f00f14321f8cc1ab9e8df1930e5418e06949efe6649950cb1ec51", (
        "the vendored message set has changed. If that was deliberate, it came from "
        "`capture_oracle.py --messages` against the pinned commit — say so and move "
        "this hash; if it was not, the licensing gate is now comparing against "
        "something nobody vouched for.")

    body = json.loads(oracle.read_text(encoding="utf-8"))
    assert body["count"] == len(body["messages"]), (
        f"the file says {body['count']} messages and carries {len(body['messages'])}")
    assert body["_source"]["commit"] == "e47c13c1925abc3ed4698cb5ed9e73b5eb544353", (
        "the messages and the oracle sweep must come from one commit of the reference")
    assert len(set(body["messages"])) == len(body["messages"]), "the set has duplicates"


#: Prose surfaces. Every one of these is published: `README.md` and
#: `CHANGELOG.md` are what PyPI links to, `NOTICE` and `THIRD_PARTY.md` travel
#: in the wheel, and `docs/` is what a reader follows from either.
PROSE = ["README.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md",
         "NOTICE", "THIRD_PARTY.md"]

_ASSERTS = re.compile(
    r"(VDI\s?2770|the guideline|the standard)\s+"
    r"(requires?|required|mandates?|demands?|prescribes?|stipulates?|"
    r"specifies|defines|says|states|forbids?|prohibits?|allows?|permits?)\b",
    re.I)

#: Prose may say what VDI 2770 requires only where it also says where that came
#: from, or where it is naming the form this project refuses to use. Each entry
#: records which of the two it is. Reword the sentence and it stops matching, so
#: the decision gets made once per sentence rather than once per project.
SOURCED = {
    "README.md": [
        ("VDI 2770 defines twelve document classes",
         "the sentence after it names the two sources that publish the table free"),
    ],
    "CONTRIBUTING.md": [
        ("not what the standard requires",
         "an instruction not to assert it — a mention, not a claim"),
    ],
    "docs/licensing.md": [
        ("so this is what VDI 2770 requires",
         "the policy sentence, quoting the form it forbids"),
    ],
}


def test_prose_does_not_assert_what_the_paid_guideline_requires():
    """`rules.json` carries an `obligation` on every rule so that no claim about
    VDI 2770 travels without its source. Prose had no such gate, and a sentence
    in the changelog asserted "VDI 2770 requires PDF/A" with nothing behind it —
    a claim `P3` and `P4` are both written to refuse, since their obligation is
    `ours` precisely because we cannot check the guideline.

    The guideline is paid and was not read. A statement about what it requires is
    therefore either sourced somewhere free, or it is repetition of something
    somebody once heard — which is the thing CONTRIBUTING.md forbids "even from
    memory".
    """
    paths = PROSE + sorted(str(p.relative_to(ROOT)) for p in (ROOT / "docs").glob("*.md"))
    unsourced = []
    for name in paths:
        path = ROOT / name
        if not path.exists():
            continue
        # Collapsed, so a sentence that wraps across lines is still one string
        # and an allowance keyed on its words survives a re-wrap.
        text = " ".join(path.read_text(encoding="utf-8").split())
        for m in _ASSERTS.finditer(text):
            context = text[max(0, m.start() - 90):m.end() + 90]
            if any(fragment in context for fragment, _ in SOURCED.get(name, ())):
                continue
            unsourced.append(f"{name}: …{context}…")
    assert not unsourced, (
        "a public page states what VDI 2770 requires without saying where that "
        "came from:\n  " + "\n  ".join(unsourced))


def test_every_allowance_still_matches_something():
    """An allowance for a sentence nobody wrote any more is a hole with a reason
    attached. This is the count assert the generated files get."""
    for name, allowed in SOURCED.items():
        text = " ".join((ROOT / name).read_text(encoding="utf-8").split())
        for fragment, why in allowed:
            assert fragment in text, (
                f"{name} no longer contains {fragment!r}, allowed because {why}")


def _tracked_names():
    """Git when there is a repository, a walk when there is not — the same
    question has to be answerable inside an sdist, where only shipped files
    exist."""
    import subprocess

    found = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if found.returncode == 0 and found.stdout.split():
        return found.stdout.split()
    skip = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", "build", "dist", ".venv"}
    return [str(p.relative_to(ROOT)) for p in ROOT.rglob("*")
            if p.is_file() and not skip & set(p.relative_to(ROOT).parts)]


_TAG = re.compile(r"<[^>]*>")


def _prose_of(text):
    """Sentences, not structure. Every conforming metadata file repeats the same
    element and attribute names, so a line-for-line comparison against the corpus
    flags `<DigitalFile FileFormat="application/pdf">` — which is the format, not
    anybody's writing. Stripping the tags leaves what a person composed."""
    out = []
    for chunk in _TAG.sub("\n", text).split("\n"):
        collapsed = " ".join(chunk.split())
        if len(collapsed) >= 40 and len(collapsed.split()) >= 6:
            out.append(collapsed)
    return out


def test_no_source_of_ours_carries_prose_from_the_vendored_corpus():
    """`corpus/examples/` is MIT and accounted for as MIT. Everything outside it
    is listed in THIRD_PARTY.md as this project's own, under Apache-2.0.

    A test fixture here was built by copying a `DocumentVersion` out of the
    corpus — German prose and all, down to the upstream typo — because the test
    needed a long block and that was the shortest way to get one. No assertion
    read a word of it, and `MANIFEST.in` puts `tests/*.py` in the sdist, so it
    would have shipped under the wrong notice for the sake of filler.

    Attribution is the fix for material we need. This is the other case: we did
    not need it.
    """
    corpus = [n for n in _tracked_names() if n.startswith("corpus/examples/")]
    phrases = {}
    for name in corpus:
        try:
            text = (ROOT / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue                      # binary fixtures carry no prose to lift
        for phrase in _prose_of(text):
            phrases.setdefault(phrase, name)
    assert phrases, "no prose was extracted from the corpus, so this proves nothing"

    ours = [n for n in _tracked_names()
            if not n.startswith("corpus/")
            and n.rsplit(".", 1)[-1] in ("py", "md", "json", "xml", "toml", "yml", "txt")]
    copied = []
    for name in ours:
        try:
            body = " ".join((ROOT / name).read_text(encoding="utf-8").split())
        except (UnicodeDecodeError, OSError):
            continue
        for phrase, source in phrases.items():
            if phrase in body:
                copied.append(f"{name} carries {source}: {phrase[:60]}…")
    assert not copied, (
        "a file this project calls its own repeats prose from the vendored "
        "corpus:\n  " + "\n  ".join(copied))
