"""CI runs what `make check` runs — and with the same versions.

Same command is not the same environment. That lesson cost a red build once
already, in the sibling project, so the version pins are asserted too.
"""
import re

from conftest import ROOT, spelled

MAKEFILE = (ROOT / "Makefile").read_text(encoding="utf-8")
CI = (ROOT / ".github" / "workflows" / "ci.yml")


#: Targets `make check` deliberately does not depend on, with the reason. A
#: target here is not exempt from being explained — it is exempt from being run
#: on every contributor's machine on every change.
OUTSIDE_CHECK = {
    "check": "the target itself; it cannot be one of its own prerequisites",
    "clean": "it deletes things and judges nothing, so running it as part of the "
             "gate would only mean the gate throws away its own inputs",
    "oracle-fully-swept": "a release question rather than a change question. A "
                          "container may sit unswept for as long as it takes to run "
                          "the `oracle` workflow, and the divergence counts exclude "
                          "it meanwhile; it stops being acceptable the moment those "
                          "counts are published, which is what a release does",
    "zipapp": "it fetches the dependency it bundles, and `make check` is offline "
              "— which is the property this tool sells, so the gate that proves "
              "it must not be the thing that breaks it. CI runs it on every "
              "push, because a build nobody runs until tag day breaks on tag day",
    "mutations": "minutes rather than seconds, and it is a check *on* the suite "
                 "rather than part of it — it only tells you something new when a "
                 "gate changes",
    "standalone": "one interpreter start per test file — a minute, and it only "
                  "tells you something new when a file gains an import. It asks "
                  "what a shared process cannot: does any file pass only because "
                  "of what ran before it",
}


def recipe_commands(include=None):
    """The commands the Makefile runs, by default only those `check` reaches."""
    out = []
    current = None
    for line in MAKEFILE.splitlines():
        if re.match(r"^[a-zA-Z0-9_-]+:", line):
            current = line.split(":")[0]
        elif line.startswith("\t") and current:
            if include is None and current in OUTSIDE_CHECK:
                continue
            out.append(line.strip())
    return out


def test_pinned_versions_match_pyproject():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for name in ("ruff", "pytest", "xmlschema"):
        m = re.search(rf"{name.upper()}_VERSION\s*:=\s*([0-9.]+)", MAKEFILE)
        assert m, f"Makefile does not pin {name}"
        assert f'{name}=={m.group(1)}' in pyproject, (
            f"{name} is pinned to {m.group(1)} in the Makefile but not in pyproject.toml")


def test_ci_actually_exercises_the_oldest_python_we_promise():
    """`requires-python` is a promise. The only way it stays true is if CI runs
    that interpreter — a dependency can quietly stop supporting it, which is
    exactly how this project once shipped a floor it could not install on."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    floor = re.search(r'requires-python\s*=\s*">=([0-9.]+)"', pyproject)
    assert floor, "pyproject declares no requires-python"
    ci = CI.read_text(encoding="utf-8")
    matrix = re.search(r"python-version:\s*\[(.*?)\]", ci)
    assert matrix, "CI declares no python-version matrix"
    versions = re.findall(r'"([0-9.]+)"', matrix.group(1))
    assert floor.group(1) in versions, (
        f"pyproject promises Python {floor.group(1)} but CI never runs it: {versions}")


def ci_commands():
    """The commands CI actually runs, not the text of the file.

    Searching the raw YAML for a command string passes when the step is
    commented out, which is one keystroke away from a CI that runs nothing.
    """
    out, in_block, indent = [], False, 0
    for raw in CI.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if in_block:
            if stripped and (len(raw) - len(raw.lstrip())) > indent:
                if not stripped.startswith("#"):
                    out.append(stripped.split("#")[0].strip())
                continue
            in_block = False
        m = re.match(r"^(\s*)-?\s*run:\s*(.*)$", raw)
        if m:
            indent = len(m.group(1))
            value = m.group(2).strip()
            if value in ("|", ">", "|-", ">-"):
                in_block = True
            elif value and not value.startswith("#"):
                out.append(value.split("#")[0].strip())
    return [c for c in out if c]


def test_ci_runs_the_command_not_merely_mentions_it():
    """A commented-out step used to satisfy the substring check.

    This replaced a weaker test that searched the whole workflow file for each
    command. Anything that passed here passed there too, so the weaker one could
    not fail on its own and was deleted rather than left to look like coverage.
    """
    assert CI.exists(), "no CI workflow"
    commands = ci_commands()
    assert commands, "no run: steps found in the workflow"
    for cmd in recipe_commands():
        core = cmd.replace("$(PYTHON)", "python").strip()
        if core.startswith("rm "):
            continue
        assert any(core in c for c in commands), (
            f"CI never runs: {core}\n  it runs: {commands}")


def test_ci_runs_nothing_the_gate_does_not():
    """The Makefile's first line says CI runs *exactly* these targets and points
    at this file. Only one direction was proved: every `make check` command
    appears in the workflow. CI could grow a check nobody runs locally — or
    replace one — and "exactly" would still read as proved.

    A step this test does not recognise is either a gate that belongs in
    `make check`, or setup. Setup is named here, once, so adding one is a
    decision somebody writes down.
    """
    SETUP = (
        "pip install", "pip download", "actions/", "python -m build",
        "python -m venv", "git ", "echo ",
    )
    #: And the third kind: a gate CI runs that `make check` does not, with the
    #: reason. `OUTSIDE_CHECK` says why a target is not in `check`; this says
    #: why one of those still runs on every push. Two lists rather than one
    #: because they answer different questions, and a target can be in the first
    #: without belonging in the second — `mutations` and `standalone` are.
    CI_ONLY = {
        "python tools/build_zipapp.py --check":
            "it fetches the dependency it bundles, and `make check` is offline "
            "-- the property this tool sells. CI has the network, and a build "
            "nobody runs until tag day is a build that breaks on tag day.",
    }
    # The `check` recipes, plus the targets named above — a CI step matching one
    # of those is recognised because somebody wrote down why it is there.
    recipes = [c.replace("$(PYTHON)", "python").strip()
               for c in recipe_commands(include={"zipapp"})]
    for command, reason in CI_ONLY.items():
        assert reason and command in recipes, (
            f"{command!r} is named as CI-only and the Makefile does not run it")
    for step in ci_commands():
        core = step.strip()
        if not core or core.startswith("#"):
            continue
        if any(core.startswith(s) or s in core for s in SETUP):
            continue
        assert any(r in core for r in recipes), (
            f"CI runs a check `make check` does not:\n  {core}\n"
            f"Either add it to the Makefile, or name it as setup in this test.")


def test_make_check_depends_on_every_gate():
    """`make check` is what a contributor runs. A target the Makefile defines but
    `check` does not depend on runs only in CI, which is how a green local tree
    pushed a red build: the sdist gate existed, and `check` never called it."""
    targets, prereqs = [], []
    for line in MAKEFILE.splitlines():
        m = re.match(r"^([a-zA-Z0-9_-]+):\s*(.*)$", line)
        if not m:
            continue
        targets.append(m.group(1))
        if m.group(1) == "check":
            prereqs = m.group(2).split()
    assert prereqs, "the Makefile has no `check` target"
    exempt = set(OUTSIDE_CHECK)
    missing = [t for t in targets if t not in exempt and t not in prereqs]
    assert not missing, (
        f"`make check` does not run: {missing}. Either add them, or add them to the "
        f"exemption above with a reason.")


def test_every_file_that_carries_the_version_carries_the_same_one():
    """One release in two parts, and four files that can disagree about which
    release it is.

    Each half has a manifest and a `__version__`, and the halves are pinned to
    each other exactly. `import vdi2770; vdi2770.__version__` is what a report
    prints, so code ahead of its manifest names a release nobody can install,
    and a manifest ahead of its code publishes that number for something else.
    The exact pin then turns either into an install that cannot resolve.

    This is a claim about the repository, so it is here and not in the reader's
    own suite — that suite must not read files above the package, because an
    sdist of it contains the package and nothing else.
    """
    def stated(path, pattern):
        found = re.search(pattern, path.read_text(encoding="utf-8"), re.M)
        assert found, f"{path} states no version"
        return found.group(1)

    reader = ROOT / "packages" / "vdi2770"
    said = {
        "pyproject.toml":
            stated(ROOT / "pyproject.toml", r'^version = "([^"]+)"'),
        "packages/vdi2770/pyproject.toml":
            stated(reader / "pyproject.toml", r'^version = "([^"]+)"'),
        "src/vdi2770_validate/__init__.py":
            stated(ROOT / "src" / "vdi2770_validate" / "__init__.py",
                   r'^__version__ = "([^"]+)"'),
        "packages/vdi2770/src/vdi2770/__init__.py":
            stated(reader / "src" / "vdi2770" / "__init__.py",
                   r'^__version__ = "([^"]+)"'),
    }
    assert len(set(said.values())) == 1, (
        f"the two halves go out under one tag and these disagree about which "
        f"release that is: {said}")


def test_ci_runs_every_python_any_manifest_advertises():
    """A classifier on PyPI is a promise to whoever reads it before installing.

    The existing floor test reads one manifest and nothing else, so the reader
    package advertised `Programming Language :: Python :: 3.13` while CI ran 3.9
    and 3.12 and no interpreter ever confirmed it. Two distributions means two
    manifests making the promise, and the reader's `requires-python` has to hold
    on its own — it is installed by name, by people who never see the other one.
    """
    matrix = re.search(r"python-version:\s*\[(.*?)\]", CI.read_text(encoding="utf-8"))
    assert matrix, "CI declares no python-version matrix"
    tested = set(re.findall(r'"([0-9.]+)"', matrix.group(1)))

    for name in ("pyproject.toml", "packages/vdi2770/pyproject.toml"):
        text = (ROOT / name).read_text(encoding="utf-8")
        block = re.search(r"^classifiers = \[(.*?)^\]", text, re.M | re.S)
        assert block, f"{name} declares no classifiers"
        advertised = set(re.findall(r"Programming Language :: Python :: (\d+\.\d+)",
                                    block.group(1)))
        missing = sorted(advertised - tested)
        assert not missing, (
            f"{name} advertises Python {missing} and CI runs {sorted(tested)}. "
            f"Either run it or stop claiming it.")

        floor = re.search(r'requires-python\s*=\s*">=([0-9.]+)"', text)
        assert floor and floor.group(1) in tested, (
            f"{name} promises Python {floor.group(1) if floor else '?'} "
            f"and CI never runs it")


def test_contributing_names_every_target_make_check_runs():
    """CONTRIBUTING described `make check` as five things; it was six then and is
    nine now — the number is derived below. The one it
    left out is the sdist gate — the one a contributor is least likely to guess
    and the one that has caught the most."""
    prereqs = []
    for line in MAKEFILE.splitlines():
        m = re.match(r"^check:\s*(.*)$", line)
        if m:
            prereqs = m.group(1).split()
    assert prereqs, "the Makefile has no `check` target"
    prose = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    missing = [t for t in prereqs if f"`{t}`" not in prose]
    assert not missing, f"CONTRIBUTING does not name what `make check` runs: {missing}"

    # Naming them is not counting them. The paragraph said "ten targets" and then
    # listed nine that "judge something" — a list that both re-included
    # `fixtures`, which the same sentence had just excluded as a build step, and
    # dropped `reader-api-matches-its-version` entirely. Every name was present,
    # so the check above was green throughout.
    para = next(b for b in prose.split("\n\n") if "`make check` is the whole gate" in b)
    assert f"It is {spelled(len(prereqs))} targets" in para, (
        f"`make check` runs {len(prereqs)} targets and CONTRIBUTING says otherwise:\n{para}")
    judging = [t for t in prereqs if t != "fixtures"]
    listed = re.findall(r"`([a-z][a-z-]+)`", para.split("judge something:", 1)[1])
    assert sorted(listed) == sorted(judging), (
        f"the paragraph lists {listed}\nand `make check` runs {judging} (minus the "
        f"build step). A name in the wrong list still passes the check above.")
    assert len(listed) == len(set(listed)), (
        f"a target is named twice in the same list: {listed}")


def test_no_stale_copy_of_the_source_tree_is_left_lying_around():
    """`build/lib/vdi2770_validate/` held a complete pre-SDK-split copy: four
    modules — `domain.py`, `readers/zipread.py`, `readers/xmlread.py`,
    `readers/pdfread.py` — that moved into the `vdi2770` package and no longer
    exist in `src/`. It is gitignored, so it is invisible in review and
    permanent on any tree that ever built a distribution. A `grep -r` finds it,
    and the file it finds is the one nobody should edit.

    A fresh `build/` is fine — this only fails on a module that `src/` has
    dropped, which is exactly when the copy starts misleading somebody.
    """
    stale = []
    for build_dir in (ROOT / "build" / "lib", ROOT / "packages" / "vdi2770" / "build" / "lib"):
        if not build_dir.exists():
            continue
        for built in build_dir.rglob("*.py"):
            rel = built.relative_to(build_dir)
            for src_root in (ROOT / "src", ROOT / "packages" / "vdi2770" / "src"):
                if (src_root / rel).exists():
                    break
            else:
                stale.append(str(built.relative_to(ROOT)))
    assert not stale, (
        f"a build directory holds modules that no longer exist in src/: {sorted(stale)}. "
        f"Run `make clean`; the sdist gate should not have left them.")


def test_contributing_installs_what_ci_installs():
    """Whatever CI installs, the contributor recipe has to name.

    CI used to install the reader from the working tree before the validator
    that pinned it, and CONTRIBUTING said `pip install -e ".[dev]"` and nothing
    else -- so a contributor following it resolved the reader from PyPI and ran
    the gate against a different reader than CI did. One install now, and this
    still has to hold: it is the direction that catches CI growing a step
    nobody wrote down.
    """
    prose = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    # Editable installs of this repository itself. `pip install build` is a tool
    # the wheel gate needs, not a thing under test.
    installs = [c for c in ci_commands()
                if c.startswith("python -m pip install -e ")]
    assert installs, "CI installs nothing"
    for cmd in installs:
        assert cmd in prose, f"CI runs `{cmd}` and CONTRIBUTING does not mention it"


def workflows():
    return sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def commands_in(path):
    """The commands a workflow actually runs, not the text of the file."""
    out, in_block, indent = [], False, 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if in_block:
            if stripped and (len(raw) - len(raw.lstrip())) > indent:
                if not stripped.startswith("#"):
                    out.append(stripped.split("#")[0].strip())
                continue
            in_block = False
        if stripped.startswith("run:"):
            rest = stripped[4:].strip()
            if rest in ("|", ">"):
                in_block, indent = True, len(raw) - len(raw.lstrip())
            elif rest:
                out.append(rest)
    return out


def test_a_workflow_that_publishes_runs_the_whole_gate():
    """Two release workflows listed the gate's commands by hand, and the lists
    went stale the moment the gate grew.

    `release.yml` ran six of nine targets. `release-sdk.yml` — the one that
    published the reader to PyPI — ran two, and never ran
    `tools/api_fingerprint.py`, whose entire purpose is to stop that workflow
    publishing a reader whose public surface has moved under an old version.
    Nothing noticed, because the parity test read `ci.yml` and no other file.

    A workflow that publishes runs `make check`. Not a copy of it.
    """
    # "Uploads an artifact" was the proxy, and it is too wide: a workflow that
    # uploads a *diagnostic* for a human to read publishes nothing, and making it
    # run the whole gate is minutes spent answering a question it never asked.
    # What matters is whether something leaves here that a person could install —
    # a PyPI upload, or a built distribution one download away from being one.
    def publishes(w):
        text = w.read_text(encoding="utf-8")
        if "pypi-publish" in text:
            return True
        return any("dist" in ln.split("path:", 1)[1]
                   for ln in text.splitlines() if ln.strip().startswith("path:"))

    publishing = [w for w in workflows() if publishes(w)]
    assert publishing, "no workflow publishes anything; this test is looking in the wrong place"
    for w in publishing:
        ran = commands_in(w)
        assert any(c.strip() == "make check" for c in ran), (
            f"{w.name} publishes and does not run `make check`. It runs: {ran}")
        # And that the evidence it publishes counts is complete. `OUTSIDE_CHECK`
        # states the requirement in prose -- "it stops being acceptable the
        # moment those counts are published, which is what a release does" --
        # and stated it to nobody: deleting the step from either workflow left
        # the suite green.
        assert any(c.strip() == "make oracle-fully-swept" for c in ran), (
            f"{w.name} publishes divergence counts and does not check the sweep "
            f"is complete. It runs: {ran}")


def test_a_step_that_runs_make_check_runs_it_where_the_makefile_is():
    """`release-sdk.yml` set `defaults.run.working-directory: packages/vdi2770`
    for the whole file. A step added there without `working-directory: .` ran
    from inside the library, where there is no Makefile and no
    `packages/vdi2770` — so the SDK release failed before it could publish, and
    the gate that step exists to run never ran. That file is gone with the
    distribution it published, and no workflow sets a file-wide default today,
    so this asserts nothing about the tree until one does again.

    Checked structurally rather than by name: any workflow with a file-wide
    default must override it on a step that runs a repository-root command.
    """
    import re

    for w in workflows():
        text = w.read_text(encoding="utf-8")
        # Read the block, do not match three literal lines. `\s+` cannot span a
        # comment, so one comment line between `run:` and `working-directory:`
        # made this find nothing, `continue` past every workflow, and pass
        # vacuously over exactly the failure it exists to prevent.
        default = None
        lines, depth = text.splitlines(), None
        for n, line in enumerate(lines):
            if line.startswith("defaults:"):
                depth = n
                continue
            if depth is None:
                continue
            if line and not line[0].isspace():
                break                       # the block ended
            stripped = line.strip()
            if stripped.startswith("working-directory:"):
                default = stripped.split(":", 1)[1].strip()
                break
        if default is None or default == ".":
            continue
        for step in re.split(r"\n      - ", text):
            root_commands = [c for c in ("make check", "make ", "python tools/")
                             if c in step]
            if not root_commands:
                continue
            assert re.search(r"^\s+working-directory:\s*\.\s*$", step, re.M), (
                f"{w.name} defaults to {default!r} and a step runs "
                f"{root_commands} without `working-directory: .`:\n{step[:200]}")


def test_the_publishing_workflow_checks_the_order_at_all():
    """Unconditionally, because the condition is the thing being protected.

    The sibling below asserts this too, but only on the branch where the floor
    names an unpublished release -- and it needs the tag history, which a copied
    tree does not have, so it skips wherever the gates are measured. The claim
    does not depend on today's floor: this workflow publishes both
    distributions, one of them depends on the other, and the order has to be
    checked at the moment a release happens because that is the only moment
    anything knows one is.

    The gate ran the other way round while the reader was its own distribution
    -- the validator pinned it and it had to go first. The direction moved; the
    reason a build cannot catch this did not.
    """
    body = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "tools/check_release_order.py" in body, (
        "release.yml does not run tools/check_release_order.py. Nothing else "
        "asks an index whether the package the redirect depends on exists -- "
        "the gate installs it from the working tree and `python -m build` does "
        "not resolve runtime "
        "dependencies -- so without this step the validator can be tagged first "
        "and published permanently unresolvable.")
    assert (ROOT / "tools" / "check_release_order.py").exists(), (
        "release.yml runs a script that is not in this tree")
    # `--offline` leaves the gate checking the tag and skipping the index, which
    # is the half that was there when it was still claiming to have asked. One
    # flag in one workflow line puts it back.
    for line in body.splitlines():
        if "check_release_order.py" in line and not line.lstrip().startswith("#"):
            assert "--offline" not in line, (
                "release.yml runs the order gate with --offline, so nothing asks "
                "the index whether the pinned reader was published: " + line.strip())


def test_this_release_number_was_not_already_spent_in_the_old_namespace():
    """Reader releases went out as `sdk-v*` while it was published on its own
    schedule; from this release both halves go out under one `v*` tag.

    The two spellings share their numbers and not their meaning, so a number
    already spent on the reader alone cannot be spent again on the pair: PyPI
    refuses a re-upload, and it would refuse it after the tag was pushed and the
    first half of the release had already gone out under a number that does not
    come back.

    This replaces a test that asked whether the pin's *floor* named something
    installable. The pin is exact now and gated against this repository's own
    version, which answers that question by construction; this one is what the
    exact pin does not answer.
    """
    import subprocess

    here = re.search(r'^version = "([^"]+)"',
                     (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
                     re.M).group(1)
    tags = subprocess.run(["git", "tag", "--list", "sdk-v*"], cwd=ROOT,
                          capture_output=True, text=True)
    if tags.returncode != 0:
        import pytest
        pytest.skip("not a git checkout; the tag history is not available here")
    spent = {t for t in tags.stdout.split() if t}
    assert f"sdk-v{here}" not in spent, (
        f"the reader already went out as sdk-v{here}, so publishing {here} as "
        f"the pair would be a second upload of a number PyPI has already seen.")

def test_a_target_outside_the_gate_has_a_written_reason():
    """A Makefile target `make check` does not run is a decision, and the place
    to record it is beside the code that lets it through — not in a commit
    message. This also stops the exemption list becoming a way to quiet a gate:
    adding a name here means writing why."""
    targets = [line.split(":")[0] for line in MAKEFILE.splitlines()
               if re.match(r"^[a-zA-Z0-9_-]+:", line)]
    for name, why in OUTSIDE_CHECK.items():
        assert name in targets, f"{name} is exempted and the Makefile has no such target"
        assert len(why) > 30, f"{name} is exempted without a real reason"
    unknown = [n for n in OUTSIDE_CHECK if n not in targets]
    assert not unknown, unknown


def test_the_packaging_gates_clear_what_a_previous_build_left():
    """setuptools falls back to a previous run's `SOURCES.txt` when no VCS plugin
    is present, so `*.egg-info` makes the next distribution assembled from the
    last build's file list rather than from `MANIFEST.in`.

    Measured: with `recursive-include corpus *` deleted from `MANIFEST.in`, the
    sdist gate passed with an egg-info directory present and failed without it.
    Both packaging gates could not fail on a packaging declaration at all, on any
    machine that had built before — and both leave that directory behind
    themselves. `build/lib` is the same trap and was already handled; this is its
    sibling.
    """
    for tool in ("check_sdist.py", "check_wheel.py"):
        source = (ROOT / "tools" / tool).read_text(encoding="utf-8")
        assert "egg-info" in source, (
            f"tools/{tool} builds a distribution without clearing *.egg-info, so it "
            f"measures the last build rather than this commit")

    clean = (ROOT / "Makefile").read_text(encoding="utf-8")
    recipe = clean[clean.index("\nclean:"):]
    assert "egg-info" in recipe, "`make clean` leaves the fossil that blinds those gates"
    assert "**/__pycache__" not in recipe, (
        "`**` is not recursive under /bin/sh; that line deleted one level and left "
        "the package's own bytecode behind")


def test_the_fixture_generator_owns_its_output_directory(tmp_path):
    """It only ever wrote. A fixture deleted from the generator stayed on disk
    and went on satisfying firing coverage, so a fresh clone and a machine that
    had built before disagreed about what the catalogue covers.

    In a sandbox, not in `tests/fixtures/`. This test used to plant its stray
    file in the real directory and put the tree back in a `finally` — which
    deleted the directory outright and rebuilt it *without checking whether the
    rebuild worked*. One failing assertion here left the developer with no
    fixtures at all and the next test file unable to collect; the run after that
    reported four unrelated failures. A test that repairs the tree it damaged is
    one unhandled exception away from not repairing it.

    The generator takes its root from its own path, so a copy of the script beside
    a copy of the three corpus containers it reads is a complete, disposable
    installation of it.
    """
    import shutil
    import subprocess
    import sys

    (tmp_path / "tools").mkdir()
    shutil.copy2(ROOT / "tools" / "make_fixtures.py", tmp_path / "tools")
    # The whole corpus, not the files the generator happens to read today: an
    # enumeration here would turn "the generator started using another example"
    # into a failure of this test, which is about something else.
    shutil.copytree(ROOT / "corpus", tmp_path / "corpus")

    first = subprocess.run([sys.executable, "tools/make_fixtures.py"],
                           cwd=tmp_path, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr[-400:]
    out = tmp_path / "tests" / "fixtures"
    built = sorted(p.name for p in out.glob("*.zip"))
    assert built, "the generator produced nothing in a clean tree"

    stray = out / "zz-not-generated.zip"
    stray.write_bytes(b"PK\x03\x04 not produced by the generator")
    again = subprocess.run([sys.executable, "tools/make_fixtures.py"],
                           cwd=tmp_path, capture_output=True, text=True)
    assert again.returncode == 0, again.stderr[-400:]
    assert not stray.exists(), (
        "the generator left a file it did not produce; whatever else is in "
        "that directory is then evidence too")
    assert sorted(p.name for p in out.glob("*.zip")) == built, (
        "the second run does not produce what the first one did")


def test_the_code_in_this_tree_is_the_code_its_version_names():
    """The fingerprint watches the reader's public *surface*. Nothing watched its
    behaviour.

    `pdfread._is_encrypted` was repaired twice after `sdk-v0.6.1` was published —
    a scan that cost 135 seconds on a 1.5 KB archive, and one that called a plain
    PDF encrypted. Neither touched a name in `__all__`, so `api_fingerprint
    --check` stayed green at 0.6.1, and a user installing that version would have
    got the one on PyPI: the one without the repairs.

    A version is a promise about what you get, not only about what you can call.
    Both halves of the distribution, because they share one number now: a commit
    to `src/` after the tag is the same broken promise as a commit to the
    reader's, and only the reader's half was ever watched.
    """
    import subprocess

    tags = subprocess.run(["git", "tag", "--list", "v*", "sdk-v*"], cwd=ROOT,
                          capture_output=True, text=True)
    if tags.returncode != 0 or not tags.stdout.split():
        import pytest
        pytest.skip("no tag history here; this compares against the last release")

    here = re.search(r'^version = "([^"]+)"',
                     (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
                     re.M).group(1)
    # Either spelling. The reader's releases went out as `sdk-v*` while it was
    # its own distribution, and those numbers are on PyPI; reading only the
    # current prefix would make them all look unreleased.
    tag = next((t for t in (f"v{here}", f"sdk-v{here}") if t in tags.stdout.split()),
               None)
    if tag is None:
        # `skip`, not `return`. A bare return reports as a pass, and this test
        # spent its whole life reporting as one: the version in the tree is by
        # definition the unreleased one, so the tag is absent every time until
        # the moment of release. The sibling five lines above already says skip.
        import pytest
        pytest.skip(f"nothing tags {here} yet; it is being written")

    moved = subprocess.run(["git", "diff", "--name-only", tag, "--",
                            "src", "packages/vdi2770/src"],
                           cwd=ROOT, capture_output=True, text=True)
    changed = [p for p in moved.stdout.split() if p]
    assert not changed, (
        f"this tree says it is {here}, `{tag}` is published, and these have "
        f"moved since: {changed}. Whoever installs {here} does not get them. "
        f"Bump the version.")


def test_a_gate_that_starts_python_does_not_leave_bytecode_behind():
    """`__pycache__` is not where the bytecode goes on every machine.

    `sys.pycache_prefix` moves it out of the tree entirely — on the machine this
    was written on, to `~/Library/Caches`. A gate that clears `__pycache__` and
    then re-reads a file it has just restored is relying on a directory that may
    hold nothing, and CPython validates a cache on (mtime, size): restore a file
    to its previous size inside the same second and the stale bytecode wins.

    That is not hypothetical. It produced a `make check` failure that named a
    budget as moved when the source on disk was correct, and 73,000 cache files
    had accumulated outside the tree where no cleanup looks.

    The mutation table already sets this. The others start Python the same way
    and did not.

    Read as a syntax tree, not as text. `"PYTHONDONTWRITEBYTECODE" in body` was
    satisfied by the word appearing anywhere in the file: strip every `env=` from
    the real `subprocess.run` calls, leave a comment saying the variable used to
    be set, and this passed. That is the same shape as the gate that read an
    explanatory comment instead of the config line it meant to check, found in
    this repository a day earlier, and it is worth saying twice: a check that
    greps for a name is a check that a name is mentioned.
    """
    import ast
    import re

    for name in sorted(p.name for p in (ROOT / "tools").glob("*.py")):
        source = (ROOT / "tools" / name).read_text(encoding="utf-8")
        tree = ast.parse(source)

        # Names bound to something that sets the variable, so `env=NO_BYTECODE`
        # counts and `env=os.environ` does not -- and transitively, because
        # `env = dict(NO_BYTECODE, PYTHONPATH=tmp)` carries it without spelling
        # it. Iterated to a fixed point rather than assumed to be one level.
        # Not the name a `subprocess.run(...)` result is bound to. `r =
        # subprocess.run(..., env=NO_BYTECODE)` puts the carrier's name in the
        # assignment's source, which made `r` -- a `CompletedProcess` -- count as
        # an environment.
        bindings = [
            (target.id, ast.get_source_segment(source, node) or "")
            for node in ast.walk(tree) if isinstance(node, ast.Assign)
            if not (isinstance(node.value, ast.Call)
                    and "subprocess." in (ast.get_source_segment(source, node.value) or ""))
            for target in node.targets if isinstance(target, ast.Name)
        ]
        carriers, grew = set(), True
        while grew:
            grew = False
            for bound, text in bindings:
                if bound in carriers:
                    continue
                if ("PYTHONDONTWRITEBYTECODE" in text
                        or any(re.search(rf"\b{c}\b", text) for c in carriers)):
                    carriers.add(bound)
                    grew = True

        for call in [n for n in ast.walk(tree) if isinstance(n, ast.Call)]:
            shown = ast.get_source_segment(source, call) or ""
            if not (isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "subprocess"):
                continue
            if "sys.executable" not in shown:
                continue
            env = next((k.value for k in call.keywords if k.arg == "env"), None)
            assert env is not None, (
                f"tools/{name} line {call.lineno} starts Python in a subprocess "
                f"with no env=, so it leaves bytecode wherever this interpreter "
                f"puts it — which is not always a directory anything cleans")
            passed = ast.get_source_segment(source, env) or ""
            # `\b`, as the loop above already uses. `c in passed` is a
            # substring test, and this file's own carrier names include `env` --
            # so `env=os.environ`, which is the exact regression this gate is
            # named for, contained the word `env` and passed. The gate that
            # replaced a grep was still doing one, three lines from the end.
            assert ("PYTHONDONTWRITEBYTECODE" in passed
                    or any(re.search(rf"\b{re.escape(c)}\b", passed)
                           for c in carriers)), (
                f"tools/{name} line {call.lineno} passes env={passed}, which "
                f"does not carry PYTHONDONTWRITEBYTECODE")



def test_ci_installs_both_halves_from_this_tree_and_the_reader_first():
    """Deleting an editable install from CI leaves nothing red.

    `test_contributing_installs_what_ci_installs` checks the other direction —
    that whatever CI installs is written down — so removing one shrinks what it
    has to check and it passes.

    Two halves, two installs, and the order carries the weight. The rules pin
    the reader exactly. Install the rules first and pip goes to an index for a
    version nobody has published yet; on the day it *is* published, that same
    line quietly installs the released reader instead of the one in this commit,
    and every result in the run is about a different tree. That is not
    hypothetical -- it is the split that shipped a release whose own fix never
    reached the user.
    """
    editable = [c for c in ci_commands()
                if c.startswith("python -m pip install -e ")]
    assert len(editable) == 2, (
        f"CI makes {len(editable)} editable installs: {editable}. This "
        f"repository builds two distributions and both have to come from the "
        f"tree, or the run is partly about whatever the index holds.")
    assert editable[0].endswith("packages/vdi2770"), (
        f"CI installs {editable[0]} before the reader. The rules pin the reader "
        f"exactly, so pip resolves that pin from an index instead of from this "
        f"commit.")
    assert "packages/" not in editable[1], (
        f"CI's second install is {editable[1]}, not the repository root")


def test_nothing_in_the_fast_suite_installs_from_an_index():
    """`make check` is offline, and that is the property this tool sells: it is
    what lets the thing run inside a plant network with no route out.

    Nothing enforced it. A test added with the packaging work installed this
    tree with `pip install <root>`, which goes to PyPI for the runtime
    dependency, and it passed everywhere anyone ran it -- on a laptop with a
    network, and in CI, which also has one. The promise held exactly where
    nobody could check it, which is the shape of every claim in this repository
    that turned out to be false.

    Scoped to `pip install`: an index is the only thing in `make check` that
    needs a route out, and `--no-index` is the flag that refuses one. The
    packaging gates that do install run outside the fast suite, from wheels they
    built themselves, and pass that flag.
    """
    offenders = []
    for suite in (ROOT / "tests", ROOT / "packages" / "vdi2770" / "tests"):
        for path in sorted(suite.rglob("test_*.py")):
            text = path.read_text(encoding="utf-8")
            for found in re.finditer(r'"pip"\s*,\s*"install"', text):
                call = text[found.start():found.start() + 400]
                if "--no-index" not in call:
                    line = text[:found.start()].count("\n") + 1
                    offenders.append(f"{path.relative_to(ROOT)}:{line}")
    assert not offenders, (
        f"these install from an index inside `make check`, which is supposed to "
        f"run with no route out: {offenders}. Build the artifact and install it "
        f"with --no-index, or move the check to a target CI runs separately.")


def test_every_workflow_that_installs_this_project_installs_the_reader_first():
    """One workflow had both install lines and the other had one.

    The rules pin the reader exactly, and the reader is not on an index until
    the release that publishes it. A workflow that installs this repository and
    nothing else therefore fails outright before that release — and, after it,
    fails in the worse direction: it succeeds, having installed the *published*
    reader rather than the one in the commit it is running against.

    The one that was missing it is the sweep, which is where the reference
    implementation's verdicts come from — the evidence a release publishes
    divergence counts out of. `test_ci_installs_both_halves_from_this_tree_and_the_reader_first`
    reads one file; nothing looked across them.
    """
    from pathlib import Path

    for path in sorted(Path(CI.parent).glob("*.yml")):
        body = path.read_text(encoding="utf-8")
        rules = body.find('pip install -e "."')
        if rules < 0:
            rules = body.find('pip install -e ".[dev]"')
        if rules < 0:
            continue
        reader = body.find("pip install -e packages/vdi2770")
        assert 0 <= reader < rules, (
            f"{path.name} installs this repository without installing the "
            f"reader from the tree first. The pin is exact, so pip goes to an "
            f"index for it: before the release that is a hard failure, and "
            f"after it the run silently becomes about the published reader "
            f"instead of this commit.")
