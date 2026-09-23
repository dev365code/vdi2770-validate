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

#: GitHub's identifier shape. Four-character groups, lowercase base32 without
#: the ambiguous letters -- pinned here so a typo is a mismatch rather than a
#: second "id" that happens to be cited nowhere.
GHSA = re.compile(r"GHSA-[0-9a-hj-km-np-z]{4}-[0-9a-hj-km-np-z]{4}-[0-9a-hj-km-np-z]{4}")

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
    """Advisory id -> the release the page says fixes it."""
    out = {}
    for para in re.split(r"\n(?=- )", advisories_section()):
        ids = set(GHSA.findall(para))
        if not ids:
            continue
        assert len(ids) == 1, f"one entry names more than one advisory: {sorted(ids)}"
        fixed = re.search(r"fixed in (\d+\.\d+\.\d+)", para)
        assert fixed, (
            f"the entry for {ids.pop()} does not say which release fixes it; the "
            f"promise above it undertakes to name that release")
        out[ids.pop()] = fixed.group(1)
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
    assert "From 0.8.0 on" in section, (
        "the advisory promise no longer says where it starts; undated, it claims "
        "0.5.0, 0.6.0 and 0.7.0 too, and those have no advisories")
    assert "A security fix that shipped in a release has" not in section, (
        "the undated promise is back on the page")


def test_the_page_says_what_is_below_the_date():
    """A date on the promise is only honest if the reader is told what the date
    excludes; otherwise the narrowing reads as there having been nothing."""
    section = advisories_section()
    for release in ("0.5.0", "0.6.0", "0.7.0"):
        assert release in section, (
            f"the section names no hardening in {release}, so a reader pinning "
            f"below 0.8.0 is told only that there are no advisories")
