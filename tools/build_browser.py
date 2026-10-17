#!/usr/bin/env python3
"""Build the browser form: `vdi2770.html`, one page that checks a container where it is opened.

Why it exists. The single file still needs a Python, and a machine that may not
have one installed may still have to look at a delivery. A browser is on every
such machine, and a page that runs the check inside the tab takes the container
nowhere: it is read where the page is open.

    python tools/build_browser.py                    # dist/vdi2770.html
    python tools/build_browser.py --runtime FILE     # with the runtime release already here

Everything the check needs is inside the page: the reader and the rules, copied
from this tree the way the single file copies them; `xmlschema`; and Pyodide, a
build of CPython that runs in the browser, with its standard library. The page
asks for nothing to start. Opened from a disk it makes no request at all, and
served it makes one, for itself. `tools/browser_gates.py` holds it to that, and
to giving the command's report byte for byte.

Needs the network once, as the single file does: for the runtime, which is
pinned by its digest and refused if it differs, its licences, and the one
dependency.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import html
import io
import re
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BROWSER = ROOT / "browser"
sys.path.insert(0, str(ROOT / "tools"))
import build_zipapp  # noqa: E402 -- one staging for both single-file forms

#: The runtime. A Pyodide release is a build of CPython for the browser, and the
#: page carries five files of it. The digest is the release asset's as
#: published; a download that differs from it is refused, not built.
RUNTIME = {
    "name": "Pyodide",
    "version": "0.29.5",
    "python": "3.13.2",
    "url": "https://github.com/pyodide/pyodide/releases/download/0.29.5/pyodide-core-0.29.5.tar.bz2",
    "sha256": "ab08aafc11a3c9a0fe73825eb2cec78bda9464348dd17414e7ec0132ef3451e8",
}
RUNTIME_FILES = ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip",
                 "pyodide-lock.json")

#: The notices of what the runtime is built from, at the revisions it was built
#: from. The release asset carries none of them, so they are fetched, pinned the
#: same way, and printed in the page. Not only Pyodide and CPython: the `.wasm`
#: has compiled into it what CPython incorporates -- expat, libmpdec, zlib,
#: HACL* and the rest its licence page lists -- and, from the build Pyodide made
#: of it (its `Makefile.envs` and `cpython/Makefile` at that tag), Pyodide's
#: hiwire, libffi at the commit it names, and Emscripten 4.0.9 with the musl it
#: carries and its port of bzip2. `revision` is the tag or commit each is read
#: at; `between` cuts a notice out of a source file that keeps it at its head.
RUNTIME_LICENCES = (
    {"name": "Pyodide", "notice": "Pyodide", "version": "0.29.5", "revision": "0.29.5",
     "licence": "MPL-2.0", "file": "LICENSE",
     "source": "https://github.com/pyodide/pyodide/tree/0.29.5",
     "url": "https://raw.githubusercontent.com/pyodide/pyodide/0.29.5/LICENSE",
     "sha256": "1f256ecad192880510e84ad60474eab7589218784b9a50bc7ceee34c2b91f1d5"},
    {"name": "hiwire, which Pyodide compiles into the runtime", "notice": "hiwire",
     "version": "6a1e672", "revision": "6a1e67280a15d929ebeceee54a6358c9c8d5f697",
     "licence": "MPL-2.0", "file": "LICENSE",
     "source": "https://github.com/pyodide/hiwire/tree/6a1e67280a15d929ebeceee54a6358c9c8d5f697",
     "url": "https://raw.githubusercontent.com/pyodide/hiwire/"
            "6a1e67280a15d929ebeceee54a6358c9c8d5f697/LICENSE",
     "sha256": "1f256ecad192880510e84ad60474eab7589218784b9a50bc7ceee34c2b91f1d5"},
    {"name": "CPython, with its standard library", "notice": "CPython", "version": "3.13.2",
     "revision": "v3.13.2", "licence": "PSF-2.0", "file": "LICENSE",
     "source": "https://github.com/python/cpython/tree/v3.13.2",
     "url": "https://raw.githubusercontent.com/python/cpython/v3.13.2/LICENSE",
     "sha256": "78b12c3a81360b357002334f0e70ea0e92eebf7a9b358805c03c48484945f3bb"},
    {"name": "What CPython incorporates: expat, libffi, zlib, libmpdec, mimalloc and the "
             "rest its licence page lists", "notice": "CPython incorporates",
     "version": "3.13.2", "revision": "v3.13.2", "licence": "each one's own, as given there",
     "file": "Doc/license.rst",
     "source": "https://github.com/python/cpython/tree/v3.13.2",
     "url": "https://raw.githubusercontent.com/python/cpython/v3.13.2/Doc/license.rst",
     "sha256": "62f2c9c2c75d511170eb464ad5f83b78cc1f37eb2eb49c2846c9aa6c4557ee99"},
    {"name": "HACL*, as CPython carries it", "notice": "HACL*", "version": "3.13.2",
     "revision": "v3.13.2", "licence": "MIT", "file": "Modules/_hacl/Hacl_Hash_SHA2.c, its notice",
     "source": "https://github.com/python/cpython/tree/v3.13.2/Modules/_hacl",
     "url": "https://raw.githubusercontent.com/python/cpython/v3.13.2/Modules/_hacl/Hacl_Hash_SHA2.c",
     "between": ("/* MIT License", "*/"),
     "sha256": "30638efb75c8b185bb09c3df6977e3f3c5d21a1e696218cf7ade6bc4d5201b31"},
    {"name": "libffi, which Pyodide compiles into the runtime", "notice": "libffi",
     "version": "f08493d", "revision": "f08493d249d2067c8b3207ba46693dd858f95db3",
     "licence": "MIT", "file": "LICENSE",
     "source": "https://github.com/libffi/libffi/tree/f08493d249d2067c8b3207ba46693dd858f95db3",
     "url": "https://raw.githubusercontent.com/libffi/libffi/"
            "f08493d249d2067c8b3207ba46693dd858f95db3/LICENSE",
     "sha256": "2c9c2acb9743e6b007b91350475308aee44691d96aa20eacef8e199988c8c388"},
    {"name": "bzip2, as Emscripten's port builds it", "notice": "bzip2", "version": "1.0.6",
     "revision": "1.0.6", "licence": "bzip2's own, BSD-style", "file": "LICENSE",
     "source": "https://github.com/emscripten-ports/bzip2/tree/1.0.6",
     "url": "https://raw.githubusercontent.com/emscripten-ports/bzip2/1.0.6/LICENSE",
     "sha256": "4919cfb14a73cd64fcef67b107613970cf1659a09aa675dba31314f373bc7204"},
    {"name": "Emscripten, the compiler and runtime the build used", "notice": "Emscripten",
     "version": "4.0.9", "revision": "4.0.9", "licence": "MIT or University of Illinois/NCSA",
     "file": "LICENSE",
     "source": "https://github.com/emscripten-core/emscripten/tree/4.0.9",
     "url": "https://raw.githubusercontent.com/emscripten-core/emscripten/4.0.9/LICENSE",
     "sha256": "620a78084fc7ca97c0b5dea9abf891f3ffcadfdbf305276f099c9c4e12fc1d86"},
    {"name": "musl, the C library Emscripten carries", "notice": "musl", "version": "4.0.9",
     "revision": "4.0.9", "licence": "MIT", "file": "COPYRIGHT",
     "source": "https://github.com/emscripten-core/emscripten/tree/4.0.9/system/lib/libc/musl",
     "url": "https://raw.githubusercontent.com/emscripten-core/emscripten/4.0.9/"
            "system/lib/libc/musl/COPYRIGHT",
     "sha256": "f9bc4423732350eb0b3f7ed7e91d530298476f8fec0c6c427a1c04ade22655af"},
)

#: The places in `browser/page.html` this fills, each exactly once.
MARKS = ("@@TITLE@@", "@@VERSION@@", "@@LICENCES@@", "@@ASSETS@@", "@@WORKER@@")

#: This project's own notices, as the engine's wheel carries them.
OWN_NOTICES = ("LICENSE", "NOTICE", "THIRD_PARTY.md")


def verified(data: bytes, sha256: str, what: str) -> bytes:
    got = hashlib.sha256(data).hexdigest()
    if got != sha256:
        raise SystemExit(f"{what} has sha256 {got}, and this build takes only {sha256}. "
                         f"Nothing was built. If the pin is what should move, move it "
                         f"here and say why in the commit.")
    return data


def fetch(url: str, sha256: str, what: str, local: Path | None = None) -> bytes:
    if local is not None:
        return verified(local.read_bytes(), sha256, what)
    with urllib.request.urlopen(url, timeout=300) as answer:
        return verified(answer.read(), sha256, what)


def runtime_files(tarball: bytes) -> dict:
    """The files the page needs, out of the release asset, by the names the
    runtime's loader asks for."""
    found = {}
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:bz2") as tar:
        for name in RUNTIME_FILES:
            try:
                member = tar.getmember(f"pyodide/{name}")
            except KeyError:
                raise SystemExit(f"the runtime release has no pyodide/{name}") from None
            found[name] = tar.extractfile(member).read()
    return found


def script_safe(text: str, what: str) -> str:
    """Text that can sit inside a `<script>` element without ending it early."""
    if re.search(r"</script|<!--", text, re.IGNORECASE):
        raise SystemExit(f"{what} contains `</script` or `<!--`, which would end or "
                         f"change the script element it is put in")
    return text


def assemble(template: str, fills: dict) -> str:
    """Fill each place in the page once, and refuse a page that has a place
    twice, or not at all, or a fill that would itself be read as a place."""
    for mark in MARKS:
        n = template.count(mark)
        if n != 1:
            raise SystemExit(f"{mark} appears {n} times in the page; each place is filled once")
    for mark, text in fills.items():
        if any(other in text for other in MARKS):
            raise SystemExit(f"what fills {mark} contains a place of its own")
    for mark in MARKS:
        template = template.replace(mark, fills[mark])
    return template


def version() -> str:
    source = (ROOT / "packages" / "vdi2770" / "src" / "vdi2770" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'^__version__ = "([^"]+)"', source, re.M).group(1)


def app_archive(staged: Path, into: Path) -> bytes:
    """The staged tree as one zip, entries in name order, every stamp the same,
    so one tree builds into one page."""
    stamp = build_zipapp._timestamp()
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(p for p in staged.rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(path.relative_to(staged).as_posix(), stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, path.read_bytes())
    into.write_bytes(raw.getvalue())
    return raw.getvalue()


def notice_text(data: bytes, between=None) -> str:
    """The notice a fetched file holds: all of it, or the part from the first
    `between[0]` to the `between[1]` after it."""
    text = data.decode("utf-8")
    if between is None:
        return text
    start = text.index(between[0])
    return text[start:text.index(between[1], start) + len(between[1])]


def licences_html(bundled: list, runtime: list) -> str:
    """Each component, its version, its licence, where its source is, and the
    licence text itself."""
    parts = []

    def one(title, licence, source, texts):
        parts.append(f"<p><strong>{html.escape(title)}</strong> &mdash; {html.escape(licence)}"
                     + (f" &mdash; source: {html.escape(source)}" if source else "") + "</p>")
        for name, text in texts.items():
            parts.append(f"<pre aria-label=\"{html.escape(name)}\">{html.escape(text)}</pre>")

    one(f"vdi2770-validate {version()}: this page, the reader, the rules and their data",
        "Apache-2.0, with the material THIRD_PARTY.md lists",
        "https://github.com/dev365code/vdi2770-validate",
        {name: (ROOT / "packages" / "vdi2770" / name).read_text(encoding="utf-8")
         for name in OWN_NOTICES})
    for entry in runtime:
        one(f"{entry['name']} {entry['version']}", entry["licence"], entry["source"],
            {entry["file"]: entry["text"]})
    one(f"{RUNTIME['name']} {RUNTIME['version']} release asset",
        f"sha256 {RUNTIME['sha256']}", RUNTIME["url"], {})
    for dist in bundled:
        one(f"{dist['name']} {dist['version']}", dist["licence"],
            f"https://pypi.org/project/{dist['name']}/{dist['version']}/", dist["texts"])
    return "\n".join(parts)


def build(output: Path, runtime_asset: Path | None = None) -> bytes:
    runtime = runtime_files(fetch(RUNTIME["url"], RUNTIME["sha256"],
                                  f"the {RUNTIME['name']} {RUNTIME['version']} release",
                                  runtime_asset))
    licences = [dict(entry, text=notice_text(fetch(entry["url"], entry["sha256"],
                                                   f"the {entry['notice']} notice"),
                                             entry.get("between")))
                for entry in RUNTIME_LICENCES]
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / "app"
        staged.mkdir()
        bundled = []
        build_zipapp.stage(staged, python_version=".".join(RUNTIME["python"].split(".")[:2]),
                           notices=bundled)
        (staged / "__main__.py").unlink()
        (staged / "vdi2770_page.py").write_bytes((BROWSER / "vdi2770_page.py").read_bytes())
        archive = Path(tmp) / "app.zip"
        app = app_archive(staged, archive)
        if build_zipapp.nothing_names_this_machine(archive, tmp):
            raise SystemExit("the page would name the machine that built it; nothing was written")

    assets = dict(runtime, **{"app.zip": app})
    blocks = "\n".join(
        f'<script type="application/gzip" data-asset="{name}">'
        f'{base64.b64encode(gzip.compress(data, compresslevel=9, mtime=0)).decode("ascii")}'
        f'</script>'
        for name, data in assets.items())
    page = assemble((BROWSER / "page.html").read_text(encoding="utf-8"), {
        "@@TITLE@@": f"vdi2770-validate {version()} — check a VDI 2770 container in this browser",
        "@@VERSION@@": version(),
        "@@LICENCES@@": licences_html(bundled, licences),
        "@@ASSETS@@": blocks,
        "@@WORKER@@": script_safe((BROWSER / "worker.js").read_text(encoding="utf-8"), "the worker"),
    }).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(page)
    return page


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--output", default=str(ROOT / "dist" / "vdi2770.html"))
    ap.add_argument("--runtime", help="the runtime release asset, already downloaded; "
                                      "its digest is checked all the same")
    args = ap.parse_args()
    target = Path(args.output)
    page = build(target, Path(args.runtime) if args.runtime else None)
    print(f"{target} ({len(page):,} bytes)")
    print(f"sha256 {hashlib.sha256(page).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
