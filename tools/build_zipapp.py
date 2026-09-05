#!/usr/bin/env python3
"""Build the single-file form: `vdi2770.pyz`.

Why it exists. VDI 2770 containers are handed over into plant networks, and the
first thing such a network takes away is a route to an index. A wheel still
needs pip, somewhere to fetch from, usually a virtual environment and the rights
to make one. A `.pyz` needs a copy of the file and a Python.

    python vdi2770.pyz check container.zip

Everything is inside it — the rules, the reader, the bundled schema and tables,
and `xmlschema` — and nothing is compiled, so the same file runs on Linux, macOS
and Windows. It is also an ordinary zip: whoever has to approve it before it
crosses the air gap can open it and read every line, which matters more than
convenience when the approval is the hard part.

    python tools/build_zipapp.py                  # dist/vdi2770.pyz
    python tools/build_zipapp.py --check          # build it and run it

Needs the network once, to fetch the one dependency being bundled.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Both first-party packages, copied from the tree rather than installed. The
#: reader is not a dependency to be fetched; it is the other half of the same
#: distribution, and pip has nothing to look up for it.
PACKAGES = (ROOT / "src" / "vdi2770_validate",
            ROOT / "packages" / "vdi2770" / "src" / "vdi2770")

#: A ZIP entry keeps its year as a seven-bit offset from 1980, so a build that
#: inherits file mtimes is reproducible on one machine and nowhere else — the
#: half that does not matter. For a shop that approves a file before carrying it
#: across, "the hash on the release page is the hash of the file I carried in"
#: is the whole trust story. Override with SOURCE_DATE_EPOCH.
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
#: And clamp it. `SOURCE_DATE_EPOCH=0` is the commonest value a reproducible
#: build is handed and it is *outside* what the format can hold; clamping keeps
#: the promise the variable makes where refusing would break the build instead.
ZIP_EARLIEST = (1980, 1, 1, 0, 0, 0)
ZIP_LATEST = (2107, 12, 31, 23, 59, 58)


def _timestamp():
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if not epoch:
        return FIXED_TIMESTAMP
    try:
        stamp = time.gmtime(int(epoch))[:6]
    except (ValueError, OSError, OverflowError):
        # `OverflowError` is neither of the other two: a value large enough
        # gives a year in the millions rather than a stamp, and it used to
        # escape this handler.
        return FIXED_TIMESTAMP
    return min(max(stamp, ZIP_EARLIEST), ZIP_LATEST)


#: Read with a regex rather than a TOML parser. `tomllib` is 3.11+ and this
#: project's floor is 3.9 — a build tool that will not run on the oldest Python
#: the thing it builds supports is a tool nobody can use where it matters.
_MANIFEST = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def python_floor() -> str:
    """The lowest Python this project claims, read from where it is declared.

    Dependencies are resolved against it rather than against the interpreter
    doing the building. A wheel chosen for 3.13 can be one a 3.9 cannot import,
    and the file is meant to be copied to a machine nobody here has seen.
    """
    found = re.search(r'^requires-python\s*=\s*"([^"]+)"', _MANIFEST, re.M)
    if not found:
        raise SystemExit("pyproject.toml declares no requires-python")
    return found.group(1).lstrip(">=~^ ").split(",")[0].strip()


def _distribution_name(spec: str) -> str:
    return re.split(r"[<>=!~\[; ]", spec, maxsplit=1)[0].strip().lower().replace("_", "-")


#: What is copied from the tree instead of fetched. Neither name appears in
#: `dependencies` any more — the reader ships inside this distribution and
#: `vdi2770-validate` is a redirect to it — so this filter matches nothing
#: today. It is kept because the failure it prevents is silent: a first-party
#: name reappearing in that list would fetch a *released* version off an index
#: and put it inside a file built from this working tree, which is the one thing
#: a single-file build must not do, and the built file would still run.
FIRST_PARTY = {"vdi2770", "vdi2770-validate"}


def dependencies() -> list:
    """The runtime dependencies to bundle, as written. Not `pip freeze` of this
    environment: that carries whatever the development extras dragged in."""
    block = re.search(r"^dependencies\s*=\s*\[(.*?)\]", _MANIFEST, re.M | re.S)
    if not block:
        raise SystemExit("pyproject.toml declares no dependencies list")
    return [s for s in re.findall(r'"([^"]+)"', block.group(1))
            if _distribution_name(s) not in FIRST_PARTY]


def stage(into: Path) -> None:
    for package in PACKAGES:
        shutil.copytree(package, into / package.name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
                    "--target", str(into), "--only-binary", ":all:",
                    "--python-version", python_floor(),
                    *dependencies()], check=True,
                   # A subprocess that caches leaves `.pyc` files wherever this
                   # interpreter decided to put them, which is not always
                   # somewhere anything cleans. Spelled out at each call rather
                   # than behind a helper: the gate that checks for this reads
                   # the line, and a function call is not a line it can read.
                   env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    for junk in list(into.glob("*.dist-info")) + list(into.glob("__pycache__")):
        shutil.rmtree(junk, ignore_errors=True)
    (into / "__main__.py").write_text(ENTRY, encoding="utf-8")


#: The entry point — the one part of this file that is not about building.
#:
#: `xmlschema` reads its own meta-schema as a *file*: `SCHEMAS_DIR` is built from
#: `__file__` and handed to a URL opener, which works from a directory on disk
#: and from nowhere else. Our own data goes through `importlib.resources` and
#: needs none of this, but the dependency was never asked.
#:
#: So that one package is unpacked to a temporary directory and put first on the
#: path. Everything still travels in one file; the copy that needs real paths
#: gets them, for as long as the process runs. Without it the tool starts, reads
#: the container, and reports `X0` — the schema check could not run — against a
#: container with nothing wrong.
ENTRY = '''import atexit
import os
import shutil
import sys
import tempfile
import zipfile

_archive = os.path.dirname(os.path.abspath(__file__))
if zipfile.is_zipfile(_archive):
    _room = tempfile.mkdtemp(prefix="vdi2770-")
    atexit.register(shutil.rmtree, _room, ignore_errors=True)
    with zipfile.ZipFile(_archive) as _z:
        _z.extractall(_room, [n for n in _z.namelist() if n.startswith("xmlschema/")])
    sys.path.insert(0, _room)

from vdi2770_validate.cli import _run  # noqa: E402 - after the path is arranged

sys.exit(_run())
'''


def create_archive(source: Path, target: Path) -> None:
    """`zipapp.create_archive`, with the order and the timestamps pinned.

    Written out rather than called, because `zipapp` walks the directory in
    whatever order the filesystem hands back and stamps each entry with its
    mtime — two things that make one tree build into two different files.
    """
    stamp = _timestamp()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as out:
        out.write(b"#!/usr/bin/env python3\n")
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for path in sorted(p for p in source.rglob("*") if p.is_file()):
                info = zipfile.ZipInfo(str(path.relative_to(source)), stamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                z.writestr(info, path.read_bytes())
    target.chmod(0o755)


def smoke_test(pyz: Path) -> int:
    """Run it. Not import it — a file that imports and cannot answer is the
    failure this exists to catch, and the two are easy to confuse."""
    container = ROOT / "corpus" / "examples" / "container" / "documentcontainer.zip"
    done = subprocess.run([sys.executable, str(pyz), "check", str(container)],
                          capture_output=True, text=True, timeout=180,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    if done.returncode != 0 or "0 error(s)" not in done.stdout:
        print(done.stdout + done.stderr, file=sys.stderr)
        print(f"the built file did not check a clean container "
              f"(exit {done.returncode})", file=sys.stderr)
        return 1
    print(f"{pyz.name} checked a clean container and exited 0")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--output", default=str(ROOT / "dist" / "vdi2770.pyz"))
    ap.add_argument("--check", action="store_true", help="build it and run it")
    args = ap.parse_args()

    target = Path(args.output)
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / "app"
        staged.mkdir()
        stage(staged)
        create_archive(staged, target)

    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    print(f"{target} ({target.stat().st_size:,} bytes)")
    print(f"sha256 {digest}")
    return smoke_test(target) if args.check else 0


if __name__ == "__main__":
    raise SystemExit(main())
