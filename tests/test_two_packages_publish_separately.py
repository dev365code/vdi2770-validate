"""Two distributions ship from this repository, and PyPI keys a trusted publisher
on (repo, workflow file, environment). Two packages sharing that tuple would each
be able to publish as the other.

This lives in the repository's suite rather than the library's, because it is a
claim about plumbing the library's sdist does not contain -- putting it there made
the sdist gate fail on a file that was never supposed to be in the sdist.
"""
import re

from conftest import ROOT

WORKFLOWS = ROOT / ".github" / "workflows"
VALIDATOR = WORKFLOWS / "release.yml"
SDK = WORKFLOWS / "release-sdk.yml"


def environment(path):
    m = re.search(r"^\s*environment:\s*(\S+)", path.read_text(encoding="utf-8"), re.M)
    assert m, f"{path.name} publishes from no environment at all"
    return m.group(1)


def tags(path):
    m = re.search(r'tags:\s*\["([^"]+)"\]', path.read_text(encoding="utf-8"))
    assert m, f"{path.name} is triggered by no tag pattern"
    return m.group(1)


def test_both_packages_have_something_that_would_publish_them():
    assert VALIDATOR.exists() and SDK.exists()
    for wf in (VALIDATOR, SDK):
        text = wf.read_text(encoding="utf-8")
        assert "id-token" in text, f"{wf.name}: Trusted Publishing needs id-token: write"
        assert "password:" not in text, f"{wf.name}: a stored token would defeat it"


def test_they_do_not_share_a_publishing_environment():
    assert environment(VALIDATOR) != environment(SDK), (
        f"both publish from {environment(SDK)!r}; either could then publish as the other")


def test_the_tag_patterns_cannot_both_match_one_tag():
    """`sdk-v0.1.0` must not trip the validator's release, and vice versa."""
    v, s = tags(VALIDATOR), tags(SDK)
    assert v != s
    for tag in ("v0.2.0", "sdk-v0.1.0"):
        matched = [p for p in (v, s) if re.fullmatch(p.replace("*", ".*"), tag)]
        assert len(matched) == 1, f"tag {tag} matches {matched}"


def test_each_workflow_checks_that_the_tag_is_that_package_version():
    """A tag that says 0.2.0 publishing a tree that says 0.1.9 is unrecoverable:
    the number is on PyPI forever and does not match the code."""
    assert 'tag="${GITHUB_REF_NAME#v}"' in VALIDATOR.read_text(encoding="utf-8")
    assert 'tag="${GITHUB_REF_NAME#sdk-v}"' in SDK.read_text(encoding="utf-8")


def test_a_publishing_workflow_refuses_a_version_the_index_already_has():
    """A tag can be moved. Publishing cannot be undone.

    Both workflows fire on `push: tags`, and a *forced* tag update emits that
    event exactly like a new tag does. So re-pointing an old tag — which any
    history repair does — walks a days-old tree through the gate and then hands
    it to the publisher, which is asked to upload a filename the index already
    holds. What comes back is a rejection and a red run against the publishing
    environment, on a repository whose whole claim is that the gate is green.

    The step below asks the index first. It costs one HTTP request and turns an
    accident into a clean skip.
    """
    for path in (VALIDATOR, SDK):
        body = path.read_text(encoding="utf-8")
        assert "tools/check_version_is_new.py" in body, (
            f"{path.name} publishes without asking whether the index already "
            f"has this version; a re-pointed tag would try to upload over it")
