"""`docs/official-samples.md` is this tool's verdict on every sample the
reference repository publishes, written by `tools/official_samples.py` from the
tool itself. A rule that changes what the tool says about a sample changes the
page in the same commit, or this is red: a page of verdicts that the tool no
longer gives is a claim nobody can check against anything.
"""
import importlib.util

from conftest import ROOT


def _tool():
    spec = importlib.util.spec_from_file_location("official_samples", ROOT / "tools" / "official_samples.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_samples_page_is_what_the_tool_says():
    page = (ROOT / "docs" / "official-samples.md").read_text(encoding="utf-8")
    assert page == _tool().render(), (
        "docs/official-samples.md is not what this tool says about the samples; "
        "run python tools/official_samples.py --write")
