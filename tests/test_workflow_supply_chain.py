"""What the workflows will run, held to a commit rather than to a name.

`pypa/gh-action-pypi-publish@release/v1` is a branch. Whatever that branch
points at on the morning of a release is what runs in the job that holds
`id-token: write` and uploads under this project's name -- and a tag is no
better, because a tag can be moved to another commit by whoever owns it. Both
are a promise by somebody else that the code will not change under us, and
nothing here noticed either way.

So every `uses:` names a full commit object, with the human-readable version
beside it: forty characters say nothing to the next person, and the one thing
they need to know before moving a pin is what they are moving from.

There is deliberately no updater. A tool that rewrites these lines is one more
moving reference, with write access to the file that decides what runs. The
cost is real and is the reason this is written down: a pin does not pick up the
fix upstream makes to it, so moving one is a thing somebody has to do.

Two holes are worth guarding against, both of which can let a workflow run
unpinned while every test here stays green:

* It swept `*.yml`. GitHub runs `*.yaml` too, so a workflow added -- or
  renamed -- with the other spelling was invisible, and `attacker/exfil@main`
  in it passed.
* Its guard was `at least five uses:`, which `ci.yml` satisfies on its own. A
  whole workflow could leave the sweep and the only sign was two fewer green
  tests than yesterday, which nobody counts. The guard is a list now, for the
  reason `tests/test_ci_parity.py` gives for its own: a count is not a list.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"

#: What GitHub runs out of that directory, both spellings, whatever the case.
RUNS = (".yml", ".yaml")

#: The workflows this repository has. A new one has to be added here on
#: purpose, and is then swept; one that disappears from this list without
#: being deleted is the failure this list exists to catch.
EXPECTED = {"ci.yml", "dco.yml", "oracle.yml", "release.yml"}

WORKFLOWS = sorted(path for path in WORKFLOWS_DIR.iterdir()
                   if path.is_file() and path.suffix.lower() in RUNS)

#: `uses:` and what follows it, with whatever comment trails on the same line.
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*(?P<ref>\S+)\s*(?P<comment>#.*)?$", re.M)

#: A full git object name. `@v7` and `@release/v1` are the two shapes this file
#: exists to refuse; an abbreviated hash is refused as well, because a short
#: one can be made to collide and GitHub resolves it like any other ref.
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def lines():
    """Every `uses:` in every workflow, as (file, action, ref, comment)."""
    found = []
    for path in WORKFLOWS:
        for match in USES.finditer(path.read_text(encoding="utf-8")):
            action, _, ref = match.group("ref").partition("@")
            found.append((path.name, action, ref, (match.group("comment") or "").strip()))
    return found


ALL = lines()


def test_the_workflows_swept_are_the_ones_this_repository_has():
    """The sweep sees every file GitHub would run, by name.

    A glob that matches nothing passes every parametrised test below by having
    no cases, and reads in CI as a row of green. So this is the one assertion
    that does not depend on the sweep: the directory's own contents.
    """
    runs = {path.name for path in WORKFLOWS_DIR.iterdir()
            if path.is_file() and path.suffix.lower() in RUNS}
    assert runs == EXPECTED, (
        f"GitHub runs {sorted(runs)}; this file expects {sorted(EXPECTED)}. A workflow "
        "that is added, renamed or deleted is named here on purpose.")
    assert {path.name for path in WORKFLOWS} == EXPECTED


@pytest.mark.parametrize("path,action,ref", [(p, a, r) for p, a, r, _ in ALL],
                         ids=[f"{p}:{a}" for p, a, _, _ in ALL])
def test_every_action_names_a_commit(path, action, ref):
    if action == "./":
        # This repository's own action, at the commit being tested. There is no
        # third party to decide later what runs, and pinning a SHA here would
        # pin the workflow to a *past* version of the action it is supposed to
        # be exercising -- the one thing this job exists to prevent.
        return
    assert COMMIT.match(ref), (
        f"{path} uses {action}@{ref} -- a tag or a branch, which is whoever owns it "
        "deciding later what runs here. (A local action, `./.github/actions/...`, "
        "carries no ref at all and would land here too; this repository has none, "
        "and adopting one means saying so in this file.)")


@pytest.mark.parametrize("path,action,comment", [(p, a, c) for p, a, _, c in ALL],
                         ids=[f"{p}:{a}" for p, a, _, _ in ALL])
def test_every_pin_says_which_version_it_is(path, action, comment):
    """Forty characters are unreadable, and an unreadable pin is never moved."""
    if action == "./":
        return                               # see above: no version to name
    assert re.match(r"^#\s*v?\d", comment), (
        f"{path} pins {action} with no version beside it; the comment reads {comment!r}")


def test_one_action_is_pinned_to_one_commit_under_one_name():
    """Whether a comment names the right release cannot be asked offline, and
    this suite does not reach the network. What can be asked is whether the
    file agrees with itself: the same action appears many times across these
    workflows, so a pin moved in one place and not the others, or a version
    label that disagrees with the commit beside it somewhere else, is a
    difference here. Both were green before this test existed.
    """
    seen = defaultdict(set)
    for _path, action, ref, comment in ALL:
        seen[action].add((ref, comment))
    disagreeing = {action: sorted(pairs) for action, pairs in seen.items() if len(pairs) > 1}
    assert not disagreeing, (
        f"the same action is pinned two ways: {disagreeing}")
