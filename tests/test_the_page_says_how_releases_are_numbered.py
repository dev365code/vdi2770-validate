"""The page has to say what a version number means before somebody pins one.

Without this section a reader learns the rules of this project's numbering by
upgrading and finding out. The section is prose, so what is held here is the
part a reader would act on: that it exists, that every release it names is a
release this repository actually cut, that the patch releases it names really
are patch releases, and that it does not promise a support window -- a sentence
this project cannot keep and has never checked.
"""
import re

from conftest import ROOT, changelog_sections

HEADING = "## Releases and version numbers"


def section() -> str:
    page = (ROOT / "README.md").read_text(encoding="utf-8")
    assert HEADING in page, f"README.md has no {HEADING!r} section"
    body = page.split(HEADING, 1)[1]
    nxt = re.search(r"^## ", body, re.M)
    return body[: nxt.start()] if nxt else body


def released() -> set:
    """The versions this repository has a CHANGELOG section for, read out of the
    headings rather than from a list kept beside them."""
    found = set()
    for heading, _ in changelog_sections():
        m = re.search(r"(\d+\.\d+\.\d+)", heading)
        if m:
            found.add(m.group(1))
    return found


def test_every_release_the_section_names_is_one_this_repository_cut():
    """A number in prose outlives the thing it names. These are pin examples --
    a reader copies them -- so a version that was never published, or was
    renumbered, has to fail here rather than in their lockfile."""
    named = set(re.findall(r"\b(\d+\.\d+\.\d+)\b", section()))
    assert named, "the section names no version; the pin advice has no example"
    unknown = sorted(named - released())
    assert not unknown, (
        f"the section names {unknown}, which no CHANGELOG section does. "
        f"Released here: {sorted(released())}")


def test_the_patch_releases_it_names_are_patch_releases():
    """The section's argument is that a patch can still move what a pipeline
    sees, and it argues it by pointing at three. Pointing at a minor release
    instead would make the paragraph true of nothing."""
    body = section()
    claimed = set(re.findall(r"`(\d+\.\d+\.\d+)` (?:gave|bounded|turned)", body))
    assert len(claimed) >= 3, (
        f"the patch paragraph names {sorted(claimed)}; it argues from the ones "
        f"that moved a verdict and there are three")
    not_patches = sorted(v for v in claimed if v.split(".")[2] == "0")
    assert not not_patches, f"{not_patches} are not patch releases"


def test_the_section_promises_no_support_window():
    """A window is a promise with a calendar in it. This project has one
    maintainer and has never measured whether it kept one, so the page does not
    make it -- and the sentence is easy to add back without noticing."""
    body = section().lower()
    windows = [p for p in ("supported for", "support window", "months of support",
                           "latest two releases", "last two releases",
                           "security support for") if p in body]
    assert not windows, f"the section promises a support window: {windows}"
