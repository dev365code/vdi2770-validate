"""Drift gate for the capabilities picture (copied into tests/ of each repository).

What it holds:
  1. docs/capabilities.svg and docs/capabilities.md are byte-identical to what the generator
     produces from docs/capabilities.json (edit the data, run the generator, commit both). Loading
     the data also refuses comparison words, dates, markup, and done items without evidence.
  2. every piece of evidence is a file inside the repository that says the words it is cited for.
  3. the data's `as_of` equals the package version, so the picture cannot describe a stale version.
  4. README embeds the picture from the repository's raw URL, stamped with the committed picture's
     hash, inside a link to the detail page, and the image alt text equals the one-line summary the
     generator derives from the data (readers without the picture get the same six facts).
  5. README states the generator's 1.0 condition paragraph verbatim in its visible text (every
     checklist item, done or not, right after its axis label), so the picture cannot promise what
     the page does not, and a shrunken checklist changes a public sentence.
  6. the detail page docs/what-it-catches.md has one section per axis, in the drawn order, and each
     section names that axis's checklist items.
  7. the detail page and the README paragraph under the picture use no comparison words.
  8. evidence paths are posix on every platform (Windows would otherwise commit backslashes and let
     "..\\" past the escape check), and the data gates refuse what a reader could not verify: a count
     no quote leads with, a summary that does not lead with its number, a quote under three words,
     the picture's own files or the detail page as evidence, a summary piece no item says, "met"
     while an item is undone, a comparative or contrast aimed at someone else.
  9. evidence found only in an HTML comment, in README's "Where it stands" section, or in the 1.0
     paragraph does not hold: those are copies of the data, not the page vouching for it.
 10. the word lists themselves: comparatives and superlatives aimed past this tool are refused in
     short text and in prose, and plain description ("more than 200 rules", "more than one",
     "no other check here has run", "rather than") is not.
 11. the generated detail page is read through prose_only(): fenced or indented blocks (captured
     output, quoted rule text), quotation lines and bare link lines are not the project speaking;
     README's hand-written section is read whole, every visible line.
What these gates do not see, and a repository adds its own test for: whether a detail-page line
matches the data word for word, whether a quoted report output is what the tool prints, whether a
"done" item is true beyond the quoted words.

Per-repo settings: PACKAGE (import name) and, if the repo keeps the generator elsewhere, GENERATOR.
"""
import hashlib
import importlib
import json
import ntpath
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = "vdi2770"                             # per repo
GENERATOR = ROOT / "tools" / "capabilities_svg.py"
DATA = ROOT / "docs" / "capabilities.json"
SVG = ROOT / "docs" / "capabilities.svg"
MD = ROOT / "docs" / "capabilities.md"
DETAIL = ROOT / "docs" / "what-it-catches.md"
README = ROOT / "README.md"


def _gen():
    if str(GENERATOR.parent) not in sys.path:
        sys.path.insert(0, str(GENERATOR.parent))
    return importlib.import_module(GENERATOR.stem)


def _data():
    return _gen().load(str(DATA))


def _squash(text):
    return re.sub(r"\s+", " ", text)


def _home():
    m = re.search(r'(?m)^Homepage = "https://github\.com/([^/"]+)/([^/"]+)"', (ROOT / "pyproject.toml").read_text("utf-8"))
    assert m, "pyproject.toml must name the GitHub Homepage"
    return m.group(1), m.group(2)


def _sections(text):
    """{heading: body} for every H2 of the detail page, in order."""
    parts = re.split(r"(?m)^## (.+)$", text)
    return [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts) - 1, 2)]


def test_rendered_files_match_the_data():
    gen = _gen()
    data = gen.load(str(DATA))
    assert SVG.read_text(encoding="utf-8") == gen.render_svg(data), "docs/capabilities.svg is stale: rerun the generator"
    assert MD.read_text(encoding="utf-8") == gen.render_md(data), "docs/capabilities.md is stale: rerun the generator"


def test_every_piece_of_evidence_says_what_it_is_cited_for():
    gen = _gen()
    data = _data()
    for ax in data["axes"]:
        for ev in ax["evidence"]:
            assert gen.evidence_holds(str(ROOT), ev, data), (
                f"axis {ax['key']}: {ev['file']} does not say {ev['says']!r} outside the picture's own text")


def test_as_of_is_the_package_version():
    pkg = importlib.import_module(PACKAGE)
    assert _data()["as_of"] == pkg.__version__


def test_readme_links_the_committed_picture_to_the_detail_page():
    readme = README.read_text(encoding="utf-8")
    data = _data()
    owner, repo = _home()
    raw = f"https://raw.githubusercontent.com/{owner}/{repo}/main/"
    blob = f"https://github.com/{owner}/{repo}/blob/main/"
    m = re.search(r'<a href="([^"]+)">\s*<img src="' + re.escape(raw) + r'docs/capabilities\.svg\?v=([0-9a-f]{8})" alt="([^"]*)"',
                  readme)
    assert m, "README must embed the raw docs/capabilities.svg?v=<hash> inside a link to the detail page"
    assert m.group(1) == blob + data["detail"], "the picture must link to the detail page on GitHub"
    assert m.group(2) == hashlib.sha256(SVG.read_bytes()).hexdigest()[:8], "?v= is not the committed picture's hash"
    assert m.group(3) == _gen().summary_line(data), "alt text must be the generator's one-line summary"


def test_every_condition_on_the_picture_is_in_the_readme():
    gen = _gen()
    readme = _squash(gen.visible(README.read_text(encoding="utf-8")))       # what a reader sees
    assert _squash(gen.condition_paragraph(_data())) in readme, (
        "README must state the 1.0 condition paragraph verbatim (the last paragraph of docs/capabilities.md): "
        "every axis label followed by its full condition, in the drawn order, outside HTML comments")


def test_detail_page_has_one_section_per_axis_in_order_naming_its_items():
    sections = _sections(DETAIL.read_text(encoding="utf-8"))
    positions = []
    for ax in _data()["axes"]:
        label = ax["label"]
        hit = next((i for i, (h, _) in enumerate(sections) if re.fullmatch(re.escape(label) + r"(\s*[—:(].*)?", h)), None)
        assert hit is not None, f"detail page lacks a section headed {label!r}"
        positions.append(hit)
        body = sections[hit][1]
        for it in ax.get("items", []):
            assert it["text"] in body, f"the {label} section does not mention its item {it['text']!r}"
    assert positions == sorted(positions), "detail page sections must follow the drawn order"


def test_the_prose_around_the_picture_compares_with_nobody():
    gen = _gen()
    detail = gen.prose_only(DETAIL.read_text(encoding="utf-8"))
    m = gen.FORBIDDEN_PROSE.search(detail)
    assert not m, f"detail page: {m.group(0)!r} turns a self-description into a comparison"
    readme = README.read_text(encoding="utf-8")
    block = re.search(r"## Where it stands\n(.*?)(?=\n## |\Z)", readme, flags=re.DOTALL)
    assert block, "README lacks the '## Where it stands' section"
    m = gen.FORBIDDEN_PROSE.search(gen.visible(block.group(1)))  # hand-written: every visible line
    assert not m, f"README 'Where it stands': {m.group(0)!r} turns a self-description into a comparison"


def test_evidence_paths_are_posix_even_on_windows(monkeypatch):
    gen = _gen()
    monkeypatch.setattr(gen.os, "path", ntpath)          # what the generator sees on Windows
    quote = "three words of quote"
    assert gen._evidence("t", {"file": "docs/./scope.md", "says": quote}, set())["file"] == "docs/scope.md"
    for escape in ("docs/../../etc/passwd", "..\\etc\\passwd", "/etc/passwd", "C:/etc/passwd"):
        with pytest.raises(SystemExit):
            gen._evidence("t", {"file": escape, "says": quote}, set())


def _refused(tmp_path, mutate):
    data = json.loads(DATA.read_text(encoding="utf-8"))
    mutate(data)
    path = tmp_path / "capabilities.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SystemExit):
        _gen().load(str(path))


def test_the_data_gates_refuse_what_a_reader_could_not_verify(tmp_path):
    data = json.loads(DATA.read_text(encoding="utf-8"))
    axes = data["axes"]
    counts = [i for i, ax in enumerate(axes) if "items" not in ax]
    if counts:
        i = counts[0]
        now, target = axes[i]["now"], axes[i]["target"]
        _refused(tmp_path, lambda d: d["axes"][i].__setitem__("now", now + 1))                 # quote says now
        _refused(tmp_path, lambda d: d["axes"][i].__setitem__("target", target + 1))           # sentence says target
        _refused(tmp_path, lambda d: d["axes"][i].__setitem__("now_text", f"{now + 1} of {target}"))
        _refused(tmp_path, lambda d: d["axes"][i]["evidence"].__setitem__(
            0, {"file": "README.md", "says": f"{target} of {now} {target}"}))                   # a substring is not a token
    checklists = [i for i, ax in enumerate(axes) if "items" in ax]
    i = checklists[0]
    j = next(j for j, it in enumerate(axes[i]["items"]) if it["done"])
    _refused(tmp_path, lambda d: d["axes"][i]["items"][j]["evidence"].__setitem__("says", "two words"))
    _refused(tmp_path, lambda d: d["axes"][i]["items"][j]["evidence"].__setitem__("file", "docs/capabilities.json"))
    _refused(tmp_path, lambda d: d["axes"][i]["items"][j]["evidence"].__setitem__("file", d["detail"].upper()))
    _refused(tmp_path, lambda d: d["axes"][i].__setitem__("now_text", "something no item says"))
    partial = [k for k in checklists if any(not it["done"] for it in axes[k]["items"])]
    if partial:
        k = partial[0]
        undone = next(it["text"] for it in axes[k]["items"] if not it["done"])
        _refused(tmp_path, lambda d: d["axes"][k].__setitem__("target_text", "met"))          # not while undone
        _refused(tmp_path, lambda d: d["axes"][k].__setitem__("now_text", undone))            # undone is not now
    # the product name is refused before any structural check, so this reaches the word list itself
    _refused(tmp_path, lambda d: d.__setitem__("product", "a checker stricter than any other"))
    _refused(tmp_path, lambda d: d.__setitem__("product", "the most thorough checker"))


COMPARING = ("stricter than any other checker", "more rules than any checker", "unlike other validators",
             "the most thorough validator", "the strictest reading", "outperforms every reader",
             "second to none", "the widest coverage of any validator", "compared with other tools",
             "no other checker does this", "better than the reference",
             "No other iiRDS validator reads both serialisations.", "no other open-source checker does this",
             "No other library names the line.", "Any other iiRDS tool would pass this package.",
             "It finds more than twice as many defects as the reference implementation.",
             "It catches more than ten times the errors the reference misses.",
             "iirds-validate is unique among iiRDS validators.", "172 of 280, as no other iiRDS tool does")
DESCRIBING = ("more than 200 rules", "re-measured on every release rather than promised",
              "checked weekly for change", "the section of the specification it enforces",
              "other than the manifest, nothing is read twice", "the report names the rule",
              "no other check here has run", "more than one element", "listed more than once",
              "the identifier MUST be unique within the package", "no other value is used",
              "listed more than once", "more than 200 rules")


def test_comparisons_and_superlatives_are_refused_and_plain_description_is_not():
    gen = _gen()
    for phrase in COMPARING:
        assert gen.FORBIDDEN.search(phrase), f"short text should refuse {phrase!r}"
        assert gen.FORBIDDEN_PROSE.search(phrase), f"prose should refuse {phrase!r}"
    for phrase in DESCRIBING:
        assert not gen.FORBIDDEN_PROSE.search(phrase), f"prose should allow {phrase!r}"


def test_captured_output_and_quotations_are_not_the_projects_prose():
    gen = _gen()
    page = ("The report names the rule.\n\n```\nstricter than any other checker\n```\n\n"
            "    unlike other validators\n\n> the most thorough validator\n\n"
            "<https://example.org/second-to-none>\n\n[ref]: https://example.org/better-than-the-reference\n")
    assert not gen.FORBIDDEN_PROSE.search(gen.prose_only(page)), "captured output and quotations are not prose"
    assert gen.FORBIDDEN_PROSE.search(gen.prose_only(page + "\nIt is stricter than any other checker.\n"))


def test_evidence_does_not_count_when_only_the_pictures_own_text_says_it(tmp_path):
    gen = _gen()
    data = _data()
    (tmp_path / "README.md").write_text(
        "# x\n\nthe plain words here\n\n<!-- the hidden words here -->\n\n"
        "## Where it stands\n\nthe copied words here\n\n## Next\n\n" + gen.condition_paragraph(data) + "\n",
        encoding="utf-8")
    def holds(says):
        return gen.evidence_holds(str(tmp_path), {"file": "README.md", "says": says}, data)

    assert holds("the plain words here")
    assert not holds("the hidden words here"), "an HTML comment is not something a reader sees"
    assert not holds("the copied words here"), "the picture's own section cannot vouch for the picture"
    assert not holds(gen.condition_paragraph(data)), "the 1.0 paragraph is a copy of this data"
