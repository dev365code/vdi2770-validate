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
    # The listing runs to the first blank line followed by something that is
    # not another entry. Stopping at *any* blank line was right while there
    # was one advisory and wrong the moment there were two: entries are
    # separated by a blank line, so the bound cut the list after the first
    # one and the older advisory silently left the comparison.
    listing = re.match(r"(?s).*?(^- .*?)(?=\n\n(?!- )\S|\Z)", section, re.M)
    listing = listing.group(1) if listing else ""
    for para in re.split(r"\n(?=- )", listing):
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
        out[advisory] = fixed.group(1)
    return out


def cited_advisories():
    """Advisory id -> the CHANGELOG sections that cite it."""
    out = {}
    for version, body in changelog_sections().items():
        for found in set(GHSA.findall(body)):
            out.setdefault(found, set()).add(version)
    return out


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
    for advisory, fixed_in in listed_advisories().items():
        where = cited.get(advisory, set())
        assert fixed_in in where, (
            f"{advisory} says it is fixed in {fixed_in}, but that section does "
            f"not cite it (cited under: {sorted(where) or 'nothing'})")


def test_no_advisory_is_claimed_for_a_release_below_the_promise():
    """The promise starts at 0.8.0 because the practice does. An entry for an
    older release would mean the date is wrong rather than that the entry is."""
    for advisory, fixed_in in listed_advisories().items():
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


def test_the_page_points_the_check_command_at_the_releases_that_need_it():
    """`pip show vdi2770` is the check, and it was scoped to the wrong range.

    The page said *before 0.8.0*. That is wrong in both directions. It is not
    true at the bottom -- 0.1.0 has no `packages/` tree and names no reader, so
    there was nothing for the command to show -- and at the top it excludes the
    releases that need it most. A release that names its engine with a floor is
    one whose installed reader is *not* determined by the version of the command:
    a floor stops holding the moment a newer engine exists, which the README
    says in its own words. Those are precisely the releases where a reader
    asking "do I have the fix" cannot answer from the command's version alone.

    So the set is derived from the tags rather than typed here, and the page has
    to name every release in it.
    """
    import pytest

    page = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    flat = " ".join(page.split())
    assert "pip show vdi2770" in flat, (
        "the page no longer tells a reader how to see which reader they have")

    # A sentence ends at a full stop *followed by a space*, because a version
    # number is full of full stops: splitting on the bare character lands inside
    # "0.8.0" and hands back a fragment that no longer contains the scoping this
    # is here to refuse. The first spelling of this test passed for that reason.
    at = flat.find("pip show vdi2770")
    ends = [m.end() for m in re.finditer(r"\.(?:\s|$)", flat)]
    start = max([e for e in ends if e <= at], default=0)
    end = min([e for e in ends if e > at], default=len(flat))
    sentence = flat[start:end]
    assert "before 0.8.0" not in sentence, (
        "the sentence carrying `pip show vdi2770` scopes it to before 0.8.0, "
        "which excludes the floor-pinned releases where the installed reader "
        "can differ from the command -- the case the command exists for")

    floors = floor_pinned_releases()
    if floors is None:
        pytest.skip("not a git checkout; the tags are not available here")
    assert floors, "no release names its engine with a floor; this test is stale"
    missing = [v for v in floors if v not in flat]
    assert not missing, (
        f"these releases name their engine with a floor and the page does not "
        f"name them: {missing}. They are the ones where `pip show vdi2770` "
        f"answers a question the command's own version cannot")
