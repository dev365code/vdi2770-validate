"""The pictures on the front page are drawn, and a drawing can go quietly false.

A terminal shot is the one asset with that failure mode: the tool changes a
sentence, the SVG keeps the old one, and the page shows output no version ever
produced. Nothing goes red, because nothing reads a picture.

So the shot is not hand-drawn. `tools/gen_door.py` holds the lines as data, this
file rebuilds every logical line out of that data and asserts it against a live
run of the command the picture types, and `--check` asserts that what is
committed is what the generator produces today. Three questions, and they are
different ones: *is the drawing what the tool prints*, *is the committed file
what the generator draws*, and *does the page point at the committed file* (that
last one is on the page's own gate, next door).

The banner is deliberately mathematics and words -- no counts, no version -- so
there is nothing in it to go stale in the first place. That is asserted too,
because "carries no numbers" is a property somebody has to keep.
"""
from __future__ import annotations

import html
import pathlib
import re
import subprocess
import sys
import types

import pytest

from conftest import ROOT, under_test

ASSETS = ROOT / "docs" / "assets"


def generator():
    """The generator as it is on disk, not as it was last compiled.

    Read and executed rather than imported: this interpreter may keep its
    bytecode cache outside the tree (`sys.pycache_prefix`), and then a stale
    `.pyc` goes on producing the old picture while the source and the committed
    asset are both correct -- which is a debugging session nobody gets back.
    """
    source = (ROOT / "tools" / "gen_door.py").read_text(encoding="utf-8")
    module = types.ModuleType("_gen_door")
    module.__file__ = str(ROOT / "tools" / "gen_door.py")
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def _drawn_text(svg: str) -> str:
    """Every string a reader sees, with entities resolved.

    `&#160;` is a space to a reader and five characters to a regex; reading the
    markup raw is how a spacing entity gets reported as a stale number.
    """
    return html.unescape(" ".join(re.findall(r">([^<>]+)<", svg)))


def test_the_committed_pictures_match_their_generator():
    """The same question `make check` asks, asked where it is cheap. A picture
    regenerated and not committed, or committed and not regenerated, is one
    command away from the front page either way."""
    assert generator().main(["--check"]) == 0, (
        "docs/assets is out of date with tools/gen_door.py — run it")


@pytest.mark.parametrize("name", ["door.svg", "tenseconds.svg"])
def test_the_pictures_are_committed(name):
    """A guard on the two tests below: both read a file, and a glob that stopped
    matching would report a clean sweep of nothing."""
    assert (ASSETS / name).is_file(), f"docs/assets/{name} is not committed"


def test_the_banner_carries_no_number_that_can_go_stale():
    """A count drawn into a picture is a count nothing regenerates.

    Two numbers in this banner are not that: `vdi2770` is what the thing is
    called, and `VDI 2770` is the designation of the guideline it checks against.
    Neither can drift, because a change to either is a change of subject. They
    are removed by name and then *nothing else may hold a digit* — so a rule
    count, a version or a coverage figure added to the banner fails here.
    """
    text = _drawn_text((ASSETS / "door.svg").read_text(encoding="utf-8"))
    fixed = re.sub(r"VDI\s?2770|vdi2770", "", text)
    assert not re.search(r"\d", fixed), (
        f"the banner draws a number nothing regenerates: {fixed.strip()!r}")


def test_the_terminal_shots_caption_carries_no_number_either():
    """The quoted lines in the shot are checked against a live run below. The
    chrome around them — the window caption — is drawn by hand and regenerated
    by nobody, and it is inside the same file, so it needs saying separately."""
    svg = (ASSETS / "tenseconds.svg").read_text(encoding="utf-8")
    caption = [row for row in re.findall(r">([^<>]+)<", svg)
               if "real output" in row]
    assert caption, "the terminal shot has lost its caption"
    fixed = re.sub(r"vdi2770", "", " ".join(caption))
    assert not re.search(r"\d", fixed), (
        f"the caption says {caption!r}, and a number there regenerates by hand")


def _logical_lines(module):
    """The shot's rows rebuilt into the lines the tool would have printed.

    The picture wraps a remedy over three rows because it is 940 pixels wide;
    the tool prints it as one line. Which rows are continuations is recorded in
    the data rather than guessed from indentation, because guessing is how a
    genuinely-missing line gets silently glued onto the one above it.
    """
    lines = []
    for _dy, runs, kind in module.SHOT_LINES:
        text = "".join(run[2] for run in runs)
        if kind == "wrap":
            assert lines, "the shot begins with a continuation row"
            lines[-1] += " " + text.strip()
        elif kind == "line":
            lines.append(text)
    return [re.sub(r"\s+", " ", line).strip() for line in lines]


def test_every_line_drawn_in_the_shot_is_one_the_tool_really_prints():
    """Walked with one cursor, so a line drawn above the one the tool prints
    first fails as loudly as a line the tool never prints at all. A picture can
    hold every sentence of a real session and still show a session that never
    happened."""
    module = generator()
    done = subprocess.run([sys.executable, "-m", "vdi2770_validate",
                           *module.SHOT_COMMAND],
                          cwd=ROOT, capture_output=True, text=True,
                          env=under_test())
    real = [re.sub(r"\s+", " ", line).strip() for line in done.stdout.splitlines()]
    at, previous = 0, None
    for line in _logical_lines(module):
        assert line in real, (
            f"the front page draws a line the tool never prints:\n  {line}")
        try:
            at = real.index(line, at) + 1
        except ValueError:
            raise AssertionError(
                f"the picture draws this after {previous!r} and the tool prints "
                f"it before:\n  {line}") from None
        previous = line


def test_the_shot_does_not_stop_before_the_finding_it_illustrates_is_answered():
    """`line in real` is one-directional: it catches a sentence the tool never
    prints and cannot catch one the tool prints and the picture leaves out. The
    front page's whole claim is that a finding arrives with its remedy, so a
    shot that draws a finding and elides the remedy under it would be an
    advertisement for the opposite."""
    lines = _logical_lines(generator())
    findings = [i for i, line in enumerate(lines)
                if re.match(r"(error|warn|note)\s+[A-Z]\d+\b", line)]
    assert findings, "the shot draws no finding at all"
    for i in findings:
        assert any(line.lstrip().startswith("->") for line in lines[i + 1:]), (
            f"the shot draws {lines[i]!r} and never draws a remedy after it")


def test_the_command_the_shot_types_is_one_this_project_offers():
    """The picture types a command at a prompt, and a reader will type it back.
    Drawn from the same list the run above executes, so the two cannot part."""
    module = generator()
    typed = [line for _dy, runs, kind in module.SHOT_LINES if kind == "chrome"
             for line in ["".join(r[2] for r in runs)] if line.startswith("$ ")]
    assert typed, "the shot shows no command being typed"
    assert any("vdi2770-validate " + " ".join(module.SHOT_COMMAND) in line
               for line in typed), (
        f"the shot types {typed!r} and runs {module.SHOT_COMMAND!r}")
    for line in typed:
        assert re.match(r"\$ (pip install vdi2770-validate|vdi2770-validate )",
                        line), f"the shot types a command this project does not offer: {line!r}"


def test_no_distribution_ships_this_gate_without_its_subject():
    """A gate and the files it reads travel together or neither travels.

    `MANIFEST.in` names what `docs/` ships by suffix, and it was written before
    there were pictures: `*.md *.json` does not carry an `.svg`, so an sdist
    carried this file and not what it reads. The failure appeared only on a
    clean checkout, because setuptools carries `SOURCES.txt` forward and any
    machine that had built once had the pictures in it.

    Stated as the invariant rather than as one manifest's contents, because the
    suite moved: `vdi2770-validate` is an alias now and ships neither this file
    nor the pictures, which is consistent — what would not be consistent is
    shipping one of them. Asserted against the generator's own list, so a third
    picture cannot be added without this saying where it has to be named.
    """
    here = pathlib.Path(__file__).resolve()
    for where in (ROOT / "MANIFEST.in",
                  ROOT / "packages" / "vdi2770" / "MANIFEST.in"):
        manifest = where.read_text(encoding="utf-8")
        # This file, in this distribution's tree, and not pruned back out.
        mine = where.parent / "tests" / here.name
        ships_the_gate = (mine.is_file() and "recursive-include tests" in manifest
                          and "prune tests" not in manifest)
        for name in generator().PICTURES:
            carried = (f"docs/assets/{name}" in manifest
                       or "docs/assets *.svg" in manifest)
            assert carried or not ships_the_gate, (
                f"{where.parent.name}/MANIFEST.in ships this gate and not "
                f"docs/assets/{name}, so that sdist carries it without its "
                f"subject")


def test_the_elision_in_the_shot_says_what_it_elided():
    """A marked gap is still a claim about the output.

    This page has been here before, in the README's sample: *"6 more warnings of
    the same kind"* stood for four of one rule and two of another, and no gate
    read the sentence. The picture makes the same claim in a place no reader can
    check, so it is checked here — the counts by severity and the rule ids, both
    derived from a real run rather than from what the drawing says.
    """
    from vdi2770_validate.model import Severity
    from vdi2770_validate.runner import check_file

    module = generator()
    said = [("".join(run[2] for run in runs))
            for _dy, runs, kind in module.SHOT_LINES if kind == "elision"]
    assert len(said) == 1, f"the shot has {len(said)} elisions and this reads one"
    claim = re.search(r"…\s*(\d+) more error \(([^)]+)\) and (\d+) warning \(([^)]+)\)",
                      said[0])
    assert claim, f"the elision has been reworded: {said[0]!r}"

    drawn = [re.match(r"(error|warn|note)\s+([A-Z]\d+)", line)
             for line in _logical_lines(module)]
    shown = [m.group(2) for m in drawn if m]
    findings = check_file(str(ROOT / module.SHOT_COMMAND[-1])).sorted()
    assert [f.rule.id for f in findings[:len(shown)]] == shown, (
        "the shot draws findings the run does not open with")
    rest = findings[len(shown):]
    assert rest, "the shot elides nothing, so it should not claim to"

    errors = [f for f in rest if f.severity is Severity.ERROR]
    warnings = [f for f in rest if f.severity is Severity.WARNING]
    assert len(errors) == int(claim.group(1)) and len(warnings) == int(claim.group(3)), (
        f"the elision claims {claim.group(1)} error(s) and {claim.group(3)} "
        f"warning(s); what follows is {len(errors)} and {len(warnings)}")
    assert sorted({f.rule.id for f in errors}) == sorted(claim.group(2).split()), (
        f"the elision names {claim.group(2)!r} as the remaining errors; they are "
        f"{sorted({f.rule.id for f in errors})}")
    assert sorted({f.rule.id for f in warnings}) == sorted(claim.group(4).split()), (
        f"the elision names {claim.group(4)!r} as the remaining warnings; they "
        f"are {sorted({f.rule.id for f in warnings})}")
    assert len(rest) == len(errors) + len(warnings), (
        "something that is neither an error nor a warning follows, and the "
        "elision does not mention it")
