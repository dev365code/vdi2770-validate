#!/usr/bin/env python3
"""Open the browser page and hold it to what it says about itself.

    python tools/build_browser.py          # dist/vdi2770.html
    python tools/browser_gates.py          # open it, check everything here, count

The page says it checks a container in the browser, installing nothing and
sending the container nowhere, and that its report is the one the command line
gives. A browser can be made to answer each of those by counting, so this
counts.

* **Nothing is sent.** Every request is counted four ways: by the browser's own
  network events, which see the page and the worker it starts; by the server
  that hands the page out; and by the Resource Timing of the page and of the
  worker, each read from the inside. The count runs from the moment the page
  says it is ready to the moment the last container has been checked, and it has
  to be zero. A counter attached to the wrong thing reads zero as well, so the
  page and the worker are then each made to fetch once and every counter has to
  see it. And two containers are built for the run that ask the reader to reach
  out to that same server -- an external entity and a remote schema -- so the
  door is opened rather than assumed shut.
* **Nothing is fetched to start it.** While it loads, the page asks for nothing
  but itself: the runtime, the reader and the rules travel inside the file.
* **Nothing is installed.** No cookie, no storage, no cache, no service worker,
  no download it did not ask for.
* **The report is the command's.** Every official sample and every container
  here is checked by the page and by the command, with the same arguments, and
  stdout, stderr and the exit code are compared as bytes. Then the same file is
  opened from a disk, the way a downloaded copy is, and asked all of it again.

Exit 0 when all of it holds, 1 when any of it does not, and 2 when it cannot be
asked: no page, no browser, or a command running on another Python from the
page's -- where a difference could not be told apart from the door it came in
through.
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import functools
import http.server
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from collections import namedtuple
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:                     # said below, with what to install
    sync_playwright = None

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "dist" / "vdi2770.html"
SAMPLES = ROOT / "corpus" / "examples"

#: The Playwright this was written against, and the one CI installs.
PLAYWRIGHT = "1.63.0"

NO_BYTECODE = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

#: The command, from this tree, at a UTF-8 console -- the console the page
#: stands for. Spelled out rather than inherited, so that what the comparison
#: runs does not depend on the locale of whichever machine runs it.
COMMAND_ENV = dict(NO_BYTECODE, PYTHONIOENCODING="utf-8", PYTHONPATH=os.pathsep.join(
    [str(ROOT / "src"), str(ROOT / "packages" / "vdi2770" / "src")]))

sys.path.insert(0, str(ROOT / "tools"))
from capture_oracle import containers  # noqa: E402 -- the oracle sweep's own walk


def _the_pages_python():
    """`browser/vdi2770_page.py`, which decides what the page runs.

    Loaded from its file rather than imported by name: it is the page's code and
    lives with the page, and the arguments it builds are the ones this compares
    against -- read from there, not copied here."""
    spec = importlib.util.spec_from_file_location(
        "vdi2770_page", ROOT / "browser" / "vdi2770_page.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


Run = namedtuple("Run", "argv stdout stderr code")


def official_samples() -> list:
    """Every file `corpus/MANIFEST.json` says was copied from the reference
    implementation's examples, archive or not. The manifest rather than a walk
    of the directory, so a stray file on somebody's disk is not a sample."""
    listed = json.loads((ROOT / "corpus" / "MANIFEST.json").read_text(encoding="utf-8"))
    return sorted(SAMPLES / name for name in listed["files"])


def inputs() -> list:
    """What the page and the command are both asked about: the official
    samples, then every container the oracle sweep walks, each once."""
    return list(dict.fromkeys(official_samples() + list(containers())))


def differences(page: Run, cli: Run) -> list:
    """What differs between two runs of one command, stream by stream."""
    if list(page.argv) != list(cli.argv):
        return [f"argv: the page ran {page.argv} and the command {cli.argv}, "
                f"so their outputs say nothing about each other"]
    said = []
    for stream in ("stdout", "stderr"):
        mine, theirs = getattr(page, stream), getattr(cli, stream)
        if mine != theirs:
            said.append(f"{stream}: {_where(mine, theirs)}")
    if page.code != cli.code:
        said.append(f"exit code: the page {page.code}, the command {cli.code}")
    return said


def _where(mine: bytes, theirs: bytes) -> str:
    at = next((n for n, (a, b) in enumerate(zip(mine, theirs)) if a != b),
              min(len(mine), len(theirs)))
    return (f"{len(mine)} bytes from the page, {len(theirs)} from the command, "
            f"first different at byte {at}: page {mine[max(0, at - 30):at + 50]!r}, "
            f"command {theirs[max(0, at - 30):at + 50]!r}")


def blind(expected: dict, seen: dict) -> list:
    """The counters that did not see the requests they were shown.

    A zero from one of these says nothing: it is the reading a counter gives
    when it is attached to the wrong thing."""
    return [name for name, want in expected.items() if seen.get(name, 0) < want]


def unlike(page: dict, here: dict) -> list:
    """What decides a verdict and differs between the page's runtime and the
    command's: the Python, to the minor version, and each package, exactly."""
    out = []
    if page.get("python", "").split(".")[:2] != here.get("python", "").split(".")[:2]:
        out.append("python")
    out += [name for name in ("vdi2770", "xmlschema", "elementpath")
            if page.get(name) != here.get(name)]
    return out


def command(argv, cwd) -> Run:
    done = subprocess.run([sys.executable, "-m", "vdi2770_validate", *argv],
                          cwd=cwd, capture_output=True, timeout=600, env=COMMAND_ENV)
    return Run(list(argv), done.stdout, done.stderr, done.returncode)


def versions_here() -> dict:
    done = subprocess.run(
        [sys.executable, "-c",
         "import json, sys; sys.path.insert(0, sys.argv[1]); import vdi2770_page; "
         "print(json.dumps(vdi2770_page.versions()))", str(ROOT / "browser")],
        capture_output=True, text=True, timeout=120, env=COMMAND_ENV)
    if done.returncode:
        raise SystemExit(f"could not ask this Python what it would run:\n{done.stderr}")
    return json.loads(done.stdout)


class Server:
    """Hands out the page, and writes down every request anybody makes of it."""

    def __init__(self, page: Path):
        self.page, self.seen, self._lock = page, [], threading.Lock()
        handler = functools.partial(_Handler, self)
        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.base = f"http://127.0.0.1:{self._httpd.server_address[1]}/"
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

    def saw(self, path, agent):
        with self._lock:
            self.seen.append((path, agent))

    def count(self):
        with self._lock:
            return len(self.seen)

    def since(self, mark):
        with self._lock:
            return self.seen[mark:]

    def close(self):
        self._httpd.shutdown()
        self._httpd.server_close()


class _Handler(http.server.BaseHTTPRequestHandler):
    def __init__(self, server_record, *args, **kwargs):
        self.record = server_record
        super().__init__(*args, **kwargs)

    def do_GET(self):                         # the name http.server calls
        self.record.saw(self.path, self.headers.get("User-Agent", ""))
        if self.path == "/" + self.record.page.name:
            body = self.record.page.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    do_POST = do_HEAD = do_GET

    def log_message(self, *args):
        pass


#: The two containers `doors` makes, by name, so the run can be asked whether
#: they were in it.
DOORS = ("door-external-entity.zip", "door-remote-schema.zip")


def doors(into: Path, base: str) -> list:
    """Two containers that ask the reader to reach the server this run started.

    Both are the clean sample with one change to its metadata: one declares an
    external entity at the server and uses it, the other points its schema
    location there. A reader that followed either would make a request the
    server writes down, while the page is being counted."""
    clean = SAMPLES / "container" / "documentcontainer.zip"
    meta = "VDI2770_Metadata.xml"
    original = zipfile.ZipFile(clean).read(meta).decode("utf-8")
    entity = original.replace(
        '<?xml version="1.0" encoding="UTF-8"?>\n',
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<!DOCTYPE Document [<!ENTITY pull SYSTEM "{base}door/entity">]>\n', 1).replace(
        '<ClassName Language="en">Technical specification</ClassName>',
        '<ClassName Language="en">&pull;</ClassName>', 1)
    schema = original.replace(
        'xsi:schemaLocation="http://www.vdi.de/schemas/vdi2770 vdi2770.xsd"',
        f'xsi:schemaLocation="http://www.vdi.de/schemas/vdi2770 {base}door/schema.xsd"', 1)
    made = []
    for name, text in zip(DOORS, (entity, schema)):
        if text == original:
            raise SystemExit(f"{name}: the clean sample no longer has the text this "
                             f"door is made by changing, so the door would be shut")
        target = into / name
        with zipfile.ZipFile(clean) as src, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as out:
            for info in src.infolist():
                out.writestr(info, text.encode("utf-8") if info.filename == meta
                             else src.read(info.filename))
        made.append(target)
    return made


#: Read a run out of the page as base64, so the bytes cross unchanged.
READ_RUNS = """(k) => {
  const b64 = (u8) => { let s = "";
    for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
    return btoa(s); };
  return window.vdi2770.runs.slice(k).map(r => ({argv: r.argv, code: r.code,
    stdout: b64(r.stdout), stderr: b64(r.stderr)}));
}"""

TIMING = "performance.getEntriesByType('resource').map(e => e.name)"


def page_runs(page, path: Path) -> list:
    """Hand the page one file through its own file input, as a person does, and
    read back the runs it made of it."""
    k = page.evaluate("window.vdi2770.runs.length")
    page.set_input_files("#file", str(path))
    page.wait_for_function(
        f"window.vdi2770.failed || (window.vdi2770.runs.length >= {k + 2} && !window.vdi2770.busy)",
        timeout=600_000)
    failed = page.evaluate("window.vdi2770.failed")
    if failed:
        raise SystemExit(f"the page failed on {path.name}: {failed}")
    return [Run(r["argv"], base64.b64decode(r["stdout"]), base64.b64decode(r["stderr"]), r["code"])
            for r in page.evaluate(READ_RUNS, k)]


class Watched:
    """One open page, with every counter attached before it loads."""

    def __init__(self, context, url, server):
        self.url, self.server, self.requests, self.downloads, self.console = url, server, [], [], []
        context.on("request", lambda r: self.requests.append(r.url))
        self.page = context.new_page()
        self.page.on("download", lambda d: self.downloads.append(d))
        self.page.on("console", lambda m: self.console.append(m.text))
        self.page.on("pageerror", lambda e: self.console.append(f"page error: {e}"))
        started = time.monotonic()
        self.page.goto(url)
        try:
            self.page.wait_for_function(
                "window.vdi2770 && (window.vdi2770.ready || window.vdi2770.failed)", timeout=180_000)
        except Exception as e:
            raise SystemExit(f"the page did not get ready: {e}\n" + "\n".join(self.console[-20:])) from None
        failed = self.page.evaluate("window.vdi2770.failed")
        if failed:
            raise SystemExit(f"the page could not start: {failed}")
        self.ready_after = time.monotonic() - started
        self.runtime = self.page.evaluate("window.vdi2770.runtime")
        if len(self.page.workers) != 1:
            raise SystemExit(f"the page started {len(self.page.workers)} workers; this counts one")
        self.worker = self.page.workers[0]
        self.loaded = self.mark()

    def mark(self):
        return {"browser": len(self.requests), "server": self.server.count(),
                "page timing": len(self.page.evaluate(TIMING)),
                "worker timing": len(self.worker.evaluate(TIMING))}

    def since(self, mark):
        return {"browser": self.requests[mark["browser"]:],
                "server": [path for path, _ in self.server.since(mark["server"])],
                "page timing": self.page.evaluate(TIMING)[mark["page timing"]:],
                "worker timing": self.worker.evaluate(TIMING)[mark["worker timing"]:]}

    def asked_while_loading(self):
        """What the page fetched before it was ready, other than its own blobs."""
        return [u for u in self.requests[:self.loaded["browser"]]
                if not u.startswith(("blob:", "data:"))]

    def controls(self, base):
        """Make the page and the worker fetch once each, and see who noticed."""
        mark = self.mark()
        self.page.evaluate(f"fetch('{base}control/page').then(r => r.status, e => String(e))")
        self.worker.evaluate(f"fetch('{base}control/worker').then(r => r.status, e => String(e))")
        time.sleep(1)
        wanted = {f"{base}control/page", f"{base}control/worker", "/control/page", "/control/worker"}
        seen = self.since(mark)
        counted = {name: sum(1 for url in urls if url in wanted) for name, urls in seen.items()}
        stray = {name: [u for u in urls if u not in wanted] for name, urls in seen.items()}
        return counted, {name: urls for name, urls in stray.items() if urls}


#: Each counter, and how many of the two control requests it should see: the
#: page's own timing cannot see the worker's, nor the worker's the page's.
CONTROLS = {"browser": 2, "server": 2, "page timing": 1, "worker timing": 1}


def judge(watched, label, todo, expected, base, problems) -> tuple:
    """Every file through one open page; then the counts, then the controls."""
    opened = sorted(path.name for path in todo if path.name in DOORS)
    if opened != sorted(DOORS):
        problems.append(f"{label}: the files checked do not include both containers that ask "
                        f"the reader to reach the server ({', '.join(DOORS)}), so the count "
                        f"below says nothing about a reader that was asked to")
    own = watched.asked_while_loading()
    if own != [watched.url]:
        problems.append(f"{label}: while loading, the page asked for {own}; it should ask "
                        f"for itself and nothing else")
    runs = {path: page_runs(watched.page, path) for path in todo}
    time.sleep(1)
    sent = watched.since(watched.loaded)
    for name, urls in sent.items():
        if urls:
            problems.append(f"{label}: {len(urls)} request(s) after load, seen by the {name} "
                            f"counter: {urls[:5]}")
    counted, stray = watched.controls(base)
    for name in blind(CONTROLS, counted):
        problems.append(f"{label}: the {name} counter did not see the control requests, so "
                        f"the zero it read proves nothing")
    for name, urls in stray.items():
        problems.append(f"{label}: requests beside the controls, seen by the {name} counter: {urls[:5]}")
    if watched.downloads:
        problems.append(f"{label}: the page started {len(watched.downloads)} download(s) by itself")
    compared = 0
    for path in todo:
        for as_json, run in zip((False, True), runs[path]):
            compared += 1
            shown = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path.name
            for line in differences(run, expected[(path, as_json)]):
                problems.append(f"{label}: {shown} ({'--json' if as_json else 'text'}): {line}")
    return runs, compared, sum(len(urls) for urls in sent.values())


def installs_nothing(context, watched, label, problems):
    """No cookie and no storage, and -- where a page could have them at all --
    no service worker and no cache. A document opened from a disk cannot
    register either: the browser refuses the question for it."""
    state = context.storage_state()
    if state.get("cookies") or state.get("origins"):
        problems.append(f"{label}: the page left something stored: {state}")
    if not watched.url.startswith("http"):
        return
    registered = watched.page.evaluate(
        "navigator.serviceWorker ? navigator.serviceWorker.getRegistrations().then(r => r.length) : 0")
    cached = watched.page.evaluate("self.caches ? caches.keys().then(k => k.length) : 0")
    if registered or cached:
        problems.append(f"{label}: service workers {registered}, caches {cached}")


def shows_what_was_compared(watched, last, label, problems):
    """What a person reads and saves is what was compared: the report on the
    page, and the JSON behind its link, for the last file checked."""
    text, as_json = last
    if watched.page.evaluate("document.getElementById('report').textContent") != text.stdout.decode("utf-8"):
        problems.append(f"{label}: the report on the page is not the bytes it was compared on")
    with watched.page.expect_download() as download:
        watched.page.click("#json")
    if Path(download.value.path()).read_bytes() != as_json.stdout:
        problems.append(f"{label}: the JSON a person saves is not the JSON that was compared")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--page", default=str(PAGE))
    ap.add_argument("--only", nargs="*", help="check these files instead of everything here")
    args = ap.parse_args()

    page_file = Path(args.page).resolve()
    if sync_playwright is None:
        print(f"Playwright is not installed. This gate needs it and one browser:\n"
              f"    python -m pip install \"playwright=={PLAYWRIGHT}\"\n"
              f"    python -m playwright install chromium", file=sys.stderr)
        return 2
    if not page_file.is_file():
        print(f"there is no page at {page_file} to judge; build it with "
              f"`python tools/build_browser.py`", file=sys.stderr)
        return 2

    argv_for = _the_pages_python().argv_for
    here = versions_here()
    todo = [Path(p).resolve() for p in args.only] if args.only else inputs()
    problems = []
    server = Server(page_file)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            todo = todo + doors(Path(tmp), server.base)

            # The command first, with the server already up: anything asked of
            # the server now is the command's doing, not the page's.
            mark = server.count()
            jobs = [(path, as_json) for path in todo for as_json in (False, True)]
            with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 2) as pool:
                expected = dict(zip(jobs, pool.map(
                    lambda job: command(argv_for(job[0].name, job[1]), job[0].parent), jobs)))
            if server.since(mark):
                problems.append(f"the command reached the server: {server.since(mark)[:5]}")

            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    for label, url in (("served", server.base + page_file.name),
                                       ("opened from a disk", page_file.as_uri())):
                        context = browser.new_context(accept_downloads=True)
                        watched = Watched(context, url, server)
                        mismatch = unlike(watched.runtime, here)
                        if mismatch:
                            print(f"the page runs {watched.runtime} and the command here {here}; "
                                  f"they differ in {mismatch}, so a difference between their "
                                  f"reports could not be told apart from that. Run this on "
                                  f"Python {watched.runtime['python']} with the same packages.",
                                  file=sys.stderr)
                            return 2
                        runs, compared, sent = judge(watched, label, todo, expected,
                                                     server.base, problems)
                        installs_nothing(context, watched, label, problems)
                        shows_what_was_compared(watched, runs[todo[-1]], label, problems)
                        print(f"{label}: ready in {watched.ready_after:.1f} s; {len(todo)} files, "
                              f"{compared} runs compared with the command; requests after "
                              f"load: {sent}")
                        context.close()
                finally:
                    browser.close()
    finally:
        server.close()

    for line in problems:
        print(f"  {line}", file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} thing(s) the page says about itself did not hold.", file=sys.stderr)
        return 1
    print(f"The page sent nothing after loading, installed nothing, and said what the "
          f"command says about all {len(todo)} files, served and opened from a disk.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
