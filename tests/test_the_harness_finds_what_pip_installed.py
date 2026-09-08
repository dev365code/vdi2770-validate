"""The upgrade harness asks whether a console script is installed. It has to
ask in a way that is true on the platform it is asking about.

`CreateProcess` appends `.exe` when you run a path that has no extension, which
is why the harness's `pip` and `python` work unqualified on Windows and nobody
noticed anything. The one place that asks a *question* — is this command
installed? — got a plain `Path.exists()`, and on Windows that answers no about
an installation that has it.

This matters twice over. The harness has an assertion that a particular install
carries *no* command, and an absence that is right for the wrong reason is a
gate that passes while seeing nothing. And the release this file belongs to is
the one that moves the command's owner, so the harness's answer about which
installs carry it is the thing being checked.

Synthetic directories rather than a venv: the case that was wrong is the one
this machine cannot produce.
"""
import sys

sys.path.insert(0, "tools")

from check_upgrade_paths import installed_command  # noqa: E402

COMMAND = "vdi2770-validate"


def test_a_plain_file_is_the_command(tmp_path):
    """What pip writes on Linux and macOS."""
    (tmp_path / COMMAND).write_text("#!/usr/bin/env python\n")
    assert installed_command(tmp_path, COMMAND) == tmp_path / COMMAND


def test_the_windows_executable_is_the_command(tmp_path):
    """What pip writes on Windows, and what the old lookup called absent."""
    made = tmp_path / (COMMAND + ".exe")
    made.write_bytes(b"MZ")
    assert installed_command(tmp_path, COMMAND) == made


def test_nothing_installed_is_nothing(tmp_path):
    """The answer the harness turns into `None`, so that an install with no
    command reads as one rather than as a crash."""
    assert installed_command(tmp_path, COMMAND) is None


def test_a_name_that_merely_starts_the_same_is_not_the_command(tmp_path):
    """setuptools has written `<name>-script.py` beside the executable, and a
    glob for `vdi2770-validate*` takes it for the command. So would
    `vdi2770-validate-extras` if anyone ever shipped one."""
    (tmp_path / (COMMAND + "-script.py")).write_text("")
    (tmp_path / (COMMAND + "-extras")).write_text("")
    assert installed_command(tmp_path, COMMAND) is None


def test_the_plain_file_wins_when_both_are_there(tmp_path):
    """Not a preference — a fixed order, so the harness reports one path and
    the same one every time it is asked."""
    (tmp_path / COMMAND).write_text("")
    (tmp_path / (COMMAND + ".exe")).write_bytes(b"MZ")
    assert installed_command(tmp_path, COMMAND) == tmp_path / COMMAND
