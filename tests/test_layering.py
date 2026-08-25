"""Rules validate the model, not the serialisation — enforced, not promised.

A rule that cannot import a parser cannot accidentally check how the document
was spelled instead of what it says.
"""
import ast
import re
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


# Any rule id, quoted or not. The version that looked for five hard-coded ids in
# quotes was the weaker half of a pair: the SDK's own copy of this check (see
# packages/vdi2770/tests/test_it_stands_alone.py) already caught an unquoted id
# in a comment, and that comment had the severity wrong. Two checks of the same
# rule should not disagree about how hard they look.
RULE_ID = re.compile(r"\b(?:Z|X|M|F|P)\d{1,2}\b")


#: Modules that wrap a parser or an external tool. They must not know rule ids.
#: Named, not globbed: this walked `readers/*.py`, and when that one-file
#: directory was dissolved the glob would have matched nothing and passed. A
#: gate that goes quiet on a rename is the failure this file is about.
READER_MODULES = ["xsdvalidate.py"]


def test_readers_do_not_know_rule_ids():
    for name in READER_MODULES:
        f = SRC / name
        assert f.exists(), f"{name} has moved; this gate is looking at nothing"
        mods = imports_of(f)
        assert "catalog" not in mods and "..catalog" not in mods, f"{f.name} imports the catalogue"
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            hit = RULE_ID.search(line)
            assert not hit, f"{f.name}:{n} names rule id {hit.group(0)!r}: {line.strip()}"


def test_unicode_canonicalisation_is_defined_once_in_the_project():
    """`nfc` belongs to whoever reads archives. There were two copies of that one
    line in two packages — and `names.py`, which holds the second one's caller,
    exists because every place that compares a name has to do it the same way.

    A grep is what this was, and a grep cannot tell a call from a sentence about
    one: writing the function's name in a comment that explains why it is not
    wrapped counted as a second definition. It reads the code now.
    """
    import ast

    hits = []
    for root in ("src", "packages/vdi2770/src"):
        for path in sorted((ROOT / root).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                if (isinstance(fn, ast.Attribute) and fn.attr == "normalize"
                        and isinstance(fn.value, ast.Name) and fn.value.id == "unicodedata"):
                    hits.append(f"{path.relative_to(ROOT)}:{node.lineno}")

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


def test_no_rule_module_offers_a_default_its_caller_never_uses():
    """`rules/container.py::check` carried `declared=frozenset()` and
    `is_declared_payload=False`. There is one caller and it passes both by
    keyword, and no test calls the module directly — so the defaults described a
    way of using it that nothing does, and a future caller forgetting an
    argument would have got a silent wrong answer instead of a TypeError.

    The other four rule modules take no defaults, which is what makes this a
    stray rather than a convention.
    """
    import inspect
    import sys

    sys.path.insert(0, str(SRC.parent))
    offenders = {}
    for f in sorted((SRC / "rules").glob("*.py")):
        if f.name == "__init__.py":
            continue
        module = __import__(f"vdi2770_validate.rules.{f.stem}", fromlist=["check"])
        params = inspect.signature(module.check).parameters
        defaulted = [n for n, p in params.items() if p.default is not inspect.Parameter.empty]
        if defaulted:
            offenders[f.stem] = defaulted
    assert not offenders, (
        f"rule modules with unused defaults: {offenders}. The runner passes every "
        f"argument; a default here only hides a caller that forgot one.")


def test_a_tool_measures_the_reader_in_this_tree():
    """A tool that puts only `src` on the path imports whichever `vdi2770` is
    installed. On a machine with the published reader that is a different library
    than the one in the commit, so the gate reports coverage — or renders a
    document — for code nobody is changing.

    `capture_oracle.py` got this right and the others copied the shorter line.
    """
    tools = ROOT / "tools"
    for f in sorted(tools.glob("*.py")):
        source = f.read_text(encoding="utf-8")
        if "vdi2770_validate" not in source:
            continue
        if 'ROOT / "src"' not in source:
            continue
        assert 'packages' in source and 'vdi2770' in source, (
            f"tools/{f.name} imports the validator and does not put the reader in "
            f"this tree ahead of an installed one")


def test_a_rule_module_holds_no_reference_to_a_parser():
    """The checks above read the source: `ast.Import` sees `import zipfile`, and
    a grep sees three literal call spellings. Neither sees

        _zr = __import__("importlib").import_module("vdi2770.zipread")

    which is a builtin and a string, so widening the forbidden list cannot close
    it. Reproduced: two such lines in `rules/metadata.py` left the layering file
    green.

    So this asks the module rather than its text. After import, a rule module's
    namespace must contain no parser and no reader — whatever spelling put it
    there.
    """
    import importlib
    import types

    # A whole module is the thing that must not be here: holding `zipread` gives
    # a rule every function on it. Individual values are allowed — `Kind` and
    # `nfc` are the constants and the one helper `model.py` re-exports, which
    # `test_rules_only_reach_readers_for_constants` is about and the docs
    # describe. What a rule may not have is a door.
    forbidden = {"zipfile", "xml", "xmlschema", "io", "re", "importlib",
                 "vdi2770", "vdi2770.zipread", "vdi2770.xmlread", "vdi2770.pdfread",
                 "vdi2770.domain"}
    parsers = {"parse", "read", "read_file", "build", "member_bytes", "validate",
               "read_pdf", "parse_xml", "read_container", "read_container_file"}
    for f in sorted((SRC / "rules").glob("*.py")):
        if f.name == "__init__.py":
            continue
        module = importlib.import_module(f"vdi2770_validate.rules.{f.stem}")
        for name, value in vars(module).items():
            if name.startswith("__"):
                continue
            if isinstance(value, types.ModuleType):
                assert value.__name__ not in forbidden and not value.__name__.startswith(
                    ("vdi2770.", "xml.")), (
                    f"rules/{f.name} holds the module {value.__name__!r} as {name!r}, "
                    f"which is every function on it")
                continue
            origin = getattr(value, "__module__", None)
            reaches = origin in forbidden and (
                (callable(value) and name in parsers)
                or getattr(value, "__name__", "") in parsers)
            assert not reaches, (
                f"rules/{f.name} holds {name!r} from {origin!r}. A rule validates "
                f"the model; reaching a parser lets it check how a document was "
                f"spelled instead of what it says.")
