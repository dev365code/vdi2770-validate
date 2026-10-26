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

Needs the network once, to fetch the locked wheels, or their copies via --wheels.
"""
from __future__ import annotations

import argparse
import email
import hashlib
import http.client
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

import bundle_lock

ROOT = Path(__file__).resolve().parents[1]

#: One package now, copied from the tree rather than installed: the readers and
#: the validator are one distribution, and pip has nothing to look up for it.
#: Listing `vdi2770/validate` beside `vdi2770` would copy it twice — once at the
#: top of the archive and once inside its parent — and the copy at the top is
#: the one nothing imports.
PACKAGES = (ROOT / "packages" / "vdi2770" / "src" / "vdi2770",)

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


def verified(data: bytes, sha256: str, what: str) -> bytes:
    got = hashlib.sha256(data).hexdigest()
    if got != sha256:
        raise SystemExit(f"{what} has sha256 {got}, and this build takes only {sha256}. "
                         f"Nothing was built. If the pin is what should move, move it "
                         f"here and say why in the commit.")
    return data


def fetch(url: str, sha256: str, what: str, local: Path | None = None,
          local_option: str = "--wheels DIR") -> bytes:
    if local is not None:
        try:
            data = local.read_bytes()
        except OSError as exc:
            raise SystemExit(f"cannot read {local}: {exc}") from None
        return verified(data, sha256, what)
    try:
        with urllib.request.urlopen(url, timeout=300) as answer:
            data = answer.read()
    except (OSError, http.client.HTTPException) as exc:
        reason = " ".join(str(exc).split())
        raise SystemExit(f"cannot fetch {what} from {url}: {reason}; "
                         f"use a local copy with {local_option}") from None
    return verified(data, sha256, what)


def python_floor() -> str:
    """The lowest Python the project promises, rather than the builder's."""
    manifest = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    found = re.search(r'^requires-python\s*=\s*">=([0-9.]+)"', manifest, re.M)
    if not found:
        raise SystemExit("pyproject.toml declares no requires-python floor")
    return found.group(1)


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


def stage(into: Path, wheels: Path | None = None, notices: list | None = None) -> None:
    """Copy this tree beside only the wheels the bundle lock describes.

    No resolver runs here. Each wheel is checked before anything is unpacked,
    including its declared requirements: a wheel cannot silently extend the
    list of code carried across. Local copies pass exactly the same checks.
    Licence texts are read before the distribution metadata is removed.
    """
    entries = bundle_lock.read_lock()
    checked = []
    for entry in entries:
        data = fetch(entry["url"], entry["sha256"], entry["file"],
                     wheels / entry["file"] if wheels is not None else None)
        if len(data) != entry["size"]:
            raise SystemExit(f"{entry['file']} has size {len(data)}, and this build takes only {entry['size']}")
        bundle_lock.wheel_metadata(data, entry, entries)
        checked.append(data)
    into.mkdir(parents=True, exist_ok=True)
    for package in PACKAGES:
        shutil.copytree(package, into / package.name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for data in checked:
        with zipfile.ZipFile(io.BytesIO(data)) as wheel:
            wheel.extractall(into)
    if notices is not None:
        notices.extend(_notices(into))
    for junk in (list(into.glob("*.dist-info")) + list(into.glob("*.egg-info"))
                 + list(into.rglob("__pycache__"))
                 + [into / "bin", into / "Scripts"]):
        shutil.rmtree(junk, ignore_errors=True)
    (into / "__main__.py").write_text(ENTRY, encoding="utf-8")


def _notices(into: Path) -> list:
    """What each locked wheel says about its own licence."""
    found = []
    for info in sorted(into.glob("*.dist-info")):
        meta = email.message_from_string((info / "METADATA").read_text(encoding="utf-8"))
        texts = {}
        for path in sorted(p for p in info.rglob("*") if p.is_file()):
            rel = path.relative_to(info).as_posix()
            if rel.startswith("licenses/") or re.match(r"(?i)(licen[cs]e|copying|notice)", path.name):
                texts[rel] = path.read_text(encoding="utf-8", errors="replace")
        said = meta.get("License-Expression") or meta.get("License") or ""
        if not said or "\n" in said or len(said) > 60:
            said = next((c.rsplit("::", 1)[-1].strip() for c in meta.get_all("Classifier") or []
                         if c.startswith("License ::")), "see the text below")
        found.append({"name": meta["Name"], "version": meta["Version"], "licence": said,
                      "texts": texts})
    return found


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

from vdi2770.validate.entry import run  # noqa: E402 - after the path is arranged

sys.exit(run())
'''


def create_archive(source: Path, target: Path) -> None:
    """`zipapp.create_archive`, with the order and the timestamps pinned.

    Written out rather than called, because `zipapp` walks the directory in
    whatever order the filesystem hands back and stamps each entry with its
    mtime — two things that make one tree build into two different files.
    Pinned, one tree builds into one file wherever the zlib the building Python
    links compresses alike.
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


def nothing_names_this_machine(pyz: Path, build_dir: Path | None = None) -> int:
    """The bundle says nothing about where it was built.

    Several things, each of which would make two builds differ or would name
    the machine. No entry under `bin/` or `Scripts/` (pip's console scripts,
    whose shebang is an absolute path). No compiled bytecode (`.pyc` or
    `__pycache__`, stamped with a source mtime). And no entry naming a directory
    this build touched -- the tree it copied from, the home of whoever ran it,
    or the temporary directory it staged into -- because a bundle that names a
    filesystem is one two machines cannot produce alike, and it publishes
    whoever built it.

    Checked on the artifact rather than on the staging directory. A staging
    step that stops removing something is exactly the change this has to
    notice, and the artifact is the only place that cannot be argued with.
    """
    said = []
    with zipfile.ZipFile(pyz) as z:
        for name in z.namelist():
            if name.startswith(("bin/", "Scripts/")):
                said.append(f"{name} is a console script pip wrote; its first "
                            f"line is the path of the interpreter that "
                            f"installed it, and a zipapp cannot run it anyway")
            if name.endswith(".pyc") or "__pycache__" in name:
                said.append(f"{name} is compiled bytecode; a `.pyc` embeds the "
                            f"mtime of the source it came from, so a bundle that "
                            f"carries one is not two-machine reproducible")
        needles = [(str(ROOT).encode(), "the directory this was built from"),
                   (str(Path.home()).encode(),
                    "the home directory of whoever built it")]
        if build_dir is not None:
            # The directory the build actually ran in. It is a system temp dir,
            # under neither of the two above on macOS -- where the release file
            # is built -- so without it the check is narrower than it reads.
            needles.append((str(build_dir).encode(),
                            "the temporary directory this build staged into"))
        for name in z.namelist():
            body = z.read(name)
            for needle, what in needles:
                if needle in body:
                    said.append(f"{name} contains {what}")
                    break
    for line in said:
        print(f"  {line}", file=sys.stderr)
    if said:
        print(f"\n{len(said)} thing(s) in the bundle name this machine.",
              file=sys.stderr)
        return 1
    return 0


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
    ap.add_argument("--wheels", type=Path, help="locked wheel files, already downloaded; "
                                             "their digests are checked all the same")
    args = ap.parse_args()

    target = Path(args.output)
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / "app"
        staged.mkdir()
        stage(staged, wheels=args.wheels)
        create_archive(staged, target)

    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    print(f"{target} ({target.stat().st_size:,} bytes)")
    print(f"sha256 {digest}")
    # Always, not only under `--check`: this is a property of the file that is
    # about to be published, and the run that builds a release asset is exactly
    # the run that would skip the checking.
    if nothing_names_this_machine(target, tmp):
        return 1
    return smoke_test(target) if args.check else 0


if __name__ == "__main__":
    raise SystemExit(main())
