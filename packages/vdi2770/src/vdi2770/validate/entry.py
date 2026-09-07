"""The first thing that runs, and the only thing that may run before the check.

Nothing in this module, or in anything it imports, may touch the reader.

That is not tidiness. `cli` imports `report`, which imports `model`, which
imports `NS`, `UnsafeXml` and `XmlTooLarge` from `vdi2770.xmlread` — so the
command's own import chain depends on the reader's public surface, and the state
this check exists to catch is exactly the state where that surface is not there.
Measured, on a pair built from the index today:

    pip install "vdi2770-validate==0.6.0"      # resolves reader 0.4.0 by range
    pip install --no-deps .                    # rules move, reader does not
    vdi2770-validate --version
    ImportError: cannot import name 'XmlTooLarge' from 'vdi2770.xmlread'
    rc=1

`rc=1` is this tool's code for *a container has findings*. So the confusion the
check was written to prevent happened one step before the check could run, and
said something false about somebody's container on the way past. A guard that
depends on what it guards is not a guard.

So the two doors — the console script and `python -m vdi2770_validate` — come
here first, and here asks one question of two strings before anything is
imported that could fail. A caller who writes `import vdi2770_validate` and
reaches for the rules gets an `ImportError` naming the missing symbol, which is
loud, immediate and unambiguous; that door is documented rather than guarded,
because a library cannot be given an entry point it did not call.
"""
from __future__ import annotations

from typing import Optional


def run(argv: Optional[list] = None) -> int:
    from .agreement import refuse_early
    early = refuse_early()
    if early is not None:
        return early
    # Only now. Everything below this line can need the reader.
    from .cli import _run
    return _run(argv)
