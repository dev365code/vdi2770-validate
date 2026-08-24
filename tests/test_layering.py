"""Rules validate the model, not the serialisation — enforced, not promised.

A rule that cannot import a parser cannot accidentally check how the document
was spelled instead of what it says.
"""
import ast
from pathlib import Path

from conftest import ROOT

SRC = ROOT / "src" / "vdi2770_validate"
# `vdi2770` too: model.py re-exports the vocabulary a rule needs, and reaching
# past it for `Kind` and the reserved filenames made that module's docstring
# three-quarters true.
FORBIDDEN_IN_RULES = {"zipfile", "xml", "xmlschema", "io", "re", "vdi2770"}


def imports_of(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                out.add(("." * node.level) + (node.module or ""))
            elif node.module:
                out.add(node.module.split(".")[0])
    return out


def test_rules_cannot_reach_a_parser():
    for f in sorted((SRC / "rules").glob("*.py")):
        found = imports_of(f) & FORBIDDEN_IN_RULES
        assert not found, f"{f.name} imports {found}; rules must not touch the serialisation"


def test_rules_only_reach_readers_for_constants():
    """rules/ may name the reserved file names, but must not import reader logic."""
    for f in sorted((SRC / "rules").glob("*.py")):
        text = f.read_text(encoding="utf-8")
        for bad in ("zipread.read(", "xmlread.parse(", "xsdvalidate.validate("):
            assert bad not in text, f"{f.name} calls {bad}"


def test_readers_do_not_know_rule_ids():
    for f in sorted((SRC / "readers").glob("*.py")):
        mods = imports_of(f)
        assert "catalog" not in mods and "..catalog" not in mods, f"{f.name} imports the catalogue"
        text = f.read_text(encoding="utf-8")
        for rid in ("Z1", "Z3", "X2", "M1", "P4"):
            assert f'"{rid}"' not in text, f"{f.name} hard-codes rule id {rid}"


def test_unicode_canonicalisation_is_defined_once_in_the_project():
    """`nfc` belongs to whoever reads archives. There were two copies of that one
    line in two packages — and `names.py`, which holds the second one's caller,
    exists because every place that compares a name has to do it the same way."""
    import subprocess

    hits = subprocess.run(
        ["grep", "-rn", "unicodedata.normalize", "src", "packages/vdi2770/src"],
        cwd=ROOT, capture_output=True, text=True).stdout.strip().splitlines()
    assert len(hits) == 1, "more than one definition of canonical form:\n  " + "\n  ".join(hits)
    assert hits[0].startswith("packages/vdi2770/src/vdi2770/zipread.py"), hits[0]


def test_the_reader_package_tests_stay_inside_the_reader_package():
    """Three gates have now been written in the SDK's suite that read files above
    it — a workflow, a repository-wide grep — and each one broke the sdist check,
    because an sdist contains the package and nothing else.

    A claim about the repository belongs in the repository's suite. This is the
    rule, enforced, so it stops being learned one incident at a time.
    """
    sdk_tests = ROOT / "packages" / "vdi2770" / "tests"
    for f in sorted(sdk_tests.glob("*.py")):
        text = f.read_text(encoding="utf-8")
        for bad in ("HERE.parent.parent", '".github"', "packages/vdi2770", "ROOT /"):
            assert bad not in text, (
                f"{f.name} reaches outside the package ({bad!r}); "
                f"put that assertion in the repository's own suite")
