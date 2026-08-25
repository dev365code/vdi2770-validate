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
ALLOWED = {"collections", "dataclasses", "enum", "io", "re", "typing",
           "unicodedata", "xml", "zipfile", "zlib"}


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
    """The vocabulary is a value, not a regex over this module's source.

    The scrape saw eight of thirteen: every kind emitted through `_refuse()` is
    written in a shape it does not match, so `unsafe-member-name`,
    `suspicious-compression`, `member-too-large`, `member-unreadable` and
    `metadata-too-large` could all be deleted from the README with the gate
    green. `model.py`'s own comment says the fix — "a value cannot be missed by a
    regex" — and the validator's copy of this check was migrated to
    `DEFECT_KINDS` while this one was not.
    """
    from vdi2770 import DEFECT_KINDS, REFUSAL_KINDS

    readme = (SRC.parent.parent / "README.md").read_text(encoding="utf-8")
    missing = sorted(k for k in DEFECT_KINDS if f"`{k}`" not in readme)
    assert not missing, f"the reader can emit kinds the README does not name: {missing}"
    assert REFUSAL_KINDS <= DEFECT_KINDS, sorted(REFUSAL_KINDS - DEFECT_KINDS)

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



def test_the_readme_names_every_budget_the_code_can_enforce():
    """The budget list said `pdfread` had four; it had six, and it had had six
    for a while. A count in prose is a claim nobody re-checks, so the list names
    the constants and this asserts the naming is complete.
    """
    import re

    from vdi2770 import pdfread, xmlread, zipread

    readme = (SRC.parent.parent / "README.md").read_text(encoding="utf-8")
    # `xmlread` was not in this loop, so the element cap this package grew
    # was the one budget the README did not have to name — while the README
    # says a test fails if either module grows one it does not list.
    for mod in (zipread, pdfread, xmlread):
        names = {n for n in dir(mod) if n.startswith(("MAX_", "MIN_"))}
        assert names, f"{mod.__name__} has no budgets; this test is looking in the wrong place"
        missing = sorted(n for n in names if f"`{n}`" not in readme)
        assert not missing, f"{mod.__name__} enforces budgets the README does not name: {missing}"
    m = re.search(r"`vdi2770\.pdfread` has (\w+) of its own", readme)
    assert m, "the sentence counting pdfread's budgets has been reworded"
    words = {"four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
    real = len([n for n in dir(pdfread) if n.startswith(("MAX_", "MIN_"))])
    assert words.get(m.group(1)) == real, f"the README says {m.group(1)}; there are {real}"


def test_the_reader_does_not_write_sentences_about_what_it_refused():
    """`rejected` held a second English sentence per refusal — "larger than this
    tool will read", "over this tool's limit" — written beside the `Defect` that
    already recorded the same fact. Two wordings for one event can disagree, and
    prose about what a caller should conclude is the thing this package does not
    do. `near_misses` lost its sentence for the same reason; this is the other
    half of it.

    `rejected` maps a name to the `Defect` that refused it. Whoever writes the
    report writes the sentence.
    """
    import io
    import zipfile

    from vdi2770 import zipread
    from vdi2770.model import Defect

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("VDI2770_Metadata.xml", b"<x/>")
        z.writestr("../escape.txt", b"x")
    c = zipread.read(buf.getvalue(), "x.zip")

    assert "../escape.txt" in c.rejected
    refusal = c.rejected["../escape.txt"]
    assert isinstance(refusal, Defect), f"rejected carries {type(refusal).__name__}, not a fact"
    assert refusal.kind == "unsafe-member-name"
    assert refusal in c.defects, "the refusal and the defect are the same object"


def test_every_exception_this_package_raises_can_be_caught_by_name():
    """`XmlTooLarge` was raised at the module boundary and not exported, so the
    only way to tell it from "your file is malformed" was a string compare on
    `__class__.__name__` — which is what the validator was reduced to.

    Its two siblings, `XmlError` and `UnsafeXml`, are both exported. Nothing
    noticed the third, because `test_the_declared_public_surface_is_the_real_one`
    checks one direction only: everything reachable is declared. The fingerprint
    walks `__all__`, so an unexported class is invisible to the release gate
    too — it could be renamed in a patch release and `--check` would pass.

    A caller is meant to write `except vdi2770.XmlTooLarge`. This is what makes
    that possible next time somebody adds one.
    """
    import importlib
    import inspect
    import pkgutil

    import vdi2770

    raised = {}
    for info in pkgutil.iter_modules(vdi2770.__path__, "vdi2770."):
        mod = importlib.import_module(info.name)
        for name, obj in vars(mod).items():
            if (inspect.isclass(obj) and issubclass(obj, Exception)
                    and obj.__module__ == mod.__name__):
                raised[name] = mod.__name__

    assert raised, "this package raises nothing of its own; the test is looking wrongly"
    missing = sorted(n for n in raised if n not in vdi2770.__all__)
    assert not missing, (
        f"raised but not exported, so a caller cannot catch it by name: "
        f"{ {n: raised[n] for n in missing} }")
