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
import sys

from vdi2770 import validate as _engine

_OLD = __name__ + "."
_NEW = _engine.__name__ + "."


class _TheSameModule(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Resolves `vdi2770_validate.x.y` to the object `vdi2770.validate.x.y` is.

    A loader whose `create_module` returns an existing module is allowed to,
    and that is the whole trick: the import machinery adopts what it is handed
    instead of executing a file, so the two names index one object.
    """

    def find_spec(self, name, path=None, target=None):
        if not name.startswith(_OLD):
            return None
        return importlib.util.spec_from_loader(name, self)

    def create_module(self, spec):
        module = importlib.import_module(_NEW + spec.name[len(_OLD):])
        sys.modules[spec.name] = module
        return module

    def exec_module(self, module):
        """Already executed, under its own name."""

    # `runpy` asks a loader for code rather than for a module, so
    # `python -m vdi2770_validate` reaches past `create_module` entirely and
    # calls these. Both answer about the module the old name stands for.
    def _real(self, name):
        return importlib.import_module(_NEW + name[len(_OLD):])

    def get_code(self, name):
        real = self._real(name)
        return real.__loader__.get_code(real.__name__)

    def is_package(self, name):
        return hasattr(self._real(name), "__path__")


sys.meta_path.insert(0, _TheSameModule())
sys.modules[__name__] = _engine
