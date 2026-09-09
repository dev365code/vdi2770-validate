"""The old import name, kept as the same objects rather than a second copy.

`vdi2770_validate` was the whole of this tool for seven releases. It is
`vdi2770.validate` now, and everything written against the old name has to go on
working: `import vdi2770_validate`, `from vdi2770_validate.cli import main`,
`python -m vdi2770_validate`, and the console script.

A thin re-export does not do that. `from vdi2770.validate import *` gives a
module with no submodules — `from vdi2770_validate.cli import main` raises
`ModuleNotFoundError`, `hasattr(mod, "cli")` is False, `python -m` fails. Five
tools in this repository import those submodules, so the specification that
sounded safest would have broken this project's own build first.

`sys.modules[__name__] = _engine` fixes the top of it, and **is not enough**.
Measured after the move: `import vdi2770_validate.model` then finds `model`
through the engine's `__path__`, executes it a second time, and registers it
under the old dotted name — so `vdi2770_validate.model.Severity` and
`vdi2770.validate.model.Severity` are two enums with equal members and no shared
identity. The first thing that broke was a dictionary keyed on severity, in a
report built through one path and rendered through the other. Nothing warns:
both names import, both look right, and `is` is false everywhere.

Mixed use is not hypothetical. This repository's own suite reaches for the old
name while the code under test uses the new one, and any caller upgrading a
codebase does the same thing for a while. So the finder below answers for the
whole old prefix, and answers with the module that already exists.

What none of this can fix, and what the upgrade note says out loud: a pickle
written through the *new* path names `vdi2770.validate.…`, and code holding only
the old release cannot read it. No aliasing technique removes that, and hiding
it would only make it the beginning of somebody's investigation.
"""
import importlib
import importlib.abc
import importlib.util
import pathlib
import sys


#: What this distribution says it needs. Read from its own metadata rather than
#: written here: the number lives in one place and this file is not it.
#:
#: The engine is imported *after* this, because importing it is the thing that
#: fails. `vdi2770.validate` does not exist in a reader old enough to matter --
#: `pip install --no-deps` over 0.4 leaves exactly that -- and the import error
#: names a submodule, which reads as a broken installation of this package
#: rather than as an engine that is seven releases behind. A guard cannot
#: depend on what it guards, one layer further out than the last time this
#: project learned it.
def _too_old(engine):
    """Whether the installed engine is older than the release this alias is.

    Only the release segment is compared. A hand-rolled reader of every digit
    in a version string got this wrong in five ways at once -- `0.8.0.post1`,
    `0.8.0rc1`, `0.8.0`, `1.0` against `1.0.0`, `0.8.0+ds1` -- because it
    took the trailing digit of a pre/post/local marker for another release
    component and called a correct engine too old. `packaging` would answer
    properly and the reader declares no dependencies, so what is compared is the
    part that is unambiguous without it: the leading `N.N.N`, zero-padded to the
    same length. Everything from the first non-digit run is ignored, which is
    the same answer for `0.8.0` and `0.8.0.post1` -- deliberately, since an
    alias and its engine differing only in a post-release is not a mismatch.

    It returns `None` on anything it cannot read. A guard that raises is not a
    guard, and this one is reached through a console script where an exception
    is a traceback and an exit of 1 -- this tool's code for a container that has
    findings.
    """
    import re
    from importlib.metadata import PackageNotFoundError, version
    try:
        needs = version("vdi2770-validate")
    except PackageNotFoundError:
        return None                     # not installed as a distribution
    except Exception:                                       # noqa: BLE001
        return None

    def release(v):
        if not isinstance(v, str):
            return None
        m = re.match(r"\s*(?:\d+!)?(\d+(?:\.\d+)*)", v)
        return tuple(int(n) for n in m.group(1).split(".")) if m else None

    have, wanted = release(engine), release(needs)
    if have is None or wanted is None:
        return None
    width = max(len(have), len(wanted))
    have += (0,) * (width - len(have))
    wanted += (0,) * (width - len(wanted))
    return None if have >= wanted else (engine, needs)


import vdi2770 as _reader  # noqa: E402

_behind = _too_old(getattr(_reader, "__version__", "0"))

if _behind is not None:
    # Refuse, and refuse in a shape the console script can carry.
    #
    # Raising here would be honest and useless: pip generates that script as
    # `from vdi2770_validate.entry import run`, so an exception at import is a
    # traceback and an exit of 1 -- this tool's code for *a container has
    # findings*, about a container nobody looked at. The same trap the `cli`
    # module was carrying, one layer further out: a guard that cannot answer
    # through the door it guards has not guarded it.
    #
    # So the alias supplies the one thing that door reaches for, and that thing
    # says what is wrong and hands back 3.
    import types

    # What was measured, and nothing else. An earlier version of this sentence
    # added "and without the module it points at" -- which is a second claim,
    # about a thing the comparison never looked at, and false whenever an old
    # engine happens to carry a `validate` package.
    _said = (f"vdi2770-validate: INSTALLATION: this is an alias for "
             f"`vdi2770.validate`, and the installed `vdi2770` is {_behind[0]}, "
             f"older than the {_behind[1]} this alias stands for. Install them "
             f"together: `pip install --upgrade 'vdi2770[validate]'`.")

    def _refuse(argv=None):
        print(_said, file=sys.stderr)
        return 3

    _entry = types.ModuleType(__name__ + ".entry")
    _entry.run = _refuse
    sys.modules[_entry.__name__] = _entry
    # And on the package, because `import vdi2770_validate.entry` then reaching
    # for the attribute is as ordinary as `from … import entry`.
    sys.modules[__name__].entry = _entry
    # `python -m vdi2770_validate` goes through the real `__main__.py` beside
    # this file, which imports `.entry` and therefore finds the refusal. A
    # fabricated `__main__` module cannot serve it: `runpy` reads `__spec__`,
    # a module made by hand has none, and the ValueError that follows becomes
    # an exit of 1 -- the code that says a container has findings.
else:
    from vdi2770 import validate as _engine

    _OLD = __name__ + "."
    _NEW = _engine.__name__ + "."

    #: The modules that are really here, beside this file. `__main__.py` is one:
    #: `python -m vdi2770_validate` has to find a file with code in it, and a
    #: finder that claims the name and then cannot answer `get_code` turns the
    #: command into an `AttributeError`. Captured before `sys.modules` is
    #: replaced, because after that this package's own `__path__` is the
    #: engine's.
    _MINE = frozenset(
        f.stem for d in list(__path__) for f in pathlib.Path(d).glob("*.py")
        if f.name != "__init__.py")

    class _TheSameModule(importlib.abc.MetaPathFinder, importlib.abc.Loader):
        """Resolves `vdi2770_validate.x.y` to the object `vdi2770.validate.x.y` is.

        A loader whose `create_module` returns an existing module is allowed to,
        and that is the whole trick: the import machinery adopts what it is
        handed instead of executing a file, so the two names index one object.
        """

        def find_spec(self, name, path=None, target=None):
            if not name.startswith(_OLD):
                return None
            # Resolved, not imported. `spec_from_loader` asks a loader that
            # defines `is_package` whether the name is one -- so answering that
            # by importing meant that merely *asking for the spec* of
            # `vdi2770_validate.__main__` executed the module, whose last line
            # is `sys.exit(run())`. `pydoc`, a debugger or anything else that
            # introspects would have run the command line and taken the process
            # with it. `find_spec` on the real name resolves without executing,
            # and a name that is not there gets `None`, so the machinery raises
            # about the name that was actually asked for.
            tail = name[len(_OLD):]
            if tail.split(".")[0] in _MINE:
                return None             # a real file here; the ordinary finder owns it
            real = importlib.util.find_spec(_NEW + tail)
            if real is None:
                return None
            return importlib.util.spec_from_loader(
                name, self,
                is_package=real.submodule_search_locations is not None)

        def create_module(self, spec):
            module = importlib.import_module(_NEW + spec.name[len(_OLD):])
            sys.modules[spec.name] = module
            return module

        def exec_module(self, module):
            """Already executed, under its own name."""

    # Once. Anything that drops this module and imports it again -- the suite
    # does exactly that -- would otherwise stack another finder in front of
    # every import in the process.
    #
    # Marked rather than type-checked: re-executing this module defines a new
    # class, so `isinstance` against it does not recognise the finder the last
    # execution installed, and four of them accumulated in a five-line loop.
    _MARK = "_vdi2770_alias_finder"
    if not any(getattr(f, _MARK, False) for f in sys.meta_path):
        _finder = _TheSameModule()
        setattr(_finder, _MARK, True)
        sys.meta_path.insert(0, _finder)
    sys.modules[__name__] = _engine
