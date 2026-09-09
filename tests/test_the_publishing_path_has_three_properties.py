"""Three things about the release workflow, each of which was once not true.

They are here together because they are one subject — what the jobs that put
this project on an index are allowed to be — and because each was found by
reading rather than by failing. A repair that leaves no assertion behind is a
repair that has to be found again.

  1. **Only the two publishers hold a publishing token, and nothing holds a
     writable repository.** Three jobs carried no `permissions:` block at all,
     so they took whatever the repository's default happened to be — measured as
     `read`, which made the exposure zero that day and left it resting on a
     setting nobody looking at this file can see.
  2. **Every action is pinned to a commit.** The publish step was
     `pypa/gh-action-pypi-publish@release/v1`, a moving reference, and it is the
     one piece of code in that job which is not ours and runs while the job
     holds a token that can publish as a real distribution.
  3. **A publisher downloads and uploads and does nothing else.** So that
     re-running it after a half-finished release repeats no decision, and so
     that the bytes it hands to PyPI are the bytes a gate installed.

Read from the file, offline, as pure functions of its text.
"""
import re

import yaml

from conftest import ROOT

RELEASE = ROOT / ".github" / "workflows" / "release.yml"
WORKFLOWS = sorted(p for p in (ROOT / ".github" / "workflows").iterdir()
                   if p.suffix in (".yml", ".yaml"))


def workflow(path):
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def publishers(doc):
    return {name for name, job in doc["jobs"].items()
            if any("pypi-publish" in str(step.get("uses", ""))
                   for step in job.get("steps", []))}


def switched_off(thing) -> bool:
    """A job or a step that will never run.

    `if: false` leaves everything where it is -- the name, the command, the
    whole block -- and stops it happening. A test that reads the file for a
    step's presence cannot tell the difference, and two mutation rows written to
    prove these checks bite survived by doing exactly that.
    """
    said = str(thing.get("if", "")).strip().lower()
    return said in ("false", "${{ false }}", "0", "off")


def test_only_the_publishers_can_publish():
    """`id-token: write` is what mints a Trusted Publishing token. Exactly the
    two jobs whose last step is an upload have it, and they have nothing else:
    a job-level block replaces the workflow's floor rather than adding to it,
    so these two hold no repository access at all."""
    doc = workflow(RELEASE)
    minting = {name for name, job in doc["jobs"].items()
               if (job.get("permissions") or {}).get("id-token") == "write"}
    assert minting == publishers(doc), (
        f"jobs that can mint a publishing token: {sorted(minting)}; jobs that "
        f"publish: {sorted(publishers(doc))}. Those have to be the same set.")


def test_no_job_in_any_workflow_can_write_to_this_repository():
    """Not just the release. A workflow that can write `contents` can move a
    tag, and a tag is what starts a release."""
    for path in WORKFLOWS:
        doc = workflow(path)
        for name, job in doc.get("jobs", {}).items():
            for scope, level in (job.get("permissions") or {}).items():
                assert not (scope == "contents" and level == "write"), (
                    f"{path.name}:{name} can write to the repository")


def test_the_release_states_its_own_floor():
    """In the file, not in a repository setting.

    A job with no `permissions:` block takes the repository default, and the
    default is a thing somebody can change without touching this file. Three
    jobs here were in that state; the floor says what they get.
    """
    doc = workflow(RELEASE)
    assert (doc.get("permissions") or {}).get("contents") == "read", (
        "release.yml states no floor, so a job that names no permissions takes "
        "whatever the repository default happens to be")
    for name, job in doc["jobs"].items():
        stated = job.get("permissions")
        assert stated is None or stated, (
            f"{name} declares an empty permissions block, which reads as a "
            f"decision and is one only if it is written as one")


def test_every_action_is_pinned_to_a_commit():
    """A tag or a branch is a name somebody else can repoint.

    `release/v1` was one, in the step that runs while the job holds a token
    that publishes. The human-readable version goes in a comment beside it,
    because a bare forty characters tells a reader nothing about what they are
    upgrading from.

    The pins are of the versions that were already in use, not of the newest
    releases: pinning and upgrading are two changes, and doing both in the
    commit before a release makes it impossible to say which one broke it.
    """
    for path in WORKFLOWS:
        for line in path.read_text(encoding="utf-8").splitlines():
            found = re.search(r"uses:\s*([\w.-]+/[\w.-]+)@(\S+)", line)
            if not found:
                continue
            owner, ref = found.groups()
            # Every one, `actions/*` included. The argument that first-party
            # actions are different does not survive being said out loud: what
            # matters is that the code runs inside a job holding a token that
            # publishes, and `actions/download-artifact` runs in exactly that
            # job. GitHub owning the repository does not make `@v4` immutable —
            # it is a tag, and a tag is a name its owner can move.
            assert re.fullmatch(r"[0-9a-f]{40}", ref), (
                f"{path.name} uses {owner}@{ref}, which is a name its owner can "
                f"repoint. Pin the commit.")
            assert "#" in line, (
                f"{path.name} pins {owner} to a commit and does not say which "
                f"version that is, so nobody can tell what upgrading it means")


def test_a_publisher_downloads_and_uploads_and_does_nothing_else():
    """No checkout, no `pip install`, no build, no script from the tree.

    Two reasons. Re-running a publisher is the whole of the recovery path when
    the engine is on the index and the alias is not, and a job that only
    downloads and uploads repeats no decision when it is re-run. And the code
    that runs beside a publishing token should be as small as it can be made.

    The checksum step is allowed: it reads two files and compares them, and it
    is the line that makes "these are the bytes the gate tested" a checked fact
    rather than an argument about the job graph.
    """
    doc = workflow(RELEASE)
    for name in publishers(doc):
        for step in doc["jobs"][name].get("steps", []):
            uses, run = str(step.get("uses", "")), step.get("run", "")
            assert "checkout" not in uses, f"{name} checks out the tree"
            for forbidden in ("pip install", "python -m build", "make ",
                              "python tools/"):
                assert forbidden not in run, (
                    f"{name} runs `{forbidden.strip()}` while holding a token "
                    f"that publishes: {run[:120]}")


# --- What actually broke: a job asked for one of the two names it needed ------

def uploads(job):
    return {str(s.get("with", {}).get("name")) for s in job.get("steps", [])
            if "upload-artifact" in str(s.get("uses", ""))}


def downloads(job):
    return {str(s.get("with", {}).get("name")) for s in job.get("steps", [])
            if "download-artifact" in str(s.get("uses", ""))}


def test_every_artifact_a_job_asks_for_is_made_upstream_of_it():
    """A name, not a file.

    The defect was here and it was silent: the job that runs the upgrade matrix
    downloaded `dist-rules` and needed `dist-reader` as well, so every case that
    installs could not resolve, and the gate standing between the two uploads
    was red on any tag. Locally it passed, because `make` builds both wheels
    into one directory — it could only fail where nobody had run it.

    A name asked for and never made is the same shape and would fail the same
    way, so this asks the question of the graph rather than of a run.
    """
    doc = workflow(RELEASE)
    jobs = doc["jobs"]

    def upstream(name, seen=None):
        seen = seen if seen is not None else set()
        needs = jobs[name].get("needs") or []
        for up in ([needs] if isinstance(needs, str) else needs):
            if up not in seen:
                seen.add(up)
                upstream(up, seen)
        return seen

    made_by = {a: n for n, j in jobs.items() for a in uploads(j)}
    for name, job in jobs.items():
        for wanted in downloads(job):
            assert wanted in made_by, (
                f"{name} downloads `{wanted}` and no job uploads it")
            assert made_by[wanted] in upstream(name), (
                f"{name} downloads `{wanted}`, which {made_by[wanted]} makes, "
                f"and does not wait for it")


def test_the_gate_receives_both_distributions_and_both_records():
    """Named, not counted.

    The job that installs and upgrades has to have both wheels in one directory
    or it is checking half a release, and it has to have both checksum lists or
    it is checking bytes it cannot name. Counting them would be satisfied by
    two copies of one.
    """
    doc = workflow(RELEASE)
    gate = next(n for n, j in doc["jobs"].items()
                if any("check_upgrade_paths.py" in (s.get("run") or "")
                       for s in j.get("steps", [])))
    assert downloads(doc["jobs"][gate]) == {
        "dist-reader", "dist-rules", "sums-reader", "sums-rules"}, (
        f"{gate} receives {sorted(downloads(doc['jobs'][gate]))}")


def test_the_checksums_are_not_handed_to_the_index():
    """`gh-action-pypi-publish` uploads what it finds in `dist/`.

    A record of what was built, written into that directory, is a file offered
    to PyPI as part of the release. Every checksum artifact therefore lands
    somewhere else, and this says so rather than trusting whoever edits the
    paths next.
    """
    doc = workflow(RELEASE)
    for name, job in doc["jobs"].items():
        for step in job.get("steps", []):
            with_ = step.get("with") or {}
            if str(with_.get("name", "")).startswith("sums-"):
                assert not str(with_.get("path", "")).startswith("dist"), (
                    f"{name} puts a checksum record in the directory the "
                    f"publish action uploads")
            run = step.get("run") or ""
            if "SHA256SUMS" in run:
                assert "dist/SHA256SUMS" not in run, (
                    f"{name} writes SHA256SUMS into dist/, which is the "
                    f"directory handed to PyPI")


def build_commands(text):
    """Every `python -m build` in a file, normalised to one spelling.

    `$(PYTHON)` is `python`, and a trailing `/` on a directory is not a
    difference. What is a difference: `--wheel`, which makes no sdist, and a
    default `--outdir` that has to be looked up rather than read.
    """
    made = []
    for line in text.splitlines():
        # Substituted before anything is stripped. `lstrip("$ ")` turns
        # `$(PYTHON)` into `(PYTHON)`, so the Makefile's two recipes were read
        # as no builds at all and this compared CI against the release while
        # silently skipping the third file it names.
        stripped = line.replace("$(PYTHON)", "python").strip()
        if not stripped.startswith(("python -m build", "run: python -m build")):
            continue
        words = stripped.split("run: ", 1)[-1].split("#", 1)[0].split()
        made.append(" ".join(w.rstrip("/") for w in words))
    return sorted(made)


def test_the_wheels_a_push_builds_are_the_wheels_a_tag_builds():
    """One spelling of "build the two distributions", in three files.

    They diverged and nothing said so: CI's rehearsal passed `--wheel`, so it
    made no sdist, while the release made both — and the parity gate waves
    `python -m build` through as setup, so neither the difference nor anything
    else about those lines was ever compared. A rehearsal that builds
    differently from the thing it rehearses is a rehearsal of something else.
    """
    release = build_commands(RELEASE.read_text(encoding="utf-8"))
    ci = build_commands((ROOT / ".github" / "workflows" / "ci.yml")
                        .read_text(encoding="utf-8"))
    makefile = build_commands((ROOT / "Makefile").read_text(encoding="utf-8"))
    assert release, "release.yml builds nothing"
    assert set(ci) == set(release), (
        f"CI builds {ci} and the release builds {release}; the wheels every "
        f"push checks are not the wheels a tag would publish")
    assert set(makefile) == set(release), (
        f"`make wheels` builds {makefile} and the release builds {release}; a "
        f"contributor's rehearsal is of something else")


def test_the_release_builds_the_single_file_it_hands_out():
    """The front page points at `releases/latest/download/vdi2770.pyz`.

    That URL resolves against whichever release is newest, so a release without
    that asset does not merely lack a file — it breaks a link on the front page
    the moment it is created. And the release workflow did not build it: for
    0.8.0 the file was produced by hand, which is the arrangement that works
    until the day somebody forgets, and nothing would have said so.

    Asserted here rather than trusted, and asserted about the workflow rather
    than about a release, because a release is a thing that has already
    happened by the time anybody could read it.
    """
    import re

    body = RELEASE.read_text(encoding="utf-8")
    page = (ROOT / "README.md").read_text(encoding="utf-8")
    if "releases/latest/download/vdi2770.pyz" not in page:
        return                       # the page stopped promising it
    doc = workflow(RELEASE)
    builds = [(name, step) for name, job in doc["jobs"].items()
              for step in job.get("steps", [])
              if "build_zipapp.py" in (step.get("run") or "")]
    assert builds, (
        "the front page points at `vdi2770.pyz` in the latest release and the "
        "release workflow does not build one, so creating a release breaks "
        "that link")
    for name, step in builds:
        assert not switched_off(step) and not switched_off(doc["jobs"][name]), (
            f"{name} builds the single file behind an `if:` that is never "
            f"true, so the release would still hand out no such asset")
    assert re.search(r"vdi2770\.pyz", body), (
        "the workflow builds the single file and does not name it as an asset")


def test_the_release_asks_the_index_about_itself_after_publishing():
    """The rows that consult the index go stale the moment a release lands.

    Two of them did, an hour after 0.8.0: one asserted the shape of requirement
    the release had just retired, and the other built its "before" state with a
    bare `pip install`, which stopped naming the older release the moment a
    newer one existed. Both were correct until the publish and wrong after it,
    and the first thing that noticed was the next push to `main` — a red badge
    on a repository whose release had just succeeded.

    The matrix that runs before the publish cannot see this: it asks about an
    index that does not yet hold this release. So the same matrix runs once
    more at the end, against the index as it now stands, in a job that publishes
    nothing and can only report.
    """
    doc = workflow(RELEASE)
    after = [name for name, job in doc["jobs"].items()
             if any("check_upgrade_paths.py" in (s.get("run") or "")
                    for s in job.get("steps", []))
             and publishers(doc) & set(upstream(doc["jobs"], name))]
    after = [n for n in after if not switched_off(doc["jobs"][n])]
    assert after, (
        "nothing runs the upgrade matrix after the release is on the index, so "
        "a row that goes stale on publication is first seen by whoever pushes "
        "next")
    for name in after:
        assert name not in publishers(doc), (
            f"{name} both publishes and re-checks; a job that reports should "
            f"not be one that uploads")


def upstream(jobs, name, seen=None):
    seen = seen if seen is not None else set()
    needs = jobs[name].get("needs") or []
    for up in ([needs] if isinstance(needs, str) else needs):
        if up not in seen:
            seen.add(up)
            upstream(jobs, up, seen)
    return seen
