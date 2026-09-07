#!/usr/bin/env python3
"""No two distributions here claim a path, a command, or an import name.

The manifest gate compares what two manifests *say*. This compares what the
artifacts *are*, and against what is already on the index — which is the
comparison that matters, because the destruction happens between a release and
the one before it, not between two files in one working tree.

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
import io
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = (ROOT, ROOT / "packages" / "vdi2770")

#: The release already on the index. The comparison that matters is against
#: what people already have, and this is the newest thing they can have.
PUBLISHED = ("vdi2770==0.7.0", "vdi2770-validate==0.7.0")

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


def _download(spec: str, out: Path) -> Path:
    done = subprocess.run(
        [sys.executable, "-m", "pip", "download", "--no-deps",
         "--only-binary", ":all:", "--dest", str(out), spec],
        env=NO_BYTECODE, capture_output=True, text=True)
    if done.returncode:
        print(done.stdout[-2000:], done.stderr[-2000:], file=sys.stderr)
        raise SystemExit(f"could not fetch {spec}; this gate needs the index")
    made = sorted(out.glob("*.whl"))
    if len(made) != 1:
        raise SystemExit(f"{spec}: expected one wheel, found {made}")
    return made[0]


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
        distribution = info.split("/")[0].rsplit("-", 2)[0]
        for name in names:
            if name.endswith("/"):
                continue
            owned.add(f"path {name}")
            top = name.split("/")[0]
            if not top.endswith(".dist-info") and not top.endswith(".data"):
                owned.add(f"import {top[:-3] if top.endswith('.py') else top}")
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


def overlaps(wheels: list) -> list:
    said = []
    read = [claims(w) + (w.name,) for w in wheels]
    for i, (name_a, owned_a, file_a) in enumerate(read):
        for name_b, owned_b, file_b in read[i + 1:]:
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
        for n, spec in enumerate(PUBLISHED):
            here = out / f"index{n}"
            here.mkdir()
            wheels.append(_download(spec, here))
        said = overlaps(wheels)
        for line in said:
            print(f"  {line}", file=sys.stderr)
        if said:
            print(f"\n{len(said)} pair(s) of distributions claim the same thing.",
                  file=sys.stderr)
            return 1
        print(f"{len(wheels)} wheels, no two distributions claiming one path, "
              f"command or import name")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
