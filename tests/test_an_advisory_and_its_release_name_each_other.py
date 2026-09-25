"""An advisory and the release that fixes it name each other, on both pages.

SECURITY.md promised more than it could keep: *"A security fix that shipped in a
release has a GitHub security advisory on this repository."* Measured against
this repository that was false by a wide margin -- 0.5.0, 0.6.0 and 0.7.0 carry
a great deal of hardening against hostile input, and there is one advisory. The
promise is dated now, from 0.8.0 on, and what is below the date is named rather
than implied away.

A dated promise is worth whatever keeps it, and what keeps it is the CHANGELOG:
an advisory's id is cited in the section of the release that fixes it, and the
ids on the two pages are the same set. So an advisory listed for a release whose
section never mentions it, an id cited in a section that the page does not list,
and an id that drifts on one page alone are each red. A release with no security
fix writes nothing and is not asked to: absence is the ordinary case, and a gate
that wanted a line per release would be a gate somebody silences.

What this cannot do is ask GitHub whether the advisory exists. Nothing in this
suite opens a socket -- a promise made on the same page it is checking -- so the
live check belongs to whoever publishes, against the API, at the moment of
publishing.
"""
import importlib.util
import re
from pathlib import Path

from vdi2770_validate import __version__

ROOT = Path(__file__).resolve().parent.parent

#: GitHub's identifier shape: three four-character groups. The bounds matter
#: more than the alphabet. Unanchored, this matched the correct id *inside* a
#: wrong one -- `GHSA-xp97-jcmj-h45f9` and `XGHSA-xp97-jcmj-h45f` both came back
#: as the right identifier, so a page could carry a link that 404s and every
#: test here would stay green. The alphabet is the one GitHub actually emits.
GHSA = re.compile(r"(?<![\w-])GHSA-(?:[23456789cfghjmpqrvwx]{4}-){2}"
                  r"[23456789cfghjmpqrvwx]{4}(?![\w-])")

#: Where the promise starts. Below this the CHANGELOG is the record, and the
#: Advisories section says so in prose rather than leaving a reader to infer
#: that nothing happened down there.
PROMISED_FROM = (0, 8, 0)

#: Which repository an advisory of ours lives on, read from the project's own
#: metadata rather than written here -- a constant typed into a test is a
#: second place to change, which is the thing this file keeps finding.
REPO = re.search(
    r"Homepage = \"https://github\.com/([^/\"]+/[^/\"]+)\"",
    (ROOT / "pyproject.toml").read_text(encoding="utf-8")).group(1)


def as_number(version):
    return tuple(int(p) for p in version.split("."))


def changelog_sections():
    """Version -> that section's text, newest first in the file."""
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    heads = list(re.finditer(r"^## +(\S+).*$", text, re.M))
    out = {}
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        out[h.group(1).lstrip("v")] = text[h.end():end]
    return out


def advisories_section():
    """The `## Advisories` section of SECURITY.md."""
    text = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    m = re.search(r"(?ms)^## Advisories\s*$(.*?)(?=^## |\Z)", text)
    assert m, "SECURITY.md has no `## Advisories` section"
    return m.group(1)


def _generator():
    spec = importlib.util.spec_from_file_location(
        "advisories", ROOT / "tools" / "advisories.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: The generator that writes the security page's list from the record. Its
#: `load` refuses a record that cannot be true -- a fix inside the range it
#: closes, an entry that names a fix and says nothing closes it -- so the tests
#: below start from one that can.
ADVISORIES = _generator()


def records():
    """The advisories as `docs/advisories.json` records them, in page order."""
    return ADVISORIES.load()


def listed_advisories():
    """Advisory id -> the release that fixes it (None while no release closes
    it), and the last release it reaches.

    Read from the record, not from the page. This used to parse the page's
    sentences, and each round of hardening found another sentence it read in the
    page's favour: a fix taken from a paragraph fifteen lines below the entry, an
    entry calling a fixed advisory open, another advisory's release read as this
    one's. The page is written from the record now, and a test holds it there.
    """
    return {a["id"]: (a["fixed_in"], a["through"]) for a in records()}


def cited_advisories():
    """Advisory id -> the CHANGELOG sections that cite it."""
    out = {}
    for version, body in changelog_sections().items():
        for found in set(GHSA.findall(body)):
            out.setdefault(found, set()).add(version)
    return out


def correction_lines(section):
    """The corrections appended to a section, one per line."""
    return re.findall(r"^\*\(Correct.*\)\*$", section, re.M)


def sentences_naming(advisory, text):
    """The sentences of `text` that name `advisory`, each on one line.

    A sentence and not a paragraph: 0.10.0 says in one paragraph that
    GHSA-62p8-4642-mwfp is not yet closed and, one sentence later, that
    GHSA-3pfq-57fx-w4q5 now reaches 0.9.5 -- read by the paragraph, what is said
    of one was taken as said of the other, and a true page went red.
    """
    named = re.compile(rf"(?<![\w-]){re.escape(advisory)}(?![\w-])")
    return [sentence
            for para in re.split(r"\n\s*\n", text)
            for sentence in re.split(r"(?<=[.!?])\s+", " ".join(para.split()))
            if named.search(sentence)]


def reaches(text):
    """Every release `text` says a range reaches, however it says so."""
    return re.findall(r"(?:up to(?: and including)?|through|reach(?:es|ing)?)\s+"
                      r"(\d+\.\d+\.\d+)(?![\d.]*\d)", text)


def dated_corrections(section, advisory):
    """(date, line) for each correction appended to `section` that names
    `advisory`; the date is None where the correction carries none."""
    named = re.compile(rf"(?<![\w-]){re.escape(advisory)}(?![\w-])")
    out = []
    for line in correction_lines(section):
        if named.search(line):
            dated = re.match(r"\*\(Correct(?:ion|ed)\s+(\d{4}-\d{2}-\d{2})\b", line)
            out.append((dated.group(1) if dated else None, line))
    return out


def stated_ranges(text):
    """Every release `text` says a range runs up to or through. Not "reaches":
    "does not reach 0.10.2" says the opposite, and a range stated outright is
    what a reader on that release acts on."""
    return re.findall(r"(?:up to(?: and including)?|through)\s+(\d+\.\d+\.\d+)(?![\d.]*\d)", text)


def takes_back(line, release):
    """Whether a correction says a claim that `release` fixed the advisory was
    wrong: that the range reaches `release` or later, or that no release closes
    it yet. Read whole, as the one line and one correction it is."""
    return (ADVISORIES.OPEN in " ".join(line.split())
            or any(as_number(r) >= as_number(release) for r in reaches(line)))


def takes_nothing_back(advisory, line, release):
    """Whether a correction naming `advisory` leaves `release`'s claim standing:
    no sentence naming the advisory says its range reaches `release` or later,
    says nothing closes it, or names a later release -- the one that fixed it."""
    later = re.compile(r"(?<![\d.])(\d+\.\d+\.\d+)(?![\d.]*\d)")
    return not any(
        ADVISORIES.OPEN in s
        or any(as_number(r) >= as_number(release) for r in reaches(s))
        or any(as_number(r) > as_number(release) for r in later.findall(s))
        for s in sentences_naming(advisory, line))


def test_an_advisory_is_cited_somewhere_at_all():
    """The guard that keeps the three below from passing on empty sets.

    They are set comparisons, and two empty sets are equal. This one fails the
    day the last citation is deleted from the CHANGELOG, rather than turning
    the rest of the file green.
    """
    assert cited_advisories(), (
        "no advisory id appears anywhere in CHANGELOG.md; SECURITY.md promises "
        "one for every security fix from 0.8.0 on and nothing holds that promise")


def test_the_two_pages_name_the_same_advisories():
    listed, cited = set(listed_advisories()), set(cited_advisories())
    assert listed == cited, (
        f"only on the security page: {sorted(listed - cited)}; "
        f"only in the changelog: {sorted(cited - listed)}")


def test_the_security_page_lists_what_the_record_says():
    """The list on the security page is the record, written out; a hand edit to
    it, or a record edited without writing the page again, is red."""
    page = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    written = ADVISORIES.page_with(page, ADVISORIES.listing(records(), ADVISORIES.repo()))
    assert written == page, (
        "SECURITY.md's list of advisories is not what docs/advisories.json says; "
        "run python tools/advisories.py --write")


def test_every_advisory_the_page_names_is_recorded():
    """The prose around the list names advisories too, and an id there that the
    record does not have is a link a reader can follow to nothing of ours."""
    page = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    stray = sorted(set(GHSA.findall(page)) - set(listed_advisories()))
    assert not stray, f"SECURITY.md names advisories the record does not: {stray}"


def test_each_advisory_is_cited_where_the_record_puts_it():
    """The record says which release fixes an advisory, which releases claimed
    to and took the claim back, which corrections name it, and how far it
    reaches; the changelog has to say the same, section by section.

    What is read from the changelog is kept to what cannot be read two ways:
    which sections name the advisory, each correction that names it and its
    date, a range's last release, and the words the record uses for an
    advisory no release closes. Which correction took a claim back is written
    in the record rather than read out of its words -- every reading of those
    words found another sentence it read the wrong way. What the words are
    still held to is that a correction recorded as taking a claim back says the
    range reaches that release, and one recorded as taking nothing back does
    not say so.
    """
    cited = cited_advisories()
    changelog = changelog_sections()
    OPEN = ADVISORIES.OPEN
    for a in records():
        advisory, fixed_in, through = a["id"], a["fixed_in"], a["through"]
        where = cited.get(advisory, set())
        said = {v: sentences_naming(advisory, changelog[v]) for v in where}
        # Every correction that names the advisory is in the record, by the
        # section it is appended to and its date, and everything the record
        # names is there. A record left as it was when a correction was
        # appended is red here, whatever the correction says.
        found = {}
        for v in sorted(where, key=as_number):
            for date, line in dated_corrections(changelog[v], advisory):
                assert date, (
                    f"a correction appended to {v} names {advisory} and carries no "
                    f"date; the record names a correction by its date")
                found.setdefault((v, date), []).append(line)
        recorded = {(c["in"], c["on"]) for c in a["corrections"]}
        claimed = {c["in"] for c in a["corrections"] if c["took_back"]}
        assert set(found) == recorded, (
            f"{advisory}: corrections that name it {sorted(found)}; the record "
            f"names {sorted(recorded)}")
        # A release that claimed the fix and was wrong keeps its claim -- the
        # section is the record of its tag -- and the correction that takes it
        # back says how far the advisory now reaches, or that nothing closes it.
        for c in (c for c in a["corrections"] if c["took_back"]):
            v, date = c["in"], c["on"]
            assert any(takes_back(line, v) for line in found[(v, date)]), (
                f"the record says the correction of {date} appended to {v} took "
                f"back its claim to fix {advisory}, and it does not say the range "
                f"reaches {v} or that no release closes it yet; say how far it "
                f"now reaches")
        # One that took nothing back does not say it did.
        for c in (c for c in a["corrections"] if not c["took_back"]):
            v, date = c["in"], c["on"]
            after_the_fix = fixed_in is not None and as_number(v) >= as_number(fixed_in)
            assert all(takes_nothing_back(advisory, line, v) for line in found[(v, date)]), (
                f"the record says the correction of {date} appended to {v} took "
                f"nothing back, and a sentence in it naming {advisory} says the "
                f"range reaches {v} or later, that nothing closes it yet, or names "
                f"a later release. A sentence is read as said of every advisory it "
                f"names, so if it speaks of another advisory too, give each its own"
                + ("" if after_the_fix else
                   f"; if it does take {v}'s claim back, record it as one that did"))
        if fixed_in is None:
            # Every release so far is inside it, up to the one being written.
            assert through == __version__, (
                f"{advisory} is not yet closed by any release, and the record says "
                f"it reaches up to {through}; the release being written is "
                f"{__version__}")
            # And the last word on it says so: the newest section that names
            # it. A fixed advisory recorded as open would otherwise pass here --
            # its sections name it, and none of them says the words.
            assert where, f"{advisory} is not cited anywhere in the changelog"
            latest = max(where, key=as_number)
            assert any(OPEN in s for s in said[latest]), (
                f"{advisory} is recorded as not yet closed by any release, and "
                f"the newest section naming it, {latest}, does not say so in a "
                f"sentence that names it")
            # And no section naming it still stands as a fix: each one said it
            # was open, or claimed a fix that a correction took back. An
            # advisory reopened with the sections that called it fixed left
            # uncorrected is otherwise green.
            standing = sorted((v for v in where if v not in claimed
                               and not any(OPEN in s for s in said[v])), key=as_number)
            assert not standing, (
                f"{advisory} is recorded as not yet closed by any release, and "
                f"{standing} name it without saying so or being recorded as a "
                f"claim a correction took back")
            continue
        assert fixed_in in where, (
            f"{advisory} is recorded as fixed in {fixed_in}, and that section does "
            f"not cite it (cited under: {sorted(where) or 'nothing'})")
        # Before the fix, a section naming it either claimed the fix and was
        # corrected, or said the advisory was open. Anything else is a release
        # before the one recorded as the fix that talks about it as fixed.
        early = sorted((v for v in where if as_number(v) < as_number(fixed_in)),
                       key=as_number)
        unexplained = [v for v in early
                       if v not in claimed and not any(OPEN in s for s in said[v])]
        assert not unexplained, (
            f"{advisory} is recorded as fixed in {fixed_in}, and {unexplained} "
            f"name it earlier without being recorded as a claim taken back")
        # From the fix on, nothing calls it open.
        still = sorted((v for v in where if as_number(v) >= as_number(fixed_in)
                        and any(OPEN in s for s in said[v])), key=as_number)
        assert not still, (
            f"{advisory} is recorded as fixed in {fixed_in}, and {still} say no "
            f"release closes it yet. A sentence is read as said of every advisory "
            f"it names: if one sentence speaks of two, give each its own")
        # And nowhere does a range stated for it run up to the fix: "now reaches
        # up to 0.9.4" in any section says 0.9.4 did not fix it, whatever the
        # record names.
        overrun = sorted((v for v in where if any(
            as_number(r) >= as_number(fixed_in) for s in said[v] for r in stated_ranges(s))),
            key=as_number)
        assert not overrun, (
            f"{advisory} is recorded as fixed in {fixed_in}, and {overrun} state "
            f"a range for it up to {fixed_in} or later. A sentence is read as said "
            f"of every advisory it names: if one sentence speaks of two, give each "
            f"its own")
        # And the release that fixed it says how far it reached: the range a
        # reader on an older release reads is the one the record gives.
        assert any(through in reaches(s) for s in said[fixed_in]), (
            f"the record says {advisory} reaches up to {through}, and no sentence "
            f"naming it in the {fixed_in} section says so")


def test_what_a_correction_says_is_held_to_what_it_is_recorded_as():
    """The record says which corrections took a claim back; the words are held
    to that from both sides. One recorded as taking 0.9.5's claim back says how
    far the advisory reaches -- across two sentences, or in other words than
    "up to" -- and one that says only which later release fixed it does not
    count as either, so it is red until it says the range. One recorded as
    taking nothing back -- 0.8.1's, which gave the fix its advisory -- names no
    range reaching its release and no later fix."""
    advisory = "GHSA-3pfq-57fx-w4q5"
    for line in (
            f"so 0.9.5 did not complete the fix for {advisory}. It now reaches up to 0.9.5.",
            f"{advisory} reaches 0.9.5 as well.",
            f"{advisory} reaches up to and including 0.9.5.",
            f"{advisory} now reaches up to 0.9.5 and is fixed in 0.9.6."):
        assert takes_back(f"*(Correction 2026-09-24: {line})*", "0.9.5"), line
    only_the_fix = f"*(Correction 2026-09-24: {advisory} is fixed in 0.9.6.)*"
    assert not takes_back(only_the_fix, "0.9.5")
    assert not takes_nothing_back(advisory, only_the_fix, "0.9.5")
    copied = (f"*(Correction 2026-09-24: {advisory} now reaches up to 0.9.3 and is "
              f"fixed in 0.9.5.)*")
    assert not takes_back(copied, "0.9.4"), "a range short of the release takes nothing back"
    xp97 = ("*(Correction 2026-09-23: the fix described above has advisory "
            "GHSA-xp97-jcmj-h45f, published after this section was written and "
            "reaching every release of both distributions up to 0.8.0.)*")
    assert takes_nothing_back("GHSA-xp97-jcmj-h45f", xp97, "0.8.1")
    assert not takes_back(xp97, "0.8.1")


def test_no_advisory_is_claimed_for_a_release_below_the_promise():
    """The promise starts at 0.8.0 because the practice does. An entry for an
    older release would mean the date is wrong rather than that the entry is."""
    for advisory, (fixed_in, _reaches) in listed_advisories().items():
        if fixed_in is None:
            continue
        assert as_number(fixed_in) >= PROMISED_FROM, (
            f"{advisory} is listed as fixed in {fixed_in}, below the release the "
            f"page says the practice starts at")


def test_the_promise_carries_the_date_it_was_narrowed_to():
    """The sentence this file exists because of, kept from coming back.

    It read "A security fix that shipped in a release has a GitHub security
    advisory on this repository" -- true of 0.8.1 and of nothing before it.
    """
    section = advisories_section()
    promise = re.search(r"(?s)\*\*(.*?a security fix that ships in a release.*?)\*\*",
                        section, re.I)
    assert promise, (
        "the Advisories section no longer opens with the bolded promise this "
        "file is here to keep; reword it and this gate stops reading anything")
    # Not `in section`. The first version of this searched the whole section,
    # so undating the promise and putting the phrase in any other sentence --
    # a sentence about the CHANGELOG, say -- left it green. The date has to be
    # inside the promise it dates.
    assert "From 0.8.0 on" in " ".join(promise.group(1).split()), (
        "the advisory promise no longer says where it starts; undated, it claims "
        "0.5.0, 0.6.0 and 0.7.0 too, and those have no advisories")


def test_the_page_says_what_is_below_the_date():
    """A date on the promise is only honest if the reader is told what the date
    excludes; otherwise the narrowing reads as there having been nothing."""
    section = advisories_section()
    for release in ("0.5.0", "0.5.1", "0.6.0", "0.7.0"):
        assert release in section, (
            f"the section does not name {release}, so a reader pinning below "
            f"0.8.0 is told only that there are no advisories")
    # 0.5.1 is on that list for a reason that is easy to lose: 0.5.0 *describes*
    # the scan fix and did not deliver it -- it asked for the fixed reader with
    # a range that permitted the unfixed one -- so a reader who pins 0.5.0 and
    # does what this page says (read that section) concludes they are safe and
    # is not. The page has to say which release delivers, not only which
    # describes.
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "0.5.0 did not deliver its own fix" in changelog, (
        "the 0.5.1 section no longer says that 0.5.0 did not deliver its fix, "
        "and the Advisories section sends readers there for exactly that")
    # And the page has to send them somewhere. Replacing this whole paragraph
    # with "there are no advisories for 0.5.0, 0.5.1, 0.6.0 or 0.7.0" satisfies
    # every assertion above -- it names all four -- and is the narrowing read
    # as though nothing happened, which is what this test is against.
    #
    # Saying candidly what is below the date is not something a gate can check.
    # Pointing a reader at the record is, and a denial that also points at the
    # record has stopped being a bare denial.
    listed = section.rfind("- [")
    assert listed != -1, "the Advisories section lists no advisory at all"
    below = section[listed:]
    assert "CHANGELOG" in below, (
        "the section says there are no advisories below 0.8.0 and does not say "
        "where the record of those fixes is; a reader is left with a denial")


def floor_pinned_releases():
    """Releases whose engine is named with a floor, read from the tags.

    A tuple typed here would be the thing this file exists to catch, one file
    over: the page would be held to a list somebody wrote rather than to what
    the releases declare. `git show <tag>:pyproject.toml` is the declaration.
    Returns None where the tags are not available, which is an sdist.
    """
    import subprocess

    tags = subprocess.run(["git", "tag", "-l", "v*"], cwd=ROOT,
                          capture_output=True, text=True)
    if tags.returncode != 0 or not tags.stdout.strip():
        return None
    out = []
    for tag in sorted(tags.stdout.split(), key=lambda t: as_number(t[1:])):
        got = subprocess.run(["git", "show", f"{tag}:pyproject.toml"], cwd=ROOT,
                             capture_output=True, text=True)
        if got.returncode != 0:
            continue
        m = re.search(r'"vdi2770(?:\[[^\]]*\])?\s*(==|~=|>=|>)\s*([\d.]+)"',
                      got.stdout)
        if m and m.group(1) in (">=", ">"):
            out.append(tag[1:])
    return out


def test_the_page_names_every_release_pinned_with_a_floor():
    """The paragraph that tells a reader where to move names every release that
    asked for its engine with a floor.

    Each of them is inside the range of an advisory, and that paragraph is where
    a reader on one is told to move -- so it is where their release has to be
    named, not anywhere on the page: 0.8.0 appears there eight times for other
    reasons, and a search of the whole page passed with it gone from the one
    sentence that mattered. The set is derived from the tags rather than typed
    here.

    This test once said the opposite of why. It held that these were the
    releases where `pip show vdi2770` mattered most, because a floor leaves the
    installed reader open. From 0.8.0 on, a reader and command that disagree are
    refused rather than judged, so a floor does not leave a verdict open; the
    releases where a silently older reader matters are 0.2.0 to 0.6.x, which
    asked for it with a range. The assertion that enforced the old reason is
    gone. This one is kept for the reason above.
    """
    import pytest

    page = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    flat = " ".join(page.split())
    assert "pip show vdi2770" in flat, (
        "the page no longer tells a reader how to see which reader they have")

    floors = floor_pinned_releases()
    if floors is None:
        pytest.skip("not a git checkout; the tags are not available here")
    assert floors, "no release names its engine with a floor; this test is stale"

    # There used to be an assertion here refusing any wording that scoped this
    # advice below the floor-pinned releases. Its premise was backwards. From
    # 0.8.0 on, a reader and command that disagree are refused rather than
    # judged, so the releases where `pip show` matters most are 0.2.0 to 0.6.x,
    # which asked for the reader with a range. An assertion enforcing the
    # opposite is worse than none.
    move = [" ".join(p.split()) for p in re.split(r"\n\s*\n", page)
            if re.search(r"Move to \*\*\d+\.\d+\.\d+\*\*", p)]
    assert len(move) == 1, (
        f"expected one paragraph telling a reader where to move, found {len(move)}")
    missing = [v for v in floors
               if not re.search(rf"(?<![\d.]){re.escape(v)}(?!\.?\d)", move[0])]
    assert not missing, (
        f"these releases name their engine with a floor and the paragraph that "
        f"says where to move does not name them: {missing}")


def what_a_reader_is_told():
    """The pages a reader is told things by now: the front pages, the page PyPI
    shows for each distribution, the security page, and the corrections appended
    to the changelog. A released section is the record of its tag and is not
    asked to know what came after it."""
    pages = {"README.md", "SECURITY.md"}
    for home in ("", "packages/vdi2770/"):
        meta = (ROOT / home / "pyproject.toml").read_text(encoding="utf-8")
        shown = re.search(r'^readme = "([^"]+)"', meta, re.M)
        assert shown, f"{home}pyproject.toml no longer names the page PyPI shows"
        pages.add(home + shown.group(1))
    told = {page: (ROOT / page).read_text(encoding="utf-8") for page in sorted(pages)}
    told["a correction in CHANGELOG.md"] = "\n".join(re.findall(
        r"^\*\(Correct.*\)\*$", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"),
        re.M))
    return told


def test_every_release_a_page_sends_a_reader_to_is_past_every_advisory():
    """Wherever a page tells a reader which release to move to, no advisory the
    security page lists reaches that release.

    The advice is written once and the advisories keep arriving. The correction
    appended to 0.9.1 told a reader to move to 0.9.4 or later, and three
    advisories now reach 0.9.4 -- the sentence written to move a reader off an
    affected release moved them onto one.
    """
    told = what_a_reader_is_told()
    sent = [(page, v) for page, text in told.items()
            for v in re.findall(r"(\d+\.\d+\.\d+)\**\s+or later", text)]
    assert sent, "no page says which release to move to; this test reads nothing"
    # An advisory no release closes yet is past no release; the pages name it
    # as the exception wherever they speak of every repair.
    reach = {a: r for a, (fixed, r) in listed_advisories().items() if fixed}
    inside = [f"{page} sends a reader to {v}, and {a} reaches up to {r}"
              for page, v in sent for a, r in sorted(reach.items())
              if as_number(v) <= as_number(r)]
    assert not inside, inside


#: An exact pin a page can hand a reader: either distribution by name, extras
#: and all (`vdi2770[validate]==0.10.0`), or this repository's action by its
#: ref, written out in full or as the ref alone in a code span (`@v0.9.7`).
#: The trailing guard keeps `0.9.7` from being read out of `0.9.71` or
#: `0.9.7.1`, which name some other release or none.
PIN = re.compile(
    r"(?:(?<![\w-])vdi2770(?:-validate)?(?:\[[^\]\s]*\])?==(?P<dist>\d+\.\d+\.\d+)"
    r"|" + re.escape(REPO) + r"@v(?P<ref>\d+\.\d+\.\d+)"
    r"|`@v(?P<bare>\d+\.\d+\.\d+))(?![\d.]*\d)")


def test_every_pin_a_page_hands_a_reader_is_past_every_advisory():
    """A pin is advice with the words taken out, and it gets copied rather than
    read. The test above reads "x.y.z or later" and nothing else, so every
    `pip install "vdi2770-validate==..."`, every `uses: ...@v...` and every
    "`==...` installs one matching pair" on the front page could be moved into
    an advisory's range with this whole file green.

    Two kinds of pin are held here. One a reader copies whole -- the action's
    ref, and a pin on a line that runs `pip install` -- whatever release it
    names. And any exact pin from the release the advisory promise starts at
    on, however it is phrased. A pin below that release is left to the page:
    the ones there are the record of what an early release did (0.5.0 installed
    beside the reader it had not fixed), and the promise the advisories keep
    does not reach down there -- the page sends a reader past it in words,
    which the test above holds.
    """
    handed = []
    for page, text in what_a_reader_is_told().items():
        for line in text.splitlines():
            for m in PIN.finditer(line):
                release = m.group("dist") or m.group("ref") or m.group("bare")
                copied = m.group("dist") is None or "pip install" in line
                handed.append((page, release, copied))
    assert any(copied for _, _, copied in handed), (
        "no page hands a reader a pin to copy; this test reads nothing")
    reach = {a: r for a, (fixed, r) in listed_advisories().items() if fixed}
    inside = [f"{page} hands a reader {v}, and {a} reaches up to {r}"
              for page, v, copied in handed
              if copied or as_number(v) >= PROMISED_FROM
              for a, r in sorted(reach.items())
              if as_number(v) <= as_number(r)]
    assert not inside, inside
