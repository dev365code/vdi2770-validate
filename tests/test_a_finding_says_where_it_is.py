"""A diagnosis a sender cannot locate is a diagnosis they cannot act on.

The report already carries this and nothing held it, which is the state a
property is in just before it quietly stops being true. Measured over the corpus
and the fixtures at the time of writing: 126 findings from 37 of the 42 rules,
every one naming its container -- with the nesting path, so a finding inside a
document container inside a documentation container says which -- and every rule
either always naming a member or never naming one.

"Never" is the right answer for four of them. `Z1`, `Z2`, `Z3` and `Z8` are
`about: container`: the archive is empty, is neither kind of container, holds no
document containers. There is no member to name, and inventing one would be
worse than the null.

What this file refuses is the third state: a rule that names a member for one
container and not for another. That is the shape a reader cannot learn -- they
check the field, find it filled, and build a pipeline on a location that goes
missing on the next delivery.
"""
import json
import subprocess
import sys

from conftest import CORPUS, FIXTURES, ROOT


def reports():
    """Every report this tree produces over everything it ships."""
    inputs = sorted(CORPUS.rglob("*.zip")) + sorted(FIXTURES.rglob("*.zip"))
    assert inputs, "no containers to judge; this gate would prove nothing"
    import os
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), str(ROOT / "packages" / "vdi2770" / "src")]
        + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    out = []
    for path in inputs:
        done = subprocess.run(
            [sys.executable, "-m", "vdi2770.validate", "check", str(path), "--json"],
            cwd=ROOT, capture_output=True, text=True, env=env)
        # 0 clean, 1 findings; anything else and stdout is not a report.
        if done.returncode in (0, 1) and done.stdout.strip():
            out.extend(json.loads(done.stdout))
    assert out, "no reports were produced; nothing below is being checked"
    return out


def findings():
    return [f for d in reports() for f in d.get("findings", [])]


def test_every_finding_names_the_container_it_is_about():
    """Including the path through any nesting: the JAR convention in
    `Location.__str__` is what makes `outer.zip!/inner.zip` greppable, and a
    finding that named only the outer archive would send a sender looking in the
    wrong file."""
    seen = findings()
    assert seen, "no findings at all; this gate would pass vacuously"
    anonymous = [(f["rule"], f["where"]) for f in seen if not f["where"].get("container")]
    assert not anonymous, f"findings that name no container: {anonymous}"


def test_a_rule_names_a_member_always_or_never():
    """The two honest answers, and not the third.

    A rule that is about the archive names no member; a rule about something
    inside it names one every time. A rule that does both is telling a reader
    the field is optional in a way they cannot predict.
    """
    by_rule = {}
    for f in findings():
        got = bool(f["where"].get("member"))
        by_rule.setdefault(f["rule"], set()).add(got)
    inconsistent = {r: "names a member for some containers and not others"
                    for r, answers in by_rule.items() if len(answers) > 1}
    assert not inconsistent, (
        f"these rules answer 'where' differently on different inputs, which is "
        f"the one shape a consumer cannot build on: {inconsistent}")


#: The rules whose findings name no member, measured rather than inferred.
#:
#: An earlier draft asked `about` instead, on the theory that a container-level
#: rule has no member to name. `about` does not mean that: 34 of the 42 rules
#: are `about: container` and most of them name a member -- `P4` is one, and it
#: names the PDF it read. So that draft permitted any of those 34 to drop its
#: location silently, which is the whole failure it was written to prevent.
#:
#: This is the inventory instead. Six rules name no member, and all six are
#: about the archive itself: it is empty, it is neither kind of container, it
#: holds no document containers, its members sit in folders. There is nothing to
#: point at, and inventing something would be worse than the null.
#:
#: `Z13` was on this list and is not any more. It reported every folder it
#: declined to open in one finding, with the names in the detail sentence, and
#: it reports one finding per folder now -- which is what took it off. That is
#: what this set is for: a rule leaving it is a debt paid, and the test below
#: fails while a paid debt is still written down as owed.
NAMES_NO_MEMBER = {"Z1", "Z2", "Z3", "Z7", "Z8", "Z9"}


def test_which_rules_name_a_member_is_the_recorded_set():
    """Derived from what the tool does, compared against what is written here.

    Two ways to fail, and both matter. A rule that stops naming a member has
    lost a location a reader could have used. A rule that starts naming one has
    gained something worth knowing, and the set here would otherwise go stale
    and start excusing a rule nobody meant to excuse.
    """
    by_rule = {}
    for f in findings():
        by_rule.setdefault(f["rule"], set()).add(bool(f["where"].get("member")))
    observed = {r for r, answers in by_rule.items() if answers == {False}}
    lost = sorted(observed - NAMES_NO_MEMBER)
    gained = sorted(NAMES_NO_MEMBER & {r for r, a in by_rule.items() if a == {True}})
    assert not lost, (
        f"{lost} name no member and are not recorded as memberless. If that is "
        f"meant, add them here with the reason; a location that went missing "
        f"reads exactly like one that was never there.")
    assert not gained, (
        f"{gained} name a member now and are still recorded as memberless. "
        f"Remove them, so this set stays a list of real debts rather than a "
        f"list of rules somebody once excused.")


#: Findings pointing into the metadata that do not say where in it, and why.
#: Held both ways, like the set above: a rule that stops placing its findings
#: fails, and so does one written here that places them now.
NOT_PLACED = {
    ("X2", "column"): ("the schema checker reports the line of the element it refused, "
                       "and not the column"),
    ("X4", "line"): "the schema checker stopped part of the way down and does not say where",
    ("Z10", "line"): ("two entries in the archive's directory share the metadata's name; "
                      "the finding is about the directory, not about a place in the file"),
}


def test_a_finding_in_the_metadata_says_the_line():
    """A finding about the metadata points at the line and column it is about.

    The report has carried a line for these since the reader kept positions,
    and nothing required it: a rule written later could drop it, and the
    first a reader would know is a finding they have to search the file for.
    """
    from vdi2770.zipread import MAIN_XML, METADATA_XML

    in_metadata = [f for f in findings()
                   if str(f["where"].get("member") or "").rsplit("/", 1)[-1] in (METADATA_XML, MAIN_XML)]
    assert in_metadata, "no finding points into the metadata; this gate would prove nothing"
    unplaced = {(f["rule"], "line" if f["where"].get("line") is None else "column")
                for f in in_metadata
                if f["where"].get("line") is None or f["where"].get("column") is None}
    assert unplaced <= set(NOT_PLACED), (
        f"findings in the metadata that do not say where in it: {sorted(unplaced - set(NOT_PLACED))}")
    assert set(NOT_PLACED) <= unplaced, (
        f"{sorted(set(NOT_PLACED) - unplaced)} say where they are now and are still "
        f"written down as not saying it. Remove them.")
