"""Nothing this repository publishes describes the rhythm of the work.

A verdict is the product. How long something took, on which day it happened,
what a stretch of work spent itself on — none of that is a property of the
code, and all of it is in files that go into an sdist and stay there.

The reason this is a gate rather than a habit is that the habit missed it three
times. A search came back empty while the phrase was in the file, split across
a line break; a sweep of ten documents did not include the test files, which are
prose too; and the commit message written to remove one such phrase quoted it.
Each miss was a different shape of the same thing — looking somewhere the words
were not.

So: every tracked text file, read with its line breaks taken out, against a list
that grows when somebody finds a new way to say it.
"""
import re
import subprocess

from conftest import ROOT

#: Phrases that say when the work happened. Each one is a claim about elapsed
#: time or a calendar, not a figure of speech: `yesterday's green` is about a
#: stale result and stays, a rule title counting entries in one domain stays,
#: and `today` meaning "as things now stand" stays. What goes is the sentence
#: that tells a reader how long something took or on which day it happened.
#:
#: Written with `\s+` rather than a literal space, which does two things. It
#: matches the wrapped form directly, so the pattern no longer depends on the
#: normalisation below to see a phrase split across a line break -- and the one
#: that was missed twice was split exactly that way. And it keeps the forbidden
#: strings out of this file, which is the whole reason the file could not be
#: committed the first time: a list of what must not be written, written.
WHEN = (
    r"one\s+afternoon", r"the\s+next\s+day", r"this\s+cycle",
    r"this\s+release\s+cycle", r"twice\s+in\s+one\s+day",
    r"\bovernight\b", r"the\s+same\s+day", r"\bthis\s+week\b",
    r"in\s+one\s+sitting", r"last\s+night", r"\bso\s+far\s+today\b",
    r"over\s+the\s+last\s+few\s+(days|hours)",
    r"in\s+(a|one)\s+single\s+(day|session|sitting)",
)

#: Files that are not prose this project publishes as its own voice.
NOT_OURS = (
    "corpus/",                       # vendored, byte-for-byte
    "tests/data/",                   # vendored message lists
    "docs/oracle-sweep.json",        # produced by running somebody else's tool
    # The mutation table holds broken versions of this repository's own text on
    # purpose -- including the sentence this gate forbids, because the row that
    # proves the gate bites has to put it back. Forbidding it here would forbid
    # showing that the gate works. This is the only file in the exemption list
    # that is ours, and it is exempt for the reason a gate exists at all.
    "tools/mutation_table.py",
    # This file was exempt too, until the patterns were written with `\s+`:
    # a list of phrases that must not appear is a list that contains them, and
    # the exemption was invisible while the file was untracked, because
    # `git ls-files` does not list what is not committed. The first run in a
    # tree with no git, where the fallback walks everything, reported it. It is
    # no longer exempt, because it no longer contains them.
)

TEXT = (".md", ".py", ".txt", ".toml", ".yml", ".yaml", ".cfg", ".json")


#: Directories that hold nothing this project wrote: build output, virtual
#: environments, caches. Only consulted where there is no git to ask.
NOT_SOURCE = {".git", ".venv", "venv", "build", "dist", "__pycache__",
              ".pytest_cache", ".ruff_cache", "node_modules"}


def _names():
    """Every file, from git where there is a git and from the tree where there
    is not.

    `git ls-files` is the better answer -- it knows what is committed and
    ignores build output by construction -- and it is not always available:
    the mutation harness runs on a copy of the tree with no `.git`, and so does
    an unpacked sdist. The first version called it with `check=True`, so in
    those places this gate did not fail, it *errored*, which the harness
    reported as "the tests it names already fail before the mutation".
    """
    done = subprocess.run(["git", "ls-files"], cwd=ROOT,
                          capture_output=True, text=True)
    if done.returncode == 0 and done.stdout.strip():
        return [n for n in done.stdout.split("\n") if n]
    return [str(p.relative_to(ROOT)) for p in sorted(ROOT.rglob("*"))
            if p.is_file() and not set(p.relative_to(ROOT).parts) & NOT_SOURCE
            and not p.name.endswith(".egg-info")]


def tracked():
    for name in _names():
        if not name.endswith(TEXT):
            continue
        if any(name.startswith(skip) or name == skip for skip in NOT_OURS):
            continue
        yield name


def test_no_published_file_says_when_the_work_happened():
    pattern = re.compile("|".join(WHEN), re.I)
    found = []
    for name in tracked():
        # Line breaks taken out first. The phrase that was missed twice was
        # `this\ncycle`, and no pattern read against the raw file could see it.
        prose = " ".join((ROOT / name).read_text(encoding="utf-8",
                                                 errors="replace").split())
        for m in pattern.finditer(prose):
            found.append(f"{name}: …{prose[max(0, m.start() - 50):m.end() + 50]}…")
    assert not found, (
        "published prose describes when the work happened rather than what it "
        "does:\n  " + "\n  ".join(found))


def test_the_sweep_actually_reads_something():
    """A file list that comes back empty passes every assertion above it.

    This project has shipped that gate once already — a check that collected
    nothing and reported success on everything — so the list is asserted to be
    a list of real files, and to include the two kinds that were missed: the
    changelog, and the test files.
    """
    names = list(tracked())
    assert len(names) > 50, f"the sweep found {len(names)} files"
    assert "CHANGELOG.md" in names
    assert any(n.startswith("tests/") and n.endswith(".py") for n in names), (
        "the sweep does not read the test files, which is where a phrase "
        "survived the sweep of the documents")
