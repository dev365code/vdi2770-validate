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


def _rows():
    page = (ROOT / "docs" / "official-samples.md").read_text(encoding="utf-8")
    rows = [line.split("|")[1:-1] for line in page.splitlines() if line.startswith("| `")]
    assert rows, "the page lists no sample; the tests below would prove nothing"
    return [[cell.strip() for cell in row] for row in rows]


def test_each_exit_on_the_page_is_what_the_command_returns(capsys):
    """Held to the command itself, not to the generator's copy of how an exit
    is decided: a new exit code in the command would otherwise leave the page
    reading 1 where a pipeline sees something else, and the page would still be
    what the generator writes."""
    import vdi2770.validate.cli as cli
    for sample, exit_code, *_ in _rows():
        path = ROOT / "corpus" / "examples" / sample.strip("`")
        returned = cli.main(["check", "--quiet", "--no-bundle", str(path)])
        capsys.readouterr()
        assert exit_code == str(returned), (
            f"{sample}: the page says exit {exit_code}, the command returns {returned}")


def test_the_rules_on_each_row_are_in_the_order_a_reader_counts():
    """M3 before M13, as the rules page and the `rules` command list them --
    not the order a string sort gives."""
    import re
    for sample, *_, fired in _rows():
        ids = re.findall(r"\b([A-Z]+)(\d+) ×", fired)
        assert ids == sorted(ids, key=lambda i: (i[0], int(i[1]))), f"{sample}: {fired}"
