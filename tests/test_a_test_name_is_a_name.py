"""No test is named after the bytes it was given.

`pytest.mark.parametrize` builds an id out of the parameter values, so a case
handed a whole document is called after that document. It is unreadable in a
log everywhere, and on Windows it is fatal: pytest writes the current test id
into `PYTEST_CURRENT_TEST`, and Windows refuses an environment variable over
32767 characters, so every such case failed in teardown with a `ValueError` from
`os.environ` — the test itself having passed.

That was found by the first Windows run in CI, on a suite that was green on
Linux. The parameters it caught were two PDFs; the rule is general, so
the gate is general.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from conftest import ROOT

#: Long enough for a descriptive name with parameters, far short of a document.
#: The two cases that failed were thousands of characters; the longest honest
#: name here is a fraction of this.
LONGEST = 200


#: A plugin, because `--collect-only -q` prints a count per file rather than the
#: ids themselves — which is how the first version of this gate collected
#: nothing at all and passed. Asking pytest for the node ids is the only way to
#: get what pytest made; the parameters are in the source and the ids are not.
_PLUGIN = """
def pytest_collection_modifyitems(items):
    for item in items:
        print("NODEID " + item.nodeid)
"""


def collected():
    """Every test id the suite would run."""
    with tempfile.TemporaryDirectory() as tmp:
        plugin = Path(tmp) / "collect_the_ids.py"
        plugin.write_text(_PLUGIN, encoding="utf-8")
        env = {**os.environ, "PYTHONPATH": tmp, "PYTHONDONTWRITEBYTECODE": "1"}
        done = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q",
             "-p", "no:cacheprovider", "-p", "collect_the_ids"],
            cwd=str(ROOT), env=env, capture_output=True, text=True)
    assert done.returncode == 0, f"collection failed:\n{done.stdout[-2000:]}"
    found = [line[len("NODEID "):] for line in done.stdout.splitlines()
             if line.startswith("NODEID ")]
    assert found, "the plugin collected no ids at all; this gate would pass on anything"
    return found


def test_no_test_is_named_after_its_own_input():
    over = [f"{line[:80]}… ({len(line)} characters)"
            for line in collected() if len(line) > LONGEST]
    assert not over, (
        "test ids longer than "
        f"{LONGEST} characters:\n  " + "\n  ".join(over)
        + "\n\nA parametrised case is named after its parameters unless `ids=` "
          "says otherwise. Windows refuses an environment variable over 32767 "
          "characters and pytest puts the id in one, so a case named after a "
          "document passes and then fails in teardown.")
