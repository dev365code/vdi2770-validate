#!/usr/bin/env python3
"""Write the list of advisories in SECURITY.md from `docs/advisories.json`.

    python tools/advisories.py --write    # rewrite the list between the markers
    python tools/advisories.py --check    # exit 1 if the page is not what the data says

What an advisory reaches and which release closes it used to be read out of the
security page's sentences, and every sentence written a new way was a new way
for that reading to go wrong in the page's favour: an entry could call a fixed
advisory open, or be read as naming another advisory's release, and stay green.
The data is the record now. The page carries it in words between two markers,
and the test that holds the changelog to the advisories reads the data.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "advisories.json"
PAGE = ROOT / "SECURITY.md"
BEGIN = ("<!-- advisories: written by tools/advisories.py from docs/advisories.json;"
         " edit the data, not this list -->")
END = "<!-- /advisories -->"
#: GitHub's identifier shape, bounded so that a longer id does not contain it.
GHSA = re.compile(r"GHSA-(?:[23456789cfghjmpqrvwx]{4}-){2}[23456789cfghjmpqrvwx]{4}")
VERSION = re.compile(r"\d+\.\d+\.\d+")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
#: What an entry says, in so many words, while no release closes it. The test
#: looks for the same words in the changelog.
OPEN = "not yet closed by any release"
DISTRIBUTIONS = ("vdi2770-validate", "vdi2770")


def number(version: str) -> tuple:
    return tuple(int(p) for p in version.split("."))


def repo() -> str:
    """The repository an advisory of ours lives on, from the project's metadata."""
    meta = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'Homepage = "https://github\.com/([^/"]+/[^/"]+)"', meta).group(1)


def _refuse(advisory: str, why: str) -> None:
    raise SystemExit(f"docs/advisories.json, {advisory}: {why}")


def load(path: Path = DATA) -> list:
    """The advisories, in the order the page lists them, refused where the record
    cannot be true: a fix that is not after the range it closes, an entry that
    names a fix and says no release closes it, a claim taken back after the
    release that did close it.

    `corrections` names each correction in the changelog that names the
    advisory, by the section it is appended to and its date, and says whether it
    took back that section's claim to fix it -- the one appended to 0.8.1 took
    nothing back, it gave the fix its advisory. Which is which is written here,
    not read out of the correction's words."""
    records = json.loads(path.read_text(encoding="utf-8"))["advisories"]
    seen = set()
    for a in records:
        name = a.get("id", "?")
        if not isinstance(name, str) or not GHSA.fullmatch(name):
            _refuse(name, "not an advisory identifier")
        if name in seen:
            _refuse(name, "listed twice")
        seen.add(name)
        extra = set(a) - {"id", "text", "from", "through", "fixed_in", "open",
                          "corrections"}
        if extra:
            _refuse(name, f"fields this generator does not read: {sorted(extra)}")
        text = a.get("text")
        if not isinstance(text, str) or not text or text != " ".join(text.split()):
            _refuse(name, "`text` is one run of words, with no line breaks or doubled spaces")
        if GHSA.search(text):
            _refuse(name, "`text` names an advisory; the entry is about its own")
        if OPEN in text:
            _refuse(name, f"`text` says {OPEN!r}; that belongs in `open`")
        froms = a.get("from")
        if not isinstance(froms, dict) or tuple(sorted(froms)) != tuple(sorted(DISTRIBUTIONS)):
            _refuse(name, f"`from` names each of {DISTRIBUTIONS} and nothing else")
        through = a.get("through")
        for v in [*froms.values(), through]:
            if not isinstance(v, str) or not VERSION.fullmatch(v):
                _refuse(name, f"{v!r} is not a version")
        if any(number(v) > number(through) for v in froms.values()):
            _refuse(name, "a range that starts after it ends")
        fixed = a.get("fixed_in")
        if fixed is not None and (not isinstance(fixed, str) or not VERSION.fullmatch(fixed)):
            _refuse(name, f"`fixed_in` {fixed!r} is neither a version nor null")
        if fixed is not None and number(fixed) <= number(through):
            _refuse(name, f"fixed in {fixed}, which is inside the range it closes (up to {through})")
        if (fixed is None) != ("open" in a):
            _refuse(name, "`open` says what is still open, and only an entry no release "
                          "fixes has one")
        if fixed is None and OPEN not in a["open"]:
            _refuse(name, f"`open` does not say {OPEN!r}")
        corrections = a.get("corrections")
        if not isinstance(corrections, list) or any(
                not isinstance(c, dict) or set(c) != {"in", "on", "took_back"}
                or not isinstance(c["in"], str) or not VERSION.fullmatch(c["in"])
                or not isinstance(c["on"], str) or not DATE.fullmatch(c["on"])
                or not isinstance(c["took_back"], bool)
                for c in corrections):
            _refuse(name, "`corrections` lists {in: release, on: date, took_back: "
                          "true or false}")
        keys = [(number(c["in"]), c["on"]) for c in corrections]
        if keys != sorted(set(keys)):
            _refuse(name, "`corrections` is in release order, then date, each once")
        claimed = sorted({c["in"] for c in corrections if c["took_back"]}, key=number)
        if fixed is not None and any(number(v) >= number(fixed) for v in claimed):
            _refuse(name, f"a claim taken back at or after {fixed}, the release that fixed it")
        if any(number(v) > number(through) for v in claimed):
            _refuse(name, "a release that claimed the fix is outside the range, so the "
                          "claim was true")
    return records


def reach(a: dict) -> str:
    """The sentence ending an entry: the versions it reaches, then the fix or what is open."""
    f = a["from"]
    if f["vdi2770-validate"] == f["vdi2770"]:
        who = f"`vdi2770-validate` and `vdi2770` from {f['vdi2770']}"
    else:
        who = f"`vdi2770-validate` from {f['vdi2770-validate']} and `vdi2770` from {f['vdi2770']}"
    tail = f"; fixed in {a['fixed_in']}." if a["fixed_in"] else f". {a['open']}"
    return f"{who}, up to {a['through']}{tail}"


def entry(a: dict, owner: str) -> str:
    head = f"- [{a['id']}](https://github.com/{owner}/security/advisories/{a['id']}):"
    body = textwrap.fill(f"{a['text']} {reach(a)}", width=79, initial_indent="  ",
                         subsequent_indent="  ", break_long_words=False,
                         break_on_hyphens=False)
    return f"{head}\n{body}"


def listing(records: list, owner: str) -> str:
    return "\n\n".join(entry(a, owner) for a in records)


def page_with(page: str, written: str) -> str:
    """`page` with what lies between the markers replaced by `written`."""
    if page.count(BEGIN) != 1 or page.count(END) != 1 or page.index(BEGIN) > page.index(END):
        raise SystemExit("SECURITY.md needs the two markers, once each and in order:\n"
                         f"  {BEGIN}\n  {END}")
    start, end = page.index(BEGIN) + len(BEGIN), page.index(END)
    return f"{page[:start]}\n\n{written}\n\n{page[end:]}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    page = PAGE.read_text(encoding="utf-8")
    want = page_with(page, listing(load(), repo()))
    if args.check:
        if want != page:
            print("SECURITY.md's list of advisories is not what docs/advisories.json "
                  "says; run python tools/advisories.py --write", file=sys.stderr)
            return 1
        print("SECURITY.md lists the advisories docs/advisories.json records")
        return 0
    PAGE.write_text(want, encoding="utf-8")
    print("wrote the list in SECURITY.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
