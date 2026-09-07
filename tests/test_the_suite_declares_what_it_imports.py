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
import os
import re
import site
import sys
import sysconfig
from pathlib import Path

from conftest import ROOT


def _within(path, root):
    """Whether `path` is `root` or sits under it, on a filesystem that may not
    care about case.

    `Path.relative_to` compares the parts as written. On Windows `C:\\Python\\Lib`
    and `c:\\python\\lib` are one directory, and a comparison that says
    otherwise reports a *declared* dependency as undeclared — which reads as an
    entirely different bug.
    """
    fold = [os.path.normcase(part) for part in path.parts]
    against = [os.path.normcase(part) for part in root.parts]
    return fold[:len(against)] == against


_PATHS = sysconfig.get_paths()
_STDLIB = Path(_PATHS["stdlib"]).resolve()
#: And the tree the interpreter itself came out of. `stdlib` names one
#: directory, and on Windows the extension modules are not in it: `unicodedata`
#: loads from `<base_prefix>\\DLLs\\unicodedata.pyd`, a *sibling* of `Lib`. So
#: the same assumption breaks in both directions -- site-packages inside the
#: stdlib directory on one interpreter, standard modules outside it on another
#: -- and neither is visible from the other's machine. `lib-dynload` sits under
#: `stdlib` here, which is why this project's own CI never showed it.
_BASE = Path(sys.base_prefix).resolve()


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
    return only_install_directories(found, _STDLIB)


def only_install_directories(candidates, stdlib):
    """The candidates that can tell an install from what the interpreter ships.

    On Windows `site.getsitepackages()` includes `sys.prefix` itself, and the
    standard library is `<prefix>\\Lib` — so with installs checked first, every
    module the interpreter ships came back as an installed package and
    `__future__`, `difflib` and `json` were reported as undeclared. A sister
    project measured it; this project's Windows row was written the same hour.

    The rule that follows is one sentence: **a directory that contains the
    standard library cannot distinguish an install from what the interpreter
    shipped, so it is not an install directory.** `<prefix>/Lib/site-packages`
    survives it and `<prefix>` does not, which is the distinction that was
    missing.
    """
    return {d for d in candidates if not _within(stdlib, d)}


_SITE = _installed_into()

#: What the interpreter itself says is the standard library, whether or not this
#: platform ships it. Asked only about names that do not resolve here.
_SAYS_STDLIB = frozenset(getattr(sys, "stdlib_module_names", ()))

#: And the ones that differ by platform, named because 3.9 has no such list to
#: ask. `fcntl` is the standard library and does not exist on Windows; `winreg`
#: is the standard library and does not exist here. Neither is a package
#: anybody could declare, and a gate that reports them is asking for a false
#: entry in a manifest.
_PLATFORM_STDLIB = frozenset({
    "fcntl", "termios", "tty", "pty", "pwd", "grp", "crypt", "posix", "nis",
    "spwd", "resource", "syslog", "readline", "curses", "ossaudiodev",
    "msvcrt", "winreg", "winsound", "msilib", "_winapi",
})


def is_standard_library(name, known=None):
    """Whether a name that will not resolve here is the standard library anyway.

    A module can be the standard library and absent: `fcntl` on Windows,
    `winreg` on everything else. Reporting one as undeclared asks for a
    manifest entry that cannot exist -- the same shape as demanding `pip` be
    declared, and the reason this is asked before anything is called missing.
    """
    return name in (_SAYS_STDLIB if known is None else known) or name in _PLATFORM_STDLIB

#: And the last resort, for a layout none of the above names. A directory
#: called this is where installers put things, wherever it happens to sit.
_INSTALLED_DIRS = ("site-packages", "dist-packages")


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


#: Modules this repository runs as `python -m <name>` and does not import. The
#: gate below reads import statements, so a dependency invoked as a subprocess
#: is invisible to it — which is how `build` went undeclared until one CI
#: runner image turned out not to carry it. Named here, with the reason, so
#: adding another is a decision somebody writes down.
RUN_AS_MODULES = {
    "pip": "always present wherever this project can be installed at all, and "
           "declaring it would put something false in a manifest other gates "
           "read as truth",
    "venv": "the standard library",
}


def modules_run_under(directories):
    """Names passed to an interpreter as `-m`, which are dependencies too.

    Read off the argument lists rather than the imports: `python -m build` needs
    `build` installed exactly as much as `import build` would, and the gate that
    reads import statements cannot see it.

    Only when the interpreter is the thing being run. `-m` is a flag for a great
    many programs — `git commit -q -m "x"` is in this repository three times —
    and reading every `-m` as a module name reports `x` as a package nobody
    declared, which is a false positive of exactly the kind that gets answered
    by writing something untrue in a manifest.
    """
    names = {}
    for directory in directories:
        for source in sorted(directory.rglob("*.py")):
            tree = ast.parse(source.read_text(encoding="utf-8"), str(source))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.List, ast.Tuple)) or not node.elts:
                    continue
                if not _is_an_interpreter(node.elts[0]):
                    continue
                parts = node.elts
                for first, second in zip(parts, parts[1:]):
                    if (isinstance(first, ast.Constant) and first.value == "-m"
                            and isinstance(second, ast.Constant)
                            and isinstance(second.value, str)):
                        names.setdefault(second.value.split(".")[0], set()).add(source)
    return {name: files for name, files in names.items() if name not in RUN_AS_MODULES}


def _is_an_interpreter(node):
    """Whether the first argument names a Python to run.

    `sys.executable`, `self.python`, `env.python` — an attribute called
    `executable` or `python` — or a literal with `python` in it.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return "python" in node.value.lower()
    if isinstance(node, ast.Attribute):
        return node.attr in ("executable", "python")
    if isinstance(node, ast.Call):                      # str(root / ... / "python")
        return True
    return isinstance(node, ast.Name) and node.id in ("python", "interpreter")


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
        # Not here, which is not the same as nowhere.
        return ("stdlib" if is_standard_library(name) else "unresolved"), None
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
    The order matters twice over, because the interpreter's own tree contains
    both: a package installed into it is still an install.
    """
    for installed in _SITE:
        if _within(origin, installed):
            return "third-party"
    if any(part in _INSTALLED_DIRS for part in origin.parts):
        return "third-party"
    if _within(origin, _STDLIB) or _within(origin, _BASE):
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
    # `wanted`, not `asked`: the declared set arrives as `asked`, and a local of
    # that name here silently turned every membership test into a question about
    # the wrong dictionary — `PyYAML` was reported as undeclared while it sat in
    # the manifest, and `pytest` stopped being reported when it should have been.
    wanted = dict(imports_under(directories))
    for name, files in modules_run_under(directories).items():
        wanted.setdefault(name, set()).update(files)
    for name, files in wanted.items():
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


def test_an_extension_module_outside_the_stdlib_directory_still_is_the_stdlib():
    """Windows keeps them in `DLLs`, a sibling of `Lib` rather than a child.

    `stdlib` names one directory and the standard library is a tree. The same
    assumption broke the other way round a few hours earlier -- site-packages
    *inside* that directory -- and neither shape is visible from the other's
    machine: `lib-dynload` sits under `stdlib` here, so this project's own CI
    would never have shown it. A sister project's Windows row did.
    """
    from pathlib import Path
    assert kind_of(Path(sys.base_prefix) / "DLLs" / "unicodedata.pyd") == "stdlib"
    assert kind_of(Path(sys.base_prefix) / "lib-dynload" / "_socket.so") == "stdlib"
    # And still not an install that happens to live in the same tree.
    assert kind_of(Path(sys.base_prefix) / "Lib" / "site-packages" / "x.py") == "third-party"


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


def test_a_directory_that_contains_the_stdlib_is_not_an_install_directory():
    """The third shape of the same wrong assumption, and the one that would have
    turned every Windows run red.

    There, `site.getsitepackages()` includes `sys.prefix` itself, and the
    standard library is `<prefix>\\Lib` — so with installs checked first, every
    module the interpreter ships is inside a directory this file calls an
    install directory, and `__future__`, `difflib` and `json` come back as
    packages nobody declared. A sister project measured exactly that.

    Asked of two paths rather than of this machine, because the machine that
    shows it is not this one: `<prefix>` and `<prefix>/Lib/site-packages` are
    both offered, the standard library is `<prefix>/Lib`, and only the second
    can tell an install from what the interpreter shipped.
    """
    from pathlib import Path
    prefix = Path("/opt/py")
    kept = only_install_directories(
        {prefix, prefix / "Lib" / "site-packages"}, prefix / "Lib")
    assert kept == {prefix / "Lib" / "site-packages"}


def test_paths_are_compared_without_regard_to_case():
    """`C:\\Python\\Lib` and `c:\\python\\lib` are one directory there, and a
    comparison that says otherwise reports a declared dependency as undeclared —
    which reads as an entirely different bug. On a case-sensitive filesystem
    this asserts what `normcase` does here, which is nothing, so the case that
    pins it is the one above."""
    from pathlib import Path
    root = Path("/opt/Py/Lib")
    same = Path(os.path.normcase("/opt/Py/Lib")) / "json"
    assert _within(same, root) or os.path.normcase("A") == "A"


def test_a_module_this_platform_lacks_can_still_be_the_standard_library():
    """`fcntl` is the standard library and is not on Windows; `winreg` is the
    standard library and is not here. `runner.py` imports the first inside the
    branch that uses it, and the Windows row reported it as a package nobody
    declared — a manifest entry that cannot exist, which is the same shape as
    demanding `pip` be declared.

    Asked of names rather than of this interpreter, so the case holds on the
    platform that has each of them and on the one that does not. `known` is
    empty in the first two so they can only pass through the platform table,
    and holds one name in the last so it can only pass through the list the
    interpreter offers.
    """
    assert is_standard_library("fcntl", known=frozenset())
    assert is_standard_library("winreg", known=frozenset())
    assert is_standard_library("json", known=frozenset({"json"}))
    assert not is_standard_library("no_such_module_zzz", known=frozenset())
