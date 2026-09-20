#!/usr/bin/env python3
"""The release body, taken from the CHANGELOG rather than written twice.

Every release so far was described by hand, and the description had to agree
with a section somebody else had already written. Two hand-written accounts of
one release drift; this takes the account that ships in the repository and adds
the part a release page needs and a changelog does not -- how to check the file
you just downloaded.

    python tools/release_notes.py --version 0.9.1 --pyz-sha <hex>

It refuses rather than improvises. A CHANGELOG whose top section is for another
version, or which has no opening paragraph, gets no release notes: a release
that describes itself wrongly is worse than one nobody could cut.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: What the opening paragraph has started with since 0.8.0. It is the sentence a
#: person reads first on the release page, and the one the CHANGELOG is written
#: to lead with, so it is also the marker that the section is shaped as expected.
LEAD = "Who should take this release"


class CannotDescribe(Exception):
    """The CHANGELOG cannot be read as this release's description."""


def top_section(changelog: str) -> tuple[str, str]:
    """The newest section's version and body, or a refusal.

    A released section carries a date; the section being written carries the
    word "unreleased". Describing the second as a release is the last hand step
    before a tag that nothing else checks -- the version matches, the prose
    reads right, and the page says a release happened that did not.
    """
    heads = list(re.finditer(r"^## +(\S+)(.*)$", changelog, re.M))
    if not heads:
        raise CannotDescribe("CHANGELOG.md has no section heading")
    first = heads[0]
    rest = first.group(2)
    if not re.search(r"\d{4}-\d{2}-\d{2}", rest):
        raise CannotDescribe(
            f"the top section reads '## {first.group(1)}{rest}' and carries no date, so it "
            f"is the section being written rather than one that shipped. Date it first.")
    end = heads[1].start() if len(heads) > 1 else len(changelog)
    return first.group(1), changelog[first.end():end].strip("\n")


def opening_paragraph(section: str) -> str:
    """The first paragraph, as one line of prose.

    The CHANGELOG wraps at the width of the page it lives on; a release body is
    read in a browser, so the wrapping is undone here rather than shipped.
    """
    for block in section.split("\n\n"):
        block = block.strip()
        if block.startswith(LEAD):
            return " ".join(block.split())
    raise CannotDescribe(
        f"the top section has no paragraph starting {LEAD!r}; it opens with "
        f"{section.strip()[:60]!r}")


def body(version: str, pyz_sha: str, changelog: str) -> str:
    """The notes for `version`, refusing if the CHANGELOG is about another one."""
    said, body_text = top_section(changelog)
    if said != version:
        raise CannotDescribe(
            f"the CHANGELOG's top section is {said}, and this release is {version}. "
            f"One of the two is wrong and it is not for this script to decide which.")
    lead = opening_paragraph(body_text)
    lead = "**" + LEAD + ":**" + lead[len(LEAD) + 1:]
    if not re.fullmatch(r"[0-9a-f]{64}", pyz_sha):
        raise CannotDescribe(f"that is not a sha256 of anything: {pyz_sha!r}")
    return f"""{lead}

Full notes: `CHANGELOG.md`, section {version}.

## One file, no install

`vdi2770.pyz` is attached to this release: everything inside one readable zip,
for a machine that may not install packages.

```
python vdi2770.pyz check YOUR-CONTAINER.zip
```

```
sha256  {pyz_sha}
```

The wheels and sdists are the same bytes PyPI serves, and `SHA256SUMS-reader`
and `SHA256SUMS-rules` record them:

```
sha256sum -c SHA256SUMS-reader
sha256sum -c SHA256SUMS-rules
```

A workflow does not need any of this: `uses: dev365code/vdi2770-validate@v{version}`
installs the same release from the index and runs it.
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--version", required=True, help="the release being described")
    ap.add_argument("--pyz-sha", required=True, help="sha256 of the single file")
    ap.add_argument("--changelog", default=str(ROOT / "CHANGELOG.md"))
    ap.add_argument("-o", "--output", help="where to write; stdout by default")
    args = ap.parse_args(argv)

    version = args.version[1:] if args.version.startswith("v") else args.version
    try:
        text = body(version, args.pyz_sha.strip().lower(),
                    pathlib.Path(args.changelog).read_text(encoding="utf-8"))
    except CannotDescribe as e:
        print(f"refusing to describe this release: {e}", file=sys.stderr)
        return 1
    if args.output:
        pathlib.Path(args.output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
