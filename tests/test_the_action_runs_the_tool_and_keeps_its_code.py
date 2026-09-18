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
    ran = [body for body in _run_bodies(action) if re.search(r'set -- "\$PY" "\$PYZ" check', body)
           and re.search(r'set -- "\$PY" -m vdi2770_validate check', body)]
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
    body = next(b for b in _run_bodies(action) if '"$@" || rc=$?' in b)
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


def test_no_expression_at_all_is_interpolated_into_a_shell_script(action):
    """`${{ inputs.paths }}` inside a `run:` makes a container name a place to
    put commands. Inputs travel as environment variables and are quoted where
    they are used -- so a file called `; rm -rf /` is a file, not a sentence.

    The rule is not "no inputs" but "no expressions": `github.event.*` carries
    text strangers write, and this test used to look only for `inputs.`, which
    is narrower than the sentence above it claims.
    """
    offenders = [body for body in _run_bodies(action) if "${{" in body]
    assert not offenders, (
        "an expression is interpolated into a script rather than passed through "
        f"env: {offenders}")


def test_the_workflow_only_interpolates_things_it_wrote_itself():
    """The same rule where this repository uses the action. `steps.*.outcome`
    and the action's own outputs are ours; anything from `github.event` is a
    stranger's text and has no business in a shell."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    allowed = re.compile(r"^steps\.[\w-]+\.(outcome|outputs\.[\w-]+)$")
    bad = []
    for name, job in workflow["jobs"].items():
        if not name.startswith("the-action"):
            continue
        for step in job["steps"]:
            for expr in re.findall(r"\$\{\{\s*([^}]+?)\s*\}\}", step.get("run", "")):
                if not allowed.match(expr):
                    bad.append((name, expr))
    assert not bad, f"a shell in the action's job interpolates something else: {bad}"


def test_only_the_install_step_can_reach_an_index(action):
    """The tool opens no socket for any input. The action may install the
    checker -- once, and only when it was not handed a file -- and nothing else
    here is allowed to make that promise smaller."""
    reaching = [s for s in action["runs"]["steps"]
                if "run" in s and re.search(r"\bcurl\b|\bwget\b|pip install", s["run"])]
    assert len(reaching) == 1 and reaching[0].get("id") == "obtain", (
        f"more than the install step reaches out: {[s.get('id') for s in reaching]}")
    assert reaching[0].get("if") == "inputs.pyz == ''", (
        "the install runs even when the caller supplied the file, which is the one "
        "thing carrying your own copy is supposed to avoid")


def test_the_default_path_takes_the_release_from_the_index(action):
    """Release assets are attached by a person, and a person can forget -- two
    of this repository's own releases carry none. Publishing to the index is
    what the release workflow does by itself, so that is what the action leans
    on; `pyz:` remains for a runner that cannot reach an index at all."""
    install = next(s for s in action["runs"]["steps"] if s.get("id") == "obtain")
    assert "pip install" in install["run"]
    assert "vdi2770-validate==$version" in install["run"], (
        "the install does not pin the version it resolved")
    assert "--only-binary" in install["run"], (
        "a source build on somebody else's runner is not this action's to ask for")
    assert "--target" in install["run"], (
        "installing into the caller's environment changes a machine this action "
        "does not own")
    assert "releases/download" not in ACTION.read_text(encoding="utf-8"), (
        "the default path is back on a release asset, which is the dependency "
        "this design removed")


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
    body = next(b for b in _run_bodies(action) if '"$@" || rc=$?' in b)
    guard = body.split('set -- "$PY" "$PYZ" check')[0]
    assert '! -f "$PYZ"' in guard, "nothing checks that the checker is actually there"
    assert "exit 64" in guard, "a missing file does not come back as a usage error"


def test_a_carried_file_can_be_pinned_to_a_hash(action):
    """The default path is an index, and `pip` checks what an index serves. What
    is left unchecked is a file somebody carried in by hand, so the input that
    checks *that* stays."""
    assert "sha256" in action["inputs"], "there is no way to pin a file carried in"

    checking = next(b for b in _run_bodies(action) if "WANT_SHA" in b)
    assert "sha256sum" in checking or "shasum" in checking, (
        "the hash input exists and nothing checks it")


def test_the_checker_is_allowed_to_fail_without_ending_the_step(action):
    """GitHub runs `shell: bash` with `-e` already set.

    A bare `python ... check` that exits non-zero therefore ends the step where
    it stands, and every line after it -- the output, the branch, the message --
    is never reached. The first version of this action was written as though
    `set -uo pipefail` decided that, and CI failed twice before the flags in
    GitHub's own invocation line explained why.
    """
    body = next(b for b in _run_bodies(action) if '"$@" || rc=$?' in b)
    call = next(line for line in body.splitlines() if line.strip().startswith('"$@"'))
    assert call.rstrip().endswith("|| rc=$?"), (
        f"the checker is called in a way errexit would end the step on: {call!r}")
    assert "rc=0" in body.split(call)[0], "rc is read before it is ever set"
