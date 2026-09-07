"""The front page is two documents at once, and the second one has no repository.

`README.md` is what GitHub renders and it is also `readme = "README.md"` in
`pyproject.toml` — the description the package index shows to somebody arriving
from `pip install`. A relative link works on the first and is dead on the
second, and a picture referenced relatively is dead there too.

A picture has a second failure mode the text does not: GitHub serves it through
an image proxy that caches by URL. Change the file, leave the address alone, and
every reader who has already seen the page keeps the old picture — so the page
goes on showing a verdict the tool stopped printing, with every gate green,
including the ones next door that ask whether the committed picture is true.
None of those asks whether the *page* points at the committed picture.

So: every picture is served from this repository's raw host, and its `?v=` is
the hash of the committed file. `tools/gen_door.py` sets both when it writes.
"""
from __future__ import annotations

import hashlib
import re

from conftest import ROOT

README = (ROOT / "README.md").read_text(encoding="utf-8")


def _home():
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    home = re.search(r'(?m)^Homepage = "https://github\.com/([^/"]+)/([^/"]+)"',
                     project)
    assert home, "pyproject.toml names no GitHub Homepage to check against"
    return home.groups()


def _pictures():
    """Every image on the page, found by every spelling one can be written in.

    Three, because a gate that reads one spelling is a gate a picture can be
    added beside. An `<img>` tag, a markdown `![](...)`, and a reference-style
    `![][label]` resolved through its definition — and the label match is
    case-folded, because markdown's is.
    """
    found = re.findall(r"""<img\s[^>]*?src=["']([^"']+)["']""", README)
    found += [target for _alt, target
              in re.findall(r"!\[([^\]]*)\]\(([^)\s]+)\)", README)]
    referenced = {label.lower() for label
                  in re.findall(r"!\[[^\]]*\]\[([^\]]+)\]", README)}
    found += [target for label, target
              in re.findall(r"(?m)^\[([^\]]+)\]:\s*(\S+)\s*$", README)
              if label.lower() in referenced]
    return found


def test_every_link_on_the_front_page_resolves_off_the_repository():
    """In-page anchors are fine — they resolve wherever the page is rendered."""
    links = re.findall(r"\]\(([^)]+)\)", README)
    assert links, "the front page has no links at all"
    dead = [target for target in links
            if not target.startswith(("http://", "https://", "#"))]
    assert not dead, (
        "these targets are relative, and this file is also the package "
        f"description, where there is no repository to resolve them: {dead}")


def test_the_page_shows_pictures_and_badges_this_gate_can_see():
    """A guard on the gate below, which passes over an empty list. A picture
    added in a spelling `_pictures` cannot read would leave it reporting a clean
    sweep of nothing at all."""
    owner, repo = _home()
    sources = _pictures()
    badges = [t for t in sources
              if t.startswith("https://img.shields.io/")
              or t.startswith(f"https://github.com/{owner}/{repo}/actions/")]
    assert len(badges) >= 4, (
        f"the front page carries a badge row and this gate sees {len(badges)} "
        f"of them; one was removed, or moved somewhere this cannot read")
    assert len(sources) - len(badges) >= 2, (
        "the page draws the banner and the terminal shot, and this gate sees "
        f"{len(sources) - len(badges)} pictures that are not badges")


def test_every_picture_on_the_page_is_the_one_committed():
    owner, repo = _home()
    ours = f"raw.githubusercontent.com/{owner}/{repo}/"
    badge_hosts = ("https://img.shields.io/",
                   f"https://github.com/{owner}/{repo}/actions/")
    for source in _pictures():
        if source.startswith(badge_hosts):
            continue
        assert source.startswith("https://" + ours), (
            f"{source} is not served from this repository's raw host ({ours}). "
            f"A relative path is dead on the package index, and another owner's "
            f"host is not this project's picture.")
        branch, _, tail = source.split(ours, 1)[1].partition("/")
        path, _, query = tail.partition("?")
        picture = ROOT / path
        assert picture.is_file(), (
            f"the page points at {path}, which this repository does not have")
        cachebuster = query[2:] if query.startswith("v=") else ""
        digest = hashlib.sha256(picture.read_bytes()).hexdigest()[:8]
        assert cachebuster, (
            f"{path} is referenced off {branch} with no ?v= — change the file "
            f"and every reader who has seen it keeps the old one")
        assert cachebuster == digest, (
            f"{path} has changed since the page was written: the URL says "
            f"?v={cachebuster} and the committed file hashes to {digest}. "
            f"Readers behind the image proxy would keep the old picture.")


def test_the_badge_that_counts_rules_counts_the_catalogue():
    """A number inside a badge URL is a number no other gate here reads.

    `test_promises.py` holds every "N rules" in the prose to the catalogue, and
    a shields.io label is not that shape — `rules-39_with_a_remedy` matches
    nothing it looks for. So the badge could have said any number at all.
    """
    from vdi2770_validate.catalog import rules

    badge = re.search(r"img\.shields\.io/badge/rules-(\d+)", README)
    assert badge, "the front page no longer carries a badge counting the rules"
    assert int(badge.group(1)) == len(set(rules())), (
        f"the badge says {badge.group(1)} rules; the catalogue has "
        f"{len(set(rules()))}")


def test_every_rule_the_gallery_names_is_a_rule_with_that_severity():
    """The gallery is the page's shortest promise: *ship this, and it says
    that*. It names rule ids and the severity each one carries, and both are
    prose until something reads them — a renamed rule or a severity that moved
    would leave the page advertising a verdict the tool no longer gives.
    """
    from vdi2770_validate.catalog import rules
    from vdi2770_validate.report import MARK

    catalogue = rules()
    # The word the page prints is the word the renderer prints, taken from the
    # renderer's own table rather than spelled again here: the severities are
    # `error`/`warning`/`info` and what a reader sees on the line is `error`,
    # `warn`, `info`, and a second copy of that mapping is a second thing to
    # keep.
    label = {severity: mark.strip() for severity, mark in MARK.items()}
    gallery = re.search(r"\n\| You ship this \| .*?\n\n", README, re.S)
    assert gallery, "the front page no longer has the gallery table"
    words = "|".join(sorted(label.values()))
    named = re.findall(rf"`({words})\s+([A-Z]\d+)`", gallery.group(0))
    assert len(named) >= 4, (
        f"the gallery names {len(named)} findings; it was written with more, so "
        f"either it shrank or this gate stopped reading it")
    for shown, rule_id in named:
        assert rule_id in catalogue, (
            f"the gallery names {rule_id}, which is not a rule this tool has")
        assert label[catalogue[rule_id].severity] == shown, (
            f"the gallery shows {rule_id} as {shown} and the tool prints it as "
            f"{label[catalogue[rule_id].severity]}")


def test_the_requirement_the_page_quotes_is_the_one_the_project_declares():
    """The page explains what the old name asks for, and quotes it. That
    quotation is prose: nothing read it.

    It is the one requirement on this page that a release moves, and it moves in
    `pyproject.toml` — so a reader arriving after a version bump would be shown
    something the project no longer declares, in the paragraph whose whole
    subject is which engine you get.
    """
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    declared = re.search(r'"(vdi2770\[[^"]+)"', project)
    assert declared, "pyproject.toml no longer asks for the engine by name"
    quoted = re.findall(r"`(vdi2770\[[^`]+)`", README)
    assert quoted, "the front page no longer quotes the requirement it explains"
    assert set(quoted) == {declared.group(1)}, (
        f"the page quotes {sorted(set(quoted))} and pyproject.toml declares "
        f"{declared.group(1)!r}")


def test_the_python_versions_on_the_page_are_the_ones_that_are_run():
    """The page said `Python 3.9+`, which is what `requires-python` declares and
    not what anybody has run.

    `>=3.9` is a statement about what pip will install onto, so it takes in 3.10
    and 3.11 — and nothing here has ever executed on either. A reader on 3.11
    reads "3.9+" as "supported". The project's own classifiers already say the
    narrower, true thing, and CI runs exactly that set; the front page was the
    one surface stating the wider one.

    Held to both sources, because they can drift from each other too: a version
    added to CI and not to the classifiers is a version the index will not
    advertise, and the reverse is a version nobody runs.
    """
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    classified = set(re.findall(r'"Programming Language :: Python :: (\d+\.\d+)"',
                                project))
    assert classified, "pyproject.toml classifies no Python version"

    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    matrix = re.search(r"python-version:\s*\[([^\]]+)\]", workflow)
    assert matrix, "ci.yml no longer declares a python-version matrix"
    run = set(re.findall(r"\d+\.\d+", matrix.group(1)))
    assert classified == run, (
        f"the classifiers say {sorted(classified)} and CI runs {sorted(run)}; "
        f"one of them is advertising a version nobody executes")

    facts = re.search(r"\*\*Python ([^*]+)\*\*", README)
    assert facts, "the front page no longer states which Pythons it runs on"
    shown = set(re.findall(r"\d+\.\d+", facts.group(1)))
    assert shown == run, (
        f"the page says Python {facts.group(1).strip()!r} and what is actually "
        f"run is {sorted(run)}")
    assert "+" not in facts.group(1), (
        "`3.9+` takes in the versions between the ones that are run and the "
        "highest one that is; say the set, not the floor")


def test_a_file_the_page_hands_you_says_where_it_comes_from():
    """The page offered `vdi2770.pyz` — *copy one file in* — and nothing on it
    said how anyone gets that file.

    Nothing publishes it. There is no release asset here, so the only route is
    building it, and the page did not say so. An offer of a file nobody can
    obtain is worse than no offer: it reads like a download.

    The same paragraph also said *"No Python where the containers are?"*, which
    is false and is contradicted by the builder's own first paragraph —
    `tools/build_zipapp.py`: "A `.pyz` needs a copy of the file and a Python."
    What the single-file form removes is the *index*, pip, a virtual environment
    and the rights to make one. Not the interpreter. Both halves came from
    copying a template sentence instead of reading the tool.
    """
    # Anywhere on the page, not against a backtick. The first version of this
    # anchored on `` `name` ``, and the very fix it was written to force moved
    # the name inside a longer command span and into a build line -- so the gate
    # went looking for a spelling the page no longer used and reported that the
    # single-file form had been withdrawn.
    offered = set(re.findall(r"\b([\w.-]+\.pyz)\b", README))
    assert offered, "the front page no longer offers the single-file form"
    for name in offered:
        builds = "tools/build_zipapp.py" in README
        serves = re.search(r"https://github\.com/[\w./-]+/releases/[\w./-]*"
                           + re.escape(name), README)
        assert builds or serves, (
            f"the page tells a reader to use {name} and never says where it "
            f"comes from — there is no release asset, so the only honest answer "
            f"is the command that builds it")

    assert "No Python" not in README, (
        "the single-file form needs an interpreter; what it removes is the "
        "index, pip and the rights to make a virtual environment. "
        "tools/build_zipapp.py says so in its own opening paragraph.")
