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
