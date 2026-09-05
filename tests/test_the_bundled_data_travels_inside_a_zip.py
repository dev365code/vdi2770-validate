"""The tool has to work as a single file, and its data has to come with it.

`resources.py` reached the bundled schema and tables through
`Path(__file__).parent / "data"` and read them with `.read_text()`. Inside a
zipapp that path names something that is not a directory, so every one of them
raises — and `schema_stamp` catches `OSError` and answers `None`, which is the
worst of the three: the report says the build carries no schema, quietly, and
nothing else notices.

Built here rather than asserted about: the question is whether the data is
reachable when the package is a zip, and only a zip answers it.
"""
from __future__ import annotations

import subprocess
import sys
import zipapp
from pathlib import Path

import pytest

from conftest import CLEAN_DOCUMENT, ROOT

READER = ROOT / "packages" / "vdi2770" / "src" / "vdi2770"
VALIDATOR = ROOT / "src" / "vdi2770_validate"


@pytest.fixture(scope="module")
def one_file(tmp_path_factory):
    """The two packages and an entry point, zipped into one file."""
    import shutil

    staged = tmp_path_factory.mktemp("staged")
    shutil.copytree(VALIDATOR, staged / "vdi2770_validate")
    shutil.copytree(READER, staged / "vdi2770")
    (staged / "__main__.py").write_text(
        "from vdi2770_validate.cli import _run\n_run()\n", encoding="utf-8")
    out = staged.parent / "vdi2770.pyz"
    zipapp.create_archive(staged, out, interpreter=None)
    return out


def _run_inside(pyz: Path, code: str) -> subprocess.CompletedProcess:
    """Run `code` with the zipapp on the path — the data has to come from it."""
    import os

    env = dict(os.environ)
    env["PYTHONPATH"] = str(pyz)
    env.pop("PYTHONHOME", None)
    return subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, timeout=120, env=env, cwd=str(ROOT))


def test_the_rules_are_readable_from_inside_the_zip(one_file):
    done = _run_inside(one_file, "from vdi2770_validate.catalog import rules; "
                                 "print(len(rules()))")
    assert done.returncode == 0, done.stderr[-600:]
    assert int(done.stdout.strip()) > 30, done.stdout


def test_the_schema_is_readable_from_inside_the_zip(one_file):
    """Both halves: the version it stamps on itself, and the schema text a
    validation actually needs. `schema_stamp` answering `None` is not a pass —
    it swallows the error and reports the build as carrying no schema."""
    done = _run_inside(one_file, "from vdi2770_validate.resources import schema_stamp, "
                                 "schema_text; print(schema_stamp(), len(schema_text()))")
    assert done.returncode == 0, done.stderr[-600:]
    stamp, size = done.stdout.split()
    assert stamp == "2019-08-23", f"the build reported its schema as {stamp!r}"
    assert int(size) > 1000, size


def test_a_container_is_checked_by_the_single_file(one_file):
    """End to end, because the point of the file is that somebody can run it."""
    done = subprocess.run([sys.executable, str(one_file), "check", str(CLEAN_DOCUMENT)],
                          capture_output=True, text=True, timeout=180, cwd=str(ROOT))
    assert done.returncode == 0, done.stdout + done.stderr
    assert "0 error(s)" in done.stdout, done.stdout
