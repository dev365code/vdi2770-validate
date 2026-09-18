"""Every text file this project opens for itself names an encoding.

`open("f")` and `Path.read_text()/write_text()` decode and encode with the
platform default: UTF-8 on Linux and macOS, cp1252 on Windows. A file this
project writes as UTF-8 and reads back with no `encoding=` is a mojibake bug
that appears only on Windows -- the platform this suite runs on least -- so it
is the wrong place to find out. This holds our own file I/O to an explicit
UTF-8.

**Subprocess is deliberately out of scope.** A `subprocess(..., text=True)`
reading a child's stdout must decode it in the *child's* encoding, which on
Windows is the console code page, not UTF-8: forcing utf-8 there turned an
em-dash (byte 0x97 in cp1252) into a UnicodeDecodeError and reddened
windows-latest while every local gate and a review on macOS stayed green. The
encoding of a child's output belongs to the child; only the encoding of a file
*we* open belongs to us, and that is the line this guard draws.

Scope is every tree: the shipped package, the tooling, and the suites. What is
*not* caught, by choice, so this file does not lie about its reach:
`Path.open()` / `io.open()` (attribute calls -- indistinguishable from a
binary `ZipFile.open()`/`tarfile.open()` without running the code) and a
`text=`/`encoding=` passed as a variable. None exist in a text mode in the
tree today; a future one is a known gap, not a silent one.
"""
import ast

from conftest import ROOT

#: Read from top of the tree down: the package we ship and the code that tests
#: and builds it. (Subprocess output is not a file we open -- see the docstring.)
SCOPE = ("src", "packages/vdi2770/src", "tools", "tests", "packages/vdi2770/tests")


def _builtin_open_without_encoding(node):
    """`open(...)` (the builtin, by name) in a text mode with no `encoding=`."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "open"):
        return False
    if any(k.arg == "encoding" for k in node.keywords):
        return False
    mode = "r"
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
        mode = node.args[1].value
    for k in node.keywords:
        if k.arg == "mode" and isinstance(k.value, ast.Constant):
            mode = k.value.value
    return "b" not in str(mode)


def _read_text_without_encoding(node):
    """`.read_text()` with no `encoding=`.

    A positional argument means this is `importlib.metadata`'s `read_text(name)`,
    which is UTF-8 by contract and takes no `encoding=` -- not `pathlib`'s. Only
    the no-argument `pathlib` form is ours to pin.
    """
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "read_text" and not node.args
            and not any(k.arg == "encoding" for k in node.keywords))


def _write_text_without_encoding(node):
    """`.write_text(content)` with no `encoding=` (`pathlib`; nothing else in
    this tree defines `write_text`)."""
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "write_text"
            and not any(k.arg == "encoding" for k in node.keywords))


def _offenders():
    hits = []
    for base in SCOPE:
        for path in sorted((ROOT / base).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (_builtin_open_without_encoding(node)
                        or _read_text_without_encoding(node)
                        or _write_text_without_encoding(node)):
                    hits.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
    return hits


def test_every_file_we_open_names_an_encoding():
    offenders = _offenders()
    assert not offenders, (
        "text file I/O with no encoding= reads/writes as cp1252 on Windows; add "
        'encoding="utf-8" (or open in binary with "rb"/"wb"):\n  '
        + "\n  ".join(offenders))
