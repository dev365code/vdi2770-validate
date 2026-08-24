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
