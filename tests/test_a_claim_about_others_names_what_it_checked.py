"""A sentence about what *other* tools do is a claim this repository cannot
support, because it has measured one other tool.

`docs/oracle-sweep.json` holds the reference implementation's verdicts on the
corpus, pinned to one commit. That is the whole of what is known here about
anybody else's checker. From it, "the reference implementation has no rule for
this" is derivable; "nobody else says it" is not, and neither is any sentence
that ranks this tool against a field it never ran.

The rule this file applies: prose that ships -- the pages, the changelog, the
action's description and the rule data -- may say what *this* tool does and what
*the pinned reference* does. A phrase that quantifies over everyone else fails
here, and the fix is to narrow the sentence to what was measured rather than to
delete it: the thing it was reaching for is usually true of the reference and
worth keeping.
"""
import json
import re

from conftest import ROOT

#: Phrases that assert something about a field this repository has not run.
#: Each alternative is a claim shape, not a word: `only` on its own is ordinary
#: English ("the only one a user can find in their ZIP listing") and three true
#: sentences in the changelog use it.
UNSUPPORTABLE = re.compile(
    r"nobody else|no one else|everyone else"
    r"|world'?s first|industry.?first|first and only"
    r"|the only (?:tool|validator|implementation|checker|project)"
    r"|no other (?:tool|validator|implementation|checker|project)"
    r"|unique(?:ly)? (?:in|among)"
    r"|unmatched|best[- ]in[- ]class|state of the art"
    r"|zero false positives|no false positives",
    re.I)

#: Everything a reader of this project meets without opening a test file.
PAGES = ["README.md", "README-vdi2770-validate.md", "packages/vdi2770/README.md",
         "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md", "action.yml"]

RULES = "packages/vdi2770/src/vdi2770/validate/data/rules.json"


def published_prose():
    """Every (where, text) pair a reader can reach, pages and rule data alike."""
    for name in PAGES:
        page = ROOT / name
        for number, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
            yield f"{name}:{number}", line
    for page in sorted((ROOT / "docs").glob("*.md")):
        rel = page.relative_to(ROOT)
        for number, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
            yield f"{rel}:{number}", line
    rules = json.loads((ROOT / RULES).read_text(encoding="utf-8"))
    rules = rules["rules"] if isinstance(rules, dict) and "rules" in rules else rules
    for rule in (rules.values() if isinstance(rules, dict) else rules):
        for field, value in rule.items():
            if isinstance(value, str):
                yield f"{RULES} {rule.get('id')}.{field}", value


def test_no_page_claims_something_about_everyone_else():
    found = [(where, UNSUPPORTABLE.search(text).group(0), text.strip()[:120])
             for where, text in published_prose() if UNSUPPORTABLE.search(text)]
    assert not found, (
        "these sentences quantify over tools this repository has not run. "
        "Narrow each to what was measured -- the pinned reference implementation, "
        "named -- rather than deleting it:\n"
        + "\n".join(f"  {w}: <{m}> {t}" for w, m, t in found))


def test_the_sweep_reads_the_pages_it_is_named_for():
    """A scanner over an empty list passes. This one has to have read the front
    page and the rule data, which is where such a sentence is written."""
    where = {w.split(":")[0].split(" ")[0] for w, _ in published_prose()}
    assert "README.md" in where and RULES in where, sorted(where)


def test_the_phrase_list_catches_the_shape_it_is_for():
    """The guard fails on the sentence it was written for. Without this, a
    pattern that stopped matching would read as a clean repository."""
    for sentence in ("worth saying even though nobody else says it",
                     "the only validator that runs offline",
                     "the world's first VDI 2770 checker",
                     "no false positives on the corpus"):
        assert UNSUPPORTABLE.search(sentence), sentence
    for ordinary in ("those four releases are the only ones that ask for a floor",
                     "the only one a user can find in their ZIP listing",
                     "this is the first release to carry the action"):
        assert not UNSUPPORTABLE.search(ordinary), ordinary
