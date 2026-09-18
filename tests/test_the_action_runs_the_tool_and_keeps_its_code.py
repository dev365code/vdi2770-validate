"""The action is a door, not a second implementation.

One engine, several entrances: a terminal, an import, a single file, and now a
workflow step. An entrance earns its place by passing the same verdict through
unchanged -- so what this file holds it to is that it runs the tool, hands the
tool the user's arguments without letting them become commands, and returns the
code the tool returned rather than a flattened success or failure.
"""
import re

import pytest
import yaml

from conftest import ROOT

ACTION = ROOT / "action.yml"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def action():
    return yaml.safe_load(ACTION.read_text(encoding="utf-8"))


def _run_bodies(action):
    return [s["run"] for s in action["runs"]["steps"] if "run" in s]


def test_the_action_runs_the_single_file(action):
    assert action["runs"]["using"] == "composite"
    ran = [body for body in _run_bodies(action) if re.search(r'python "\$PYZ" check', body)]
    assert ran, "no step runs the checker; the action would be a door onto nothing"


def test_the_exit_code_reaches_the_job(action):
    """A step that returns success or failure loses the difference between "your
    container has a finding" (1) and "your workflow is misspelt" (64).

    It cannot be had both ways at once, and CI is what said so: with the step
    failing, `steps.<id>.outputs.exit-code` came back empty, because GitHub
    publishes no outputs for a step it has decided failed. So the action does
    one or the other on purpose -- fail with the code, or succeed and hand it
    over -- and the code is written to the output before either branch, so the
    log has it even when the job cannot.
    """
    body = next(b for b in _run_bodies(action) if 'python "$PYZ" check' in b)
    assert 'exit-code=$rc' in body, "the code is not published as an output"
    assert re.search(r'exit "\$rc"', body), "the code is computed and then thrown away"
    assert action["outputs"]["exit-code"]["value"] == "${{ steps.check.outputs.exit-code }}"
    assert "fail-on-finding" in action["inputs"], "there is no way to ask for the code"
    written, branched = body.index("exit-code=$rc"), body.index("fail-on-finding is false")
    assert written < branched, (
        "the code is written after the branch that can end the step, so the one "
        "case that needs it most -- a failure -- would not have it")


def test_the_gate_is_the_default(action):
    """An action that reports and does not stop anything is decoration. Somebody
    who wants the reading asks for it; somebody who wants the gate types nothing.
    """
    assert str(action["inputs"]["fail-on-finding"]["default"]).lower() == "true"


def test_no_user_input_is_interpolated_into_a_shell_script(action):
    """`${{ inputs.paths }}` inside a `run:` makes a container name a place to
    put commands. Inputs travel as environment variables and are quoted where
    they are used -- so a file called `; rm -rf /` is a file, not a sentence."""
    offenders = [body for body in _run_bodies(action) if re.search(r"\$\{\{\s*inputs\.", body)]
    assert not offenders, (
        "an input is interpolated into a script rather than passed through env: "
        f"{offenders}")


def test_only_the_fetch_step_can_reach_the_network(action):
    """The tool opens no socket for any input. The action may fetch the file it
    runs -- once, and only when it was not handed one -- and nothing else here
    is allowed to make that promise smaller."""
    reaching = [s for s in action["runs"]["steps"]
                if "run" in s and re.search(r"\bcurl\b|\bwget\b|pip install", s["run"])]
    assert len(reaching) == 1 and reaching[0].get("id") == "fetch", (
        f"more than the fetch step touches the network: {[s.get('id') for s in reaching]}")
    assert reaching[0].get("if") == "inputs.pyz == ''", (
        "the fetch runs even when the caller supplied the file, which is the one "
        "thing carrying your own copy is supposed to avoid")


def test_the_repository_uses_its_own_action_both_ways(action):
    """An action nobody runs is a README section. This repository runs it on
    every push: once with a file it built (no network), once against a release
    it fetches, and once on a container that must fail."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"].get("the-action-this-repo-offers")
    assert job, "ci.yml no longer exercises the action"
    uses = [s for s in job["steps"] if s.get("uses") == "./"]
    assert len(uses) >= 3, f"the action is used {len(uses)} times; both paths and a failure are three"
    assert any("pyz" in s.get("with", {}) for s in uses), "the offline path is never taken"
    assert any("version" in s.get("with", {}) for s in uses), "the fetching path is never taken"
    failing = [s for s in uses if s.get("continue-on-error")]
    assert failing, "nothing checks that a container with findings fails the step"
    reporting = [s for s in uses if str(s.get("with", {}).get("fail-on-finding", "")).lower() == "false"]
    assert reporting, (
        "the mode that hands back the code is never exercised, and it is the mode "
        "whose behaviour GitHub -- not this repository -- decides")


def test_every_input_is_described_where_a_user_would_look(action):
    """The front page is where somebody decides whether to use this. An input
    that exists only in `action.yml` is an input nobody knows about."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    # Split on the section, and *fail* when the marker is gone rather than
    # falling back to the whole page. The fallback was live for an hour: the
    # heading became "Four doors" in the same commit that wrote this, so the
    # test searched the entire README and passed on words that happen to appear
    # elsewhere. A gate with a fallback is a gate with an off switch.
    marker = "### In a workflow"
    assert marker in readme, f"README no longer has a {marker!r} section for the action"
    section = readme.split(marker, 1)[1].split("\n## ", 1)[0]
    missing = [name for name in action["inputs"] if name not in section]
    assert not missing, f"the action's own section does not mention: {missing}"


def test_a_missing_checker_is_the_callers_mistake_and_says_so(action):
    """`pyz: dist/typo.pyz` must not come back as "nothing could be read".

    CPython exits 2 when it cannot open the file it was given, and 2 is this
    tool's code for a container it could not read at all -- so a typo in the
    workflow would be reported as the supplier's archive being unreadable. The
    step checks the file is there and exits 64, the code for "you typed it
    wrong", before python is asked.
    """
    body = next(b for b in _run_bodies(action) if 'python "$PYZ" check' in b)
    guard = body.split('python "$PYZ" check')[0]
    assert '! -f "$PYZ"' in guard, "nothing checks that the checker is actually there"
    assert "exit 64" in guard, "a missing file does not come back as a usage error"


def test_an_unverified_download_is_admitted_out_loud(action):
    """This project refuses to run a third-party action from a tag. It cannot
    then hand its own users an unverified executable and say nothing: either the
    caller passes the hash the release prints, or the step says it did not check.
    """
    assert "sha256" in action["inputs"], "there is no way to pin what gets downloaded"
    fetch = next(s for s in action["runs"]["steps"] if s.get("id") == "fetch")
    assert "WANT_SHA" in fetch["run"] and "hashlib.sha256" in fetch["run"], (
        "the hash input exists and nothing checks it")
    assert "without checking a hash" in fetch["run"], (
        "a run that verified nothing has to say so where somebody reads it")


def test_the_checker_is_allowed_to_fail_without_ending_the_step(action):
    """GitHub runs `shell: bash` with `-e` already set.

    A bare `python ... check` that exits non-zero therefore ends the step where
    it stands, and every line after it -- the output, the branch, the message --
    is never reached. The first version of this action was written as though
    `set -uo pipefail` decided that, and CI failed twice before the flags in
    GitHub's own invocation line explained why.
    """
    body = next(b for b in _run_bodies(action) if 'python "$PYZ" check' in b)
    call = next(line for line in body.splitlines() if 'python "$PYZ" check' in line)
    assert call.rstrip().endswith("|| rc=$?"), (
        f"the checker is called in a way errexit would end the step on: {call!r}")
    assert "rc=0" in body.split(call)[0], "rc is read before it is ever set"
