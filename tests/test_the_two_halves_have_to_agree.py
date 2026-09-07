"""What the tool asks about its own installation before it judges anything.

The reader and the rules ship under one tag and carry one number. This is the
question that follows from that: do the two loaded halves still say the same
thing, and does an install record sitting beside the loaded code agree with it.

Every case here is wrong on exactly one axis, because a case broken two ways
proves neither assertion — delete either check and it still fails on the other,
and the mutation for the deleted one survives.

The refusals matter less than the silences. A validator that refuses a working
installation is a new destruction wearing a safety label, and the first draft of
this check refused six of them: the single-file build on any machine that had
also pip-installed the reader, a `--target` layer over a base image, a source
checkout with a stale `.egg-info`, a coherent process whose environment changed
in another window, an `rc1` spelled with a hyphen, and — the one that decides the
shape — anything at all whose records live somewhere other than where the code
was loaded from.
"""
import sys
import types

import pytest

from vdi2770_validate import agreement


@pytest.fixture(autouse=True)
def _uncached():
    """The answer is computed once per process, which is the point of it. Each
    case here wants its own."""
    agreement._ANSWER.clear()
    yield
    agreement._ANSWER.clear()


def _site(tmp_path, name, version, *, record=None, record_kind="dist-info"):
    """A directory holding one importable package and, optionally, a record.

    `record_kind` is the axis of the `.egg-info` case: a build artifact carries
    `PKG-INFO` and an installed distribution carries `METADATA`, and that is
    what tells them apart.
    """
    site = tmp_path / "site"
    package = site / name.replace("-", "_")
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    if record is not None:
        if record_kind == "dist-info":
            info = site / f"{name}-{record}.dist-info"
            info.mkdir()
            (info / "METADATA").write_text(
                f"Metadata-Version: 2.1\nName: {name}\nVersion: {record}\n", encoding="utf-8")
        else:
            info = site / f"{name.replace('-', '_')}.egg-info"
            info.mkdir()
            (info / "PKG-INFO").write_text(
                f"Metadata-Version: 2.1\nName: {name}\nVersion: {record}\n", encoding="utf-8")
    return site


def _loaded(monkeypatch, reader="0.8.0", rules="0.8.0"):
    """Both halves, as loaded modules. Nothing here imports the real ones: the
    question is about two `__version__` strings and where they came from."""
    for name, version in (("vdi2770", reader), ("vdi2770_validate", rules)):
        module = types.ModuleType(name)
        module.__version__ = version
        module.__file__ = f"/nowhere/{name}/__init__.py"
        monkeypatch.setitem(sys.modules, name, module)


def test_two_halves_that_agree_say_nothing(monkeypatch):
    _loaded(monkeypatch)
    monkeypatch.setattr(agreement, "_co_located_records", lambda module, name: {})
    assert agreement.disagreement() is None


def test_two_halves_that_disagree_are_caught(monkeypatch):
    """One axis: the reader's number. Everything else is the passing case."""
    _loaded(monkeypatch, reader="0.7.0")
    monkeypatch.setattr(agreement, "_co_located_records", lambda module, name: {})
    said = agreement.disagreement()
    assert said and "0.7.0" in said and "0.8.0" in said


def test_the_same_release_spelled_two_ways_is_one_release(monkeypatch):
    """`0.8.0-rc1` is what a hand-edited literal says and `0.8.0rc1` is what the
    build backend writes. Refusing over the punctuation would be a refusal of a
    working install."""
    _loaded(monkeypatch, reader="0.8.0-rc1", rules="0.8.0rc1")
    monkeypatch.setattr(agreement, "_co_located_records", lambda module, name: {})
    assert agreement.disagreement() is None


def test_a_record_beside_the_code_that_disagrees_is_caught(monkeypatch, tmp_path):
    site = _site(tmp_path, "vdi2770", "0.8.0", record="0.7.1")
    monkeypatch.syspath_prepend(str(site))
    module = types.ModuleType("vdi2770")
    module.__file__ = str(site / "vdi2770" / "__init__.py")
    assert "0.7.1" in str(agreement._co_located_records(module, "vdi2770"))


def test_a_record_somewhere_else_on_the_path_is_not_this_installations(monkeypatch, tmp_path):
    """The decision the whole shape rests on.

    The single-file build carries no record at all and puts itself first on
    `sys.path`; a `--target` layer wins over a base image that has its own
    copy. In both, a record with a different number exists on this machine and
    says nothing about the code that loaded. Compared against everything on the
    path, the first draft refused both — and the `.pyz` is sold to people with
    no route to an index, handed a `pip install` as the remedy.
    """
    elsewhere = _site(tmp_path, "vdi2770", "0.7.1", record="0.7.1")
    monkeypatch.syspath_prepend(str(elsewhere))
    running_from = tmp_path / "elsewhere"
    running_from.mkdir()
    module = types.ModuleType("vdi2770")
    module.__file__ = str(running_from / "vdi2770" / "__init__.py")
    assert agreement._co_located_records(module, "vdi2770") == {}


def test_a_build_artifact_beside_the_code_is_not_an_install_record(monkeypatch, tmp_path):
    """An `.egg-info` in a source checkout, which is this repository on any day
    somebody moves a version literal before reinstalling. The `Makefile` already
    says these linger; turning that into a refusal of every verdict would stop
    `make test`.

    One axis against the case above it: the record is `PKG-INFO` rather than
    `METADATA`, and that is the whole difference.
    """
    site = _site(tmp_path, "vdi2770", "0.8.0", record="0.7.1", record_kind="egg-info")
    monkeypatch.syspath_prepend(str(site))
    module = types.ModuleType("vdi2770")
    module.__file__ = str(site / "vdi2770" / "__init__.py")
    assert agreement._co_located_records(module, "vdi2770") == {}


def test_a_namespace_package_still_says_where_it_loaded():
    """It has no `__file__` at all, and the layout under discussion for this
    project is exactly that. Read off `__file__` alone, the check would fall
    silent on the release it was written for."""
    ordinary = types.ModuleType("a")
    ordinary.__file__ = "/site/a/__init__.py"
    namespace = types.ModuleType("b")
    namespace.__path__ = ["/site/b"]
    assert agreement._where_it_loaded(ordinary) == agreement._where_it_loaded(namespace)


def test_it_is_computed_once(monkeypatch):
    """Not a saving — a correction. `__version__` freezes at import, so the only
    thing that can change under a long-lived process is the metadata beside it,
    and re-reading it per verdict bought exactly one behaviour: a coherent,
    correct, still-running process refusing everything because somebody upgraded
    the environment in another window."""
    _loaded(monkeypatch)
    asked = []

    def counted(module, name):
        asked.append(name)
        return {}

    monkeypatch.setattr(agreement, "_co_located_records", counted)
    assert agreement.disagreement() is None
    first = len(asked)
    assert agreement.disagreement() is None
    assert len(asked) == first, "the answer was computed a second time"


def test_the_refusal_reaches_the_command_as_three_and_writes_no_report(monkeypatch, capsys):
    """The check is only worth what the command does with it.

    Raised out of `check_bytes`, it used to be caught by the sweep's own
    `except Exception`, reported as `cannot read it`, counted as an unreadable
    path — and written into the JSON as a document stamped `toolVersion` by the
    install that had just said it could not account for itself. The exit was 2,
    or 1 in a mixed batch, which a CI log cannot tell from a failing container.
    """
    from vdi2770_validate import cli

    def refuse():
        raise agreement.InstallationDisagrees("the two halves say different things")

    monkeypatch.setattr(cli, "refuse_if_disagreeing", refuse)
    monkeypatch.setattr("vdi2770_validate.runner.refuse_if_disagreeing", refuse)
    code = cli.main(["check", "--json", "corpus/examples/container/documentcontainer.zip"])
    out, err = capsys.readouterr()
    assert code == 3, f"the refusal came back as {code}"
    assert out.strip() == "", f"a report was written anyway: {out[:200]}"
    assert err.startswith(agreement.MARKER), err[:200]


def test_the_version_is_not_answered_by_half_an_installation(monkeypatch, capsys):
    """`--version` in a split install prints the rules half, which is true about
    the package it came from and false about the tool that would run. That is
    the one number a person must not be handed on its own, and argparse's own
    `version` action prints it during parsing, before anything could ask."""
    from vdi2770_validate import cli

    def refuse():
        raise agreement.InstallationDisagrees("the two halves say different things")

    monkeypatch.setattr(cli, "refuse_if_disagreeing", refuse)
    code = cli.main(["--version"])
    out, err = capsys.readouterr()
    assert code == 3
    assert out.strip() == ""
    assert err.startswith(agreement.MARKER)


def test_a_caller_who_never_touches_the_command_still_goes_through_it(monkeypatch):
    """The other door.

    The front page sells `import vdi2770_validate` as a way to use this, and a
    caller coming through it would otherwise get verdicts from an installation
    nothing had questioned. The check sits at the report rather than at the
    start of the command, so both doors pass through one call — and it raises
    instead of exiting, because a library that calls `sys.exit` tears down
    somebody else's process.
    """
    from vdi2770_validate import runner

    def refuse():
        raise agreement.InstallationDisagrees("the two halves say different things")

    monkeypatch.setattr(runner, "refuse_if_disagreeing", refuse)
    with pytest.raises(agreement.InstallationDisagrees):
        runner.check_bytes(b"not a zip", "x.zip")
