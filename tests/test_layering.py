"""Rules validate the model, not the serialisation — enforced, not promised.

A rule that cannot import a parser cannot accidentally check how the document
was spelled instead of what it says.
"""
import ast
from pathlib import Path

from conftest import ROOT

SRC = ROOT / "src" / "vdi2770_validate"
FORBIDDEN_IN_RULES = {"zipfile", "xml", "xmlschema", "io", "re"}


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
