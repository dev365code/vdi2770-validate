"""Refuse to publish a version the index already holds.

Both release workflows fire on `push: tags`, and a *forced* tag update emits
that event exactly as a new tag does. Re-pointing an old tag -- which any repair
of history does -- therefore walks a days-old tree through the gate and hands it
to the publisher, which is asked to upload a filename the index already has. The
answer is a rejection, and a red run against the publishing environment.

The version cannot be taken back either way, so the honest thing is to ask
before building rather than to discover it at the upload. A version already on
the index means this tag has already been released, and nothing is wrong with
the tree -- but this refuses anyway, and loudly, because a shell step has no exit
code for *stop and be pleased about it*. A red run that uploaded nothing costs a
glance at the log. Returning 0 hands the same tree to the publisher and spends
the failure against the publishing environment instead.

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

from packaging.version import InvalidVersion, Version

INDEX = "https://pypi.org/pypi/{name}/json"


def published(name: str, timeout: float = 15.0) -> set:
    """Every version the index holds for `name`, or an empty set if it holds none.

    `.get("releases", {})` was a gate that could not fail. PyPI's legacy JSON API
    is deprecated; the day a 200 comes back without that key, every version reads
    as unpublished and this starts approving the duplicate uploads it exists to
    refuse -- with nobody the wiser until the upload. An answer we cannot read is
    a refusal, which is what the caller does with the exception.
    """
    try:
        with urllib.request.urlopen(INDEX.format(name=name), timeout=timeout) as r:
            answer = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return set()               # nothing published yet, which is fine
        raise
    if not isinstance(answer, dict) or "releases" not in answer:
        raise ValueError(f"the index answered about {name} without a `releases` "
                         f"key; this cannot tell published from unpublished")
    return set(answer["releases"])


def holds(have, version: str) -> bool:
    """Whether `have` already holds `version`, spelled either way.

    `"0.7.0-rc1" in {"0.7.0rc1"}` is False, and PyPI stores the second: a
    pre-release or `.post` tag walked past the one gate that exists to catch a
    filename the index already has, and was rejected at the upload instead.
    `Version` is what the index itself compares with. A spelling neither side can
    parse falls back to the string, because refusing to answer here would block a
    release over a version number that is merely unusual.
    """
    try:
        want = Version(version)
    except InvalidVersion:
        return version in have
    for one in have:
        try:
            if Version(one) == want:
                return True
        except InvalidVersion:
            if one == version:
                return True
    return False


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
    if holds(have, a.version):
        print(f"{a.package} {a.version} is already on the index. This tag has "
              f"been released; nothing to do.", file=sys.stderr)
        return 1
    print(f"{a.package} {a.version} is not on the index yet.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
