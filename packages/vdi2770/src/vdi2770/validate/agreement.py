"""Do the two halves of this installation say the same number? — draft.

A program that signs conformance verdicts has no reason to trust the installer.
Every packaging failure this project has had ended with a tool that looked
healthy to `pip check` and was not, so the last line is inside the tool.

**What this verifies, exactly.** The reader and the rules ship together under
one tag and always carry the same number. This asks whether the two loaded
halves still say the same thing, and whether the record beside the loaded code
agrees with it. That is all. It is not an integrity check and must not be sold
as one: a copy of the rules package earlier on `sys.path`, carrying the same
version literal, replaces every rule in this tool and nothing here notices --
`__version__` is a hand-edited literal that stays put for a whole development
cycle, so the likeliest shadow of all satisfies this by accident.

**What it does not do.** It says nothing about age. `pip install
vdi2770-validate==0.7.0` builds a coherent 0.7.0 pair whose report honestly says
`toolVersion: 0.7.0`, and giving somebody the version they asked for is not a
fault. Refusing there would be a new destruction wearing a safety label.

**Records are read where the code is, or not at all.** An earlier draft compared
the loaded version against every record on the path, and refused:

  - the single-file build on any machine that had also pip-installed the reader
    -- the `.pyz` is the door for machines with no route to an index, and the
    refusal handed those users a `pip install`;
  - a `--target` layer over a base image, where two intact copies exist and the
    layer wins deterministically;
  - a source checkout carrying a stale `.egg-info`, which is this repository on
    any day somebody bumps the literal before reinstalling.

None of those is an installation that cannot account for itself. So a record
counts only when it sits in the same directory as the code that loaded, and
only when it is a real install record: an `.egg-info` left over from a build is
not what an installed distribution looks like, and is told apart by having no
`METADATA` of its own.

**Computed once.** The first draft recomputed per verdict, on the reasoning that
an install can change under a long-lived process. It can -- but `__version__` is
read off `sys.modules` and freezes at import, so the only thing that can change
is the metadata, and the only behaviour that bought was a coherent, correct,
still-running process refusing every verdict because somebody upgraded the
environment in another window. Caching is not a cost trade here; it is the more
correct reading.
"""
from __future__ import annotations

import re
from typing import Optional

#: Printed first on the refusal line. A CI step is red for any non-zero exit,
#: and this is the only thing in the log that separates "the containers failed"
#: from "the tool declined to judge".
MARKER = "vdi2770-validate: INSTALLATION"


class InstallationDisagrees(Exception):
    """Raised instead of exiting: this is a library as well as a command.

    `check_bytes` is called by people who imported this package, and a library
    that calls `sys.exit` tears down somebody else's process -- or, in a
    framework that catches `SystemExit`, produces a 500 with the diagnosis
    swallowed. The command translates this into an exit code; nothing else does.
    """


_SEP = re.compile(r"[-_.]+")
_MARKERS = re.compile(r"\.?(alpha|beta|preview|pre|post|rev|rc|dev|a|b|c|r)\.?")
#: `post01` and `post1` are the same release; the backend writes the second and
#: a hand-edited literal often writes the first.
_PADDING = re.compile(r"(?<!\d)0+(\d)")


def folded(version: str) -> str:
    """One spelling of a version, for comparing two spellings of one version.

    A build backend normalises what a hand-edited literal writes: `0.8.0-rc1`
    becomes `0.8.0rc1` on the way into the metadata, and a raw `==` between them
    is a refusal over punctuation. `packaging` would do this properly and the
    reader declares no dependencies, so this is the fold rather than the
    standard: it makes the spellings of one version agree and does not try to
    order two versions.
    """
    one = _MARKERS.sub(r"\1", _SEP.sub(".", version.strip().lower()))
    return _PADDING.sub(r"\1", one)


def _where_it_loaded(module):
    """The directory an installed copy of this module would sit in, or None.

    `__file__` for a package is `<somewhere>/<name>/__init__.py`, so the
    directory two levels up is where a record for it would live.

    A namespace package has no `__init__.py` and therefore **no `__file__` at
    all** -- reading it raises, and an earlier draft treated that as "nowhere to
    look" and fell silent. That is exactly the layout this project is moving to:
    a reader shipping `vdi2770/validate/` with no `vdi2770/__init__.py`. The
    check would have gone quiet on the release it was written for, which is the
    third time in this repository that something written to protect a decision
    could not see the shape the decision takes. `__path__` is what a namespace
    package has instead, and it says the same thing.
    """
    from pathlib import Path
    try:
        where = module.__file__
        if where:
            return Path(where).resolve().parent.parent
    except (AttributeError, OSError):
        pass
    try:
        roots = list(module.__path__)
    except (AttributeError, TypeError):
        return None
    for root in roots:
        try:
            return Path(root).resolve().parent
        except (TypeError, OSError):
            continue
    return None


def _co_located_records(module, name):
    """Install records sitting where the loaded code is.

    An `.egg-info` is excluded by having no `METADATA`: it is a build artifact,
    it lives in the source directory the loaded module also lives in, and it
    goes stale the moment a version literal moves.
    """
    from importlib.metadata import Distribution
    from pathlib import Path
    here = _where_it_loaded(module)
    if here is None:
        return {}                       # a zipapp or a frozen build: no place to look
    found = {}
    try:
        discovered = list(Distribution.discover(name=name))
    except Exception:                                       # noqa: BLE001
        return {}
    for dist in discovered:
        try:
            base = Path(dist.locate_file("")).resolve()
            if base != here or dist.read_text("METADATA") is None:
                continue
            found[str(getattr(dist, "_path", base))] = dist.version
        except Exception:                                   # noqa: BLE001
            continue
    return found


def _disagreement() -> Optional[str]:
    try:
        import vdi2770
    except Exception as e:                                  # noqa: BLE001
        return f"the reader this tool is built on did not import: {e!r}"
    try:
        from vdi2770 import validate as rules
    except Exception as e:                                  # noqa: BLE001
        return f"the rules did not import: {e!r}"

    reader = getattr(vdi2770, "__version__", None)
    ruleset = getattr(rules, "__version__", None)

    # And the old name, when a machine still has it. Absent is fine -- the
    # single-file build carries no alias and a clean install of 0.8 has no
    # reason to. What is not fine is a *stale* one: `vdi2770-validate` shipped
    # real code with a version of its own until 0.7, so a machine that upgraded
    # the engine and left that behind imports seven releases of rules under a
    # name everything written before this still uses. Same shape as the split
    # pair, and the reason this check exists.
    legacy = None
    try:
        import vdi2770_validate as _old
        legacy = getattr(_old, "__version__", None)
    except Exception:                                       # noqa: BLE001
        pass
    if legacy is not None and ruleset is not None and folded(legacy) != folded(ruleset):
        return (f"`import vdi2770_validate` gives {legacy} and the rules in "
                f"`vdi2770.validate` are {ruleset}. The old name is an alias "
                f"for the new one from 0.8 on, so a different number there is "
                f"an older release still installed under it.")
    if reader is None or ruleset is None:
        missing = "reader" if reader is None else "rules"
        return (f"the {missing} half does not say what version it is; what is "
                f"on the path is not a release of it")
    if folded(reader) != folded(ruleset):
        return (f"the reader at {vdi2770.__file__} says {reader} and the rules "
                f"at {rules.__file__} say {ruleset}. They ship together under "
                f"one tag and carry one number.")

    # Both records live where the *reader* was loaded from: a distribution's
    # `.dist-info` sits beside the top-level package, and `vdi2770.validate` is
    # a directory below it. Asking about `vdi2770/validate/` found nothing,
    # ever -- so the loop's second turn was checking a stale `vdi2770-validate`
    # record it could not see, which is the state this check kept for after the
    # merge.
    for module, name, loaded in ((vdi2770, "vdi2770", reader),
                                 (vdi2770, "vdi2770-validate", ruleset)):
        records = _co_located_records(module, name)
        spellings = {folded(v) for v in records.values()}
        if len(spellings) > 1:
            return (f"{module.__file__} loaded, and beside it are "
                    + ", ".join(f"{path} recording {v}" for path, v in sorted(records.items())))
        if spellings and folded(loaded) not in spellings:
            path, recorded = next(iter(records.items()))
            return (f"{module.__file__} says it is {loaded} and {path}, in the "
                    f"same directory, records {recorded}")
    return None


_ANSWER: list = []


def disagreement() -> Optional[str]:
    """What does not add up, or None. Computed once per process."""
    if not _ANSWER:
        _ANSWER.append(_disagreement())
    return _ANSWER[0]


def refuse_early() -> Optional[int]:
    """An exit code to stop on, or None to carry on. For the entry points only.

    The same question as `refuse_if_disagreeing`, answered before there is
    anything to raise into: this runs ahead of the imports that would fail, so
    it reports rather than raises and hands the code straight back to the door
    it was called from. `disagreement()` is computed once, so the check further
    in costs nothing after this.
    """
    said = disagreement()
    if said is None:
        return None
    import sys
    print(f"{MARKER}: {said}", file=sys.stderr)
    return 3


def refuse_if_disagreeing() -> None:
    """Raise rather than judge.

    A verdict from an installation that cannot say what it is, is the thing
    this exists to prevent, and a warning printed above a PASS is read as a
    PASS.
    """
    said = disagreement()
    if said is not None:
        raise InstallationDisagrees(said)
