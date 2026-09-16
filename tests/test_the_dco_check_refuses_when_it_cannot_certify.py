"""The DCO check must refuse when it cannot certify, not pass by default.

`dco.yml` reads the commit range inside a `for sha in $(git rev-list ...)` word
list. When that rev-list errors -- the base branch was force-pushed out from
under a re-run, so the base SHA recorded in the frozen event payload is no
longer an object -- the substitution is empty, the loop body never runs, and
the job exits 0 having examined nothing. `set -e` and `pipefail` do not catch a
failing substitution in a for-list; measured, not assumed. A gate that cannot
tell must refuse, the same rule the release's ci-judged gate is built on, and
this holds the workflow's own shell to it.

The real `run:` block is lifted out of `dco.yml` and executed under the shell
GitHub uses for a `run:` step -- `bash --noprofile --norc -eo pipefail` -- with
the two event SHAs turned into environment variables. Asserting on the exit
code, because that is the whole of what a required check reports, and reading
the real file so a regression in it is caught here rather than in a rerun
nobody is watching.
"""
import os
import subprocess

import pytest

from conftest import ROOT

DCO = ROOT / ".github" / "workflows" / "dco.yml"

#: The check is a bash `run:` block; GitHub runs it on Linux. On Windows the
#: shell and its quoting differ and are not what ships, so the behaviour under
#: test is a Linux one.
linux_only = pytest.mark.skipif(
    os.name == "nt",
    reason="the DCO check is a bash run: block that GitHub runs on Linux")

SIGNOFF = "\n\nSigned-off-by: A Contributor <a@b.example>"


def dco_script():
    """The signoff step's `run:` block, with the two `${{ }}` event SHAs turned
    into `$PR_BASE` / `$PR_HEAD` so the real script can run outside Actions."""
    import yaml

    doc = yaml.safe_load(DCO.read_text(encoding="utf-8"))
    run = next(s["run"] for s in doc["jobs"]["signoff"]["steps"] if "run" in s)
    run = run.replace("${{ github.event.pull_request.base.sha }}", "${PR_BASE}")
    run = run.replace("${{ github.event.pull_request.head.sha }}", "${PR_HEAD}")
    assert "${{" not in run, f"an event expression went unsubstituted: {run!r}"
    return run


def a_repo(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True,
                       capture_output=True, text=True, encoding="utf-8")
    git("init", "-q")
    git("config", "user.email", "a@b.example")
    git("config", "user.name", "A Contributor")
    return git


def commit(tmp_path, message):
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", message],
                   cwd=tmp_path, check=True, capture_output=True, text=True,
                   encoding="utf-8")
    done = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True,
                          capture_output=True, text=True, encoding="utf-8")
    return done.stdout.strip()


def run_check(tmp_path, base, head):
    env = dict(os.environ, PR_BASE=base, PR_HEAD=head)
    done = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", dco_script()],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", env=env)
    return done.returncode, done.stdout + done.stderr


@linux_only
def test_a_signed_commit_is_accepted(tmp_path):
    a_repo(tmp_path)
    base = commit(tmp_path, "root" + SIGNOFF)
    head = commit(tmp_path, "the work" + SIGNOFF)
    code, said = run_check(tmp_path, base, head)
    assert code == 0, said


@linux_only
def test_an_unsigned_commit_is_refused(tmp_path):
    a_repo(tmp_path)
    base = commit(tmp_path, "root" + SIGNOFF)
    head = commit(tmp_path, "the work, with no certificate of origin")
    code, said = run_check(tmp_path, base, head)
    assert code != 0
    assert head[:7] in said, said


@linux_only
def test_one_unsigned_among_signed_is_refused(tmp_path):
    """A single missing sign-off fails the range, not just an all-unsigned one."""
    a_repo(tmp_path)
    base = commit(tmp_path, "root" + SIGNOFF)
    commit(tmp_path, "signed work" + SIGNOFF)
    head = commit(tmp_path, "the one without")
    code, said = run_check(tmp_path, base, head)
    assert code != 0
    assert head[:7] in said, said


@linux_only
def test_a_range_it_cannot_compute_is_a_refusal_not_a_pass(tmp_path):
    """The fail-open this file is named for.

    A base SHA that is no longer an object -- its branch force-pushed under a
    re-run -- makes `git rev-list` error. The check must refuse; passing here
    means it certified nothing and reported green.
    """
    a_repo(tmp_path)
    head = commit(tmp_path, "the work" + SIGNOFF)
    absent = "deadbeef" * 5  # forty hex, not an object in this repository
    code, said = run_check(tmp_path, absent, head)
    assert code != 0, (
        "a commit range the check could not compute exited 0: it examined no "
        f"commit and passed. Output: {said!r}")
