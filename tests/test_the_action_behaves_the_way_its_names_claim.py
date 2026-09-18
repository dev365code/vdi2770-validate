"""Run the action's own shell, the way GitHub runs it, and read what happens.

Every other test of this action parses YAML and matches strings, and the suite
stayed green through two red CI runs: `set -uo pipefail` does not clear the `-e`
that `shell: bash` already carries, so a non-zero verdict ended the step before
the line that publishes the code. Reading the file could not see that. Running
it can.

The stub is a fake `python` that exits a chosen code, so no container is checked
here and nothing is slow. What is under test is the step's arithmetic: what it
publishes, and what status it leaves behind, for each code the tool can return
and each mode the caller can ask for.
"""
import os
import pathlib
import shutil
import subprocess

import pytest
import yaml

from conftest import ROOT

ACTION = ROOT / "action.yml"
# The invocation GitHub prints in its own logs. Recorded here rather than
# guessed: the flags are the whole reason this file exists.
BASH = shutil.which("bash") or "/bin/bash"
GITHUB_BASH = [BASH, "--noprofile", "--norc", "-e", "-o", "pipefail"]


def _check_step():
    action = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
    return next(s for s in action["runs"]["steps"] if s.get("id") == "check")


def _check_step_body():
    return _check_step()["run"]


def _declared_env():
    """Every variable the step declares, empty by default.

    GitHub defines all of them -- an input nobody passed arrives as an empty
    string, not as an absent name -- and the step runs under `set -u`. A harness
    that sets only the interesting ones tests a shell nobody will ever run, and
    this one did: three tests failed on `WANT_SHA: unbound variable` the moment
    the action grew an input.
    """
    return dict.fromkeys(_check_step().get("env", {}), "")


def _run(tmp_path, exit_code, fail_on_finding="true", pyz=None, paths="a.zip"):
    """The `check` step, with a stub interpreter and this action's own env."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    # Both names: the action asks for `python3` first and falls back to
    # `python`, the way a runner without `actions/setup-python` forces it to.
    for name in ("python3", "python"):
        stub = stub_dir / name
        stub.write_text(f'#!/bin/sh\nprintf "stub ran: %s\\n" "$*"\nexit {exit_code}\n', encoding="utf-8")
        stub.chmod(0o755)

    checker = pyz
    if checker is None:
        checker = tmp_path / "vdi2770.pyz"
        checker.write_text("not really a zipapp; the stub never reads it", encoding="utf-8")

    script = tmp_path / "step.sh"
    script.write_text(_check_step_body(), encoding="utf-8")
    output = tmp_path / "GITHUB_OUTPUT"
    output.write_text("", encoding="utf-8")

    env = dict(os.environ)
    env.update(_declared_env())
    env.update({
        "PATH": f"{stub_dir}:{os.environ['PATH']}",
        "PYZ": str(checker),
        "PATHS": paths,
        "FAIL_ON_FINDING": fail_on_finding,
        "GITHUB_OUTPUT": str(output),
    })
    done = subprocess.run([*GITHUB_BASH, str(script)], capture_output=True, text=True, env=env)
    published = dict(
        line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines() if "=" in line
    )
    return done.returncode, published.get("exit-code"), done.stdout + done.stderr


@pytest.mark.parametrize("code", [0, 1, 2, 3, 64])
def test_a_verdict_is_published_and_the_gate_fails_on_it(tmp_path, code):
    """Whatever the checker returns, the code is written down; the step's own
    status is that code, because the default is a gate."""
    status, published, _ = _run(tmp_path, code)
    assert published == str(code), f"the code the tool returned was not published for {code}"
    assert status == code, f"the gate returned {status} for a checker that returned {code}"


@pytest.mark.parametrize("code", [0, 1, 2, 3, 64])
def test_asked_not_to_fail_it_succeeds_and_still_says_what_happened(tmp_path, code):
    status, published, _ = _run(tmp_path, code, fail_on_finding="false")
    assert published == str(code)
    assert status == 0, f"fail-on-finding:false still failed the step with {status}"


def test_a_checker_that_never_ran_is_not_reported_as_a_verdict(tmp_path):
    """127 is "no python here", not "your container has a finding".

    In report mode this was the worst of the two: the step succeeded, and a job
    gating on step status passed a run in which nothing was checked.
    """
    status, published, log = _run(tmp_path, 127, fail_on_finding="false")
    assert status != 0, (
        f"a run where the checker never executed came back as success "
        f"(published {published!r}): {log[-400:]}")
    assert "not a verdict" in log, "nothing says this was not a judgement on the container"


def test_a_missing_checker_is_a_usage_error_before_python_is_asked(tmp_path):
    status, published, log = _run(tmp_path, 0, pyz=tmp_path / "nowhere.pyz")
    assert status == 64, f"a missing checker came back as {status}, not a usage error"
    assert published is None, "a run that never happened published a verdict"


def _argv_from(tmp_path, paths):
    """What the tool was actually handed, for a given `paths` input."""
    stub_seen = tmp_path / "argv.txt"
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    for name in ("python3", "python"):
        stub = stub_dir / name
        stub.write_text(
            '#!/bin/sh\n: > "$ARGV_FILE"\nfor a in "$@"; do printf "%s\\n" "$a" >> "$ARGV_FILE"; done\nexit 0\n',
            encoding="utf-8")
        stub.chmod(0o755)
    checker = tmp_path / "vdi2770.pyz"
    checker.write_text("stub", encoding="utf-8")
    script = tmp_path / "step.sh"
    script.write_text(_check_step_body(), encoding="utf-8")
    output = tmp_path / "GITHUB_OUTPUT"
    output.write_text("", encoding="utf-8")
    env = dict(os.environ)
    env.update(_declared_env())
    env.update({
        "PATH": f"{stub_dir}:{os.environ['PATH']}", "PYZ": str(checker),
        "PATHS": paths, "FAIL_ON_FINDING": "true",
        "GITHUB_OUTPUT": str(output), "ARGV_FILE": str(stub_seen),
    })
    subprocess.run([*GITHUB_BASH, str(script)], capture_output=True, text=True, env=env)
    argv = stub_seen.read_text(encoding="utf-8").splitlines() if stub_seen.exists() else []
    return argv[2:] if len(argv) > 2 else []          # past the zipapp and `check`


def test_a_path_with_a_space_in_it_can_be_named(tmp_path):
    """"Separated by spaces" cannot mean a directory name may not contain one.

    Written on one line, `paths` splits on spaces -- that is what the input has
    always promised and workflows rely on it. Written as a YAML block, it is one
    container per line, which is the only way to name `/my containers/a.zip` at
    all. Before that, it reached the tool as two arguments and came back as exit
    2, "nothing could be read": the caller's directory name, reported as the
    supplier's archive being unreadable.
    """
    one_per_line = "/my containers/a.zip\n/plain/b.zip\n"
    assert _argv_from(tmp_path, one_per_line) == ["/my containers/a.zip", "/plain/b.zip"]


def test_one_line_still_means_space_separated(tmp_path):
    """The documented form, unchanged: two names on one line are two paths."""
    assert _argv_from(tmp_path, "a.zip b.zip") == ["a.zip", "b.zip"]


def test_a_container_named_like_a_pattern_is_not_expanded(tmp_path):
    """`a[1].zip` is a filename somebody's scanner produced, not a glob. Left to
    the shell it either matched something else or vanished."""
    assert _argv_from(tmp_path, "a[1].zip") == ["a[1].zip"]


def test_the_stub_really_is_what_ran(tmp_path):
    """The premise: if `python` resolved to a real interpreter, every assertion
    above would be measuring something else."""
    _, _, log = _run(tmp_path, 3)
    assert "stub ran:" in log, log[-300:]
    # The file, not `shutil.which`: on Windows that asks for an extension a
    # shell script does not have, and the CI row there failed on the premise
    # while the thing it was a premise for had worked.
    assert (tmp_path / "bin" / "python3").exists(), "the stub was never written"


def test_a_runner_with_no_python_is_told_so(tmp_path):
    """macOS runners ship no bare `python`, and `python3` only through
    `actions/setup-python`. Without this the step reached `exit 127`, which the
    code table above would have been asked to call a verdict."""
    empty = tmp_path / "empty-path"
    empty.mkdir()
    checker = tmp_path / "vdi2770.pyz"
    checker.write_text("stub", encoding="utf-8")
    script = tmp_path / "step.sh"
    script.write_text(_check_step_body(), encoding="utf-8")
    output = tmp_path / "GITHUB_OUTPUT"
    output.write_text("", encoding="utf-8")
    env = dict(os.environ)
    env.update(_declared_env())
    env.update({"PATH": str(empty), "PYZ": str(checker), "PATHS": "a.zip",
                "FAIL_ON_FINDING": "true", "GITHUB_OUTPUT": str(output)})
    done = subprocess.run([*GITHUB_BASH, str(script)], capture_output=True, text=True, env=env)
    assert done.returncode == 64, f"no interpreter came back as {done.returncode}"
    assert "no python on PATH" in done.stdout + done.stderr


def test_the_exit_codes_the_action_publishes_are_the_ones_the_tool_defines():
    """`action.yml` writes the contract out for a reader, and `cli.py` owns it.

    Two hand-written copies of one table drift, and nothing here would have
    noticed: this is the test that notices.
    """
    import re as _re
    described = pathlib.Path(ACTION).read_text(encoding="utf-8")
    block = described.split("exit-code:", 1)[1].split("value:", 1)[0]
    in_docs = {int(n) for n in _re.findall(r"\b(\d+)\b", block)}
    cli = (ROOT / "packages" / "vdi2770" / "src" / "vdi2770" / "validate" / "cli.py").read_text(encoding="utf-8")
    table = cli.split("EXIT_CODES", 1)[1].split('"""', 2)[1] if '"""' in cli.split("EXIT_CODES", 1)[1][:200] else cli.split("EXIT_CODES", 1)[1][:800]
    in_cli = {int(n) for n in _re.findall(r"^\s*(\d+)\s", table, _re.M)}
    assert in_cli, "could not read the tool's own exit-code table"
    assert in_cli <= in_docs, (
        f"the tool defines exit codes the action does not describe: {sorted(in_cli - in_docs)}")


def _run_installed(tmp_path, target, exit_code=0):
    """The default door: nothing carried in, something installed instead."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    argv_file = tmp_path / "argv.txt"
    for name in ("python3", "python"):
        stub = stub_dir / name
        stub.write_text(
            '#!/bin/sh\n: > "$ARGV_FILE"\nfor a in "$@"; do printf "%s\\n" "$a" >> "$ARGV_FILE"; done\n'
            f'printf "PYTHONPATH=%s\\n" "${{PYTHONPATH:-}}" >> "$ARGV_FILE"\nexit {exit_code}\n',
            encoding="utf-8")
        stub.chmod(0o755)
    script = tmp_path / "step.sh"
    script.write_text(_check_step_body(), encoding="utf-8")
    output = tmp_path / "GITHUB_OUTPUT"
    output.write_text("", encoding="utf-8")
    env = dict(os.environ)
    env.update(_declared_env())
    env.update({"PATH": f"{stub_dir}:{os.environ['PATH']}", "PYZ": "", "TARGET": str(target),
                "PATHS": "a.zip", "FAIL_ON_FINDING": "true",
                "GITHUB_OUTPUT": str(output), "ARGV_FILE": str(argv_file)})
    done = subprocess.run([*GITHUB_BASH, str(script)], capture_output=True, text=True, env=env)
    seen = argv_file.read_text(encoding="utf-8").splitlines() if argv_file.exists() else []
    return done.returncode, seen, done.stdout + done.stderr


def test_the_default_door_runs_what_was_installed(tmp_path):
    """No `pyz:` means the released distribution, run out of the directory the
    install step left it in -- and the caller's own environment untouched, which
    is why it is `--target` and `PYTHONPATH` rather than a plain install."""
    target = tmp_path / "installed"
    target.mkdir()
    status, argv, log = _run_installed(tmp_path, target)
    assert status == 0, log[-300:]
    assert argv[:3] == ["-m", "vdi2770_validate", "check"], argv
    assert f"PYTHONPATH={target}" in argv, argv


def test_nothing_installed_is_a_usage_error_not_a_verdict(tmp_path):
    """If the install step left nothing behind, there is no checker -- and a
    step that reported that as a finding would be blaming a container for it."""
    status, _, log = _run_installed(tmp_path, tmp_path / "never-made")
    assert status == 64, f"came back as {status}"
    assert "nothing was installed" in log


def test_a_carried_file_can_be_held_to_a_hash(tmp_path):
    """The reason `sha256:` still exists once the default path is an index: a
    file carried into a closed network is checked by somebody, or by nobody."""
    checker = tmp_path / "vdi2770.pyz"
    checker.write_bytes(b"not the file you were promised")
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    for name in ("python3", "python"):
        stub = stub_dir / name
        stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)
    script = tmp_path / "step.sh"
    script.write_text(_check_step_body(), encoding="utf-8")
    output = tmp_path / "GITHUB_OUTPUT"
    output.write_text("", encoding="utf-8")
    env = dict(os.environ)
    env.update(_declared_env())
    env.update({"PATH": f"{stub_dir}:{os.environ['PATH']}", "PYZ": str(checker),
                "WANT_SHA": "0" * 64, "PATHS": "a.zip", "FAIL_ON_FINDING": "true",
                "GITHUB_OUTPUT": str(output)})
    done = subprocess.run([*GITHUB_BASH, str(script)], capture_output=True, text=True, env=env)
    assert done.returncode == 64, f"a file that is not what was asked for came back as {done.returncode}"
    assert "hashes to" in done.stdout + done.stderr
