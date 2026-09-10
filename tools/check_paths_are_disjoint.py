#!/usr/bin/env python3
"""No two distributions here claim a path, a command, or an import name.

The manifest gate compares what two manifests *say*. This compares what the
artifacts *are*, and against what is already on the index — which is the
comparison that matters, because the destruction happens between a release and
whatever an installation already has, not between two files in one working tree.

**Why paths.** pip uninstalls a distribution by the record it wrote at install
time: every path in that record is deleted. If two distributions ever write the
same path, installing the second overwrites the first's file and removing either
one deletes a file the other is still using. Nothing warns. `pip check` stays
green. The tool stops running.

**Why not the RECORD alone.** A wheel's RECORD has no `bin/` entries at all —
measured: zero. pip synthesises the console scripts at install time from
`entry_points.txt`, so a comparison of RECORDs is blind to exactly the files
that vanished first when this project last destroyed an installation. The
comparison here is therefore three sets at once:

  * every path the wheel records,
  * every console script name it declares, parsed out of `entry_points.txt`
    rather than pattern-matched, because a name is a section entry and not a
    substring, and
  * every top-level import name it ships, which is the directory pip would
    remove and the name a second distribution would shadow.

**Which pairs.** Only across distribution *names*. Two versions of one
distribution share their paths by design — that is pip replacing its own — and
demanding otherwise would fail every release. What must never overlap is
`vdi2770` against `vdi2770-validate`, in every combination of what this tree
builds and what the index already serves.

Outside `make check` because it needs the network: the published wheels are the
other half of the comparison, and a check that only ever reads the working tree
is a check on a state nobody is changing.
"""
from __future__ import annotations

import configparser
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from packaging.utils import parse_sdist_filename, parse_wheel_filename
from packaging.version import Version

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = (ROOT, ROOT / "packages" / "vdi2770")

#: Both names, and every release the index serves under them.
#:
#: The comparison that matters is against what people already have, and what
#: they have is anything that was ever published: an installation of 0.6 is
#: upgraded by the same command as one of the newest release. This used to be a
#: constant naming the newest release, and the next release left it comparing
#: against the one before -- green, because nothing collided with that either.
#: A number written here is right until the next upload, so the list is asked
#: for instead.
NAMES = ("vdi2770", "vdi2770-validate")

#: The index in the form pip reads it (PEP 691). What matters is what
#: `pip install` would fetch, and this is the page it fetches it from. It is
#: pypi.org itself rather than whatever index pip is configured to use here:
#: the question is what everybody else installs.
SIMPLE = "https://pypi.org/simple/{name}/"

#: Seconds to wait before each attempt at one request. This used to be two
#: `pip download` calls, and pip tries a failed request again; twenty requests
#: with no second try would turn one dropped connection into a red run.
ATTEMPTS = (0, 2, 5)

NO_BYTECODE = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def _build(project: Path, out: Path) -> Path:
    for stale in list(project.glob("**/*.egg-info")) + [project / "build"]:
        shutil.rmtree(stale, ignore_errors=True)
    done = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(out), str(project)],
        env=NO_BYTECODE, capture_output=True, text=True)
    if done.returncode:
        print(done.stdout[-2000:], done.stderr[-2000:], file=sys.stderr)
        raise SystemExit(f"{project.name}: could not build a wheel")
    made = sorted(out.glob("*.whl"))
    if len(made) != 1:
        raise SystemExit(f"{project.name}: expected one wheel, found {made}")
    return made[0]


def _ask(name: str, timeout: float = 15.0) -> dict:
    """What the index says about `name`.

    `no-cache` asks any cache on the way not to answer from what it stored
    (RFC 9111 §5.2.1.4 -- a preference the client states, not a rule a cache
    must follow). PyPI's own CDN does not follow it: measured, the same request
    twice came back `x-cache: MISS, HIT, HIT` under `max-age=600`, and a query
    string nobody else sends was answered from the cache too. So this can see
    the index as it was up to ten minutes ago, unless the index clears that
    cache when a file is uploaded -- which is not something this can observe.
    """
    request = urllib.request.Request(SIMPLE.format(name=name), headers={
        "Accept": "application/vnd.pypi.simple.v1+json",
        "Cache-Control": "no-cache",
    })
    try:
        return json.loads(_read(request, timeout))
    except Exception as e:                       # noqa: BLE001 - the network is the risk
        raise SystemExit(f"could not ask the index about {name}: {e}. The "
                         f"published wheels are half of this comparison, and "
                         f"without them there is nothing to compare against") from e


def _read(request, timeout: float) -> bytes:
    """The body of one response, asked for again after a failure that may pass."""
    for wait in ATTEMPTS:
        time.sleep(wait)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as r:
                return r.read()
        except Exception as e:                   # noqa: BLE001 - the network is the risk
            failed = e
    raise failed


def wheels_in(name: str, answer) -> list:
    """`(filename, url, sha256)` for every wheel the index lists under `name`.

    Each refusal below is a way the comparison could come out smaller than what
    is published without saying so -- and a comparison against nothing passes:

      * an answer this cannot read, down to one entry of it;
      * a file listed twice, where the second download would replace the
        first and the first archive would never be read;
      * a file without a digest, which could not be checked after download;
      * a release with no wheel -- whether the index lists it under
        `versions` (PEP 700) or only by its source archive. pip would build
        that one, and what it installs is not something this can read out of
        a wheel;
      * no wheel at all.

    A yanked release stays in. pip still installs it when it is pinned, and
    whoever has it upgrades with the same command as everybody else.
    """
    if not isinstance(answer, dict) or not isinstance(answer.get("files"), list):
        raise SystemExit(f"the index answered about {name} without a list of "
                         f"files, so this cannot tell what is published")
    found, versions, seen = [], set(), set()
    try:
        listed = {Version(v) for v in answer.get("versions", [])}
        for entry in answer["files"]:
            filename = entry["filename"]
            if filename in seen:
                raise SystemExit(f"the index lists {filename} twice. The second "
                                 f"download would replace the first, and one of "
                                 f"the two archives would never be read")
            seen.add(filename)
            if not filename.endswith(".whl"):
                listed.add(parse_sdist_filename(filename)[1])
                continue
            digest = (entry.get("hashes") or {}).get("sha256")
            if not digest:
                raise SystemExit(f"the index lists {filename} without a sha256, "
                                 f"and a download that cannot be checked is not "
                                 f"compared")
            versions.add(parse_wheel_filename(filename)[1])
            found.append((filename, urllib.parse.urljoin(SIMPLE.format(name=name),
                                                         entry["url"]), digest))
    except (AttributeError, KeyError, TypeError, ValueError) as e:
        raise SystemExit(f"the index answered about {name} in a shape this cannot "
                         f"read ({e!r}), so it cannot tell what is published") from e
    missing = sorted(listed - versions)
    if missing:
        raise SystemExit(f"the index lists {name} {', '.join(map(str, missing))} "
                         f"with no wheel. pip would build it, and this gate reads "
                         f"what a wheel installs -- it cannot say what that "
                         f"release puts on a disk until the index has a wheel "
                         f"for it")
    if not found:
        raise SystemExit(f"the index lists no wheel for {name}. A comparison "
                         f"against nothing passes, so this refuses instead")
    return found


def _fetch(url: str, digest: str, dest: Path) -> Path:
    """The file the index published, or a refusal naming why it is not."""
    try:
        data = _read(url, 60)
    except Exception as e:                       # noqa: BLE001 - the network is the risk
        raise SystemExit(f"could not fetch {dest.name}: {e}") from e
    if hashlib.sha256(data).hexdigest() != digest:
        raise SystemExit(f"{dest.name} is not the file the index published -- "
                         f"its digest differs from the one the index gave. "
                         f"Comparing it would answer a question about some other "
                         f"archive")
    dest.write_bytes(data)
    return dest


def claims(wheel: Path) -> tuple:
    """`(distribution, {what it would own})`.

    Three kinds of claim in one set, each prefixed by what it is, so a message
    naming a collision says which kind it is rather than printing two strings
    that look alike.
    """
    owned = set()
    with zipfile.ZipFile(wheel) as z:
        names = z.namelist()
        info = next((n for n in names if n.endswith(".dist-info/METADATA")), None)
        if info is None:
            raise SystemExit(f"{wheel.name}: no .dist-info/METADATA")
        distribution = _normalised(info.split("/")[0].rsplit("-", 2)[0])
        for name in names:
            if name.endswith("/"):
                continue
            top = name.split("/")[0]
            if top.endswith(".dist-info"):
                owned.add(f"path {name}")
                continue
            if top.endswith(".data"):
                # A wheel installs `{dist}-{ver}.data/scripts/x` as `bin/x` and
                # `{dist}-{ver}.data/purelib/y` as `y` in site-packages. Recorded
                # verbatim, two distributions installing one `bin/vdi2770-validate`
                # that way claim two different strings and collide anyway -- and
                # a console script is the file that went first the last time an
                # installation here was destroyed. What is compared is where the
                # thing lands, not where it sits in the archive.
                rest = name.split("/", 2)[2] if name.count("/") >= 2 else ""
                where = name.split("/")[1] if name.count("/") >= 1 else ""
                if not rest:
                    continue
                if where == "scripts":
                    owned.add(f"command {rest}")
                else:
                    owned.add(f"path {rest}")
                    owned |= _import_name(rest)
                continue
            owned.add(f"path {name}")
            owned |= _import_name(name)
        entry = next((n for n in names if n.endswith(".dist-info/entry_points.txt")), None)
        if entry is not None:
            # Parsed. `console_scripts` is a section and a name is an option in
            # it; searching the text for a string finds the same name inside a
            # comment, inside another section, and inside the module path on the
            # right-hand side.
            parser = configparser.ConfigParser()
            parser.read_file(io.StringIO(z.read(entry).decode("utf-8")))
            for section in ("console_scripts", "gui_scripts"):
                if parser.has_section(section):
                    for command in parser.options(section):
                        owned.add(f"command {command}")
    return distribution, owned


def _normalised(name: str) -> str:
    """PEP 503, so two spellings of one distribution are one distribution.

    A dist-info directory is written `vdi2770_validate-…` by current setuptools
    and `vdi2770-validate-…` by older ones. Compared as written, the built alias
    and the published alias read as two distributions and every path they share
    -- which is all of them -- is a collision, reddening every release. The
    other way round, two genuinely different names that normalise alike would be
    skipped in silence.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def _import_name(path: str) -> set:
    """The top-level name an installed file occupies, if it is one.

    Only a directory with an `__init__.py` claims its name: PEP 420 lets two
    distributions share a namespace package on purpose, and pip removes only the
    files it recorded, so reporting that as a collision would block the very
    layout this project is moving to.
    """
    head, _, rest = path.partition("/")
    if not rest:
        return {f"import {head[:-3]}"} if head.endswith(".py") else set()
    return {f"import {head}"} if rest == "__init__.py" else set()


def overlaps(wheels: list, served: list = ()) -> list:
    """Every pair of different distributions in which both claim one thing.

    `wheels` are compared with each other and with every wheel in `served`.
    Two wheels in `served` are not compared with each other: a collision
    between two releases already on the index is a fact no tree can change,
    and failing on it would fail every release that followed. What a release
    does to what people already have is a pair with one of its own wheels in it.
    """
    said = []
    read = [claims(w) + (w.name,) for w in wheels]
    history = [claims(w) + (w.name,) for w in served]
    for i, (name_a, owned_a, file_a) in enumerate(read):
        for name_b, owned_b, file_b in read[i + 1:] + history:
            if name_a == name_b:
                # Two versions of one distribution. pip replaces its own files;
                # requiring these to be disjoint would fail every release.
                continue
            both = owned_a & owned_b
            if both:
                said.append(
                    f"{file_a} ({name_a}) and {file_b} ({name_b}) both claim "
                    + ", ".join(sorted(both)[:6])
                    + (f" and {len(both) - 6} more" if len(both) > 6 else "")
                    + ". Installing one overwrites the other's files, and "
                      "uninstalling either deletes what the other still uses.")
    return said


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        wheels = []
        for n, project in enumerate(PROJECTS):
            here = out / f"built{n}"
            here.mkdir()
            try:
                wheels.append(_build(project, here))
            finally:
                for stale in (list(project.glob("**/*.egg-info"))
                              + [project / "build"]):
                    shutil.rmtree(stale, ignore_errors=True)
        served, summary = [], []
        for name in NAMES:
            here = out / f"index-{name}"
            here.mkdir()
            listed = wheels_in(name, _ask(name))
            for filename, url, digest in listed:
                served.append(_fetch(url, digest, here / filename))
            span = sorted({parse_wheel_filename(f)[1] for f, _, _ in listed})
            summary.append(f"{name} {span[0]}" + (f" to {span[-1]}" if len(span) > 1
                                                  else "")
                           + f", {len(listed)} wheel{'s' if len(listed) > 1 else ''}")
        for line in overlaps(served):
            print(f"  note, not counted: {line}", file=sys.stderr)
        said = overlaps(wheels, served)
        for line in said:
            print(f"  {line}", file=sys.stderr)
        if said:
            print(f"\n{len(said)} pair(s) of distributions claim the same thing.",
                  file=sys.stderr)
            return 1
        print(f"{len(wheels) + len(served)} wheels -- {len(wheels)} built here and "
              f"every one the index serves ({'; '.join(summary)}) -- no two "
              f"distributions claiming one path, command or import name")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
