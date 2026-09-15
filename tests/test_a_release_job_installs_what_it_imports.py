"""Every release job installs what the scripts it runs import.

The miss that turned a tag red was exactly this: `upgrade-gate` ran a tool that
imports `packaging` at module level and installed nothing, so it died on the one
interpreter `setup-python` gives -- fresh, without `packaging`. `make check` and
`ci.yml` were green because they install `.[dev]`, which carries it; the job that
runs on a tag does not. A test that checks imports against a manifest cannot see
this -- the distribution is declared, just not installed in that job. So this
reads the workflow and checks each job against the code it actually runs.

The `.[dev]` extra is expanded from the manifest rather than listed here, so a
distribution moving in or out of it stays in one place. `make` targets are out
of scope: the job that runs `make check` installs `.[dev]`, and modelling every
target's needs would be a second copy of the Makefile.
"""
import ast
import re
import sys

import yaml

from conftest import ROOT

RELEASE = ROOT / ".github" / "workflows" / "release.yml"
FIRST_PARTY = {"vdi2770", "vdi2770_validate"}
#: import name -> distribution, where the two differ.
DISTRIBUTION = {"yaml": "PyYAML"}
#: `python -m X` forms that need a third-party distribution named X.
DASH_M = {"build", "pytest", "ruff"}


def _dev_extra():
    """Distributions `pip install .[dev]` makes importable (the root extra)."""
    block = re.search(r"^dev\s*=\s*\[(.*?)\]",
                      (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
                      re.M | re.S)
    if not block:
        return set()
    return {re.split(r"[<>=!~;\[\s]", s)[0].strip()
            for s in re.findall(r'"([^"]+)"', block.group(1))}


def _installed(run_text):
    """Distributions a job's `pip install` lines make importable."""
    dev, got = _dev_extra(), set()
    for line in re.findall(r"pip install\s+([^\n]*)", run_text):
        for raw in line.split():
            tok = raw.strip("\"'")
            if tok in ("-e", "-U", "--upgrade", "pip") or tok.startswith("-"):
                continue
            if "[dev]" in tok:
                got |= dev
                got.add("vdi2770_validate")
            elif "[validate]" in tok:
                got.add("xmlschema")
            elif tok.startswith("packages/vdi2770"):
                got.add("vdi2770")
            elif re.match(r"^[A-Za-z][\w.-]*$", tok):
                got.add(tok)
    return got


def _third_party(path):
    """Top-level names `path` imports that are not stdlib, not this project's,
    and not a sibling script under tools/."""
    std = set(sys.stdlib_module_names)
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    out = set()
    for n in names:
        if n in std or n in FIRST_PARTY or n == "__future__":
            continue
        if (ROOT / "tools" / f"{n}.py").exists():
            continue
        out.add(DISTRIBUTION.get(n, n))
    return out


def _jobs():
    doc = yaml.safe_load(RELEASE.read_text(encoding="utf-8")) or {}
    for name, job in (doc.get("jobs") or {}).items():
        yield name, "\n".join(str(s.get("run", "")) for s in job.get("steps", []))


def test_every_release_job_installs_what_the_scripts_it_runs_import():
    if not hasattr(sys, "stdlib_module_names"):   # 3.10+; the 3.9 row skips
        import pytest
        pytest.skip("needs sys.stdlib_module_names (Python 3.10+)")
    problems = []
    for name, run_text in _jobs():
        have = _installed(run_text)
        for script in sorted(set(re.findall(r"python\s+tools/(\w+)\.py", run_text))):
            path = ROOT / "tools" / f"{script}.py"
            if not path.exists():
                continue
            for dist in sorted(_third_party(path)):
                if dist not in have:
                    problems.append(f"{name}: runs tools/{script}.py, which imports "
                                    f"{dist}, and the job does not install it")
        for mod in sorted(set(re.findall(r"python -m (\w+)", run_text))):
            if mod in DASH_M and mod not in have:
                problems.append(f"{name}: runs `python -m {mod}` without installing {mod}")
    assert not problems, (
        "a release job runs code whose third-party dependency it does not "
        "install -- green locally and on push, where `.[dev]` carries it, but "
        f"red on the tag, the one place the job runs as written: {problems}")
