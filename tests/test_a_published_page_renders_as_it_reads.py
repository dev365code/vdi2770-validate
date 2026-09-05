"""A footnote written under the row it belongs to ends the table above it, and
the rows after it become pipe characters in a paragraph. In source it reads as
one table. It happened here, in `docs/divergences.md`, and every gate stayed
green: the numbers in the prose were all still right, and nothing read the shape
of a page.

The first version of this file looked for a stray line *between* two table rows,
which is the shape the mistake has in a diff and not the shape it has in a file —
there was a blank line on each side of the footnote, so that check would have
passed on the very break it was written for. What a renderer actually loses is a
row with no header above it, so that is what is counted here.

The pages are the ones somebody else reads: `README.md` and `CHANGELOG.md` are
what the package index renders, `NOTICE` and `THIRD_PARTY.md` travel inside the
wheel, and `docs/` is where both of those send a reader.
"""
import re

from conftest import ROOT

PAGES = ["README.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md",
         "THIRD_PARTY.md", "NOTICE"]

_DIVIDER = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


def _pages():
    named = [ROOT / name for name in PAGES]
    return [p for p in named + sorted((ROOT / "docs").glob("*.md")) if p.exists()]


def _cells(line: str) -> int:
    """Cells, not pipes. A pipe inside inline code or escaped with a backslash is
    a character in a cell, and counting it reports a width nobody wrote."""
    bare = re.sub(r"`[^`]*`", "", line).replace("\\|", "")
    return bare.strip().strip("|").count("|") + 1


def _blocks(lines):
    """Runs of pipe lines with nothing between them — one candidate table each.
    Fenced code is skipped: this repository prints sample output that begins with
    a pipe, and that is a program's writing, not a table."""
    fenced, block, start = False, [], 0
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            if block:
                yield start, block
                block = []
            continue
        if not fenced and line.strip().startswith("|"):
            if not block:
                start = i
            block.append(line)
        elif block:
            yield start, block
            block = []
    if block:
        yield start, block


def orphan_rows(lines):
    """Pipe rows with no header and divider above them. A renderer prints these
    as text, so they are simply missing from the table they were written for."""
    return [(start + 1, block[0].strip())
            for start, block in _blocks(lines)
            if len(block) < 2 or not _DIVIDER.match(block[1])]


def mismatched(lines):
    """Rows whose cell count differs from the header of their own table."""
    off = []
    for start, block in _blocks(lines):
        if len(block) < 2 or not _DIVIDER.match(block[1]):
            continue                      # not a table; `orphan_rows` has it
        width = _cells(block[0])
        for offset, row in enumerate(block[2:], start=start + 3):
            if _cells(row) != width:
                off.append((offset, _cells(row), width))
    return off


GOOD = """| a | b |
|---|---|
| 1 | 2 |
| 3 | `x \\| y` |
"""

#: The shape the real mistake had: a blank line, the footnote, a blank line, and
#: then a row that now belongs to nothing.
FOOTNOTE_INSIDE_THE_TABLE = """| a | b |
|---|---|
| 1 | 2 |

[^n]: a footnote written under the row it belongs to

| 3 | 4 |
"""

MISSING_A_CELL = """| a | b | c |
|---|---|---|
| 1 | 2 |
"""

SAMPLE_OUTPUT = """```
| this is a program's output |
```
"""


def test_the_checks_catch_a_page_that_is_broken():
    """Proof that these can fail, on the shape that got past the first attempt.
    A gate nobody has seen fail is a gate nobody knows the shape of."""
    assert not orphan_rows(GOOD.splitlines())
    assert not mismatched(GOOD.splitlines()), (
        "a pipe inside inline code is a character, not a cell boundary")
    assert not orphan_rows(SAMPLE_OUTPUT.splitlines()), (
        "a fenced sample is a program's writing, not a table")

    lost = orphan_rows(FOOTNOTE_INSIDE_THE_TABLE.splitlines())
    assert [line for line, _ in lost] == [7], lost
    assert lost[0][1] == "| 3 | 4 |", lost

    assert mismatched(MISSING_A_CELL.splitlines()) == [(3, 2, 3)]


def test_the_pages_being_checked_are_actually_there():
    """Both gates below pass over an empty list. A glob that stopped matching —
    a renamed directory, a page that moved — would report a clean sweep of
    nothing, which is the failure this repository has already had once."""
    found = {p.name for p in _pages()}
    assert {"README.md", "CHANGELOG.md", "THIRD_PARTY.md"} <= found, found
    assert sum(1 for p in _pages() if p.parent.name == "docs") >= 4, (
        "the docs directory contributed almost nothing; has it moved?")
    assert any("|" in p.read_text(encoding="utf-8") for p in _pages()), (
        "no page holds a table, so neither gate below is looking at anything")


def test_no_published_page_has_a_row_that_belongs_to_no_table():
    lost = []
    for page in _pages():
        for line, text in orphan_rows(page.read_text(encoding="utf-8").splitlines()):
            lost.append(f"{page.relative_to(ROOT)}:{line}: {text[:60]}")
    assert not lost, (
        "a row has no header above it, so a reader gets pipe characters in a "
        "paragraph where a table was written:\n  " + "\n  ".join(lost))


def test_every_table_row_carries_the_columns_its_header_declares():
    """A row short of a cell renders with the last column empty and a row over it
    renders with the extra dropped. Either way the page shows something the
    source does not say."""
    off = []
    for page in _pages():
        for line, got, want in mismatched(page.read_text(encoding="utf-8").splitlines()):
            off.append(f"{page.relative_to(ROOT)}:{line}: "
                       f"{got} cells, header declares {want}")
    assert not off, "a table row does not match its header:\n  " + "\n  ".join(off)
