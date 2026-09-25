"""The reference implementation is pinned, and something says when it moves.

The corpus is copied from the reference repository at one commit and the oracle
runs the reference at that commit. A pin cannot move, which is what makes a
comparison against it mean anything; it also means nothing notices when the
reference does. `tools/upstream.py` asks, every Monday, from
`.github/workflows/upstream.yml`. What is held here is the deciding, from what
`git ls-remote` prints -- no socket is opened -- and that the question is asked
about the pin the corpus and the oracle actually use.
"""
import importlib.util
import json
import re

import pytest
import yaml

from conftest import ROOT

PINNED = "e47c13c1925abc3ed4698cb5ed9e73b5eb544353"


def _tool():
    spec = importlib.util.spec_from_file_location("upstream", ROOT / "tools" / "upstream.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_default_branch_at_the_pin_has_not_moved():
    listing = f"ref: refs/heads/develop\tHEAD\n{PINNED}\tHEAD\n"
    assert _tool().verdict(listing, PINNED) is None


def test_a_default_branch_anywhere_else_has_and_says_where():
    elsewhere = "1" * 40
    said = _tool().verdict(f"ref: refs/heads/develop\tHEAD\n{elsewhere}\tHEAD\n", PINNED)
    assert said is not None, "a default branch past the pin was read as not moved"
    assert elsewhere in said and PINNED in said and "develop" in said, said


def test_no_answer_is_not_read_as_no_move():
    """A repository that answered with nothing, or with an error page, has not
    said the reference stayed put."""
    with pytest.raises(SystemExit):
        _tool().verdict("", PINNED)


def test_the_question_is_about_the_pin_the_corpus_and_the_oracle_use():
    """Three places name the commit -- the corpus manifest, the oracle workflow,
    and the question asked each week -- and a week that asks about the wrong one
    answers a question nobody has."""
    repo, pinned = _tool().pin()
    upstream = json.loads((ROOT / "corpus" / "MANIFEST.json").read_text(encoding="utf-8"))["_upstream"]
    oracle = (ROOT / ".github" / "workflows" / "oracle.yml").read_text(encoding="utf-8")
    assert (repo, pinned) == (upstream["repo"], upstream["commit"])
    assert re.search(rf"REFERENCE_COMMIT: {pinned}\b", oracle), (
        "the oracle runs the reference at a commit other than the one the corpus "
        "was copied at")


def test_a_moved_reference_is_a_red_run(monkeypatch):
    """A default branch past the pin exits 1 -- the run the week turns red for."""
    import subprocess

    tool = _tool()
    moved = subprocess.CompletedProcess(
        args=[], returncode=0, stderr="",
        stdout=f"ref: refs/heads/develop\tHEAD\n{'1' * 40}\tHEAD\n")
    monkeypatch.setattr(tool.subprocess, "run", lambda *a, **k: moved)
    assert tool.main() == 1


def test_an_unanswered_question_is_not_a_move(monkeypatch):
    """No answer from the reference's repository exits 2, not 1: a red run that
    means "moved" and a red run that means "nobody answered" call for different
    things, and read as one they teach a reader to ignore both."""
    import subprocess

    tool = _tool()
    silent = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    monkeypatch.setattr(tool.subprocess, "run", lambda *a, **k: silent)
    assert tool.main() == 2

    def hangs(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=300)
    monkeypatch.setattr(tool.subprocess, "run", hangs)
    assert tool.main() == 2, "a question that timed out is reported as a move"


#: A day of the week as cron writes it: a number from 0 to 6, the range GitHub's
#: own table of the syntax gives, or the day's three-letter name.
WEEKDAY = re.compile(r"[0-6]|(?i:mon|tue|wed|thu|fri|sat|sun)")


def test_a_question_that_could_not_be_asked_is_not_a_move(monkeypatch):
    """The repository refusing, and no `git` to ask with, are exit 2 like no
    answer at all: neither says anything about where the reference is."""
    import subprocess

    tool = _tool()
    refused = subprocess.CompletedProcess(args=[], returncode=128, stdout="",
                                          stderr="fatal: unable to access the repository")
    monkeypatch.setattr(tool.subprocess, "run", lambda *a, **k: refused)
    assert tool.main() == 2

    def no_git(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "git")
    monkeypatch.setattr(tool.subprocess, "run", no_git)
    assert tool.main() == 2


def test_the_question_is_asked_every_week():
    """A schedule that fires monthly, or never, would leave the front page's
    "checked weekly" standing on a workflow file that does not. Read as GitHub
    reads it, as YAML: commenting the schedule out -- the usual way to silence a
    workflow -- leaves no schedule, and a comment at the end of a line, quotes
    of either kind or a step's name change nothing, where a reading of the
    file's lines took comments for configuration and quotes for a missing
    schedule."""
    flow = yaml.safe_load((ROOT / ".github" / "workflows" / "upstream.yml").read_text(encoding="utf-8"))
    triggers = flow.get("on", flow.get(True)) or {}
    schedules = (triggers.get("schedule") or []) if isinstance(triggers, dict) else []
    crons = [s.get("cron", "") for s in schedules if isinstance(s, dict)]
    assert len(crons) == 1, f"the workflow has {len(crons)} schedules"
    fields = crons[0].split()
    assert len(fields) == 5, f"the schedule {crons[0]!r} is not a cron line"
    minute, hour, day, month, weekday = fields
    assert (day, month) == ("*", "*") and WEEKDAY.fullmatch(weekday), (
        f"the schedule {crons[0]!r} is not once a week")
    assert minute.isdigit() and int(minute) < 60 and hour.isdigit() and int(hour) < 24, (
        f"the schedule {crons[0]!r} does not name one minute of one hour")
    jobs = flow.get("jobs") or {}
    assert all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", str(name)) for name in jobs), (
        f"a job id GitHub does not accept: {sorted(jobs)}")
    def asks(step):
        return str(step.get("run", "")).strip() == "python tools/upstream.py"

    # The job that asks and every job it needs first: what has to run for the
    # question to be asked. A job that follows it -- one that sends word when
    # it fails, say -- may carry a condition of its own.
    chain = {name for name, job in jobs.items() if any(asks(s) for s in job.get("steps") or [])}
    assert chain, "the weekly workflow does not run the tool that asks"
    waiting = list(chain)
    while waiting:
        needs = jobs.get(waiting.pop(), {}).get("needs") or []
        for name in [needs] if isinstance(needs, str) else needs:
            if name not in chain:
                chain.add(name)
                waiting.append(name)
    before = [jobs[name] for name in sorted(chain) if name in jobs]
    asking = [step for job in before for step in job.get("steps") or [] if asks(step)]
    assert not any(job.get("continue-on-error") for job in before) and not any(
        step.get("continue-on-error") for step in asking), (
        "a job or step allowed to fail would turn a move into a green run")
    # A job or step skipped by a condition is reported as a success, so a
    # condition that is false on the schedule -- or always -- is a green week
    # whatever the reference did.
    assert not any("if" in job for job in before) and not any("if" in step for step in asking), (
        "a condition on the job or the step that asks can skip it, and a skipped "
        "job is reported as a success")
