"""The release refuses a tag that does not name the version it would publish.

The number is on the index forever and does not come round again, so a tag
saying 0.2.0 over a tree saying 0.1.9 is unrecoverable. Each publishing job
therefore checks its own package against the tag.

**This is here because the check could not run.** Both jobs read the version by
importing the package with `sys.path.insert(0, 'src')`, in an environment that
has `build` and `packaging` and nothing else. That worked while the alias was a
package of its own; after the merge its `__init__` imports the engine, which is
not installed there, so the import raised, the shell substitution produced the
empty string, and the step failed with *tag 0.8.0 != package* on every tag.

Nothing caught it. CI never ran that snippet, the test that asserts the step
exists compares the *text* of the line rather than running it, and the mutation
row only replaces the line with `true`. A gate whose first execution is the
release is not a gate — which is the same sentence this project wrote about the
job that downloads the wheels, one release earlier.

So the check is a script, it reads the manifest rather than importing anything,
and these run it.
"""
import subprocess
import sys

from conftest import ROOT

TOOL = ROOT / "tools" / "check_tag_is_the_version.py"


def run(*args, isolated=False):
    """`-I` isolates: no site-packages, no `PYTHONPATH`, no user site.

    That is stronger than the environment the release job has, and it is the
    point — this must not need anything installed, because the job that runs it
    installs almost nothing.
    """
    argv = [sys.executable] + (["-I"] if isolated else []) + [str(TOOL), *args]
    return subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)


def version_of(project):
    import re
    body = (ROOT / project / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version = "([^"]+)"', body, re.M).group(1)


def test_the_tag_that_matches_is_accepted():
    for project in (".", "packages/vdi2770"):
        done = run("--tag", version_of(project), "--project", project)
        assert done.returncode == 0, done.stdout + done.stderr


def test_it_needs_nothing_installed():
    """The failure that made this file exist, stated as its opposite."""
    done = run("--tag", version_of("."), "--project", ".", isolated=True)
    assert done.returncode == 0, (
        f"the check cannot run in an interpreter with nothing installed, which "
        f"is what the release job has: {done.stdout + done.stderr}")


def test_a_tag_that_is_not_the_version_is_refused():
    done = run("--tag", "9.9.9", "--project", ".")
    assert done.returncode != 0
    assert "9.9.9" in (done.stdout + done.stderr)


def test_each_project_is_read_from_its_own_manifest():
    """Two manifests, and the check has to read the one it was asked about.

    They carry the same number today, so a check that read the wrong file would
    pass — and would go on passing until the day they differ, which is the day
    it matters.
    """
    done = run("--tag", version_of("."), "--project", "packages/vdi2770")
    other = run("--tag", "0.0.0", "--project", "packages/vdi2770")
    assert done.returncode == 0
    assert other.returncode != 0
    assert "packages/vdi2770" in (other.stdout + other.stderr), (
        "the refusal does not say which project it was about")


def test_a_project_with_no_manifest_is_refused_not_ignored():
    done = run("--tag", "0.8.0", "--project", "docs")
    assert done.returncode != 0
    assert "pyproject.toml" in (done.stdout + done.stderr)


def test_both_publishing_jobs_run_it():
    """And on their own project, not on one project twice."""
    import re

    body = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    asked = re.findall(r"check_tag_is_the_version\.py --tag \S+ --project (\S+)", body)
    assert sorted(asked) == [".", "packages/vdi2770"], (
        f"the release checks the tag for {asked}; there are two distributions "
        f"and each has to be checked against its own manifest")
