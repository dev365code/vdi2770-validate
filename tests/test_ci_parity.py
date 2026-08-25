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
    recipes = [c.replace("$(PYTHON)", "python").strip() for c in recipe_commands()]
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


def test_the_sdk_in_this_repository_satisfies_the_pin_that_depends_on_it():
    """Two packages in one repository, and the second declares a version range
    for the first. Nothing checked that the copy sitting right here satisfies it.

    It cost a broken install already: bumping the reader to `0.3.0.dev0` while the
    validator asked for `vdi2770~=0.3.0` sent pip to PyPI, because a pre-release
    does not satisfy a compatible-release specifier. Locally and in CI the reader
    is installed from the working tree, so the pin has to accept what is there.
    """
    from packaging.requirements import Requirement
    from packaging.version import Version

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    deps = re.search(r"^dependencies = \[(.*?)\]", pyproject, re.M | re.S)
    assert deps, "the validator declares no dependencies"
    pin = next((Requirement(m) for m in re.findall(r'"([^"]+)"', deps.group(1))
                if Requirement(m).name == "vdi2770"), None)
    assert pin is not None, "the validator no longer depends on the reader"

    sdk = (ROOT / "packages" / "vdi2770" / "pyproject.toml").read_text(encoding="utf-8")
    here = Version(re.search(r'^version = "([^"]+)"', sdk, re.M).group(1))

    assert pin.specifier.contains(here, prereleases=here.is_prerelease), (
        f"the reader in this repository is {here} and the validator asks for "
        f"{pin}. `pip install -e .` will go to PyPI and fail.")

    # Accepting the reader beside it is not enough: the range has to *require* it.
    # `vdi2770~=0.3.0` accepted 0.3.1 and pip installed 0.3.0, so vdi2770-validate
    # 0.5.0 shipped with the reader whose fix was the entire reason for the
    # release. The floor is the version this was tested against.
    floors = [s.version for s in pin.specifier if s.operator in ("~=", ">=", "==")]
    assert floors, f"{pin} has no lower bound; any older reader satisfies it"
    assert Version(max(floors, key=Version)) == here, (
        f"the reader here is {here} but the pin's floor is {max(floors, key=Version)}. "
        f"A user can install an older reader than the one these tests ran against.")


def test_ci_runs_every_python_either_package_advertises():
    """A classifier on PyPI is a promise to whoever reads it before installing.

    The existing floor test reads the validator's `requires-python` and nothing
    else, so the reader package advertised `Programming Language :: Python ::
    3.13` while CI ran 3.9 and 3.12 and no interpreter ever confirmed it.
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
    """CI installs the reader from the working tree before the validator, with a
    comment saying that is what proves the commit's two halves fit together.
    CONTRIBUTING said `pip install -e ".[dev]"` and nothing else, so a
    contributor following it resolved the reader from PyPI and ran the gate
    against a different reader than CI did.
    """
    prose = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    # Editable installs of this repository's own two distributions. `pip install
    # build` is a tool the wheel gate needs, not a thing under test.
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
    publishes the reader to PyPI — ran two, and never ran
    `tools/api_fingerprint.py`, whose entire purpose is to stop that workflow
    publishing a reader whose public surface has moved under an old version.
    Nothing noticed, because the parity test read `ci.yml` and no other file.

    A workflow that publishes runs `make check`. Not a copy of it.
    """
    publishing = [w for w in workflows()
                  if "pypi-publish" in w.read_text(encoding="utf-8")
                  or "upload-artifact" in w.read_text(encoding="utf-8")]
    assert publishing, "no workflow publishes anything; this test is looking in the wrong place"
    for w in publishing:
        ran = commands_in(w)
        assert any(c.strip() == "make check" for c in ran), (
            f"{w.name} publishes and does not run `make check`. It runs: {ran}")


def test_a_step_that_runs_make_check_runs_it_where_the_makefile_is():
    """`release-sdk.yml` sets `defaults.run.working-directory: packages/vdi2770`
    for the whole file. A step added there without `working-directory: .` runs
    from inside the library, where there is no Makefile and no
    `packages/vdi2770` — so the SDK release failed before it could publish, and
    the gate that step exists to run never ran.

    Checked structurally rather than by name: any workflow with a file-wide
    default must override it on a step that runs a repository-root command.
    """
    import re

    for w in workflows():
        text = w.read_text(encoding="utf-8")
        default = re.search(r"^defaults:\s*\n\s+run:\s*\n\s+working-directory:\s*(\S+)",
                            text, re.M)
        if not default or default.group(1) == ".":
            continue
        for step in re.split(r"\n      - ", text):
            root_commands = [c for c in ("make check", "make ", "python tools/")
                             if c in step]
            if not root_commands:
                continue
            assert re.search(r"^\s+working-directory:\s*\.\s*$", step, re.M), (
                f"{w.name} defaults to {default.group(1)!r} and a step runs "
                f"{root_commands} without `working-directory: .`:\n{step[:200]}")


def test_the_pin_names_a_reader_that_has_been_published():
    """What this enforces is release *order*, not the pin's value.

    The floor test above compares the pin to the reader in this tree and requires
    them equal, which leaves exactly one open question: is that version something
    a user can already install, or is it about to be published? If it is about to
    be, the SDK has to be tagged first — and it cannot be tagged at all without
    the API baseline that gates its release.

    At one point today the pin said `vdi2770~=0.5.0` for a reader that existed
    nowhere but this working tree — 0.5.0 was never tagged. Tagging the validator
    from there would have published a distribution `pip` could not resolve, which
    is the same failure as an over-loose pin arriving from the other direction.

    A pin may name the version being released alongside it: `sdk-v<version>` in
    the tags, or the reader's version bumped in this same tree with the SDK
    release still to come. What it may not do is name a version that is neither.
    """
    import re
    import subprocess

    from packaging.requirements import Requirement

    deps = re.search(r"^dependencies = \[(.*?)\]",
                     (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M | re.S)
    pin = next(Requirement(m) for m in re.findall(r'"([^"]+)"', deps.group(1))
               if Requirement(m).name == "vdi2770")
    floor = max((s.version for s in pin.specifier if s.operator in ("~=", ">=", "==")),
                key=lambda v: tuple(int(x) for x in v.split(".")))

    tags = subprocess.run(["git", "tag", "--list", "sdk-v*"], cwd=ROOT,
                          capture_output=True, text=True)
    if tags.returncode != 0:
        import pytest
        pytest.skip("not a git checkout; the tag history is not available here")
    published = {t[len("sdk-v"):] for t in tags.stdout.split()}
    here = re.search(r'^version = "([^"]+)"',
                     (ROOT / "packages" / "vdi2770" / "pyproject.toml").read_text(encoding="utf-8"),
                     re.M).group(1)

    # Belt only, and worth saying so: the sibling above asserts `floor == here`
    # outright, so this disjunction cannot fail while that test is green. It is
    # here to survive that test being loosened, not to catch anything today.
    assert floor in published or floor == here, (
        f"the validator pins vdi2770>={floor}, which is neither a published tag "
        f"({sorted(published)}) nor the reader in this tree ({here}). Releasing the "
        f"validator on this pin gives users something pip cannot resolve.")

    # This is the live half.
    if floor == here and floor not in published:
        # Legal, and it means one thing: the SDK ships first.
        assert (ROOT / "packages" / "vdi2770" / "API.json").exists(), (
            "the pin names an unpublished reader, so `sdk-v" + here + "` has to be "
            "tagged before the validator — and the API baseline has to exist for that "
            "release to be gated at all")


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
