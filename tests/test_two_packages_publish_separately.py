"""Two distributions ship from this repository, and PyPI keys a trusted publisher
on (repo, workflow file, environment). Two publishers sharing that tuple would
each be able to publish as the other.

They were two workflow files on two tags, one per distribution, each released
on its own schedule. They are four jobs in one file now, because the two halves
are one release: same version, one tag, and `vdi2770-validate` pinning
`vdi2770` exactly. That pin is an ordering. Publish the rules first and the
index holds a distribution pip cannot resolve, under a number PyPI will not let
anyone reuse. `needs:` states that; two files firing on two tags cannot.

So the tuple is kept distinct by the half that is left -- the environment -- and
that is now the only thing standing between the two publishers. It was worth a
test when it was one of two defences; it is worth more as the only one.

This lives in the repository's suite rather than the library's, because it is a
claim about plumbing the library's sdist does not contain -- putting it there made
the sdist gate fail on a file that was never supposed to be in the sdist.
"""
import re

from conftest import ROOT

WORKFLOWS = ROOT / ".github" / "workflows"
RELEASE = WORKFLOWS / "release.yml"


def jobs(path):
    """Every job in a workflow, as name -> its block of text.

    Regex rather than a YAML parser: nothing else in this suite needs one, and
    the claims below are all about lines that must or must not be present.
    """
    text = path.read_text(encoding="utf-8")
    body = text[text.index("\njobs:"):]
    names = [(m.group(1), m.start()) for m in re.finditer(r"^  ([A-Za-z][\w-]*):$",
                                                          body, re.M)]
    assert names, f"{path.name} declares no jobs"
    bounds = [s for _, s in names] + [len(body)]
    return {n: body[bounds[i]:bounds[i + 1]] for i, (n, _) in enumerate(names)}


def publishers(path):
    """The jobs that hand something to PyPI."""
    found = {n: b for n, b in jobs(path).items() if "pypi-publish" in b}
    assert len(found) == 2, (
        f"{path.name} has {sorted(found)} publishing jobs; this repository "
        f"publishes two distributions and each needs its own")
    return found


def environment(block):
    m = re.search(r"^\s*environment:\s*(\S+)", block, re.M)
    assert m, "a publishing job runs in no environment at all"
    return m.group(1)


def test_it_is_a_tag_that_publishes():
    """The rewrite from two workflow files to two jobs dropped this.

    Each file used to declare its own `tags:` pattern and a helper asserted both
    were there — the claim being that `sdk-v0.1.0` must not trip the validator's
    release and vice versa. One file and one tag pattern now, so the collision
    is gone; what is left is the pattern itself, and nothing said it had to
    exist. Reproduced: replacing `on: push: tags` with `on: workflow_dispatch`
    left the whole suite green, and every step below reads
    `${GITHUB_REF_NAME#v}` — which is a branch name on a dispatch, and the
    version comparison would fail at the one moment nobody wants a surprise.
    """
    body = RELEASE.read_text(encoding="utf-8")
    pattern = re.search(r'tags:\s*\["([^"]+)"\]', body)
    assert pattern, "release.yml is triggered by no tag pattern"
    assert pattern.group(1).startswith("v"), (
        f"release.yml fires on {pattern.group(1)!r} and its steps strip a "
        f"leading `v` from the ref to get the version")
    assert "${GITHUB_REF_NAME#v}" in body, (
        "nothing derives the version from the tag that triggered the release")


def test_both_distributions_have_something_that_would_publish_them():
    body = RELEASE.read_text(encoding="utf-8")
    for name, block in publishers(RELEASE).items():
        assert "id-token" in block, f"{name}: Trusted Publishing needs id-token: write"
    assert "password:" not in body, "a stored token would defeat Trusted Publishing"


def test_they_do_not_share_a_publishing_environment():
    """The whole tuple, now that the workflow file is shared: if the environment
    matched too, either job could publish as the other package."""
    got = {n: environment(b) for n, b in publishers(RELEASE).items()}
    assert len(set(got.values())) == 2, (
        f"both publish from the same environment ({got}); either could then "
        f"publish as the other")


def upstream(all_jobs, start):
    """Every job `start` waits on, however many hops away. Asserting on one hop
    would pass the day a build job is inserted between two of them."""
    seen, todo = set(), [start]
    while todo:
        job = todo.pop()
        if job in seen:
            continue
        seen.add(job)
        for m in re.finditer(r"^\s*needs:\s*(.+)$", all_jobs.get(job, ""), re.M):
            todo.extend(re.findall(r"[\w-]+", m.group(1)))
    return seen


def test_the_rules_cannot_be_published_before_the_reader_they_pin():
    """The ordering the two-tag arrangement could not express.

    `vdi2770-validate` pins `vdi2770` exactly. Published first, it is
    permanently unresolvable — the version number does not come back.
    `tools/check_release_order.py` refuses that at run time; this asserts the
    workflow does not even offer it the chance.

    Which publisher is which is read from what its chain of jobs actually does,
    not from what the jobs are called: a rename would otherwise move this test's
    subject without failing it.
    """
    all_jobs = jobs(RELEASE)
    pubs = publishers(RELEASE)

    def chain(job):
        return "".join(all_jobs[j] for j in upstream(all_jobs, job))

    rules = [n for n in pubs if "--package vdi2770-validate " in chain(n)]
    reader = [n for n in pubs if n not in rules]
    assert len(rules) == 1 and len(reader) == 1, (
        f"cannot tell the two publishers apart by what they publish: "
        f"rules={rules}, reader={reader}")
    assert reader[0] in upstream(all_jobs, rules[0]), (
        f"{rules[0]} does not wait on {reader[0]}, so the rules can be "
        f"published before the reader they pin")


def test_each_publisher_checks_that_the_tag_is_the_version_it_publishes():
    """A tag that says 0.2.0 publishing a tree that says 0.1.9 is unrecoverable:
    the number is on PyPI forever and does not match the code.

    One tag drives both distributions now, so both have to be checked against
    it. Either half left on a stale number is a pair that was never built: the
    tag says one release and the wheels are two.
    """
    body = RELEASE.read_text(encoding="utf-8")
    assert body.count('tag="${GITHUB_REF_NAME#v}"') == 2, (
        "one of the two distributions is published without comparing the tag to "
        "the version in the tree")
    compares = re.findall(r'test\s+"\$tag"\s*=\s*"\$pkg"[^\n]*', body)
    assert len(compares) == 2, f"the tag is built and never compared: {compares}"
    for compare in compares:
        assert "exit 1" in compare, (
            f"the tag is compared to the version and nothing stops on a "
            f"mismatch: {compare!r}")
    # And each half's version has to come from that half. Reading the same
    # source twice compares the tag against one number and calls it two, which
    # is precisely the mismatch this exists to catch.
    reads = re.findall(r"^\s*pkg=\$\((.*)\)\s*$", body, re.M)
    assert len(reads) == 2, f"the two versions are not read from anywhere: {reads}"
    assert reads[0] != reads[1], (
        f"both jobs read the version the same way ({reads[0]!r}), so one of "
        f"them is comparing the tag against the other distribution's number")


def test_a_publishing_workflow_refuses_a_version_the_index_already_has():
    """A tag can be moved. Publishing cannot be undone.

    This fires on `push: tags`, and a *forced* tag update emits that event
    exactly like a new tag does. So re-pointing an old tag — which any history
    repair does — walks a days-old tree through the gate and then hands it to the
    publisher, which is asked to upload a filename the index already holds. What
    comes back is a rejection and a red run against the publishing environment,
    on a repository whose whole claim is that the gate is green.

    Both distributions, because both are uploaded: asking for one and not the
    other leaves the same accident available on the other half.
    """
    body = RELEASE.read_text(encoding="utf-8")
    asked = [line.strip() for line in body.splitlines()
             if "check_version_is_new.py" in line and not line.lstrip().startswith("#")]
    assert len(asked) == 2, (
        f"the index is asked about {len(asked)} of the two distributions "
        f"published here: {asked}")
    for name in ("vdi2770", "vdi2770-validate"):
        assert any(f"--package {name} " in line for line in asked), (
            f"{name} is published without asking whether the index already has "
            f"this version; a re-pointed tag would try to upload over it")
    # `--offline` exists for a machine with no route out, and it says so rather
    # than guessing. In a workflow it is the gate switched off, in one word, on
    # the line that looks like the gate is there.
    for line in asked:
        assert "--offline" not in line, (
            f"the index is asked with --offline, which is not asking: {line}")


def test_the_order_gate_runs_and_not_with_the_flag_that_skips_the_index():
    """Two ways to switch it off, and the second was the only one checked.

    `needs:` orders the jobs; it does not prove the index serves the file, and
    the redirect is unresolvable until it does. `check_release_order.py` is what
    asks. Replacing that command with `true` left every assertion in this
    repository green — the sibling above still saw the `needs:` edge, and the
    `--offline` loop below iterated over no lines at all and passed. Absence
    read as compliance.

    `--offline` is the other way: it leaves the gate checking the tag and
    skipping the index, which is the half that was there when it was still
    claiming to have asked.
    """
    body = RELEASE.read_text(encoding="utf-8")
    runs = [line.strip() for line in body.splitlines()
            if "check_release_order.py" in line and not line.lstrip().startswith("#")]
    assert runs, (
        "release.yml does not run tools/check_release_order.py. Nothing else "
        "asks an index whether the package the redirect depends on exists -- "
        "`python -m build` does not resolve runtime dependencies -- so without "
        "it the old name can be published against a version that is not there, "
        "permanently unresolvable.")
    assert (ROOT / "tools" / "check_release_order.py").exists(), (
        "release.yml runs a script that is not in this tree")
    for line in runs:
        assert "--offline" not in line, (
            "the order gate runs with --offline, so nothing asks the index "
            "whether the package was published: " + line)


def test_every_workflow_that_reads_the_tag_history_fetches_it():
    """`fetch-depth: 0` is load-bearing, and pinned by nothing.

    A default checkout is `--depth 1 --no-tags`. Without the tags,
    `check_release_order.py` and the API record refuse — they fail closed, which
    is right — but the assertions comparing this tree against a release tag do
    not: they *skip*. That is the shape the comment in `ci.yml` describes as
    "the only way a gate fails that nobody notices", and it was reachable by
    changing one character in any of these files.
    """
    from pathlib import Path

    # Not `"fetch-depth: 0" in body`. These files explain the line in a comment
    # above it, so that spelling is satisfied by the explanation while the
    # checkout itself says `1`. Found by mutating the config line and watching
    # this pass -- the first version of this test read the prose.
    setting = re.compile(r"^\s*(?!#)[^\n#]*fetch-depth:\s*(\d+)", re.M)
    reads_tags = ("make check", "check_release_order.py", "api_fingerprint.py")
    for path in sorted(Path(WORKFLOWS).glob("*.yml")):
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


def test_each_build_asks_the_index_about_the_distribution_it_actually_builds():
    """The question and the upload are separate steps, and nothing tied them
    together.

    Ask the index whether it already has `vdi2770` 0.7.0, get a clean answer,
    and then run a build that produces `vdi2770-validate` instead: every
    assertion above stays green, and a version goes onto the index that was
    never checked. PyPI does not take it back, and the number does not come
    round again.
    """
    for name, block in jobs(RELEASE).items():
        asked = re.findall(r"check_version_is_new\.py --package (\S+)", block)
        built = re.findall(r"python -m build(?:\s+(?!-)(\S+))?", block)
        if not asked and not built:
            continue
        assert len(asked) == 1 and len(built) == 1, (
            f"{name} asks the index about {asked} and builds {built}. A job "
            f"that does one without the other leaves the pairing to whoever "
            f"reads the file next.")
        # Where each distribution is built from. The rules are the repository
        # root, which `python -m build` takes as its default and writes as no
        # argument at all.
        where = {"vdi2770": "packages/vdi2770", "vdi2770-validate": ""}
        assert asked[0] in where, f"{name} asks about an unknown distribution: {asked[0]}"
        assert built[0] == where[asked[0]], (
            f"{name} asks the index about {asked[0]} and then builds "
            f"{built[0] or 'the repository root'}, which is the other one")
