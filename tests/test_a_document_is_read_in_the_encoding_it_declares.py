"""A metadata file is read in the encoding it declares.

XML 1.0 lets a document name its own encoding in its declaration (section 4.3.3)
and asks a processor to read it in that encoding -- or to stop, because bytes
that are not legal in the declared encoding are a fatal error. This reader
handed every document to expat, which reads UTF-8, UTF-16, ISO-8859-1 and
US-ASCII itself and is lent any codec that maps one byte to one character. A
document declaring an encoding that needs more than one byte for a character --
Shift_JIS, EUC-JP, EUC-KR, GB2312, Big5 -- was refused at that point, `multi-byte
encodings are not supported`, and the refusal was `X1`: the metadata file is not
well-formed XML. It was well-formed. The limit was this parser's, reported as the
sender's.

The condition this project set itself before 1.0 is held here as it is worded:
metadata in each encoding a declaration can name is read, and what the report
quotes from it comes back unchanged. And what the declaration says is still the
whole question: bytes that are not the encoding it names are still `X1`.
"""
from __future__ import annotations

import io
import json
import re
import zipfile

import pytest
from vdi2770_validate.runner import check_bytes

from conftest import CLEAN_DOCUMENT
from vdi2770_validate import report as rendering

META = "VDI2770_Metadata.xml"

#: A declaration's name for an encoding, the codec that writes it, and a class
#: name in the script it is for. The class name is wrong for the class id, so
#: `M3` quotes it -- which is the quotation this file holds to the original.
ENCODINGS = [
    ("UTF-8", "utf-8", "Technische Größe 技術"),
    ("UTF-16", "utf-16", "Technische Größe 技術"),
    ("ISO-8859-1", "latin-1", "Technische Größe"),
    ("ISO-8859-2", "iso8859-2", "Specyfikacja techniczna łódź"),
    ("ISO-8859-5", "iso8859-5", "Техническая спецификация"),
    ("ISO-8859-7", "iso8859-7", "Τεχνική προδιαγραφή"),
    ("ISO-8859-9", "iso8859-9", "Teknik şartname"),
    ("windows-1252", "cp1252", "Technische Größe €"),
    ("Shift_JIS", "shift_jis", "技術仕様書"),
    ("EUC-JP", "euc_jp", "技術仕様書"),
    ("ISO-2022-JP", "iso2022_jp", "技術仕様書"),
    ("EUC-KR", "euc_kr", "기술 사양서"),
    ("GB2312", "gb2312", "技术规格书"),
    ("GBK", "gbk", "技术规格书"),
    ("GB18030", "gb18030", "技术规格书"),
    ("Big5", "big5", "技術規格書"),
    ("HZ-GB-2312", "hz", "技术规格书"),
    ("UTF-7", "utf-7", "Technische Größe 技術"),
]

#: The encodings expat cannot read itself and that pyexpat could not lend it as
#: a table of one character per byte: the ones that take more than one byte for
#: a character, which were refused, and the ones whose escape sequences change
#: what the next bytes mean, which were read a byte at a time.
MULTI_BYTE = ["Shift_JIS", "EUC-JP", "ISO-2022-JP", "EUC-KR", "GB2312", "GBK", "GB18030", "Big5",
              "HZ-GB-2312", "UTF-7"]


def _metadata(declared: str, class_name: str) -> str:
    text = zipfile.ZipFile(CLEAN_DOCUMENT).read(META).decode("utf-8")
    assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>'), "the premise"
    text = text.replace('encoding="UTF-8"', f'encoding="{declared}"', 1)
    old = '<ClassName Language="de">Technische Spezifikation</ClassName>'
    assert text.count(old) == 1, "the premise"
    return text.replace(old, f'<ClassName Language="de">{class_name}</ClassName>')


def _container(metadata: bytes) -> bytes:
    base = zipfile.ZipFile(CLEAN_DOCUMENT)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name in base.namelist():
            z.writestr(name, metadata if name == META else base.read(name))
    return out.getvalue()


def _written(text: str, codec: str) -> bytes:
    """`text` in `codec`. A character the encoding has no bytes for -- the
    sample's own German, in a Japanese file -- is written as a character
    reference, which the document reads back as the same character."""
    return text.encode(codec, "xmlcharrefreplace")


def _findings(raw: bytes, name: str):
    said = json.loads(rendering.as_json(check_bytes(raw, name)))["findings"]
    return [(f["rule"], f["detail"], f["where"]["member"], f["where"]["line"], f["where"]["column"])
            for f in said]


@pytest.mark.parametrize("declared,codec,class_name", ENCODINGS, ids=[e[0] for e in ENCODINGS])
def test_each_encoding_a_declaration_names_is_read_and_quoted_back_unchanged(declared, codec, class_name):
    raw = _container(_written(_metadata(declared, class_name), codec))
    findings = _findings(raw, "declared.zip")
    rules = [f[0] for f in findings]
    assert "X1" not in rules, findings
    said = [f[1] for f in findings if f[0] == "M3"]
    assert said, f"the wrong class name drew no M3: {rules}"
    quoted = said[0].split("'")[1]
    # Spelled out where it could be mistaken for another script -- Cyrillic and
    # Greek letters that look Latin -- and read back to the same characters.
    assert _decoded(quoted) == class_name, (
        f"the report quotes {quoted!r}; the file says {class_name!r}")


@pytest.mark.parametrize("declared,codec,class_name", ENCODINGS, ids=[e[0] for e in ENCODINGS])
def test_the_verdict_is_the_one_the_same_document_gets_in_utf8(declared, codec, class_name):
    """Read without loss means read as the same document: the findings, their
    wording and their positions are the ones the same text draws in UTF-8."""
    same = _container(_metadata("UTF-8", class_name).encode("utf-8"))
    raw = _container(_written(_metadata(declared, class_name), codec))
    assert _findings(raw, "declared.zip") == _findings(same, "declared.zip")


#: A byte that is not legal where it stands, for each multi-byte encoding.
BROKEN = b"\xff"


@pytest.mark.parametrize("declared", MULTI_BYTE)
def test_bytes_that_are_not_the_declared_encoding_are_still_not_well_formed(declared):
    """The declaration decides how the bytes are read, so bytes it does not
    describe are a fatal error, as section 4.3.3 says -- `X1`, naming the
    encoding and where the bytes are. Nothing is replaced, and nothing past the
    parse is judged on a document that was not read."""
    codec, class_name = next((c, n) for d, c, n in ENCODINGS if d == declared)
    good = _written(_metadata(declared, class_name), codec)
    # Where the class name's text starts. The tag is ASCII in every one of
    # these; the text after it may begin with an escape sequence, or sit in a
    # run of base64, so it is not searched for.
    tag = b'<ClassName Language="de">'
    at = good.index(tag) + len(tag)
    bad = good[:at] + BROKEN + good[at:]
    with pytest.raises(UnicodeDecodeError):
        bad.decode(codec)
    findings = _findings(_container(bad), "broken.zip")
    x1 = [f for f in findings if f[0] == "X1"]
    assert x1, findings
    assert declared in x1[0][1], x1[0][1]
    # At the byte that was put there: the line, and the column counted in
    # characters, the way the parser counts every other position it reports.
    read = good.decode(codec)
    starts = read.index(tag.decode("ascii")) + len(tag)
    line = read.count("\n", 0, starts) + 1
    column = starts - (read.rfind("\n", 0, starts) + 1)
    assert (x1[0][3], x1[0][4]) == (line, column), x1[0]
    assert not [f for f in findings if f[0] in ("M3", "X2")], findings


def test_a_byte_order_mark_still_decides_against_a_declaration_that_disagrees():
    """A UTF-8 byte order mark in front of a declaration naming another
    encoding: the mark decides, as Appendix F reads it, and the disagreement
    is an error about the file, as it was."""
    raw = _container(b"\xef\xbb\xbf" + _metadata("Shift_JIS", "Technische Spezifikation").encode("utf-8"))
    assert "X1" in [f[0] for f in _findings(raw, "bom.zip")]


def test_a_name_for_one_of_pythons_own_transforms_is_not_read_through_it():
    """`unicode_escape` is a codec Python carries and no document is written in:
    read through it, a backslash sequence in the text would become markup. The
    name is one this reader does not use, as XML 1.0 lets a processor treat a
    name, and the document is read as it was before -- the backslashes are
    text."""
    import warnings

    from vdi2770 import xmlread

    # pyexpat builds its table by decoding every byte through the codec, and
    # this one warns about the `\\]` it meets on the way. That is how it read
    # such a document before as well, and it is not what this is about.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        tree = xmlread.parse(b'<?xml version="1.0" encoding="unicode_escape"?>'
                             b'<a>\\u003cb/\\u003e</a>')
    assert tree.text == "\\u003cb/\\u003e"


def test_the_library_reads_it_too():
    """`vdi2770.xmlread.parse` is a published door to the same reader."""
    from vdi2770 import xmlread

    tree = xmlread.parse(_written(_metadata("Shift_JIS", "技術仕様書"), "shift_jis"))
    names = [n for n in _walk(tree) if n.tag == "ClassName"]
    assert "技術仕様書" in [n.text for n in names]


def _decoded(rendered: str) -> str:
    """A rendering back to the characters it stands for, read here rather than
    by the reporting code whose output is being checked."""
    return re.sub(r"\\u([0-9a-fA-F]{4})|\\U([0-9a-fA-F]{8})",
                  lambda m: chr(int(m.group(1) or m.group(2), 16)), rendered)


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


#: A `<` that is not the byte 0x3C. mac-arabic has a byte of its own for it, and
#: UTF-7 can write any character, markup included, in base64.
HIDDEN_MARKUP = [("mac-arabic", b"\xbc"), ("UTF-7", b"+ADw-")]


@pytest.mark.parametrize("declared,lt", HIDDEN_MARKUP, ids=[h[0] for h in HIDDEN_MARKUP])
def test_a_document_is_charged_for_the_markup_it_holds_not_the_bytes_that_spell_it(
        declared, lt, monkeypatch):
    """The read is given a budget of elements across every document in it, and
    each document is charged before it is parsed, from what it holds. That was
    counted in the bytes, as `<`. Read in the encoding it declares, a document
    need not spell `<` with that byte, and one that does not would be charged
    nothing for its markup -- and parsed in full however many came before it.
    Charged from the text the parser is handed, it costs what it holds."""
    from vdi2770_validate import runner

    monkeypatch.setattr(runner, "MAX_TOTAL_ELEMENTS", 1_000)
    head = (f'<?xml version="1.0" encoding="{declared}"?>'
            f'<Document xmlns="http://www.vdi.de/schemas/vdi2770">').encode("ascii")
    body = head + (lt + b"a>") * 600 + (lt + b"/a>") * 600 + lt + b"/Document>"
    assert body.count(b"<") == 2, "the premise: the bytes show two `<`, the declaration's and the root's"
    plain = (b'<?xml version="1.0"?><Document xmlns="http://www.vdi.de/schemas/vdi2770">'
             b'<DocumentId DomainId="d">X</DocumentId></Document>')

    def zipped(members):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in members.items():
                z.writestr(name, data)
        return out.getvalue()

    archive = zipped({"VDI2770_Main.xml": plain, "VDI2770_Main.pdf": b"%PDF-1.4",
                      **{f"{i}.zip": zipped({META: body, "a.pdf": b"%PDF-1.4"}) for i in range(4)}})
    refused = [f for f in runner.check_bytes(archive, "budget.zip").findings if f.rule.id == "X6"]
    assert refused, "four documents of 600 elements each were parsed against a budget of 1,000"
