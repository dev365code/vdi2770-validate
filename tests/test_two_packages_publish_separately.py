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


def test_each_workflow_compares_the_tag_to_the_version_and_stops():
    """The existing check asserts a shell variable is created, not that it is
    used. Replace the comparison with `true` and nothing goes red.

    Its own docstring says what that costs: *"A tag that says 0.2.0 publishing a
    tree that says 0.1.9 is unrecoverable: the number is on PyPI forever and
    does not match the code."* The assignment is not what prevents that.
    """
    import re

    for path in (VALIDATOR, SDK):
        body = path.read_text(encoding="utf-8")
        assert re.search(r'test\s+"\$tag"\s*=\s*"\$pkg"', body), (
            f"{path.name} builds $tag and $pkg and never compares them")
        compare = re.search(r'test\s+"\$tag"\s*=\s*"\$pkg"[^\n]*', body).group(0)
        assert "exit 1" in compare, (
            f"{path.name} compares the tag to the version and does not stop on a "
            f"mismatch: {compare!r}")


def test_every_workflow_that_reads_the_tag_history_fetches_it():
    """`fetch-depth: 0` is load-bearing in all three, and pinned by nothing.

    A default checkout is `--depth 1 --no-tags`. Without the tags,
    `check_release_order.py` and the API record refuse — they fail closed, which
    is right — but the two assertions comparing this tree against `sdk-v*` do
    not: they *skip*. That is the shape the comment in `ci.yml` describes as
    "the only way a gate fails that nobody notices", and it was reachable by
    changing one character in any of the three files.
    """
    import re
    from pathlib import Path

    # Not `"fetch-depth: 0" in body`. Two of these files explain the line in a
    # comment above it, so that spelling is satisfied by the explanation while
    # the checkout itself says `1`. Found by mutating the config line and
    # watching this pass -- the first version of this test read the prose.
    setting = re.compile(r"^\s*(?!#)[^\n#]*fetch-depth:\s*(\d+)", re.M)
    reads_tags = ("make check", "check_release_order.py", "api_fingerprint.py")
    for path in sorted(Path(VALIDATOR.parent).glob("*.yml")):
        body = path.read_text(encoding="utf-8")
        if not any(name in body for name in reads_tags):
            continue
        depths = setting.findall(body)
        assert depths, (
            f"{path.name} runs something that reads the tag history and does not "
            f"set fetch-depth; a default checkout is --depth 1 --no-tags, and the "
            f"assertions that compare against a tag will skip rather than fail")
        assert all(d == "0" for d in depths), (
            f"{path.name} checks out with fetch-depth {depths} and then runs "
            f"something that reads the tag history")
