"""The package's structural promises: no dependencies, no knowledge of rules.

These are AST checks rather than runtime ones, because the point is that the
code *cannot* do these things, not that it happened not to on this input.
"""
import ast
import re
import sys
from pathlib import Path

import vdi2770

HERE = Path(__file__).resolve().parent.parent
SRC = HERE / "src" / "vdi2770"
# Every module this package is allowed to import, written out. An allow-list
# rather than "is it in the standard library?" for two reasons: it works on the
# oldest Python we support, where `sys.stdlib_module_names` does not exist, and
# it makes *adding* an import a decision someone has to make on purpose.
ALLOWED = {"dataclasses", "enum", "io", "re", "typing", "xml", "zipfile", "zlib"}


def top_level_imports(path):
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            out.add(node.module.split(".")[0])
    return out - {"__future__"}


def test_the_package_imports_nothing_outside_the_standard_library():
    """`dependencies = []` in the metadata is a claim; this is the check."""
    for f in sorted(SRC.glob("*.py")):
        outside = top_level_imports(f) - ALLOWED - {"vdi2770"}
        assert not outside, (
            f"{f.name} imports {outside}. If that is standard library and this "
            f"package should use it, add it to ALLOWED; if it is not, the "
            f"`dependencies = []` in pyproject.toml just became false.")
    stdlib = getattr(sys, "stdlib_module_names", None)
    if stdlib is not None:                      # 3.10+, which CI runs
        assert not ALLOWED - stdlib, f"the allow-list names non-stdlib modules: {ALLOWED - stdlib}"


def test_the_library_cannot_reach_the_validator():
    """If the reader could import the rule set, the split would be cosmetic."""
    for f in sorted(SRC.glob("*.py")):
        assert "vdi2770_validate" not in f.read_text(encoding="utf-8"), \
            f"{f.name} mentions the validator"


def test_the_readers_do_not_know_rule_ids():
    """A reader that names a rule id is deciding policy on the caller's behalf.

    Unquoted too: the version of this test that only looked for `"P3"` missed a
    comment saying `P3, which is an error-severity rule` -- which was both a rule
    id in the reader and, by then, the wrong severity."""
    pattern = re.compile(r"\b(?:Z|X|M|F|P)\d{1,2}\b")
    for f in sorted(SRC.glob("*.py")):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            hit = pattern.search(line)
            assert not hit, f"{f.name}:{n} names rule id {hit.group(0)!r}: {line.strip()}"


def test_the_declared_public_surface_is_the_real_one():
    submodules = {"domain", "model", "pdfread", "xmlread", "zipread"}
    for name in vdi2770.__all__:
        assert hasattr(vdi2770, name), f"__all__ names {name}, which does not exist"
    public = {n for n in dir(vdi2770) if not n.startswith("_")} - submodules
    undeclared = public - set(vdi2770.__all__)
    assert not undeclared, f"public but undeclared: {undeclared}"


def test_the_version_is_in_one_place():
    toml = (HERE / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(f'^version = "{re.escape(vdi2770.__version__)}"$', toml, re.M), \
        f"pyproject and __init__ disagree; __init__ says {vdi2770.__version__}"


def test_the_readme_does_not_promise_a_verdict():
    """The whole reason this package exists separately is that it decides nothing.
    A README sentence that says otherwise would be the first thing to rot."""
    text = (HERE / "README.md").read_text(encoding="utf-8").lower()
    for phrase in ("is pdf/a", "validates against", "conformance checker", "tells you if it is valid"):
        assert phrase not in text, f"the README claims a verdict: {phrase!r}"


def test_the_readme_names_every_defect_kind_the_code_can_emit():
    """The kinds are a public vocabulary. A kind the README does not name is a
    kind a caller cannot switch on."""
    code = (SRC / "zipread.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'Defect\("([a-z-]+)"', code))
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"`([a-z]+(?:-[a-z]+)+)`", readme))
    missing = emitted - documented
    assert not missing, f"the code emits {missing}, which the README does not name"



def test_the_notice_travels_with_this_package_too():
    """Apache-2.0 asks for the NOTICE to go with the distribution. The validator
    shipped one from the first release; this package shipped only a LICENSE,
    because its `license-files` named only that. The two are separate
    distributions of one project and the attribution belongs in both."""
    notice = HERE / "NOTICE"
    assert notice.exists(), "this package has no NOTICE"
    text = notice.read_text(encoding="utf-8")
    assert text.startswith("vdi2770\n"), "the NOTICE names the wrong package"
    assert "Apache License" in text
    toml = (HERE / "pyproject.toml").read_text(encoding="utf-8")
    assert '"NOTICE"' in toml, "the NOTICE exists but the wheel would not carry it"
    assert "None." in text, (
        "this package bundles nothing third-party; the NOTICE should say so "
        "rather than repeating the validator's list")
