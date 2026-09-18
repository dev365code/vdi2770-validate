"""The release page and the CHANGELOG say the same thing, because one is made
from the other.

Every release so far was described twice: a section in the repository, and a
body typed into a form. Two accounts of one release drift, and the one nobody
can diff is the one that drifts. This holds the generator to refusing rather
than improvising -- a release that describes itself wrongly is worse than a
release nobody could cut.
"""
import importlib.util

import pytest

from conftest import ROOT

_spec = importlib.util.spec_from_file_location(
    "release_notes", ROOT / "tools" / "release_notes.py")
release_notes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_notes)

SHA = "a" * 64

CHANGELOG = """# Changelog

Some preamble nobody releases.

## 9.9.9 — 2026-02-02

Who should take this release: anybody who reads
exit codes, wrapped the way a changelog wraps.

**Something changed.** And it is described here.

## 9.9.8 — 2026-01-01

Who should take this release: nobody, it is old.
"""


def test_the_opening_paragraph_becomes_the_opening_line():
    body = release_notes.body("9.9.9", SHA, CHANGELOG)
    assert body.startswith("**Who should take this release:** anybody who reads exit codes,"), body[:120]
    # The changelog wraps for a page; a release body is read in a browser.
    assert "reads\nexit codes" not in body


def test_the_newest_section_is_the_one_used():
    body = release_notes.body("9.9.9", SHA, CHANGELOG)
    assert "nobody, it is old" not in body


def test_a_section_for_another_version_is_refused():
    """The tag says one thing and the CHANGELOG another; this script is not the
    one to decide which is right."""
    with pytest.raises(release_notes.CannotDescribe) as caught:
        release_notes.body("9.9.8", SHA, CHANGELOG)
    assert "9.9.9" in str(caught.value) and "9.9.8" in str(caught.value)


def test_a_section_with_no_opening_paragraph_is_refused():
    broken = CHANGELOG.replace("Who should take this release: anybody who reads\nexit codes,",
                               "Something else entirely,")
    with pytest.raises(release_notes.CannotDescribe):
        release_notes.body("9.9.9", SHA, broken)


def test_a_changelog_with_no_sections_is_refused():
    with pytest.raises(release_notes.CannotDescribe):
        release_notes.body("9.9.9", SHA, "# Changelog\n\nnothing here\n")


def test_something_that_is_not_a_hash_is_refused():
    """The body prints the hash a reader checks the single file against. A
    placeholder printed there is worse than no hash at all."""
    with pytest.raises(release_notes.CannotDescribe):
        release_notes.body("9.9.9", "not-a-hash", CHANGELOG)


def test_the_body_tells_a_reader_how_to_check_what_they_downloaded():
    body = release_notes.body("9.9.9", SHA, CHANGELOG)
    assert SHA in body, "the single file's hash is not in the body"
    assert "vdi2770.pyz" in body


def test_the_body_promises_only_files_a_release_actually_carries():
    """A release carries `SHA256SUMS-reader` and `SHA256SUMS-rules`. An earlier
    draft of this body told readers to check a combined `SHA256SUMS`, which no
    release has ever had -- a verification instruction that cannot be followed
    is worse than none."""
    body = release_notes.body("9.9.9", SHA, CHANGELOG)
    assert "sha256sum -c SHA256SUMS-reader" in body
    assert "sha256sum -c SHA256SUMS-rules" in body
    assert "-c SHA256SUMS\n" not in body, "the body names a file releases do not carry"


def test_a_section_still_being_written_is_refused():
    """A released section carries a date; the one being written says
    "unreleased". Describing the second as a release is the last hand step
    before a tag that nothing else checks."""
    undated = CHANGELOG.replace("## 9.9.9 — 2026-02-02", "## 9.9.9 — unreleased", 1)
    with pytest.raises(release_notes.CannotDescribe) as caught:
        release_notes.body("9.9.9", SHA, undated)
    assert "carries no date" in str(caught.value)


def test_it_runs_against_this_repository_s_own_changelog():
    """The premise: the shape this file asserts on is the shape the CHANGELOG
    actually has. A generator that only works on its own fixture is one that
    will be found out on a tag.

    The top section here is the release being written, so it is dated the way a
    tag would date it, and the generator is asked about that.
    """
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    dated = changelog.replace(" — unreleased", " — 2026-01-01", 1)
    version, _ = release_notes.top_section(dated)
    body = release_notes.body(version, SHA, dated)
    assert body.startswith("**Who should take this release:**")
    assert f"section {version}" in body
