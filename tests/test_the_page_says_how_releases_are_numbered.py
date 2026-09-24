"""The page has to say what a version number means before somebody pins one.

Without this section a reader learns the rules of this project's numbering by
upgrading and finding out. The section is prose, so what is held here is the
part a reader would act on.

**The CHANGELOG is not the source of truth for what was released.** It carries
sections for the reader's releases as well as this package's -- `## 0.3.1` is
one, and there has never been a `vdi2770-validate` 0.3.1 on any index -- so a
version lifted from a heading may name a distribution nobody can pin. The tags
are the source: `v*` is this package, `sdk-v*` is the reader. A draft of this
file read the headings instead and blessed `0.3.1` as a patch release of this
package, in a section whose whole subject is pinning.
"""
import re
import subprocess

from conftest import ROOT
from vdi2770_validate import __version__

HEADING = "## Releases and version numbers"

#: Only as far as the paragraph counts. Written out because prose writes them
#: out, and a number spelled as a digit in this section would read as a version.
COUNT = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
         "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
         "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
         "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
         "nineteen": 19, "twenty": 20}


def section() -> str:
    page = (ROOT / "README.md").read_text(encoding="utf-8")
    assert HEADING in page, f"README.md has no {HEADING!r} section"
    body = page.split(HEADING, 1)[1]
    nxt = re.search(r"^## ", body, re.M)
    return body[: nxt.start()] if nxt else body


def published():
    """Every release of *this package*, from the tags rather than from prose --
    and the one being written.

    A patch cut from this branch is named in its own tree, the one its tag will
    point at, and until the tag exists the tags cannot say it. Read from the
    tags alone, the section could not name the release being written before
    its tag and had to name it the moment the tag existed, so no tree could be
    right on both sides of tagging. `__version__` is the one exception, and it
    is the release this tree is.
    """
    done = subprocess.run(["git", "tag", "--list", "v*"], cwd=ROOT,
                          capture_output=True, text=True)
    if done.returncode != 0 or not done.stdout.split():
        import pytest
        pytest.skip("no tag history here; this reads the tags to know what shipped")
    tags = {t[1:] for t in done.stdout.split() if re.fullmatch(r"v\d+\.\d+\.\d+", t)}
    # Only a release number: a development or candidate version between
    # releases (`0.8.1.dev0` has been one) is not a release anybody can pin.
    being_written = {__version__} if re.fullmatch(r"\d+\.\d+\.\d+", __version__) else set()
    return tags | being_written


def patches():
    return {v for v in published() if v.split(".")[2] != "0"}


def test_every_release_the_section_names_is_one_this_repository_cut():
    """These are pin examples and a reader copies them, so a number that was
    never published -- or that belongs to the other distribution -- has to fail
    here rather than in somebody's lockfile."""
    named = set(re.findall(r"\b(\d+\.\d+\.\d+)\b", section()))
    assert named, "the section names no version; the pin advice has no example"
    unknown = sorted(named - published())
    assert not unknown, (
        f"the section names {unknown}, which no `v*` tag does. Released: "
        f"{sorted(published())}. `0.3.1` is the trap: it is in the CHANGELOG, "
        f"it is on PyPI as `vdi2770`, and it has never been this package.")


def test_the_patch_paragraph_counts_what_the_tags_say():
    """Both numbers in "three of the four patch releases" are derived, not
    written. The first has to equal the releases the bullets name; the second
    has to equal the patch releases that exist. A draft asserted only that at
    least three were named, which let the sentence say "three" while naming
    four, and let "five" stand when there were four."""
    body = section()
    m = re.search(r"(\w+) of the (\w+) patch releases", body)
    assert m, "the patch paragraph no longer states two counts in words"
    said_moved, said_total = COUNT[m.group(1).lower()], COUNT[m.group(2).lower()]

    assert said_total == len(patches()), (
        f"the section says there are {said_total} patch releases; the tags say "
        f"{len(patches())}: {sorted(patches())}")

    bullets = set(re.findall(r"^- `(\d+\.\d+\.\d+)`", body, re.M))
    assert len(bullets) == said_moved, (
        f"the section says {said_moved} moved and its bullets name "
        f"{len(bullets)}: {sorted(bullets)}")
    assert bullets <= patches(), (
        f"{sorted(bullets - patches())} are named as patch releases and are not")


def test_the_section_promises_no_support_window():
    """A window is a promise with a calendar in it. This project has one
    maintainer and has never measured whether it kept one, so the page does not
    make it -- and the sentence is easy to add back without noticing."""
    body = section().lower()
    windows = [p for p in ("supported for", "support window", "months of support",
                           "supported until", "end of life", "end-of-life",
                           "latest two releases", "last two releases",
                           "security support for") if p in body]
    assert not windows, f"the section promises a support window: {windows}"


def test_the_patch_paragraph_accounts_for_every_patch_release():
    """It says it is the one place this project undertakes to be exhaustive.

    The counts were derived and gated from the start; being *named* was not.
    So the section could say "three of the five" truthfully, name the three
    that moved a verdict, add "the fourth, 0.9.1, moved none" -- and leave the
    fifth unmentioned. The fifth was 0.9.2, the security patch, which is the
    one a reader is most likely to have come to that paragraph about.
    """
    import pytest

    body = section()
    known = patches()
    if not known:
        pytest.skip("not a git checkout; the tags are not available here")
    missing = sorted(v for v in known if v not in body)
    assert not missing, (
        f"the paragraph that undertakes to be exhaustive about patch releases "
        f"does not name {missing}; it names {sorted(v for v in known if v in body)}")
