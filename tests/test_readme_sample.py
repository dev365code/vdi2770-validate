"""The README's sample session must be output the tool can actually produce.

The first one was hand-written: it showed one remedy for three findings, wrapped
a line the renderer never wraps, and quoted a column number that cannot occur.
A fabricated sample is a screenshot of a program that does not exist.
"""
import re

from conftest import ROOT
from vdi2770_validate import report as rendering
from vdi2770_validate.runner import check_file

README = (ROOT / "README.md").read_text(encoding="utf-8")
BLOCK = re.search(r"```\n\$ vdi2770-validate check (\S+)\n(.*?)```", README, re.S)


def test_the_readme_shows_a_command_that_exists():
    assert BLOCK, "no sample session found in README.md"
    assert (ROOT / BLOCK.group(1)).exists(), f"the sample runs on {BLOCK.group(1)}, which is not here"


def test_every_line_of_the_sample_is_really_produced():
    target, shown = BLOCK.group(1), BLOCK.group(2)
    real = rendering.as_text(check_file(str(ROOT / target))).splitlines()
    for line in shown.splitlines():
        if not line.strip() or line.strip().startswith("…"):
            continue          # deliberate elision, marked as such
        assert line in real, f"the README shows a line the tool never prints:\n  {line}"


def test_the_sample_does_not_claim_a_pdfa_verdict():
    assert not re.search(r"PDF/A.{0,24}\b(valid|conformant|compliant)\b", README, re.I)
