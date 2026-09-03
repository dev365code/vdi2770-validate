import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

CORPUS = ROOT / "corpus" / "examples"
FIXTURES = ROOT / "tests" / "fixtures"
CLEAN_DOCUMENT = CORPUS / "container" / "documentcontainer.zip"
CLEAN_DOCUMENTATION = CORPUS / "container" / "documentationcontainer.zip"


# Three tests spelled numbers out of three private dicts with three different
# ceilings, and all three failure modes were live: `{6: "six", 13: "thirteen"}`
# raised KeyError on 7, `{1: "24th", 2: "25th"}` was off by one, and
# `{...: "thirteen"}` reached exactly as far as the number that happened to be
# true when it was written. A prose gate that crashes instead of reporting is a
# gate nobody can read the output of.
_WORDS = ("zero one two three four five six seven eight nine ten eleven twelve "
          "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty")


def spelled(n: int) -> str:
    """The English word for a small number, or the digits when it grows past
    where writing it out stays natural. Never raises: the caller is checking
    prose, and "the prose says 21 and the count is 22" is the message that
    helps."""
    words = _WORDS.split()
    if 0 <= n < len(words):
        return words[n]
    if len(words) <= n < 30:
        return "twenty-" + words[n - 20]
    return str(n)


def ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def under_test(**kw):
    """Environment for a subprocess that must run *this* tree.

    `pytest`'s `pythonpath` setting does not cross a subprocess boundary, so
    `-m vdi2770_validate` in a child imports whatever is installed. On a dev box
    that is an editable install of the same checkout and the difference never
    shows; under `tools/mutation_table.py --run` and `tools/check_sdist.py`,
    which both run the suite from a *copy*, the child measures the original
    tree. A mutation to the CLI left `test_readme_sample.py` — the mutation
    table's canary — green in the copy it was supposed to be judging.
    """
    import os

    env = dict(os.environ, PYTHONPATH=os.pathsep.join(
        [str(ROOT / "src"), str(ROOT / "packages" / "vdi2770" / "src")]))
    env.update(kw)
    return env


def newest_changelog_section() -> str:
    """The top section of CHANGELOG.md, whatever it is called.

    Three gates read the numbers in it and all three found that section by
    slicing at the first `## 0.` — which works exactly until somebody cuts a
    release, at which point the top section *is* a `## 0.` and the slice is
    empty. The checks stopped at the one moment they exist for.

    Released sections below the top are history and must not be edited, so they
    are deliberately out of scope: work lands in a new section above them, and
    that is the one whose claims still have to be true.

    Line-anchored, fence-aware, and it does not raise. The first draft sliced on
    the substring `"\\n## "`, which missed a heading on the very first line, ended
    a section at a `## ` inside a fenced code block, and raised `ValueError` on a
    file with no sections at all -- beside a sibling whose docstring says a gate
    that crashes instead of reporting is a gate nobody can read the output of.
    """
    lines = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").splitlines(keepends=True)
    fenced, start = False, None
    for n, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced or not line.startswith("## "):
            continue
        if start is None:
            start = n
        else:
            return "".join(lines[start:n])
    return "".join(lines[start:]) if start is not None else ""


# The least a file can be and still be a PDF: a header and one indirect object.
# Tests that need "a PDF" and wrote only the header were asserting against a
# reader that agreed the header was enough, which it no longer does -- see
# `pdfread._read`. Not valid enough to render; valid enough to be the thing the
# test says it is.
A_PDF = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n"
