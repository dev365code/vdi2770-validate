"""The rules page says, under `Z1`, that some of its reasons are this reader
declining a structure the ZIP specification allows -- an archive split across
several files, a zip64 end record carrying extensible data -- and it quotes the
finding's own words for each. A quotation is a claim about another text, and
the text it quotes is this reader's: so each quoted phrase has to be what the
reader says of that very shape, built here by the end-record builder the
fixtures use. If the reader's sentence changes, the page has to change with it.
"""
import sys
import zipfile

from vdi2770_validate.runner import check_bytes

from conftest import CLEAN_DOCUMENT, ROOT

sys.path.insert(0, str(ROOT / "tools"))
import archive_ends as ENDS  # noqa: E402 - after sys.path
import rules_doc  # noqa: E402 - after sys.path

SPLIT = "this reader reads an archive that is one file"
EXTENSIBLE = "which this reader does not read"


def _plain():
    with zipfile.ZipFile(CLEAN_DOCUMENT) as z:
        return ENDS.plain({i.filename: z.read(i) for i in z.infolist()})


def _z1_details(data):
    return [f.detail or "" for f in check_bytes(data, "end.zip").findings if f.rule.id == "Z1"]


def test_the_page_quotes_both_phrases_under_z1():
    note = rules_doc.NOTES["Z1"]
    assert f'"{SPLIT}"' in note and f'"{EXTENSIBLE}"' in note
    page = (ROOT / "docs" / "rules.md").read_text(encoding="utf-8")
    z1 = page.split("### `Z1`", 1)[1].split("\n### ", 1)[0]
    assert note in z1


def test_a_split_archive_draws_the_quoted_words():
    details = _z1_details(ENDS.end(_plain(), disk=1))
    assert details and any(SPLIT in d for d in details), details


def test_extensible_data_draws_the_quoted_words():
    details = _z1_details(ENDS.zip64(_plain(), size=44 + len(ENDS.EXTENSIBLE), extensible=ENDS.EXTENSIBLE))
    assert details and any(EXTENSIBLE in d for d in details), details
