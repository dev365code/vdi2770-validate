#!/usr/bin/env python3
"""The reader's public surface, recorded against the version that published it.

    python tools/api_fingerprint.py            # show it
    python tools/api_fingerprint.py --check    # judge, against packages/vdi2770/API.json
    python tools/api_fingerprint.py --write    # record it, after a version bump

Two releases have already gone out with a pin that let pip install a reader the
validator could not use. The existing gate compares the pin's floor to the
version in the tree, which catches "the pin is too loose" and cannot catch the
other half: **the code changed and the version did not**. This cycle's reader
gained `DEFECT_KINDS`, gained `Container.parent`, and changed
`Container.rejected` from `Dict[str, str]` to `Dict[str, Defect]`, all while
calling itself 0.5.0.

Nobody was hurt by that particular one, and the reason is worth writing down:
0.5.0 was never tagged, so `release-sdk.yml` never published it. The newest
reader on PyPI is 0.4.0 and the released validator pins `~=0.4.0`, which
resolves. What would have hurt is tagging the validator from that tree — its pin
said `~=0.5.0` for a reader that existed nowhere but here. The companion check
for that is in `tests/test_ci_parity.py`.

`--write` refuses to record a changed surface under a version it has already
recorded. That is the whole point: without it, "regenerate the baseline" is a
way to make this gate quiet.
"""
from __future__ import annotations

import argparse
import dataclasses
import enum
import inspect
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "packages" / "vdi2770"
BASELINE = PACKAGE / "API.json"
#: Bumped when `surface()` changes what it records. A recorded surface from an
#: older format is not evidence about today's library, and telling the two apart
#: matters: "the library moved" and "the instrument changed" need different
#: answers, and conflating them would make every recorder improvement look like
#: a breaking release.
FORMAT = 2
sys.path.insert(0, str(PACKAGE / "src"))

import vdi2770  # noqa: E402


def surface() -> dict:
    """Everything about a name that a caller can break on.

    The first version recorded field names with their type strings, property
    names, and function parameter *names*. a review put thirteen
    mutations through it and four passed both this and the whole test suite,
    each a real breaking change to a published library:

      * a positional parameter made keyword-only — `parameters` is an ordered
        name mapping and the kind is thrown away;
      * a public dataclass field losing its default — the type was recorded, the
        default was not;
      * a return annotation changing;
      * an enum member's *value* changing, which is what callers compare against.

    So: the whole `inspect.signature` as a string, which carries kinds, defaults
    and the return annotation together; the repr of every constant a caller can
    read; the members and bases of every class; and the callables on a dataclass
    beside its fields.
    """
    def described(obj):
        if dataclasses.is_dataclass(obj):
            return {
                "fields": {f.name: [str(f.type),
                                    "no-default" if f.default is dataclasses.MISSING
                                    and f.default_factory is dataclasses.MISSING
                                    else "has-default"]
                           for f in dataclasses.fields(obj)},
                "properties": sorted(n for n, v in vars(obj).items()
                                     if isinstance(v, property) and not n.startswith("_")),
                "methods": sorted(n for n, v in vars(obj).items()
                                  if callable(v) and not n.startswith("_")),
                "bases": [b.__name__ for b in obj.__mro__[1:]],
            }
        if inspect.isfunction(obj):
            return {"signature": str(inspect.signature(obj))}
        if isinstance(obj, type):
            out = {"members": sorted(n for n in vars(obj) if not n.startswith("_")),
                   "bases": [b.__name__ for b in obj.__mro__[1:]]}
            if issubclass(obj, enum.Enum):
                # The value is the thing a caller compares against; the member
                # name is only how they spell it.
                out["values"] = {m.name: repr(m.value) for m in obj}
            return out
        if isinstance(obj, (str, int, float, bool, bytes, frozenset, tuple)):
            value = sorted(obj) if isinstance(obj, frozenset) else obj
            return {"kind": type(obj).__name__, "value": repr(value)}
        return {"kind": type(obj).__name__}

    return {name: described(getattr(vdi2770, name, None)) for name in sorted(vdi2770.__all__)}


def compatible(recorded: dict, now: dict) -> Optional[str]:
    """Is moving from `recorded` to `now` something the validator's pin permits?

    Returns None when it is, or the sentence explaining why not.

    "Bump the version" was the whole rule, and it is not enough while the
    validator pins with `~=`: `vdi2770~=0.6.0` admits every 0.6.x, so a removal
    published as 0.6.1 arrives on installed machines without anyone choosing it.
    This project shipped that mistake once already — `~=0.3.0` accepted 0.3.1 and
    pip installed the reader whose fix was the point of the release.

    Additions are compatible; a patch bump is an honest way to ship one.
    Removals and signature changes are not, and the minor has to move so the
    pin stops admitting them.
    """
    # `__version__` is in `__all__` and `surface()` records its value, so it
    # moves in every comparison this function is ever asked to make -- and this
    # function is only consulted when the version moved. Left in, `moved` is
    # never empty, the compatible branch below is unreachable, and every patch
    # release of the reader is refused including one that changes nothing else.
    # It is the version, not part of the surface the version describes.
    a = {k: v for k, v in recorded["surface"].items() if k != "__version__"}
    b = {k: v for k, v in now["surface"].items() if k != "__version__"}
    lost = sorted(set(a) - set(b))
    moved = sorted(n for n in set(a) & set(b) if a[n] != b[n])

    was, is_ = _parts(recorded["version"]), _parts(now["version"])
    if was and is_ and is_ < was:
        return (f"{recorded['version']} -> {now['version']} goes backwards. A "
                f"release does not, and a pin that admits the older one will "
                f"never see this.")
    if not lost and not moved:
        return None

    if was is None or is_ is None:
        return (f"cannot compare {recorded['version']!r} with {now['version']!r} as "
                f"release numbers, and this change needs the minor to move")
    if is_[:2] > was[:2]:
        return None
    what = []
    if lost:
        what.append(f"removed {lost}")
    if moved:
        what.append(f"changed the signature of {moved}")
    return (f"{recorded['version']} -> {now['version']} " + " and ".join(what) +
            f". The validator pins the reader with `~=`, which admits every "
            f"{was[0]}.{was[1]}.x — this release would install itself on machines "
            f"that asked for {recorded['version']}. Move the minor.")


def _parts(version: str) -> Optional[tuple]:
    """(major, minor, rest) for a release number, or None if it is not one.

    Pre-release suffixes are deliberately kept out of the comparison: 0.7.0.dev0
    and 0.7.0 differ in what is installable, not in which surface they promise.
    """
    head = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    return (int(head.group(1)), int(head.group(2)), int(head.group(3))) if head else None


def _at_tag(version: str):
    """The baseline as `sdk-v<version>` published it, or None.

    Read from git rather than from the file being judged, because the file being
    judged is the one somebody could have edited.
    """
    done = subprocess.run(["git", "show", f"sdk-v{version}:packages/vdi2770/API.json"],
                          cwd=ROOT, capture_output=True, text=True)
    if done.returncode:
        return None
    try:
        return json.loads(done.stdout)
    except json.JSONDecodeError:
        return None


def _published(version: str) -> bool:
    """Whether `sdk-v<version>` exists — whether anyone could have installed it.

    A version nobody has published is still being written and its record may
    move with it. Once the tag exists the record is evidence about something on
    an index, and `--write` stops accepting changes under it.
    """
    return f"sdk-v{version}" in _tags()


def _tags() -> set:
    """Every `sdk-v*` tag, or a refusal if git cannot answer.

    "No such tag" and "there is no tag history here" were the same answer, and
    the second one turns every guard in this file off: in a `--depth 1
    --no-tags` clone -- which is what `actions/checkout` gives you by default --
    a moved surface recorded cleanly under a version that is live on PyPI, and
    the whole gate stayed green. A guard that cannot see is a guard that says
    yes.
    """
    got = subprocess.run(["git", "tag", "--list", "sdk-v*"],
                         cwd=ROOT, capture_output=True, text=True)
    if got.returncode:
        raise SystemExit(
            "cannot read the tag history, and every judgement in this file rests "
            "on it. Fetch tags (`git fetch --tags`, or `fetch-depth: 0`) and try "
            "again -- guessing here means recording a surface under a version "
            "somebody may already have installed.")
    tags = {t for t in got.stdout.split() if t}
    if not tags:
        raise SystemExit(
            "this checkout has no `sdk-v*` tags at all. That is indistinguishable "
            "from nothing having been released, which is not true of this package "
            "-- fetch tags (`fetch-depth: 0`) before recording anything.")
    return tags


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--first", action="store_true",
                    help="create the baseline when there is none; refused otherwise")
    a = ap.parse_args()

    now = {"format": FORMAT, "version": vdi2770.__version__, "surface": surface()}
    recorded = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else None

    stale_format = recorded is not None and recorded.get("format") != FORMAT

    if a.write:
        # Both fields below are the tool's, not the editor's. Editing either one
        # in the JSON used to steer the refusal past the row it should have
        # compared: `"format": 2 -> 1` disabled it outright, and a made-up
        # `"version"` made it compare against nothing.
        if stale_format and _published(now["version"]):
            print(f"the fingerprint format moved and {now['version']} is published. "
                  f"Re-recording would replace evidence about something people have "
                  f"installed — read the surface diff by hand, then bump.",
                  file=sys.stderr)
            return 1
        if stale_format:
            print(f"re-recording: the fingerprint format moved "
                  f"{recorded.get('format')} -> {FORMAT}. This says nothing about "
                  f"whether the library changed.", file=sys.stderr)
        if recorded and recorded.get("version") not in (None, now["version"]):
            # Unconditionally. Guarding this with `_published(recorded["version"])`
            # made the check depend on a value the editor of this file chooses:
            # point `version` at a tag that does not exist and the branch never
            # runs at all, so `compatible()` is handed a version out of thin air
            # and waves a removal through as a patch. `--write` then overwrites
            # the field, so the committed diff shows an ordinary version bump.
            # This is what a release looks like: the recorded version shipped,
            # the package has moved past it. Refusing outright was a wall across
            # the one operation a release performs -- `sdk-v0.6.0` was the first
            # published baseline, so the first release after it had nowhere to go.
            #
            # But the version in this file is editable, and setting it to a value
            # that happens to be tagged is exactly how you make the tool compare
            # against a past that never existed. So the baseline has to *be* what
            # that tag published, not merely claim to be: the tag is the evidence
            # and this file is a copy of it.
            if not _published(recorded["version"]):
                print(f"{BASELINE.relative_to(ROOT)} says it records "
                      f"{recorded['version']}, and no sdk-v{recorded['version']} "
                      f"was ever tagged. There is nothing to compare against; "
                      f"restore the baseline from the tag it belongs to.",
                      file=sys.stderr)
                return 1
            published = _at_tag(recorded["version"])
            if published != recorded:
                print(f"{BASELINE.relative_to(ROOT)} says it records {recorded['version']}, "
                      f"and that is not what sdk-v{recorded['version']} published"
                      f"{' -- the tag has no baseline at all' if published is None else ''}. "
                      f"Restore it from the tag; a baseline that is not the record of a "
                      f"release cannot be compared against one.", file=sys.stderr)
                return 1
            why = compatible(recorded, now)
            if why:
                print(why, file=sys.stderr)
                return 1
            if _published(now["version"]):
                # Restoring the baseline from the previous tag is what this
                # file's own error messages tell you to do, and it walked a
                # surface change straight into the live version: the branch fires
                # on "the recorded version differs", which is exactly the
                # condition that makes the same-version guard below unreachable.
                print(f"sdk-v{now['version']} is already published. Whoever installed "
                      f"it does not get this surface, whatever the baseline in the "
                      f"tree says. Bump the version.", file=sys.stderr)
                return 1
            print(f"recording {now['version']}: {recorded['version']} is published and "
                  f"this move is compatible with the pin that admits it.", file=sys.stderr)
        if recorded is None and a.first and _tags():
            # "This is the first one" cannot be true of a package with releases
            # behind it. The guard tested whether *this* version was published --
            # and a release always bumps to one that is not, so `--first` was
            # open on the only path that matters.
            #
            # That narrower guard used to sit below this one as well, and could
            # not run: `_tags()` either raises or returns a non-empty set, so
            # this line answers first in every state a checkout can be in. Two
            # tests reached it, neither could tell which branch had produced the
            # 1 they asserted on, and `if False:` over it left the suite green.
            # A guard that cannot run is not a second opinion; it is a comment
            # that looks like code.
            print(f"--first records a surface as though nothing had been recorded "
                  f"before, and this package has published releases "
                  f"({len(_tags())} tags). Restore the baseline from its tag "
                  f"instead.", file=sys.stderr)
            return 1
        if recorded is None and not a.first:
            # `rm API.json && --write` was exactly as easy as regenerating it,
            # and showed up in a diff exactly the same way. Creating the baseline
            # is a thing you do once; saying so costs a flag.
            print(f"{BASELINE.relative_to(ROOT)} does not exist. If this really is the "
                  f"first one, pass --first; if it was deleted, restore it — recreating "
                  f"it records whatever is here as though it had always been.",
                  file=sys.stderr)
            return 1
        if (_published(now["version"]) and recorded and not stale_format
                and recorded["version"] == now["version"]
                and recorded["surface"] != now["surface"]):
            print(f"the public surface changed and {now['version']} is already "
                  f"published as sdk-v{now['version']}. Whoever installed it does "
                  f"not get this. Bump packages/vdi2770 (pyproject.toml and "
                  f"__init__.py), move the validator's pin with it, then rerun.",
                  file=sys.stderr)
            return 1
        # A bump is not automatically the right bump. `--write` is the one moment
        # this can be caught: after it, the recorded surface and the version agree
        # and nothing downstream can tell that a removal shipped as a patch.
        if recorded and not stale_format and recorded["version"] != now["version"]:
            why = compatible(recorded, now)
            if why:
                print(why, file=sys.stderr)
                return 1
        BASELINE.write_text(json.dumps(now, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
        print(f"wrote {BASELINE.relative_to(ROOT)} for {now['version']}")
        return 0

    if a.check:
        if recorded is None:
            print(f"{BASELINE.relative_to(ROOT)} missing — run --write", file=sys.stderr)
            return 1
        if stale_format:
            print(f"{BASELINE.relative_to(ROOT)} was recorded in format "
                  f"{recorded.get('format')} and this tool records format {FORMAT}. "
                  f"An older record is not evidence about today's library. "
                  f"Rerun --write and review the diff.", file=sys.stderr)
            return 1
        if recorded == now:
            print(f"the reader's public surface matches what {now['version']} recorded")
            return 0
        if recorded["version"] == now["version"]:
            gained = sorted(set(now["surface"]) - set(recorded["surface"]))
            lost = sorted(set(recorded["surface"]) - set(now["surface"]))
            changed = sorted(n for n in set(now["surface"]) & set(recorded["surface"])
                             if now["surface"][n] != recorded["surface"][n])
            # Two sentences, because the repair is different and the wrong one
            # costs a version number. This said "whoever installs {v} from PyPI
            # does not get this" about a version that was never published --
            # nobody can install it, so nobody is missing anything, and bumping
            # would have burned a number to fix a problem that did not exist.
            # `--write` already told the two apart; only the explanation did not.
            fix = (f"Whoever installs {now['version']} from PyPI does not get this. "
                   f"Bump the version, move the validator's pin, then rerun --write."
                   if _published(now["version"]) else
                   f"sdk-v{now['version']} was never published, so this surface has "
                   f"not been promised to anybody yet. Rerun --write and review the "
                   f"diff.")
            print(f"the reader still calls itself {now['version']} and its public surface has "
                  f"moved: added {gained}, removed {lost}, changed {changed}.\n"
                  + fix, file=sys.stderr)
        else:
            print(f"the version moved {recorded['version']} -> {now['version']} and the record "
                  f"did not. Rerun --write and review the diff.", file=sys.stderr)
        return 1

    print(json.dumps(now, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
