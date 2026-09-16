"""Every text file the tooling and the suite open names an encoding.

`open("f")`, `Path.read_text()`, and `subprocess(..., text=True)` decode with
the platform default: UTF-8 on Linux and macOS, cp1252 on Windows. A file
written as UTF-8 and read back with no `encoding=` is a mojibake bug that shows
up only on Windows -- which is exactly where this suite runs least often, so it
is the wrong place to discover the omission. The repository already passes
`encoding="utf-8"` almost everywhere; this holds the rest of the tooling and
the suite to it, so the next omission fails here and not on a runner nobody is
watching.

Scope is the developer-facing Python -- `tools/` and the test suites. The
shipped package's own file I/O is the same rule and is not swept here;
sweeping it is a change to the reader, and that is a release, not a test
edit.
"""
import ast

from conftest import ROOT

#: Where a contributor and CI read and write text, but not the shipped package.
SCOPE = ("tools", "tests", "packages/vdi2770/tests")


def _text_open_without_encoding(node):
    """`open(...)` in a text mode with no `encoding=`."""
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


def _read_or_write_text_without_encoding(node):
    """`.read_text()` / `.write_text()` with no `encoding=`."""
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("read_text", "write_text")
            and not any(k.arg == "encoding" for k in node.keywords))


def _subprocess_text_without_encoding(node):
    """A subprocess call decoding to text (`text=`/`universal_newlines=` True)
    with no `encoding=`."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("run", "Popen", "check_output", "check_call",
                                    "call")):
        return False
    if any(k.arg == "encoding" for k in node.keywords):
        return False
    return any(k.arg in ("text", "universal_newlines")
               and isinstance(k.value, ast.Constant) and k.value.value is True
               for k in node.keywords)


def _offenders():
    hits = []
    for base in SCOPE:
        for path in sorted((ROOT / base).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (_text_open_without_encoding(node)
                        or _read_or_write_text_without_encoding(node)
                        or _subprocess_text_without_encoding(node)):
                    hits.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
    return hits


def test_every_text_io_names_an_encoding():
    offenders = _offenders()
    assert not offenders, (
        "text I/O with no encoding= decodes as cp1252 on Windows; each of these "
        'wants encoding="utf-8" (or "rb"/"wb" if it is really bytes):\n  '
        + "\n  ".join(offenders))
