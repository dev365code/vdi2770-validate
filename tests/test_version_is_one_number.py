"""One version, written in three places, asserted to agree.

The project's own rule is that a number in prose must be held by a test. The
version was the exception: `pyproject.toml`, `__init__.py` and the CHANGELOG
each carry it independently, and a tag adds a fourth. A release where they
disagree is a release nobody can reason about afterwards.
"""
import re

from conftest import ROOT
from vdi2770_validate import __version__

VERSION = re.compile(r"^\d+\.\d+\.\d+(?:\.?(?:dev|a|b|rc)\d+)?$")


def pyproject_version():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    assert m, "pyproject.toml declares no version"
    return m.group(1)


def changelog_heading():
    for line in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            return line[3:].strip()
    raise AssertionError("CHANGELOG.md has no section heading")


def test_the_version_is_shaped_like_one():
    assert VERSION.match(__version__), __version__


def test_the_package_and_the_project_agree():
    assert __version__ == pyproject_version()


def test_the_changelog_top_section_matches_the_version():
    """`Unreleased` is allowed only while the version is a pre-release. Once it
    is not, the top of the changelog has to name it."""
    top = changelog_heading()
    if top.lower().startswith("unreleased"):
        assert any(k in __version__ for k in ("dev", "a", "b", "rc")), (
            f"version {__version__} looks releasable but the changelog still says {top!r}")
    else:
        assert top.split()[0].lstrip("v") == __version__, (
            f"changelog says {top!r}, package says {__version__}")


def test_a_release_workflow_exists_and_is_triggered_by_a_tag():
    wf = ROOT / ".github" / "workflows" / "release.yml"
    assert wf.exists(), "nothing would publish a tag"
    text = wf.read_text(encoding="utf-8")
    assert "tags:" in text
    assert "id-token" in text, "Trusted Publishing needs id-token: write"
    assert "password:" not in text, "a long-lived token would defeat Trusted Publishing"


def test_every_released_tag_has_a_changelog_section():
    """A tag is a version somebody can install; a version somebody can install
    with nothing written about it is a version nobody can reason about.

    The other direction is deliberately not checked: a section may exist before
    its tag, which is what `## Unreleased` is for. And this reads git, so it
    skips where there is no repository — inside an sdist there are no tags to
    check and a gate that raises there is a gate that breaks the sdist.
    """
    import re
    import subprocess

    found = subprocess.run(["git", "tag", "-l"], cwd=ROOT, capture_output=True, text=True)
    if found.returncode != 0:
        import pytest
        pytest.skip("not a git checkout")

    tags = {t[1:] for t in found.stdout.split() if re.fullmatch(r"v\d+\.\d+\.\d+", t)}
    if not tags:
        import pytest
        pytest.skip("nothing released yet")

    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    documented = {h.split()[0].lstrip("v") for h in re.findall(r"^## (\S+)", text, re.M)}
    missing = sorted(tags - documented, key=lambda v: [int(p) for p in v.split(".")])
    assert not missing, f"released with no changelog section: {missing}"


def test_a_released_section_is_frozen_at_its_tag():
    """From 0.8.0 on, a tagged release's changelog section is the text that went
    out under the tag: a released section is a record, and rewriting it changes
    what a version said when people took it.

    Only from 0.8.0. The earlier sections had their prose tidied after their
    tags -- no rule or verdict changed, and the text each carried when it was
    published is in that tag's own CHANGELOG.md, which the note at the top of the
    file points to. Restoring them here would carry that superseded wording back.

    The one edit a frozen section may take is an appended correction,
    `*(Correction YYYY-MM-DD: ...)*`: the tag's text must be a prefix of the
    section and every line past it a correction marker. Reads git, so it skips
    inside an sdist where there are no tags.
    """
    import re
    import subprocess

    baseline = (0, 8, 0)
    marker = re.compile(r"^\*\(Correct(?:ion|ed)\b.*\)\*$")

    def section(text, ver):
        m = re.search(rf"(?ms)^(## {re.escape(ver)}\b.*?)(?=^## |\Z)", text)
        return m.group(1).rstrip() if m else None

    found = subprocess.run(["git", "tag", "-l"], cwd=ROOT, capture_output=True, text=True)
    if found.returncode != 0:
        import pytest
        pytest.skip("not a git checkout")
    versions = [t[1:] for t in found.stdout.split() if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
    frozen = [v for v in versions
              if tuple(int(p) for p in v.split(".")) >= baseline]
    if not frozen:
        import pytest
        pytest.skip("nothing released at or past the baseline yet")

    main_cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    wrong = []
    for v in sorted(frozen, key=lambda s: [int(p) for p in s.split(".")]):
        tagged = subprocess.run(["git", "show", f"v{v}:CHANGELOG.md"],
                                cwd=ROOT, capture_output=True, text=True)
        if tagged.returncode != 0:
            continue  # the sibling test owns "a tag has a section"; this owns "unchanged"
        want, have = section(tagged.stdout, v), section(main_cl, v)
        if want is None or have is None:
            wrong.append(f"{v}: no section to compare")
        elif have == want:
            continue
        elif have.startswith(want):
            extra = [ln.strip() for ln in have[len(want):].splitlines() if ln.strip()]
            if not all(marker.match(ln) for ln in extra):
                wrong.append(f"{v}: edited past the tag by something other than a correction")
        else:
            wrong.append(f"{v}: the released record was rewritten, not appended to")
    assert not wrong, (
        "a released changelog section must be the text that went out under its "
        f"tag; only `*(Correction ...)*` may be appended: {wrong}")
