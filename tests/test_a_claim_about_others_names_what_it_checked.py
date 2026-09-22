"""A sentence about what *other* tools do is a claim this repository cannot
support, because it has measured one other tool on 49 containers.

`docs/oracle-sweep.json` holds the reference implementation's verdicts on that
corpus, pinned to one commit. It records the codes that were *emitted*, which is
a narrower thing than a rule inventory: a container it is silent on may simply
not exercise the condition, and a container it speaks on may be speaking about
something else. So "the reference emitted nothing here" is derivable from it;
"the reference has no rule for this" is not, and neither is any sentence that
ranks this tool against a field it never ran.

The rule this file applies: prose that ships -- the pages, the changelog, the
licence notices, the action's description and the rule data -- may say what
*this* tool does. A phrase that quantifies over everyone else fails here.

Two things a reader of a failure should know. The fix is to narrow the sentence
to what was measured rather than to delete it; what it was reaching for is
usually true of the pinned reference and worth keeping. And the gate refuses the
*shape*, so it will refuse a sentence of that shape even where the sentence is
true -- say it another way ("the one other checker this project has run"), or
this file becomes the file somebody switches off.

It reads paragraphs rather than lines. The prose here is hard-wrapped near 79
columns, so a line-oriented scan misses any claim that happens to straddle a
break -- measured at up to one line position in five for the phrases below.
"""
import json
import re

from conftest import ROOT

#: Phrases that assert something about a field this repository has not run.
#: Each alternative is a claim shape, not a word. `only` on its own is ordinary
#: English -- "the only one a user can find in their ZIP listing" -- and it
#: appears twenty-three times in the prose scanned here; a pattern that caught
#: those would be turned off within a week. Likewise `unmatched`, which is what
#: an XML reader calls a tag, and `unique in`, which is what an archive's entry
#: names have to be.
NOUN = r"(?:tool|validator|implementation|checker|project|library|package|software)"
UNSUPPORTABLE = re.compile(
    r"nobody else|no[- ]?one else|everyone else|everybody else"
    r"|nothing else (?:on the market|catches|reports|finds|sees|does)"
    r"|world'?s (?:first|only|best)|industry.?first|first and only"
    rf"|the only (?:\w+[- ]){{0,3}}{NOUN}"
    rf"|the first (?:\w+[- ]){{0,3}}{NOUN} to"
    rf"|no other (?:\w+[- ]){{0,3}}{NOUN}"
    rf"|unlike (?:other|any other|every other|all other) {NOUN}s?"
    r"|unique(?:ly)? (?:in the (?:field|market|industry)"
    r"|among (?:tools|validators|implementations|checkers))"
    rf"|best[- ]in[- ]class|state of the art|unrivall?ed|most complete {NOUN}"
    r"|(?:zero|no|0) false positives?|never a false positive"
    r"|more than any other",
    re.I)

#: Everything a reader of this project meets without opening a test file. The
#: two notices are here because they ship inside both wheels as the licence
#: text, which is the same reason `test_the_docs_count_what_they_claim.py`
#: reads them -- prose in a published artefact, outside every `.md` gate.
PAGES = ["README.md", "README-vdi2770-validate.md", "packages/vdi2770/README.md",
         "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md", "action.yml",
         "NOTICE", "THIRD_PARTY.md", "packages/vdi2770/NOTICE"]

RULES = "packages/vdi2770/src/vdi2770/validate/data/rules.json"


def flattened(text):
    """The text with every run of whitespace collapsed to one space, and a map
    from each offset back to the line it started on.

    Hard-wrapped prose puts a line break in the middle of the phrase being
    looked for. Collapsing first is what makes the scan independent of where a
    paragraph happens to wrap; the map is what lets a failure still name a line.
    """
    chars, lines, line, in_space = [], [], 1, False
    for ch in text:
        at = line
        if ch == "\n":
            line += 1
        if ch.isspace():
            if not in_space:
                chars.append(" ")
                lines.append(at)
            in_space = True
        else:
            chars.append(ch)
            lines.append(at)
            in_space = False
    return "".join(chars), lines


def strings_in(node):
    """Every string anywhere under a parsed JSON node.

    Walked rather than read field by field: a `whyOurs` that became
    `{"en": ..., "de": ...}` for a German standard would drop out of a scan that
    only accepts `str`, and nothing would notice. The top-level prose in
    `rules.json` -- what the layers and obligations mean -- is reached the same
    way, and it ships in the wheel.
    """
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from strings_in(value)
    elif isinstance(node, list):
        for value in node:
            yield from strings_in(value)


def published_prose():
    """Every (where, text) pair a reader can reach, pages and rule data alike."""
    pages = [ROOT / name for name in PAGES]
    # `rglob`, not `glob`: this repository has been bitten before by a fixed-depth
    # scan beside a recursive one -- `tools/capture_oracle.py` records the
    # container that was invisible for exactly that reason -- and a page moved
    # one directory down would leave here without a sound.
    pages += sorted(p for p in (ROOT / "docs").rglob("*.md"))
    for page in pages:
        rel = page.relative_to(ROOT)
        text, lines = flattened(page.read_text(encoding="utf-8"))
        yield str(rel), text, lines
    rules = json.loads((ROOT / RULES).read_text(encoding="utf-8"))
    for value in strings_in(rules):
        text, lines = flattened(value)
        yield RULES, text, lines


def offenders():
    found = []
    for where, text, lines in published_prose():
        for m in UNSUPPORTABLE.finditer(text):
            at = lines[m.start()] if lines else 0
            found.append((f"{where}:{at}", m.group(0), text[max(0, m.start() - 60):m.end() + 60]))
    return found


def test_no_page_claims_something_about_everyone_else():
    found = offenders()
    assert not found, (
        "these sentences quantify over tools this repository has not run. "
        "Narrow each to what was measured -- the pinned reference, on the "
        "containers it was run over -- rather than deleting it:\n"
        + "\n".join(f"  {w}: <{m}> ...{t}..." for w, m, t in found))


def test_the_sweep_reads_the_pages_it_is_named_for():
    """A scanner over an empty list passes, and so does one whose `docs` glob
    stopped matching. This names one file from each half it claims to read."""
    where = {w for w, _, _ in published_prose()}
    for required in ("README.md", "CHANGELOG.md", "NOTICE", "docs/rules.md", RULES):
        assert required in where, (required, sorted(where))


def test_the_phrase_list_catches_the_shape_it_is_for():
    """The guard fails on the sentences it was written for, including the ones
    a reader of this repository would most plausibly write: it is a Python
    reimplementation of a Java reference, so "the only Python implementation" is
    the natural sentence, and hard-wrapped prose puts a newline in the middle of
    the phrase."""
    for sentence in ("worth saying even though nobody else says it",
                     "the only validator that runs offline",
                     "the only open-source Python implementation of the guideline",
                     "the first validator to read the XSD offline",
                     "the world's first VDI 2770 checker",
                     "no false positives on the corpus",
                     "0 false positives across the corpus",
                     "unlike other tools, this one opens no socket",
                     "say what was measured, not what everybody else does",
                     "no-one else makes this judgement",
                     "nothing else on the market catches it",
                     "worth saying even though nobody\nelse says it"):
        text, _ = flattened(sentence)
        assert UNSUPPORTABLE.search(text), sentence
    for ordinary in ("those four releases are the only ones that ask for a floor",
                     "the only one a user can find in their ZIP listing",
                     "this is the first release to carry the action",
                     "the parser reports an unmatched tag and stops",
                     "entry names must be unique in the archive",
                     "each rule id is unique in the table",
                     "a run with no findings is not a run with no misses"):
        text, _ = flattened(ordinary)
        assert not UNSUPPORTABLE.search(text), ordinary
