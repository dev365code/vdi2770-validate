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
