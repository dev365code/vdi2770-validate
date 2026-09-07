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
import site
import sysconfig
from pathlib import Path

from conftest import ROOT

_PATHS = sysconfig.get_paths()
_STDLIB = Path(_PATHS["stdlib"]).resolve()


def _installed_into():
    """Every directory this interpreter installs packages into.

    `purelib` and `platlib` alone are not all of them, and the miss is not
    exotic. On the Apple command-line-tools interpreter -- the one this project
    is developed on -- `purelib` names a single directory, the interpreter's own
    `site-packages` sits *inside* `stdlib`, and the user site is neither. So
    `pip`, `setuptools` and `pkg_resources` came back as standard library:
    "underneath the stdlib directory" is not the same claim as "is the standard
    library", and Debian's `/usr/lib/python3.x/dist-packages` has the same
    shape. A test importing any of them would have been excused here and gone
    red on a machine that had them somewhere else -- silent on the developer's
    machine, which is this whole file's subject.

    `site.getsitepackages` is missing from some older virtualenvs, hence the
    getattr.
    """
    found = {Path(_PATHS[k]).resolve() for k in ("purelib", "platlib") if _PATHS.get(k)}
    for ask in ("getsitepackages", "getusersitepackages"):
        answer = getattr(site, ask, None)
        if answer is None:
            continue
        try:
            got = answer()
        except Exception:                               # noqa: BLE001
            continue
        for one in ([got] if isinstance(got, str) else list(got or ())):
            with contextlib.suppress(OSError, TypeError, ValueError):
                found.add(Path(one).resolve())
    return found


_SITE = _installed_into()

#: And the last resort, for a layout none of the above names. A directory
#: called this is where installers put things, wherever it happens to sit.
_INSTALLED_DIRS = ("site-packages", "dist-packages")


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


#: Exceptions whose handler means "this may not be here, and that is handled".
#: A bare `except:` counts too, and is spelled as `None` by the parser.
ABSENCE = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}


def _handles_absence(handler):
    caught = handler.type
    if caught is None:                                  # a bare `except:`
        return True
    named = caught.elts if isinstance(caught, ast.Tuple) else [caught]
    for one in named:
        if isinstance(one, ast.Name) and one.id in ABSENCE:
            return True
        if isinstance(one, ast.Attribute) and one.attr in ABSENCE:
            return True
    return False


def _guarded_imports(tree):
    """The import nodes whose absence the file itself deals with.

    `try: import tomllib / except ImportError: import tomli` says out loud that
    the first one may not be there. Demanding a declaration for it would be a
    false positive on the one shape that is already handled -- and the shape is
    common enough that a sister project hit it the day this gate was ported.

    Decided by what the handler catches, not by the presence of the word `try`:
    a `try` whose handler catches `ValueError` does nothing at all about an
    import that is not installed.

    The fallback counts as handled too, not only the first branch. A chain like
    `except ImportError: from pip._vendor.packaging import …` would otherwise
    make this gate demand a declaration for `pip`, and the only way to satisfy
    that is to write something false into a manifest. The two errors are not
    the same size: a false positive here is answered by corrupting the
    dependency list, while the case it gives up -- a chain where no branch is
    installed -- fails at import on every machine including the author's, the
    first time the file is run. This gate is for the accident, and the accident
    is never written as a fallback chain.
    """
    guarded = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        if not any(_handles_absence(h) for h in node.handlers):
            continue
        for inner in [*node.body, *node.handlers]:
            for maybe in ast.walk(inner):
                if isinstance(maybe, (ast.Import, ast.ImportFrom)):
                    guarded.add(maybe)
    return guarded


def imports_under(directories):
    """Top-level names imported anywhere in those trees, and where from.

    Every `Import` node in the file, not only the ones at module level: the
    import that turned CI red was inside a test function, which is precisely the
    kind a run of the suite on a machine that has the package will never
    mention.

    An import that handles its own absence does not count. A name is here if it
    is imported at least once *without* that handling, because one unguarded
    import is enough to stop a run on a machine that lacks it.
    """
    names = {}
    for directory in directories:
        for source in sorted(directory.rglob("*.py")):
            tree = ast.parse(source.read_text(encoding="utf-8"), str(source))
            guarded = _guarded_imports(tree)
            for node in ast.walk(tree):
                if node in guarded:
                    continue
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
    settled = kind_of(origin)
    if settled:
        return settled, (origin if settled == "third-party" else None)
    if _within(origin, root):
        return "ours", None
    return "third-party", origin


def kind_of(origin):
    """`third-party`, `stdlib`, or None for somewhere else -- from the path alone.

    Separate from `whose` so it can be asked about a path that is not on this
    machine. The distinction it draws is invisible here: this interpreter keeps
    the packages that show it in a directory nothing in this suite imports, so a
    version of this file that got it wrong would pass every other test and fail
    on somebody else's machine.

    Installed first, and the standard library only after. An interpreter can
    keep its `site-packages` *inside* the stdlib directory -- the Apple
    command-line-tools build does, and Debian's `dist-packages` is the same
    shape -- so asking "is it under stdlib" first answers `setuptools` wrong.
    """
    for installed in _SITE:
        if _within(origin, installed):
            return "third-party"
    if any(part in _INSTALLED_DIRS for part in origin.parts):
        return "third-party"
    if _within(origin, _STDLIB):
        return "stdlib"
    return None


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
    by definition, whatever else it does or does not have installed. That makes
    it the negative case as well as the positive one: an installed package that
    came back as standard library would go unreported here, and asking only
    whether `json` is excused would never catch that -- the interpreter this
    project is developed on keeps its own `site-packages` inside the standard
    library directory, and three installed packages were classified as the
    standard library before this line had anything to say about it.
    """
    found = undeclared(python_here(), set())
    assert "pytest" in found, f"a third-party import went unnoticed: {sorted(found)}"
    why, files = found["pytest"]
    assert "declares" in why


def test_an_import_that_handles_its_own_absence_is_not_undeclared(tmp_path):
    """`try: import x / except ImportError: <fallback>` needs no declaration.

    Paired with the test below it, which is the same file with one thing
    changed -- what the handler catches. That is the axis: the word `try` is
    present in both, and only one of them does anything about a package that is
    not installed.
    """
    (tmp_path / "asks_politely.py").write_text(
        "try:\n    import no_such_distribution_zzz\nexcept ImportError:\n"
        "    no_such_distribution_zzz = None\n", encoding="utf-8")
    assert "no_such_distribution_zzz" not in undeclared([tmp_path], declared(), root=tmp_path)


def test_a_try_that_catches_something_else_does_not_excuse_the_import(tmp_path):
    """The same file, catching `ValueError`. Nothing there handles an absent
    package, so the import still has to be declared -- and a gate that looked
    for the word `try` could not tell these two files apart."""
    (tmp_path / "asks_politely.py").write_text(
        "try:\n    import no_such_distribution_zzz\nexcept ValueError:\n"
        "    no_such_distribution_zzz = None\n", encoding="utf-8")
    assert "no_such_distribution_zzz" in undeclared([tmp_path], declared(), root=tmp_path)


def test_a_package_installed_under_the_stdlib_directory_is_not_the_stdlib():
    """The Apple command-line-tools shape, asked as a question about a path.

    `<stdlib>/site-packages/anything` is an install, not the standard library.
    Paired with the test below it: the same directory, one component different,
    and that component is the whole answer. Neither depends on where this
    machine happens to keep things, which is the point -- on the machine this
    was found on, every package that shows the difference is one nothing here
    imports, so the bug was invisible to every other test in this file.
    """
    from pathlib import Path
    installed = Path(_PATHS["stdlib"]) / "site-packages" / "somepkg" / "__init__.py"
    assert kind_of(installed) == "third-party"
    assert kind_of(Path(_PATHS["stdlib"]) / "dist-packages" / "somepkg.py") == "third-party"


def test_a_module_beside_it_in_the_stdlib_directory_still_is_the_stdlib():
    """The other half of the pair. Without this, excusing everything would pass
    the test above and nothing would hold the line in the other direction."""
    from pathlib import Path
    assert kind_of(Path(_PATHS["stdlib"]) / "json" / "__init__.py") == "stdlib"
    assert kind_of(Path(_PATHS["stdlib"]) / "zipfile.py") == "stdlib"


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
