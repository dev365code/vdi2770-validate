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

The condition this project set itself before 1.0 is held here, to the extent this
reader reads at all: metadata in each charset the IANA registry names and this
reader decodes is read, and what the report quotes from it comes back unchanged.
UCS-4 and the EBCDIC code pages are outside that, and a document in one is told
so. And what the declaration says is still the
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
    # NEC's row 13 is in Windows-31J and not in Shift_JIS, so the circled one
    # can only come back if the file was read as what it declares.
    ("Windows-31J", "cp932", "技術仕様書①"),
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
MULTI_BYTE = ["Shift_JIS", "Windows-31J", "EUC-JP", "ISO-2022-JP", "EUC-KR", "GB2312", "GBK", "GB18030", "Big5",
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


#: A byte that is not legal where it stands, for each multi-byte encoding. Not
#: 0xFF in Windows-31J, which gives that byte a character of the vendor's own;
#: there, a lead byte with nothing after it that it can lead.
BROKEN = {"Windows-31J": b"\x81\x20"}


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
    bad = good[:at] + BROKEN.get(declared, b"\xff") + good[at:]
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
    read through it, a backslash sequence in the text would become markup. No
    charset is registered under that name, so the document is not read at all,
    which is what XML 1.0 (4.3.3) makes of an encoding a processor does not
    read -- on every Python, where pyexpat used to lend expat a table built
    through the transform."""
    from vdi2770 import xmlread

    with pytest.raises(xmlread.XmlError) as refused:
        xmlread.parse(b'<?xml version="1.0" encoding="unicode_escape"?>'
                      b'<a>\\u003cb/\\u003e</a>')
    assert "unicode_escape" in refused.value.message


def _registered():
    from vdi2770 import xmlread

    return sorted(((name, codec) for codec, names in xmlread._REGISTERED.items() for name in names),
                  key=lambda pair: pair[0].lower())


@pytest.mark.parametrize("name,codec", _registered(), ids=[n for n, _ in _registered()])
def test_every_name_the_registry_gives_is_read_on_this_python(name, codec):
    """A name is read as the IANA charset registry registers it, and the same way
    on every Python: the names are this reader's, not the running Python's, and
    each is read here on whichever Python runs this -- each of the ones this
    package supports, in CI. A Python that lacked a codec the list names would
    fail here rather than read one document two ways."""
    from vdi2770 import xmlread

    tree = xmlread.parse(f'<?xml version="1.0" encoding="{name}"?>\n<a>read</a>'.encode(codec))
    assert tree.text == "read"


def test_the_registry_names_one_charset_once_and_only_names_a_declaration_can_hold():
    """Compared without regard to case, as XML 1.0 asks, no name may lead to two
    codecs. And each is one a declaration can be written with -- production 81,
    `EncName`, starts with a letter and has no colon -- so a registered name
    like `ISO_8859-1:1987` or `850`, which no well-formed declaration holds, is
    not one this list can be asked for."""
    from vdi2770 import xmlread

    seen = {}
    for codec, names in xmlread._REGISTERED.items():
        for name in names:
            assert re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]*", name), name
            assert seen.setdefault(name.lower(), codec) == codec, name


#: What the registry says and a Python's own table does not: `MS_Kanji` is an
#: alias of Shift_JIS, which some Pythons read as Windows-31J; ISO-8859-11 is
#: an alias of TIS-620; and windows-874, which no Python here knows by that
#: name, is the code page Python calls cp874.
REGISTRY_READS = [("Windows-31J", "cp932"), ("csWindows31J", "cp932"), ("MS_Kanji", "shift_jis"),
                  ("ISO-8859-11", "tis-620"), ("windows-874", "cp874"), ("ISO-8859-8-I", "iso8859-8")]


@pytest.mark.parametrize("name,codec", REGISTRY_READS, ids=[n for n, _ in REGISTRY_READS])
def test_a_registered_name_is_read_as_the_charset_registered_under_it(name, codec):
    from vdi2770 import xmlread

    assert {n.lower(): c for n, c in _registered()}[name.lower()] == codec
    assert xmlread._readable(f'<?xml version="1.0" encoding="{name}"?><a/>'.encode("ascii")) == (
        f'<?xml version="1.0" encoding="{name}"?><a/>')


#: Names a Python may know and the registry does not give a charset this reader
#: decodes: Python's own spellings, a private `x-` name, a transform, an EBCDIC
#: page, and UTF-32, which a declaration found as ASCII cannot be in.
UNREGISTERED = ["SJIS", "MS932", "cp932", "x-sjis", "cp1252", "latin_1", "unicode_escape",
                "mac-arabic", "IBM037", "UTF-32"]


@pytest.mark.parametrize("name", UNREGISTERED)
def test_a_name_the_registry_does_not_give_is_not_read_on_any_python(name):
    """`X1`, naming the encoding, on every Python -- where a document declaring
    `SJIS` was read on all of them and one declaring `Windows-31J` on some."""
    raw = _container(_metadata(name, "Technische Spezifikation").encode("ascii", "xmlcharrefreplace"))
    x1 = [f for f in _findings(raw, "unregistered.zip") if f[0] == "X1"]
    assert x1, f"a document declaring {name} was read"
    assert name in x1[0][1] and "IANA" in x1[0][1], x1[0][1]


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


#: A `<` that is not the byte 0x3C: UTF-7 can write any character, markup
#: included, in base64. (mac-arabic has a byte of its own for it, 0xBC, and is
#: not a name the registry gives, so a document declaring it is not read at all
#: -- see `UNREGISTERED`.)
HIDDEN_MARKUP = [("UTF-7", b"+ADw-")]


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


@pytest.mark.parametrize("mark,codec", [(b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be")],
                         ids=["UTF-16LE", "UTF-16BE"])
def test_a_document_expat_reads_in_utf16_is_charged_for_its_markup(mark, codec, monkeypatch):
    """expat reads UTF-16 itself, so such a document goes to it as bytes and is
    charged from them -- where every `<` is a 0x3C beside a zero. Nothing
    charged the UTF-16 path in particular, so leaving it out of the charge was a
    change no test saw: four documents, each with a valid declaration and body,
    would be parsed in full against a budget the first one spends."""
    from vdi2770_validate import runner

    monkeypatch.setattr(runner, "MAX_TOTAL_ELEMENTS", 1_000)
    text = ('<?xml version="1.0" encoding="UTF-16"?>'
            '<Document xmlns="http://www.vdi.de/schemas/vdi2770">'
            + "<a>" * 600 + "</a>" * 600 + "</Document>")
    body = mark + text.encode(codec)
    from vdi2770 import xmlread

    assert len(list(_walk(xmlread.parse(body)))) == 601, "the premise: expat reads it, all of it"
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
    assert refused, "four UTF-16 documents of 600 elements each were parsed against a budget of 1,000"


#: A document in UCS-4 or EBCDIC, told apart by its first bytes the way XML 1.0
#: (Appendix F) tells them apart before any declaration is read.
NOT_READ = [
    ("UCS-4, big-endian, with a mark", "UCS-4", b"\x00\x00\xfe\xff", "utf-32-be"),
    ("UCS-4, little-endian, with a mark", "UCS-4", b"\xff\xfe\x00\x00", "utf-32-le"),
    ("UCS-4, big-endian", "UCS-4", b"", "utf-32-be"),
    ("UCS-4, little-endian", "UCS-4", b"", "utf-32-le"),
    ("EBCDIC", "EBCDIC", b"", "cp037"),
]


@pytest.mark.parametrize("label,what,mark,codec", NOT_READ, ids=[n[0] for n in NOT_READ])
def test_a_document_in_an_encoding_this_reader_does_not_read_is_told_so(label, what, mark, codec):
    """`X1` either way -- this reader reads neither -- but saying so: the file is
    not malformed XML, it is XML in an encoding this reader does not read, and
    the report was saying the first and not the second."""
    declared = {"UCS-4": "UTF-32", "EBCDIC": "IBM037"}[what]
    text = _metadata(declared, "Technische Spezifikation")
    x1 = [f for f in _findings(_container(mark + text.encode(codec)), "unread.zip") if f[0] == "X1"]
    assert x1, f"a document in {label} drew no X1"
    assert what in x1[0][1] and "does not read" in x1[0][1], x1[0][1]


#: A byte order mark, the declaration that follows it, and what the file is in.
#: The mark settles the encoding before any declaration is read (Appendix F),
#: and the declaration still has to name the encoding the file is in (4.3.3).
MARKED = [
    ("UTF-8 mark, declared ISO-8859-1", b"\xef\xbb\xbf", "ISO-8859-1", "utf-8"),
    ("UTF-8 mark, declared windows-1252", b"\xef\xbb\xbf", "windows-1252", "utf-8"),
    ("UTF-8 mark, declared Shift_JIS", b"\xef\xbb\xbf", "Shift_JIS", "utf-8"),
    ("UTF-16LE mark, declared Shift_JIS", b"\xff\xfe", "Shift_JIS", "utf-16-le"),
    ("UTF-16BE mark, declared ISO-8859-1", b"\xfe\xff", "ISO-8859-1", "utf-16-be"),
]


@pytest.mark.parametrize("label,mark,declared,codec", MARKED, ids=[m[0] for m in MARKED])
def test_a_byte_order_mark_and_a_declaration_that_disagree_are_not_well_formed(label, mark, declared, codec):
    """A UTF-8 file with a mark that declared ISO-8859-1 -- an editor that saves
    as UTF-8 with a mark and leaves the old declaration in place makes one -- was
    read as ISO-8859-1, its German quoted back as `GrÃ¶Ã\x9fe`, and passed."""
    text = _metadata(declared, "Technische Größe")
    findings = _findings(_container(mark + text.encode(codec)), "marked.zip")
    x1 = [f for f in findings if f[0] == "X1"]
    assert x1, f"{label}: {findings}"
    assert declared in x1[0][1] and "byte order mark" in x1[0][1], x1[0][1]
    assert not [f for f in findings if f[0] == "M3"], findings


@pytest.mark.parametrize("mark,declared,codec", [(b"\xef\xbb\xbf", "UTF-8", "utf-8"),
                                                 (b"\xff\xfe", "UTF-16", "utf-16-le"),
                                                 (b"\xfe\xff", "UTF-16", "utf-16-be")],
                         ids=["UTF-8", "UTF-16LE", "UTF-16BE"])
def test_a_byte_order_mark_and_a_declaration_that_agree_are_read(mark, declared, codec):
    text = _metadata(declared, "Technische Größe")
    findings = _findings(_container(mark + text.encode(codec)), "marked.zip")
    assert "X1" not in [f[0] for f in findings], findings
    quoted = [f[1] for f in findings if f[0] == "M3"][0].split("'")[1]
    assert quoted == "Technische Größe", quoted


def test_half_of_a_character_is_not_read_as_one():
    """UTF-7 can spell half of a surrogate pair, and Python's decoder lets it
    through; no document holds one (production 2, `Char`). It is `X1` at the
    place it is written, naming the encoding -- where it was refused later, by
    the parser, at the first line, as an encoding this reader could not use."""
    good = _written(_metadata("UTF-7", "Technische Spezifikation"), "utf-7")
    tag = b'<ClassName Language="de">'
    at = good.index(tag) + len(tag)
    bad = good[:at] + b"+2AA-" + good[at:]
    x1 = [f for f in _findings(_container(bad), "half.zip") if f[0] == "X1"]
    assert x1 and "UTF-7" in x1[0][1], x1
    read = good.decode("utf-7")
    starts = read.index(tag.decode("ascii")) + len(tag)
    line = read.count("\n", 0, starts) + 1
    column = starts - (read.rfind("\n", 0, starts) + 1)
    assert (x1[0][3], x1[0][4]) == (line, column), x1[0]


def test_the_bytes_an_x1_names_are_a_few_not_a_run():
    """Inside a run of UTF-7's base64 the decoder reports the whole run as the
    bytes it could not read; a long one made a finding of hundreds of thousands
    of characters, most of them bytes that were fine. The finding names the
    first few and says there are more."""
    name = "Technische Spezifikation " + "技" * 5_000
    good = _written(_metadata("UTF-7", name), "utf-7")
    run = good.index(b"+", good.index(b'<ClassName Language="de">'))
    bad = good[:run + 4000] + b"\xff" + good[run + 4000:]
    x1 = [f for f in _findings(_container(bad), "run.zip") if f[0] == "X1"]
    assert x1 and len(x1[0][1]) < 200, len(x1[0][1]) if x1 else x1

