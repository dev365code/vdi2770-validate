"""CI runs what `make check` runs — and with the same versions.

Same command is not the same environment. That lesson cost a red build once
already, in the sibling project, so the version pins are asserted too.
"""
import re

from conftest import ROOT

MAKEFILE = (ROOT / "Makefile").read_text(encoding="utf-8")
CI = (ROOT / ".github" / "workflows" / "ci.yml")


def recipe_commands():
    out = []
    current = None
    for line in MAKEFILE.splitlines():
        if re.match(r"^[a-zA-Z0-9_-]+:", line):
            current = line.split(":")[0]
        elif line.startswith("\t") and current:
            out.append(line.strip())
    return out


def test_ci_runs_every_make_command():
    assert CI.exists(), "no CI workflow"
    ci = CI.read_text(encoding="utf-8")
    for cmd in recipe_commands():
        core = cmd.replace("$(PYTHON)", "python").strip()
        if core.startswith("rm "):
            continue
        assert core in ci or core.replace("python -m ", "") in ci, f"CI does not run: {core}"


def test_pinned_versions_match_pyproject():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for name in ("ruff", "pytest", "xmlschema"):
        m = re.search(rf"{name.upper()}_VERSION\s*:=\s*([0-9.]+)", MAKEFILE)
        assert m, f"Makefile does not pin {name}"
        assert f'{name}=={m.group(1)}' in pyproject, (
            f"{name} is pinned to {m.group(1)} in the Makefile but not in pyproject.toml")


def test_ci_actually_exercises_the_oldest_python_we_promise():
    """`requires-python` is a promise. The only way it stays true is if CI runs
    that interpreter — a dependency can quietly stop supporting it, which is
    exactly how this project once shipped a floor it could not install on."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    floor = re.search(r'requires-python\s*=\s*">=([0-9.]+)"', pyproject)
    assert floor, "pyproject declares no requires-python"
    ci = CI.read_text(encoding="utf-8")
    matrix = re.search(r"python-version:\s*\[(.*?)\]", ci)
    assert matrix, "CI declares no python-version matrix"
    versions = re.findall(r'"([0-9.]+)"', matrix.group(1))
    assert floor.group(1) in versions, (
        f"pyproject promises Python {floor.group(1)} but CI never runs it: {versions}")


def ci_commands():
    """The commands CI actually runs, not the text of the file.

    Searching the raw YAML for a command string passes when the step is
    commented out, which is one keystroke away from a CI that runs nothing.
    """
    out, in_block, indent = [], False, 0
    for raw in CI.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if in_block:
            if stripped and (len(raw) - len(raw.lstrip())) > indent:
                if not stripped.startswith("#"):
                    out.append(stripped.split("#")[0].strip())
                continue
            in_block = False
        m = re.match(r"^(\s*)-?\s*run:\s*(.*)$", raw)
        if m:
            indent = len(m.group(1))
            value = m.group(2).strip()
            if value in ("|", ">", "|-", ">-"):
                in_block = True
            elif value and not value.startswith("#"):
                out.append(value.split("#")[0].strip())
    return [c for c in out if c]


def test_ci_runs_the_command_not_merely_mentions_it():
    """A commented-out step used to satisfy the substring check."""
    commands = ci_commands()
    assert commands, "no run: steps found in the workflow"
    for cmd in recipe_commands():
        core = cmd.replace("$(PYTHON)", "python").strip()
        if core.startswith("rm "):
            continue
        assert any(core in c for c in commands), (
            f"CI never runs: {core}\n  it runs: {commands}")


def test_make_check_depends_on_every_gate():
    """`make check` is what a contributor runs. A target the Makefile defines but
    `check` does not depend on runs only in CI, which is how a green local tree
    pushed a red build: the sdist gate existed, and `check` never called it."""
    targets, prereqs = [], []
    for line in MAKEFILE.splitlines():
        m = re.match(r"^([a-zA-Z0-9_-]+):\s*(.*)$", line)
        if not m:
            continue
        targets.append(m.group(1))
        if m.group(1) == "check":
            prereqs = m.group(2).split()
    assert prereqs, "the Makefile has no `check` target"
    exempt = {"check", "clean"}
    missing = [t for t in targets if t not in exempt and t not in prereqs]
    assert not missing, (
        f"`make check` does not run: {missing}. Either add them, or add them to the "
        f"exemption above with a reason.")


def test_the_sdk_in_this_repository_satisfies_the_pin_that_depends_on_it():
    """Two packages in one repository, and the second declares a version range
    for the first. Nothing checked that the copy sitting right here satisfies it.

    It cost a broken install already: bumping the reader to `0.3.0.dev0` while the
    validator asked for `vdi2770~=0.3.0` sent pip to PyPI, because a pre-release
    does not satisfy a compatible-release specifier. Locally and in CI the reader
    is installed from the working tree, so the pin has to accept what is there.
    """
    from packaging.requirements import Requirement
    from packaging.version import Version

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    deps = re.search(r"^dependencies = \[(.*?)\]", pyproject, re.M | re.S)
    assert deps, "the validator declares no dependencies"
    pin = next((Requirement(m) for m in re.findall(r'"([^"]+)"', deps.group(1))
                if Requirement(m).name == "vdi2770"), None)
    assert pin is not None, "the validator no longer depends on the reader"

    sdk = (ROOT / "packages" / "vdi2770" / "pyproject.toml").read_text(encoding="utf-8")
    here = Version(re.search(r'^version = "([^"]+)"', sdk, re.M).group(1))

    assert pin.specifier.contains(here, prereleases=here.is_prerelease), (
        f"the reader in this repository is {here} and the validator asks for "
        f"{pin}. `pip install -e .` will go to PyPI and fail.")
