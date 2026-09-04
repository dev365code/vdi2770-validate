"""`--json` is advertised as the machine-readable shape, and it carried no
statement of what produced it: not the format's own version, not the tool's, not
the version of the VDI schema this build ships.

A consumer parsing it had no way to notice a change. That is not hypothetical —
a whole `read` object was added to this output, and every existing consumer would
have seen new keys appear with nothing to key off. The first version number has
to arrive before there are consumers to break, because afterwards it costs a
migration rather than a field.
"""
import json
import re

import pytest

from conftest import CLEAN_DOCUMENT
from vdi2770_validate import __version__
from vdi2770_validate.cli import main
from vdi2770_validate.resources import schema_path


def run(capsys, argv):
    code = main(argv)
    return code, capsys.readouterr().out


def documents(capsys, *paths):
    _, out = run(capsys, ["check", "--json", *paths])
    return json.loads(out)


def test_every_document_carries_the_report_format_version(capsys):
    for doc in documents(capsys, str(CLEAN_DOCUMENT)):
        assert isinstance(doc.get("schemaVersion"), int), doc.keys()
        assert doc["schemaVersion"] >= 1


def test_every_document_names_the_tool_version_that_produced_it(capsys):
    """The ruleset is not separately versioned — `rules.json` ships inside the
    wheel and cannot be swapped without changing the install — so this field is
    also the answer to "which rules judged this"."""
    for doc in documents(capsys, str(CLEAN_DOCUMENT)):
        assert doc.get("toolVersion") == __version__, doc.get("toolVersion")


def test_every_document_names_the_vdi_schema_this_build_carries(capsys):
    """The schema this build ships, by its own version stamp. Deliberately not
    "what this run was checked against": `X0` and `X4` exist because the schema
    check can fail to run, and a field that claimed the check happened would be
    the kind of over-claim the rest of this report is built to avoid."""
    stamped = re.search(r'\sversion="(\d{4}-\d{2}-\d{2})"',
                        schema_path().read_text(encoding="utf-8"))
    assert stamped, "the bundled schema carries a dated version attribute"
    for doc in documents(capsys, str(CLEAN_DOCUMENT)):
        assert doc.get("vdiSchema") == stamped.group(1), doc.get("vdiSchema")


def test_a_path_this_tool_could_not_read_is_still_a_versioned_document(capsys,
                                                                       tmp_path):
    """That branch never builds a report, so it never passed through the
    renderer. A consumer iterating the run would have found some documents it
    could version-check and some it could not, which is worse than none."""
    missing = str(tmp_path / "not-here.zip")
    docs = documents(capsys, str(CLEAN_DOCUMENT), missing)
    assert len(docs) == 2
    bad = docs[1]
    assert bad.get("unreadable"), bad
    assert bad.get("schemaVersion") == docs[0]["schemaVersion"], bad
    assert bad.get("toolVersion") == __version__, bad


@pytest.mark.parametrize("quiet", [False, True])
def test_quiet_does_not_remove_the_version(capsys, quiet):
    """`--quiet` hides notes. It has already been caught deleting a statement
    this tool makes about itself, and this is another one."""
    argv = ["check", "--json", str(CLEAN_DOCUMENT)] + (["--quiet"] if quiet else [])
    _, out = run(capsys, argv)
    for doc in json.loads(out):
        assert doc.get("schemaVersion"), doc.keys()
