#!/usr/bin/env python3
"""The tag names the version this project would publish, or the release stops.

A version number is on the index forever and does not come round again, so a
tag saying 0.2.0 over a tree saying 0.1.9 is not a mistake anybody can take
back. Each publishing job asks this about its own project.

**Why this is a script and not a line in the workflow.** It was a line, and the
line read the version by importing the package:

    python -c "import sys; sys.path.insert(0,'src'); import vdi2770_validate as v; print(v.__version__)"

which worked while the alias was a package of its own. After the merge its
`__init__` imports the engine, and the job that runs this installs `build` and
`packaging` and nothing else -- so the import raised, the shell substitution
produced the empty string, and every tag failed with *tag 0.8.0 != package*.
Nothing had ever run it: CI does not, and the test that asserts the step exists
compares the text of the line rather than its exit code.

So it imports nothing. The manifest is read with a pattern rather than a TOML
parser, because `tomllib` is 3.11 and later and this has to answer on whatever
interpreter the job happens to have -- the same reason `build_zipapp.py` gives.
What the manifest says and what the code says are already tied together by a
gate that reads all eleven places the version is written.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def declared_version(project: Path) -> str:
    """The `[project] version` of one manifest.

    Anchored to the start of a line: `version = "…"` also appears inside
    `requires-python`-adjacent tables and inside dependency strings, and a
    pattern that matched anywhere would take whichever came first.
    """
    manifest = project / "pyproject.toml"
    if not manifest.is_file():
        raise SystemExit(f"{manifest} does not exist, so there is no version to "
                         f"check the tag against")
    found = re.search(r'^version = "([^"]+)"', manifest.read_text(encoding="utf-8"),
                      re.M)
    if found is None:
        raise SystemExit(f"{manifest} declares no `version`")
    return found.group(1)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tag", required=True,
                   help="the tag, with any leading `v` already removed")
    p.add_argument("--project", required=True,
                   help="the directory holding the pyproject.toml to read")
    a = p.parse_args()
    project = (ROOT / a.project).resolve()
    declared = declared_version(project)
    if a.tag != declared:
        print(f"the tag says {a.tag} and {a.project}/pyproject.toml says "
              f"{declared}. One tag names one release; these are two, and the "
              f"number does not come round again.", file=sys.stderr)
        return 1
    print(f"{a.project} publishes {declared}, which is what the tag says")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
