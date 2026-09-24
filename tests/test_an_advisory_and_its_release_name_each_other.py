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
import re
from pathlib import Path

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


def listed_advisories():
    """Advisory id -> the release the page says fixes it, and the range it reaches.

    An entry ends where the next one begins *or* where the list does. Splitting
    only on the next bullet let the last entry's text run to the end of the
    section, so `fixed in 0.8.1` in a paragraph fifteen lines below was read as
    that entry naming its release -- the entry could stop naming one and the
    parser would go on reporting that it did.
    """
    out = {}
    section = advisories_section()
    # Every entry in the section, wherever it sits. Two earlier spellings each
    # bounded "the listing" as one run of bullets: the first stopped at any
    # blank line, which dropped the older advisory the moment a second was
    # added; the second stopped at the first blank line not followed by a
    # bullet, which let an entry written *below* the closing prose escape every
    # check in this function and the set comparison as well. An entry is a
    # bullet that names an advisory, and each one is cut at the end of its own
    # bullet so that prose below it is never read as part of it.
    entries = []
    for chunk in re.split(r"\n(?=- )", section):
        if not chunk.startswith("- ") or not GHSA.search(chunk):
            continue
        entries.append(re.split(r"\n\n(?!\s)", chunk)[0])
    for para in entries:
        ids = set(GHSA.findall(para))
        if not ids:
            continue
        assert len(ids) == 1, f"one entry names more than one advisory: {sorted(ids)}"
        advisory = ids.pop()
        # The entry is a link, and a link has the identifier twice: once as the
        # text a reader sees and once in the address they land on. Collecting
        # ids as a *set* cannot see a typo in one of the two -- the other copy
        # still matches, the set is still right, and the link still 404s. So
        # the two copies are compared to each other, not only to the changelog.
        link = re.search(r"\[([^\]]+)\]\((https?://[^)]+)\)", " ".join(para.split()))
        if link:
            shown, address = link.group(1), link.group(2)
            assert shown.strip() == advisory, (
                f"the entry's link reads {shown.strip()!r} and the identifier in "
                f"it is {advisory}")
            assert address.rstrip("/").endswith(advisory), (
                f"the entry for {advisory} links to {address}, which does not "
                f"end at that advisory")
            # And on *this* repository, which is what the promise above says.
            # Ending at the right identifier says nothing about whose advisory
            # it is: the same id under another owner passed every check here.
            assert address.startswith(f"https://github.com/{REPO}/security/advisories/"), (
                f"the entry for {advisory} links to {address}, which is not an "
                f"advisory on {REPO}; the promise above it says this repository")
        fixed = re.search(r"fixed in (\d+\.\d+\.\d+)", para)
        assert fixed, (
            f"the entry for {advisory} does not say which release fixes it; the "
            f"promise above it undertakes to name that release")
        # The promise has two halves -- "naming the versions it reaches **and**
        # the release that fixes it" -- and only the second was checked, so an
        # entry could drop the range it reaches and stay green.
        reaches = re.search(r"(?:up to|through|before) (\d+\.\d+\.\d+)", para)
        assert reaches, (
            f"the entry for {advisory} does not say which versions it reaches; "
            f"the promise above it undertakes to name those too")
        out[advisory] = (fixed.group(1), reaches.group(1))
    return out


def cited_advisories():
    """Advisory id -> the CHANGELOG sections that cite it."""
    out = {}
    for version, body in changelog_sections().items():
        for found in set(GHSA.findall(body)):
            out.setdefault(found, set()).add(version)
    return out


def corrections(advisory, where, changelog):
    """Section -> the latest release that section's own appended corrections say
    fixed `advisory`, for each section in `where` that has one after itself.

    Every `fixed in` on a line is read, not the first: a correction may name
    what the section claimed before what is true, and then the first is the
    section's own release.
    """
    corrected = {}
    for v in where:
        for line in re.findall(r"^\*\(Correct.*\)\*$", changelog.get(v, ""), re.M):
            if advisory not in line:
                continue
            for x in re.findall(r"(?<!not )\bfixed in (\d+\.\d+\.\d+)", line):
                if as_number(x) > as_number(corrected.get(v, v)):
                    corrected[v] = x
    return corrected


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


def test_each_advisory_is_cited_by_the_release_that_fixes_it():
    """`fixed in 0.8.1` and a citation under `## 0.8.1` are one claim, and a
    reader who follows either should land on the other."""
    cited = cited_advisories()
    changelog = changelog_sections()
    for advisory, (fixed_in, reaches) in listed_advisories().items():
        where = cited.get(advisory, set())
        assert fixed_in in where, (
            f"{advisory} says it is fixed in {fixed_in}, but that section does "
            f"not cite it (cited under: {sorted(where) or 'nothing'})")
        # The *earliest* section citing it, not merely one of them. A later
        # release that carries the same repair cites the same advisory -- so
        # once two sections named it, asking only "is `fixed in` among them"
        # stopped being able to fail, and the page could name a release after
        # the one that shipped the fix. A reader on the patch release then
        # reads that they are still exposed.
        # Except a section whose own claim was corrected: an appended line in it
        # that names this advisory and a later release it was fixed in. 0.9.3
        # cited GHSA-6hqr-phm3-chpf as fixed there, bounding by the wrong
        # measure, and 0.9.5 completed it. The page has to follow the
        # correction: naming the corrected section as the fix is refused, where
        # before it passed as long as the page and that section agreed.
        corrected = corrections(advisory, where, changelog)
        assert fixed_in not in corrected, (
            f"{advisory} says it is fixed in {fixed_in}, and that section's own "
            f"correction says the fix was completed in {corrected.get(fixed_in)}")
        earliest = min((where - set(corrected)) or where, key=as_number)
        assert fixed_in == earliest, (
            f"{advisory} says it is fixed in {fixed_in}, and the earliest "
            f"release whose section cites it is {earliest}; the page names a "
            f"release later than the one that shipped the repair")
        # And the range has to be the range that release describes. Until now
        # it was only required to *exist*: the entry could say it reaches any
        # version at all and stay green, which is the reading that leaves
        # somebody on an affected version believing they are not.
        section = changelog.get(fixed_in, "")
        said = re.search(r"(?:up to|through|before) (\d+\.\d+\.\d+)", section)
        assert said, (
            f"the {fixed_in} section does not say which versions {advisory} "
            f"reaches, so the entry's range is checked against nothing")
        assert reaches == said.group(1), (
            f"the advisory page says {advisory} reaches up to {reaches} and the "
            f"{fixed_in} section says {said.group(1)}")


def test_a_correction_that_names_the_old_release_first_still_counts():
    """A correction says most naturally what the section claimed and then what
    is true: "this section said it was fixed in 0.9.4; it is fixed in 0.9.5".
    Reading only the first `fixed in` took that line for no correction at all,
    and then a page naming 0.9.5, which is true, went red, and a page naming
    0.9.4, which is not, went green."""
    line = ("*(Correction 2026-09-24: this section said GHSA-6hqr-phm3-chpf was "
            "fixed in 0.9.4; it is fixed in 0.9.5.)*")
    section = f"\nWhat went out.\n\n{line}\n"
    assert corrections("GHSA-6hqr-phm3-chpf", {"0.9.4"}, {"0.9.4": section}) == {
        "0.9.4": "0.9.5"}


def test_no_advisory_is_claimed_for_a_release_below_the_promise():
    """The promise starts at 0.8.0 because the practice does. An entry for an
    older release would mean the date is wrong rather than that the entry is."""
    for advisory, (fixed_in, _reaches) in listed_advisories().items():
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


def test_every_release_a_page_sends_a_reader_to_is_past_every_advisory():
    """Wherever a page tells a reader which release to move to, no advisory the
    security page lists reaches that release.

    The advice is written once and the advisories keep arriving. The correction
    appended to 0.9.1 told a reader to move to 0.9.4 or later, and three
    advisories now reach 0.9.4 -- the sentence written to move a reader off an
    affected release moved them onto one. What this reads is what
    a reader is told now: the front pages, the page PyPI shows for each
    distribution, the security page, and the corrections appended to the
    changelog. A released section is the record of its tag and is not asked to
    know what came after it.
    """
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
    sent = [(page, v) for page, text in told.items()
            for v in re.findall(r"(\d+\.\d+\.\d+)\**\s+or later", text)]
    assert sent, "no page says which release to move to; this test reads nothing"
    reach = {a: r for a, (_fixed, r) in listed_advisories().items()}
    inside = [f"{page} sends a reader to {v}, and {a} reaches up to {r}"
              for page, v in sent for a, r in sorted(reach.items())
              if as_number(v) <= as_number(r)]
    assert not inside, inside
