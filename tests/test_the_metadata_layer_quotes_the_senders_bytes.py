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
import re
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
    assert _decoded(quoted) in meta, (
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


def _decoded(rendered: str) -> str:
    """A rendering back to the characters it stands for.

    Written out here rather than borrowed from the module under test: a check
    that a report can be read back is worth nothing if it is the reporting code
    that reads it.
    """
    return re.sub(r"\\u([0-9a-fA-F]{4})|\\U([0-9a-fA-F]{8})",
                  lambda m: chr(int(m.group(1) or m.group(2), 16)), rendered)


def test_a_homoglyph_survives_the_senders_own_spelling_being_quoted():
    """Quoting the sender's bytes must not blind the comparison that spells.

    `told_apart` aligns two strings position by position and gives up when the
    lengths differ, which is what quoting the un-normalised spelling made
    happen: a class name holding both a decomposed umlaut and a Cyrillic `e`
    came out as two lines nobody can tell apart -- the exact failure that helper
    exists to prevent. `escaped` handles it: a name that is not its own NFC has
    every character outside ASCII spelled out, and a Cyrillic one is outside it.

    Class 02-02, because its published German name is one of the two that carry
    a character NFD takes apart. A class whose name is all ASCII cannot
    reproduce this: the lengths never disagree and `told_apart` never gives up.
    """
    cyrillic_e = chr(0x435)
    meta = _metadata()
    meta = _at_class(meta, "02-02")
    at = meta.index('<ClassName Language="de">')
    end = meta.index("</ClassName>", at)
    wrong = unicodedata.normalize("NFD", "Zeichnungen, Pl\u00e4ne").replace(
        "e", cyrillic_e, 1)
    assert len(wrong) != len("Zeichnungen, Pl\u00e4ne"), "the premise: lengths differ"
    meta = meta[:at] + '<ClassName Language="de">' + wrong + meta[end:]

    report = check_bytes(_with_metadata(meta), "twins.zip")
    said = [f for f in report.findings if f.rule.id == "M3"]
    assert said, sorted({f.rule.id for f in report.findings})
    detail = said[0].detail or ""
    assert cyrillic_e not in detail, (
        f"a Cyrillic letter reached the page as a Latin one: {detail!r}")
    assert _decoded(detail.split("'")[1]) in meta, detail


def test_a_language_tag_that_is_not_ascii_shows_which_character_is_not():
    """`M8` says a tag is one this tool does not check. With a Cyrillic `e` in
    `en` it read *is tagged 'en', which this tool does not check*, which is
    nonsense on its face -- and unlike a class name there is no published
    counterpart to align against, so only spelling it out can help."""
    cyrillic_e = chr(0x435)
    meta = _metadata()
    at = meta.index('<ClassName Language="de">')
    meta = (meta[:at] + f'<ClassName Language="{cyrillic_e}n">x</ClassName>'
            + meta[at:])

    report = check_bytes(_with_metadata(meta), "tag.zip")
    said = [f for f in report.findings if f.rule.id == "M8"]
    assert said, sorted({f.rule.id for f in report.findings})
    assert cyrillic_e not in (said[0].detail or ""), said[0].detail


def _at_class(meta: str, class_id: str) -> str:
    at = meta.index("<ClassId>")
    end = meta.index("</ClassId>", at)
    return meta[:at] + "<ClassId>" + class_id + meta[end:]
