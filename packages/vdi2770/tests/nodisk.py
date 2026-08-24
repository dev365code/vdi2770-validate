"""Watch for a write to disk at the interpreter's own boundary, not at a name.

The guard this replaces monkeypatched `builtins.open`. `io.open` is a separate
binding to the same function, so a reader that used it wrote sixty-four bytes per
container and the whole suite stayed green — while "nothing is extracted to disk"
is claimed in SECURITY.md, both READMEs and the published containment review.

`sys.addaudithook` sees the `open` event whichever name reached it, plus the
`os.*` events that move bytes around without opening anything. A hook cannot be
uninstalled once added, so this one is installed once and gated on a flag; off,
it costs one boolean per event.
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import List, Tuple

_WRITES: List[Tuple[str, str]] = []
_WATCHING = False
_INSTALLED = False

# Events that create or change a file, as opposed to reading one.
_MUTATING = ("os.mkdir", "os.rename", "os.remove", "os.rmdir", "os.link",
             "os.symlink", "os.truncate", "shutil.copyfile", "shutil.copytree",
             "shutil.move", "tempfile.mkstemp", "tempfile.mkdtemp")
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC


def _hook(event: str, args) -> None:
    if not _WATCHING:
        return
    if event == "open":
        path, mode, flags = args
        writing = (mode is not None and set(mode) & set("wax+")) or \
                  (mode is None and isinstance(flags, int) and flags & _WRITE_FLAGS)
        if writing:
            _WRITES.append((event, f"{path!r} mode={mode!r} flags={flags!r}"))
    elif event in _MUTATING:
        _WRITES.append((event, repr(args)))


@contextmanager
def no_disk_writes():
    """Fail if anything inside touches the filesystem in a way that changes it."""
    global _WATCHING, _INSTALLED
    if not _INSTALLED:
        sys.addaudithook(_hook)
        _INSTALLED = True
    _WRITES.clear()
    _WATCHING = True
    try:
        yield _WRITES
    finally:
        _WATCHING = False
    assert not _WRITES, "wrote to disk:\n  " + "\n  ".join(f"{e}: {d}" for e, d in _WRITES)


def hook_is_working() -> bool:
    """The canary. A guard nobody has seen fire is a guard nobody should trust."""
    import tempfile
    seen = []
    global _WATCHING, _INSTALLED
    if not _INSTALLED:
        sys.addaudithook(_hook)
        _INSTALLED = True
    _WRITES.clear()
    _WATCHING = True
    try:
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "canary"), "wb").close()
        seen = list(_WRITES)
    finally:
        _WATCHING = False
        _WRITES.clear()
    return any(e == "open" for e, _ in seen)
