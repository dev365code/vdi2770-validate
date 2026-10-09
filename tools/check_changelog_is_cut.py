#!/usr/bin/env python3
"""A publishing tag requires a dated changelog with its release opening."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from release_notes import CannotDescribe, opening_paragraph, top_section

ROOT = Path(__file__).resolve().parent.parent


def check_cut(changelog: str, tag: str) -> str:
    """Development may lead the package version; a tag must name a cut section."""
    expected = re.fullmatch(r"v?(\d+\.\d+\.\d+)", tag)
    if expected is None:
        raise CannotDescribe(f"the tag {tag!r} does not name a release version")
    heads = list(re.finditer(r"^## +([^\n]+)$", changelog, re.M))
    if any(re.search(r" +— +unreleased\s*$", h[1]) for h in heads):
        raise CannotDescribe("CHANGELOG.md has an unreleased heading; date every pending section before the cut")
    if not heads:
        raise CannotDescribe("CHANGELOG.md has no section heading")
    if not re.fullmatch(r"\d+\.\d+\.\d+ +— +\d{4}-\d{2}-\d{2}", heads[0][1]):
        raise CannotDescribe("CHANGELOG.md top heading must name a version and a YYYY-MM-DD date")
    version, section = top_section(changelog)
    if version != expected[1]:
        raise CannotDescribe(f"CHANGELOG.md top section is {version} and the tag is {expected[1]}")
    if sum(h[1].split()[0] == version for h in heads) != 1:
        raise CannotDescribe(f"CHANGELOG.md must name the cut version {version} only once")
    opening_paragraph(section)
    return version


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="the publishing version, with an optional leading v")
    args = parser.parse_args(argv)
    try:
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        version = check_cut(changelog, args.tag)
    except (OSError, UnicodeError) as error:
        print(f"cannot read CHANGELOG.md: {error}", file=sys.stderr)
        return 1
    except CannotDescribe as error:
        print(str(error).replace("\n", " "), file=sys.stderr)
        return 1
    print(f"CHANGELOG.md is ready for tag {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
