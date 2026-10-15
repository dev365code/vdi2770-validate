"""What the page runs: the command's own entry point, on the file it was handed.

Nothing here decides anything about a container. The page saves the bytes it was
given under the name they came with, calls the function the console script
calls with the arguments somebody would type, and keeps exactly what that
function wrote to each stream and the code it ended with. The command's report
is the page's report; there is no second rendering of it to keep in step with
the first.

It runs inside the browser, on the Python the page carries -- `tools/build_browser.py`
puts it there -- and on any other Python as well, which is how the suite holds
it to the command without a browser.
"""
from __future__ import annotations

import io
import os
import sys
import traceback

#: Where a file the page was handed is put: the runtime's own filesystem, which
#: lives in the tab's memory. Nothing written here reaches the machine's disk.
ROOM = "/work"


def argv_for(name: str, as_json: bool) -> list:
    """What somebody at a console types to check this file where it is.

    `--no-bundle`: a diagnostic bundle written into the tab's memory is a file
    nobody could open, so the page asks for none, the way the command is asked
    for none. A name that begins with `-` would be read as an option, so it is
    passed as `./name`, as it is at a shell.
    """
    path = "./" + name if name.startswith("-") else name
    return ["check", "--no-bundle", *(["--json"] if as_json else []), path]


def check(name: str, data, as_json: bool, room: str = ROOM):
    """Check `data` as the file `name`; return (argv, stdout, stderr, exit code).

    The streams are bytes, as a process's are. The exit code is the one a process
    running the command would end with.
    """
    if name in ("", ".", "..") or "/" in name or "\0" in name:
        raise ValueError(f"not the name of a file: {name!r}")
    from vdi2770.validate import entry

    argv = argv_for(name, as_json)
    os.makedirs(room, exist_ok=True)
    target = os.path.join(room, name)
    with open(target, "wb") as fh:
        fh.write(bytes(data))
    out, err = _console(), _console()
    streams, here = (sys.stdout, sys.stderr), os.getcwd()
    try:
        sys.stdout, sys.stderr = out, err
        os.chdir(room)
        code = _exit_status(entry.run, list(argv))
    finally:
        sys.stdout, sys.stderr = streams
        os.chdir(here)
        os.remove(target)
    out.flush()
    err.flush()
    return argv, out.buffer.getvalue(), err.buffer.getvalue(), code


def versions() -> dict:
    """What decides a verdict here, so a comparison can check it compares like
    with like before it compares anything."""
    import elementpath
    import xmlschema

    import vdi2770

    return {"python": ".".join(str(n) for n in sys.version_info[:3]), "vdi2770": vdi2770.__version__,
            "xmlschema": xmlschema.__version__, "elementpath": elementpath.__version__}


def _console():
    """A UTF-8 console that ends a line the way this platform's console does.

    CPython's own streams write `\\n` everywhere but Windows, where they write
    `\\r\\n`, and leaving `newline` unset asks for exactly that. In the browser
    the runtime is a POSIX one, so the page writes `\\n`, as the command does on
    the machine it is compared against there.
    """
    return io.TextIOWrapper(io.BytesIO(), encoding="utf-8", write_through=True)


def _exit_status(run, argv) -> int:
    """`sys.exit(run(argv))`, as the interpreter finishes it.

    The console script hands `run`'s result to `sys.exit`, and argparse ends a
    run by raising `SystemExit` itself; a process turns both into a status, and
    a traceback into status 1 with the traceback on stderr. The page is not a
    process, so it does the same here.
    """
    try:
        code = run(argv)
    except SystemExit as stop:
        code = stop.code
        if code is not None and not isinstance(code, int):
            print(code, file=sys.stderr)
            return 1
    except BaseException:                # as the interpreter does, everything
        traceback.print_exc()
        return 1
    return 0 if code is None else code
