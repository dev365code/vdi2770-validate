"""Before a tag is turned into a publish, something must have judged this commit.

`make check` runs on the tagged tree inside the release workflow, and that is
one interpreter on one Linux runner. The four-row matrix — three Pythons and
Windows — runs on push, and nothing connects the two: a tag can be pushed at a
moment when the branch CI never finished, was cancelled, or failed, and the
release workflow would neither know nor care.

Cancelled is the case worth naming. A cancelled run is not a failure and not a
pass; it is a commit nobody judged, and it reads as a grey dot rather than a red
one. This project has no `concurrency` block, so nothing here cancels a run
automatically — but a person can, and the answer must be the same either way.

The gate is exercised through a stub `gh` so that these tests can put a
particular answer in front of it. What is asserted is the exit code, because
that is the whole of what the workflow reads.
"""
import json
import os
import subprocess
import sys

from conftest import ROOT

GATE = ROOT / "tools" / "check_ci_judged_this_commit.py"
SHA = "0123456789abcdef0123456789abcdef01234567"


def with_a_gh_that_says(tmp_path, runs, exit_code=0):
    """A `gh` on PATH that prints `runs` as JSON and exits `exit_code`."""
    stub = tmp_path / ("gh.bat" if os.name == "nt" else "gh")
    body = json.dumps(runs)
    if os.name == "nt":
        stub.write_text(f"@echo off\r\necho {body}\r\nexit /b {exit_code}\r\n")
    else:
        stub.write_text("#!/bin/sh\ncat <<'JSON'\n" + body
                        + f"\nJSON\nexit {exit_code}\n")
        stub.chmod(0o755)
    env = dict(os.environ, PATH=f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
               PYTHONDONTWRITEBYTECODE="1")
    return env


def ask(tmp_path, runs, exit_code=0, sha=SHA):
    env = with_a_gh_that_says(tmp_path, runs, exit_code)
    done = subprocess.run([sys.executable, str(GATE), "--commit", sha],
                          capture_output=True, text=True, env=env)
    return done.returncode, done.stdout + done.stderr


def test_a_completed_successful_run_is_a_judgement(tmp_path):
    code, said = ask(tmp_path, [{"databaseId": 1, "status": "completed",
                                 "conclusion": "success",
                                 "headSha": SHA, "workflowName": "check"}])
    assert code == 0, said


def test_no_run_at_all_is_a_refusal(tmp_path):
    """Absence is not consent. A tag pushed before CI started, or on a commit
    whose runs have been deleted, has not been judged."""
    code, said = ask(tmp_path, [])
    assert code != 0
    assert "no" in said.lower() and SHA[:7] in said, said


def test_a_cancelled_run_is_not_a_judgement(tmp_path):
    """The case this gate is named for: grey is not green."""
    code, said = ask(tmp_path, [{"databaseId": 1, "status": "completed",
                                 "conclusion": "cancelled",
                                 "headSha": SHA, "workflowName": "check"}])
    assert code != 0
    assert "cancelled" in said, said


def test_a_failed_run_is_not_a_judgement(tmp_path):
    code, said = ask(tmp_path, [{"databaseId": 1, "status": "completed",
                                 "conclusion": "failure",
                                 "headSha": SHA, "workflowName": "check"}])
    assert code != 0
    assert "failure" in said, said


def test_a_run_still_going_is_not_a_judgement(tmp_path):
    """It may yet pass. It has not, and a publish cannot be taken back."""
    code, said = ask(tmp_path, [{"databaseId": 1, "status": "in_progress",
                                 "conclusion": None,
                                 "headSha": SHA, "workflowName": "check"}])
    assert code != 0
    assert "in_progress" in said, said


def test_one_success_among_several_attempts_is_enough(tmp_path):
    """A re-run after a flake is how a red commit legitimately becomes green,
    and refusing on the presence of any failure would make a re-run useless."""
    code, said = ask(tmp_path, [
        {"databaseId": 1, "status": "completed", "conclusion": "failure",
         "headSha": SHA, "workflowName": "check"},
        {"databaseId": 2, "status": "completed", "conclusion": "success",
         "headSha": SHA, "workflowName": "check"},
    ])
    assert code == 0, said


def test_a_run_on_another_commit_does_not_count(tmp_path):
    """`--commit` is a filter this gate passes to `gh`, and a filter that is
    silently ignored would let yesterday's green stand in for today's. The
    answer is checked against the commit that was asked about."""
    other = "f" * 40
    code, said = ask(tmp_path, [{"databaseId": 1, "status": "completed",
                                 "conclusion": "success",
                                 "headSha": other, "workflowName": "check"}])
    assert code != 0
    assert other[:7] in said or SHA[:7] in said, said


def test_gh_failing_is_a_refusal_not_a_pass(tmp_path):
    """No answer is not a good answer. A missing `gh`, a token without
    `actions: read`, a rate limit — each one leaves this gate unable to tell,
    and unable to tell is the state in which it must not authorise a publish."""
    code, said = ask(tmp_path, [], exit_code=1)
    assert code != 0
    assert "could not ask" in said.lower(), said


def test_the_gate_is_wired_into_the_release_before_anything_is_published():
    """A gate that exists and is not called is a file, not a gate.

    This repository has found that shape more than once, so the assertion is
    not that the workflow mentions the script — it is that the step runs it,
    that it carries the token scope the script needs, and that it stands in the
    job that runs before the first upload. After the reader is published there
    is nothing left to refuse: PyPI does not take a version back.
    """
    import re

    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    jobs = text.split("\n  build-reader:", 1)
    assert len(jobs) == 2, "release.yml no longer starts its work in `build-reader`"
    first_job = jobs[1].split("\n  publish-reader:", 1)[0]

    assert "python tools/check_ci_judged_this_commit.py" in first_job, (
        "the release workflow does not ask whether CI judged this commit "
        "before it publishes anything")
    assert re.search(r"^\s+actions: read$", first_job, re.M), (
        "the step can run and cannot read run history, and a gate that cannot "
        "tell refuses — so the release would fail for a reason nobody wrote down")
    assert "GH_TOKEN" in first_job, (
        "`gh` with no token cannot ask, and this gate turns not-knowing into a "
        "refusal")

    # And in front of `make check`, not behind it: the cheap question about a
    # commit nobody judged should not wait on the expensive one.
    asked = first_job.index("check_ci_judged_this_commit.py")
    gate = first_job.index("run: make check")
    assert asked < gate, "the release runs the whole gate before asking whether it needs to"


def test_an_abbreviated_commit_is_named_as_the_reason(tmp_path):
    """GitHub's `--commit` filter matches the full forty characters.

    Measured against the real API: the short SHA a person copies out of `git
    log` returns nothing at all, and this gate then says the commit has not
    been judged — about a commit that has. The refusal is the safe direction
    and the wrong sentence, and this is the tool somebody reaches for when a
    release has just been refused. In the workflow it is `$GITHUB_SHA`, which
    is full, so nothing here is load-bearing for a release; it is load-bearing
    for the person trying to find out why one stopped.
    """
    code, said = ask(tmp_path, [], sha="b0db7e3")
    assert code != 0
    assert "40" in said and "b0db7e3" in said, said
