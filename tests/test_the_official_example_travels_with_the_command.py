"""`check --example` checks the official example this package carries, so a
first look at a report needs no file of one's own, no clone of this repository
and no network. The example is the reference implementation's own document
container -- MIT, the same bytes `corpus/` holds -- and the report on it is the
report on that file, whether the package is installed or runs from the single
file, where the example is not a file until something copies it out.
"""
import hashlib
import json
import os
import subprocess
import sys
import zipfile

import pytest

from conftest import CLEAN_DOCUMENT, ROOT, under_test
from vdi2770_validate import cli

PACKAGE = ROOT / "packages" / "vdi2770" / "src" / "vdi2770"
CARRIED = PACKAGE / "validate" / "data" / "example" / "documentcontainer.zip"


def _said(documents):
    return [[(f["rule"], f["severity"], f["detail"]) for f in d["findings"]] for d in documents]


def test_the_example_is_the_reference_implementations_own_byte_for_byte():
    entry = json.loads((ROOT / "corpus" / "MANIFEST.json").read_text(encoding="utf-8"))[
        "files"]["container/documentcontainer.zip"]
    assert hashlib.sha256(CARRIED.read_bytes()).hexdigest() == entry["sha256"]
    assert CARRIED.read_bytes() == CLEAN_DOCUMENT.read_bytes()


def test_check_example_reports_on_the_example_and_exits_with_its_verdict(capsys):
    assert cli.main(["check", "--example", "--json"]) == 0
    example = json.loads(capsys.readouterr().out)
    assert cli.main(["check", "--json", str(CLEAN_DOCUMENT)]) == 0
    assert _said(example) == _said(json.loads(capsys.readouterr().out)) != [[]]


def test_check_example_says_what_it_is_checking(capsys):
    assert cli.main(["check", "--example"]) == 0
    first = capsys.readouterr().out.splitlines()[0]
    assert first == ("The example this package carries: the document container of the VDI 2770 "
                     "reference implementation, MIT, (c) 2021 Johannes Schmidt."), first


@pytest.mark.parametrize("argv", [["check", "--example", str(CLEAN_DOCUMENT)], ["check"]],
                         ids=["the example and a path", "neither"])
def test_check_takes_the_example_or_paths(argv, capsys):
    """Given both, whichever won, the other would go unchecked without a word."""
    with pytest.raises(SystemExit) as e:
        cli.main(argv)
    assert e.value.code == 64
    assert "--example" in capsys.readouterr().err


def test_a_bug_report_of_the_example_says_it_was_the_example(tmp_path, capsys):
    """The bundle says how the run was asked for, and asked for again its way
    it has to be the same run: without `--example`, `check` with no path is a
    usage error."""
    assert cli.main(["check", "--example", "--bug-report", "--bundle-out", str(tmp_path)]) == 0
    capsys.readouterr()
    [written] = list(tmp_path.glob("bug-report-*.json"))
    argv = json.loads(written.read_text(encoding="utf-8"))["invocation"]["argv"]
    assert "--example" in argv and not [a for a in argv if a.startswith("<input-")], argv


def test_the_example_is_read_out_of_a_zip_as_the_single_file_holds_it(tmp_path):
    """From the single file the example is a member of an archive, not a file,
    and the check reads files."""
    held = tmp_path / "engine.zip"
    with zipfile.ZipFile(held, "w") as z:
        for path in PACKAGE.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                z.write(path, str(path.relative_to(PACKAGE.parent)))
    env = under_test(PYTHONPATH=os.pathsep.join([str(held), str(ROOT / "src")]), PYTHONDONTWRITEBYTECODE="1")
    done = subprocess.run([sys.executable, "-m", "vdi2770.validate", "check", "--example", "--json"],
                          capture_output=True, text=True, env=env, cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert ".zip" in subprocess.run(
        [sys.executable, "-c", "import vdi2770; print(vdi2770.__file__)"],
        capture_output=True, text=True, env=env, cwd=tmp_path).stdout, "the premise: the engine came from the zip"
    corpus = subprocess.run([sys.executable, "-m", "vdi2770.validate", "check", "--json", str(CLEAN_DOCUMENT)],
                            capture_output=True, text=True, env=env, cwd=tmp_path)
    assert _said(json.loads(done.stdout)) == _said(json.loads(corpus.stdout))
