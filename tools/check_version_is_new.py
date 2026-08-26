"""Refuse to publish a version the index already holds.

Both release workflows fire on `push: tags`, and a *forced* tag update emits
that event exactly as a new tag does. Re-pointing an old tag -- which any repair
of history does -- therefore walks a days-old tree through the gate and hands it
to the publisher, which is asked to upload a filename the index already has. The
answer is a rejection, and a red run against the publishing environment.

The version cannot be taken back either way, so the honest thing is to ask
before building rather than to discover it at the upload. A version already on
the index is not an error here: it means this tag has already been released, and
the right outcome is to stop quietly.

Reading the index is the one network call in this repository, and it is
deliberate: it is the only way to know what has been published. `--offline`
skips it for a machine that has no route out, and says so rather than guessing.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

INDEX = "https://pypi.org/pypi/{name}/json"


def published(name: str, timeout: float = 15.0) -> set:
    """Every version the index holds for `name`, or an empty set if it holds none."""
    try:
        with urllib.request.urlopen(INDEX.format(name=name), timeout=timeout) as r:
            return set(json.load(r).get("releases", {}))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return set()               # nothing published yet, which is fine
        raise


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--package", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--offline", action="store_true",
                   help="skip the index check and say that is what happened")
    a = p.parse_args()

    if a.offline:
        print(f"not asking the index about {a.package} {a.version}: --offline",
              file=sys.stderr)
        return 0
    try:
        have = published(a.package)
    except Exception as e:                       # noqa: BLE001 - the network is the risk
        print(f"could not ask the index about {a.package}: {e}. Refusing rather "
              f"than guessing -- a publish that turns out to be a duplicate is "
              f"a failed run against the publishing environment.", file=sys.stderr)
        return 1
    if a.version in have:
        print(f"{a.package} {a.version} is already on the index. This tag has "
              f"been released; nothing to do.", file=sys.stderr)
        return 1
    print(f"{a.package} {a.version} is not on the index yet.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
