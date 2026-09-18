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
    container has a finding" (1) and "your workflow is misspelt" (64). The code
    is published as an output and re-raised as the step's own status."""
    body = next(b for b in _run_bodies(action) if 'python "$PYZ" check' in b)
    assert 'exit-code=$rc' in body, "the code is not published as an output"
    assert re.search(r'exit "\$rc"', body), "the code is computed and then thrown away"
    assert action["outputs"]["exit-code"]["value"] == "${{ steps.check.outputs.exit-code }}"


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


def test_every_input_is_described_where_a_user_would_look(action):
    """The front page is where somebody decides whether to use this. An input
    that exists only in `action.yml` is an input nobody knows about."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Three doors")[-1] if "## Three doors" in readme else readme
    missing = [name for name in action["inputs"] if name not in section]
    assert not missing, f"README does not mention the action's inputs: {missing}"
