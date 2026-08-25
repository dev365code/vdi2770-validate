"""Refuse to release the validator before the reader it pins.

The two packages ship from one repository and the validator depends on the
reader with `~=`. `release.yml` installs the reader from the working tree
(`pip install -e packages/vdi2770`), so nothing in the gate ever asks an index
whether that version exists -- and `python -m build` does not resolve runtime
dependencies at all. Tagging `v*` before `sdk-v*` therefore succeeds, and
publishes a distribution whose dependency does not exist. On PyPI that is
permanent: the version number cannot be reused.

Until now the constraint lived in a test docstring. The test that names it takes
the `floor == here` branch and asserts only that `API.json` exists, which it
always does.

The tag history is the evidence, so this needs a checkout with tags
(`fetch-depth: 0`). Not being able to see them is a refusal, not a pass -- the
same rule `api_fingerprint._tags()` learned.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

from packaging.requirements import Requirement

ROOT = pathlib.Path(__file__).resolve().parent.parent


def floor_of_the_pin() -> str:
    """The lowest reader version the validator's pin admits."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    deps = re.search(r"^dependencies = \[(.*?)\]", text, re.M | re.S)
    if deps is None:
        raise SystemExit("pyproject.toml declares no dependencies")
    pin = next((Requirement(m) for m in re.findall(r'"([^"]+)"', deps.group(1))
                if Requirement(m).name == "vdi2770"), None)
    if pin is None:
        raise SystemExit("the validator no longer depends on the reader")
    floors = [s.version for s in pin.specifier
              if s.operator in ("~=", ">=", "==")]
    if not floors:
        raise SystemExit(f"{pin} has no lower bound; any older reader satisfies it")
    return max(floors, key=lambda v: tuple(int(x) for x in v.split(".")))


def main() -> int:
    floor = floor_of_the_pin()
    got = subprocess.run(["git", "tag", "--list", "sdk-v*"],
                         cwd=ROOT, capture_output=True, text=True)
    if got.returncode:
        print("cannot read the tag history, and the release order rests on it. "
              "Fetch tags (`fetch-depth: 0`) and try again.", file=sys.stderr)
        return 1
    tags = {t for t in got.stdout.split() if t}
    if not tags:
        print("this checkout has no `sdk-v*` tags at all, which is "
              "indistinguishable from the reader never having been released.",
              file=sys.stderr)
        return 1
    if f"sdk-v{floor}" not in tags:
        print(f"the validator pins vdi2770>={floor} and sdk-v{floor} is not "
              f"tagged. Release the reader first: published this way, "
              f"`pip install vdi2770-validate` cannot resolve, and the version "
              f"number cannot be reused to fix it.", file=sys.stderr)
        return 1
    print(f"sdk-v{floor} is tagged; the reader this pins has been released.",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
