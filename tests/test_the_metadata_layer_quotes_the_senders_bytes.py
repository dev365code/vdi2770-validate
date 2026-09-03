"""A finding that quotes the file must quote the file.

`report._where` goes out of its way to keep an archive's own spelling for member
names, "which is what a reader needs to find it in their listing". The metadata
layer compares text through `nfc` -- rightly, because a published name and the
name in front of us can spell one word two legal ways -- and then printed what
it had normalised. So a report told a sender their class name was
`'Zeichnungen, Pläne'` when their file holds the decomposed spelling of those
bytes and a search for the quoted string finds nothing.

Worse than useless: the normalisation destroys the evidence. `escaped` spells a
name out only when it is not its own NFC, and `nfc()` has just made it one, so
the helper written to make two canonically equivalent spellings tell apart can
no longer see that there were two.
"""
from __future__ import annotations

import io
import unicodedata
import zipfile

from conftest import CLEAN_DOCUMENT
from vdi2770_validate.runner import check_bytes


def _with_metadata(text: str) -> bytes:
    base = zipfile.ZipFile(CLEAN_DOCUMENT)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in base.namelist():
            z.writestr(name, text if name == "VDI2770_Metadata.xml" else base.read(name))
    return buf.getvalue()


def _metadata() -> str:
    return zipfile.ZipFile(CLEAN_DOCUMENT).read(
        "VDI2770_Metadata.xml").decode("utf-8")


def test_a_class_name_is_quoted_as_the_sender_wrote_it():
    meta = _metadata()
    at = meta.index('<ClassName Language="de">')
    end = meta.index("</ClassName>", at)
    wrong = unicodedata.normalize("NFD", "Zeichnungen, Pläne")
    assert unicodedata.normalize("NFC", wrong) != wrong, "the premise"
    meta = meta[:at] + '<ClassName Language="de">' + wrong + meta[end:]

    report = check_bytes(_with_metadata(meta), "nfd.zip")
    said = [f for f in report.findings if f.rule.id == "M3"]
    assert said, sorted({f.rule.id for f in report.findings})
    quoted = (said[0].detail or "").split("'")[1]
    assert quoted in meta or quoted.encode("unicode_escape").decode() in meta, (
        f"the report quotes {quoted!r}, which is not in the file it read")


def test_a_class_id_that_ends_in_an_invisible_character_shows_it():
    """`U+3164 HANGUL FILLER` is a letter whose glyph is empty. Printed as
    itself, `M2` reads `ClassId '02-01'` — the very value the remedy then asks
    the sender to use, so the finding looks like a bug in this tool."""
    meta = _metadata()
    at = meta.index("<ClassId>")
    end = meta.index("</ClassId>", at)
    real = meta[at + len("<ClassId>"):end]
    meta = meta[:at] + "<ClassId>" + real + "ㅤ" + meta[end:]

    report = check_bytes(_with_metadata(meta), "filler.zip")
    said = [f for f in report.findings if f.rule.id == "M2"]
    assert said, sorted({f.rule.id for f in report.findings})
    detail = said[0].detail or ""
    assert "ㅤ" not in detail, (
        f"the invisible character reached the page as itself: {detail!r}")
    assert "3164" in detail, detail
