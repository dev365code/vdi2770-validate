"""Nothing in this repository imports what no manifest declares.

Four gates were green here and the run that counts was red. A gate written to
read the release workflow imports a YAML parser; the parser was installed on the
machine that wrote it and declared nowhere, so `make check` passed locally and
the two tests guarding the publishing order failed on all three interpreters in
CI.

`packaging` is the same shape and had not gone off yet. Two release tools import
it at module level and a test imports them, so it runs on every push -- green the
whole time, because the runner image happens to carry it. That is the quieter
half: a green CI is not evidence either, when what makes it green is something
nobody asked for. It would have gone red on the day that image changed, in the
gate that keeps the reader from being published after the rules that pin it.

So the rule is declared rather than inherited. Every top-level name imported
anywhere here is one of three things: the standard library, something this
repository builds, or a distribution some manifest asks for by name.

Where a module *loads from* decides which, rather than a list of names.
`sys.stdlib_module_names` arrived in 3.10 and this project supports 3.9, where it
would filter nothing and say so to nobody; a hand-kept list of standard-library
names is a second place to forget. And the distribution a third-party import
belongs to is read from the installed file records rather than guessed from the
spelling, because `import yaml` comes from `PyYAML` and no amount of string
manipulation gets there.
"""
import ast
import contextlib
import importlib.util
import re
import sysconfig
from pathlib import Path

from conftest import ROOT

_PATHS = sysconfig.get_paths()
_STDLIB = Path(_PATHS["stdlib"]).resolve()
_SITE = {Path(_PATHS[k]).resolve() for k in ("purelib", "platlib") if _PATHS.get(k)}


def _within(path, root):
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def python_here(root=ROOT):
    """Every directory of Python this repository owns.

    Shipped code as well as tests and tools: an undeclared import inside the
    package is worse than one in a test -- it reaches a user rather than a
    maintainer -- and it is the same question, so it is the same gate. Found by
    walking rather than listed, so a `packages/<name>/` added later is covered
    the day it appears instead of the day somebody remembers this file.
    """
    found = [root / "tests", root / "tools", root / "src"]
    for which in ("tests", "tools", "src"):
        found += sorted((root / "packages").glob(f"*/{which}"))
    return [d for d in found if d.is_dir()]


def imports_under(directories):
    """Top-level names imported anywhere in those trees, and where from.

    Every `Import` node in the file, not only the ones at module level: the
    import that turned CI red was inside a test function, which is precisely the
    kind a run of the suite on a machine that has the package will never
    mention.
    """
    names = {}
    for directory in directories:
        for source in sorted(directory.rglob("*.py")):
            tree = ast.parse(source.read_text(encoding="utf-8"), str(source))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        names.setdefault(alias.name.split(".")[0], set()).add(source)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names.setdefault(node.module.split(".")[0], set()).add(source)
    names.pop("__future__", None)
    return names


def whose(name, directories, root=ROOT):
    """`stdlib`, `ours`, `third-party`, or `unresolved` -- and where it loaded.

    A sibling module the test runner puts on the path (`conftest`, the tools a
    test imports) is ours by being a file here, which is checked first because
    those do not resolve outside a run.
    """
    for directory in directories:
        if (directory / f"{name}.py").is_file() or (directory / name / "__init__.py").is_file():
            return "ours", None
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        spec = None
    if spec is None:
        return "unresolved", None
    if spec.origin in (None, "built-in", "frozen"):
        return "stdlib", None
    origin = Path(spec.origin).resolve()
    # Site-packages before anything else: a virtual environment inside the
    # working tree would otherwise make every installed package look like ours.
    for site in _SITE:
        if _within(origin, site):
            return "third-party", origin
    if _within(origin, _STDLIB):
        return "stdlib", None
    if _within(origin, root):
        return "ours", None
    return "third-party", origin


def _normalised(name):
    return re.sub(r"[-_.]+", "-", name).lower()


_RECORDS = None


def provider(origin):
    """The distribution that installed that file, or None.

    Built once: asking each distribution in turn for every module costs a walk
    of every installed file each time, and this is asked once per import name.
    """
    global _RECORDS
    if _RECORDS is None:
        from importlib.metadata import distributions
        _RECORDS = {}
        for dist in distributions():
            try:
                files = dist.files or []
            except Exception:                                   # noqa: BLE001 - unreadable metadata is not a finding
                continue
            named = (dist.metadata or {}).get("Name")
            for relative in files:
                with contextlib.suppress(Exception):
                    _RECORDS[Path(dist.locate_file(relative)).resolve()] = named
    return _RECORDS.get(origin)


def manifests(root=ROOT):
    found = [root / "pyproject.toml"] + sorted((root / "packages").glob("*/pyproject.toml"))
    return [p for p in found if p.is_file()]


def declared(root=ROOT):
    """Every distribution any manifest here asks for, runtime or dev.

    Both lists, because the question is only whether somebody wrote the name
    down: a test dependency that nothing declares breaks the same run as a
    runtime one that nothing declares.
    """
    asked = set()
    for path in manifests(root):
        text = path.read_text(encoding="utf-8")
        blocks = re.findall(r"^dependencies = \[(.*?)\]", text, re.M | re.S)
        extras = re.search(r"^\[project\.optional-dependencies\](.*?)(?=^\[|\Z)", text, re.M | re.S)
        if extras:
            blocks += re.findall(r"= \[(.*?)\]", extras.group(1), re.S)
        for block in blocks:
            for requirement in re.findall(r'"([^"]+)"', block):
                asked.add(_normalised(re.split(r"[<>=!~\[; ]", requirement, maxsplit=1)[0].strip()))
    return asked


def undeclared(directories, asked, root=ROOT):
    """Name -> (what is wrong, the files that import it)."""
    wrong = {}
    for name, files in imports_under(directories).items():
        kind, origin = whose(name, directories, root)
        if kind == "unresolved":
            wrong[name] = ("is imported but is neither installed nor a file in this repository", files)
        elif kind == "third-party":
            from_where = provider(origin) or name
            if _normalised(from_where) not in asked:
                wrong[name] = (f"comes from {from_where}, which no manifest declares", files)
    return wrong


def test_every_import_outside_the_standard_library_is_declared():
    found = undeclared(python_here(), declared())
    assert not found, "\n".join(
        f"{name} {why}; imported by "
        + ", ".join(sorted(str(f.relative_to(ROOT)) for f in files)[:3])
        for name, (why, files) in sorted(found.items()))


def test_it_notices_when_a_declaration_is_missing():
    """The same tree, read against nothing declared.

    One thing differs from the passing case -- the list of declared
    distributions -- so this pins the comparison itself. A case broken on two
    axes at once proves neither: either assertion could be deleted and it would
    still fail.

    `pytest` is the name asserted on because a machine running this test has it
    by definition, whatever else it does or does not have installed.
    """
    found = undeclared(python_here(), set())
    assert "pytest" in found, f"a third-party import went unnoticed: {sorted(found)}"
    why, files = found["pytest"]
    assert "declares" in why


def test_a_name_that_is_nowhere_is_reported(tmp_path):
    """An import of something that does not exist, with everything declared.

    The one axis is the name. It is reported rather than passed over because a
    static read is the only thing that sees an import inside a function before
    that function runs, and "not installed anywhere" and "installed but not
    declared" are the same failure to the person whose run stops.
    """
    (tmp_path / "reads_something_absent.py").write_text(
        "def go():\n    import no_such_distribution_zzz\n", encoding="utf-8")
    found = undeclared([tmp_path], declared(), root=tmp_path)
    assert "no_such_distribution_zzz" in found
    assert "neither installed nor a file" in found["no_such_distribution_zzz"][0]
