"""XML bytes -> a tree that remembers where every element was written.

We build our own node type rather than using ElementTree, for two reasons:
line numbers survive (ElementTree drops them), and the rules layer gets a
model it cannot use to inspect the serialisation.

Entity expansion is refused outright: a supplier archive must never be able to
make this process open a file or reach a host.
"""
from __future__ import annotations

import codecs
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union
from xml.parsers import expat

NS = "http://www.vdi.de/schemas/vdi2770"


class XmlError(Exception):
    def __init__(self, message: str, line: Optional[int] = None, column: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column


class UnsafeXml(XmlError):
    """The document tried to do something a data file has no business doing."""


class XmlTooLarge(XmlError):
    """The document is bigger than this reader will build a model of.

    Not the same statement as `XmlError`: the file is well-formed and this is our
    limit, not their mistake. The caller has to be able to tell those apart to
    report the right one.
    """


# The bytes were bounded and the tree built out of them was not, and the
# expansion between the two is what the sender chooses. A metadata member of
# 7.98 MB -- under `MIN_SUSPICIOUS_BYTES`, so the compression-ratio guard never
# looks at it, and under `MAX_METADATA_BYTES` -- holding 1.14 million nested
# elements compresses to a 115 KB archive and cost 952 MB, measured.
#
# The largest metadata file in this repository's corpus has 53 elements. This is
# roughly two thousand times that: generous for anything a plant will ever send,
# and finite. At the cap one tree costs about 92 MB, measured.
#
# Deliberately no depth limit. Depth was the obvious second axis and it earns
# nothing: `find_all` and `find` read one level, `domain.build` never recurses,
# and 99,999 nested elements parse in 0.11 s and 92 MB once the count is bounded
# -- the cost is per node either way. It would also take a real limit away from
# whoever reads this: the schema checker downstream gives up at about a thousand
# levels and says so, and refusing the document here first would replace that
# true statement with one about a limit invented to have one.
MAX_ELEMENTS = 100_000

# And the text hung off them, which the element cap says nothing about.
#
# The cost is in the *pieces*, not the length: expat calls back once per
# character reference, and each call is a transient `str` and a list slot. A
# document of three elements whose text is `&#120;` 450,000 times decodes to
# 450 KB of characters -- nothing -- and held 48 MB from a 4.1 KiB archive.
# Counting characters would have missed it entirely, which is why this counts
# what actually accumulates.
#
# The largest metadata file in this repository's corpus arrives in a few hundred
# pieces.
MAX_TEXT_PIECES = 200_000

# And the attributes hung off them, which neither of the two above says anything
# about. This is the third axis of one parse and it was the one nobody charged.
#
# It matters downstream rather than here: this parse is linear in attributes, but
# the schema check the validator runs afterwards is *quadratic in how many sit on
# a single element*. 12,000 of them, in a 27 KiB archive, cost 13.6 seconds --
# the same denial of service every other budget in this module exists to refuse,
# reached along the one axis that had no name.
#
# Two bounds, because the cost has two shapes and this reader has now learned
# three times that one bound cannot hold both: the per-element cap flattens the
# quadratic, and the total stops a sender from paying it once per element. At
# both caps exactly, a 0.80 MiB document costs 2.7 s end to end.
#
# Counted the way these budgets count -- expat is created with a namespace
# separator, so it never reports a namespace declaration as an attribute --
# every `VDI2770_*.xml` in this repository's corpus has at most three on one
# element and 49 in one document.
MAX_ATTRIBUTES_PER_ELEMENT = 128
MAX_ATTRIBUTES = 100_000


@dataclass
class Node:
    tag: str                       # local name, namespace stripped
    ns: str = ""
    attrib: Dict[str, str] = field(default_factory=dict)
    text: str = ""
    children: List[Node] = field(default_factory=list)
    line: int = 0
    column: int = 0
    parent: Optional[Node] = None

    # -- convenience accessors used by the domain builder -------------------
    # `Document` is not a name. `{http://www.vdi.de/schemas/vdi2770}Document` is,
    # and matching on the local name alone read an element from any vocabulary at
    # all as a VDI 2770 one. A `DocumentClassification` in somebody else's
    # namespace satisfied the rule that a document must carry a classification;
    # the German-name check issued a VDI 2770 verdict about it; and the schema
    # complaint walker, which counts children the way this does, disagreed with
    # `xmlschema` -- which counts by expanded name -- so one foreign sibling
    # shifted every position after it and a complaint named a line whose element
    # does not have the defect.
    #
    # `ns` was populated from the first commit and read by nobody. This is what
    # it is for. There is no escape hatch on purpose: this package reads one
    # vocabulary, and a caller wanting another one is not asking this package.
    def find_all(self, tag: str) -> List[Node]:
        return [c for c in self.children if c.tag == tag and c.ns == NS]

    def find(self, tag: str) -> Optional[Node]:
        for c in self.children:
            if c.tag == tag and c.ns == NS:
                return c
        return None

    def text_of(self, tag: str) -> str:
        n = self.find(tag)
        return n.text.strip() if n else ""

    def child_text(self, tag: str) -> Optional[str]:
        """Like `text_of`, but None when the element is absent rather than "".

        A caller that cannot tell those apart cannot tell "this value is wrong"
        from "there is no value", and will report the first when it means the
        second -- or, worse, treat a required-but-empty element as nothing to
        say, which is how an empty ClassId passed with no finding at all.
        """
        n = self.find(tag)
        return n.text.strip() if n else None


#: The encodings expat reads by itself, by the names it knows them by.
_EXPAT_READS = {"utf-8", "utf-16", "utf-16be", "utf-16le", "iso-8859-1", "us-ascii"}

#: The start of an XML declaration that names an encoding -- productions 23, 24,
#: 25, 26, 80 and 81 of XML 1.0 -- read off the bytes of a document whose first
#: characters are ASCII, as they are in every encoding a declaration can be
#: read in without knowing the encoding first. `EncName` is that production's
#: own alphabet.
_DECLARATION = re.compile(
    rb"<\?xml[ \t\r\n]+version[ \t\r\n]*=[ \t\r\n]*(?:\"1\.[0-9]+\"|'1\.[0-9]+')"
    rb"[ \t\r\n]+encoding[ \t\r\n]*=[ \t\r\n]*"
    rb"(?:\"([A-Za-z][A-Za-z0-9._-]*)\"|'([A-Za-z][A-Za-z0-9._-]*)')")

_LINE_BREAK = re.compile(r"\r\n|\r|\n")

#: Codecs Python carries that are not encodings a document is written in: its
#: own escape and domain-name transforms, and the two whose meaning is whatever
#: the machine's Windows code page is. A declaration naming one is a name this
#: reader does not use, which XML 1.0 (4.3.3) allows, and it is left to expat
#: exactly as before.
_NOT_FOR_DOCUMENTS = {"unicode-escape", "raw-unicode-escape", "idna", "punycode",
                      "undefined", "mbcs", "oem"}


def _readable(data: bytes) -> Union[bytes, str]:
    """The document as the parser is handed it: its bytes, or its text.

    expat reads UTF-8, UTF-16, ISO-8859-1 and US-ASCII itself, and a document in
    one of those -- or one that declares no encoding -- is handed over as the
    bytes it is. So is one that starts with a byte order mark: the declaration is
    looked for at the first byte, the mark settles the encoding before any
    declaration is read (Appendix F), and expat holds the declaration to it.

    For any other encoding a declaration names, pyexpat lends expat a table it
    builds by decoding each byte on its own, which is a reading only where every
    character is one byte and no byte changes how the next one reads. Where a
    character takes more than one, it refused -- Shift_JIS, EUC-KR, GB2312 and
    Big5 came back `multi-byte encodings are not supported`, a limit of this
    parser that reached the caller as the document's own malformation -- and
    ISO-2022-JP, whose escape sequences change what the bytes after them mean, it
    read a byte at a time, and wrongly.

    So the declared encoding is decoded here, by the codec Python has for that
    name, and strictly: bytes that are not legal in the declared encoding are
    the fatal error XML 1.0 (4.3.3) says they are, and nothing is replaced. The
    parser is then handed text, which it reads as the characters it holds
    whatever the declaration says -- so the declaration is applied once, here.
    A name nobody has a codec for -- or one whose codec is not of text, like
    `rot13` -- is handed on as bytes, and expat refuses it as it always has.
    """
    found = _DECLARATION.match(data)
    if not found:
        return data
    name = (found.group(1) or found.group(2)).decode("ascii")
    if name.lower() in _EXPAT_READS:
        return data
    try:
        codec = codecs.lookup(name).name
    except LookupError:
        return data
    if codec in _NOT_FOR_DOCUMENTS:
        return data
    try:
        return data.decode(codec)
    except LookupError:
        return data
    except UnicodeDecodeError as e:
        read = data[:e.start].decode(codec, "replace")     # only counted, for where
        breaks = list(_LINE_BREAK.finditer(read))
        line = len(breaks) + 1
        column = len(read) - (breaks[-1].end() if breaks else 0)
        raise XmlError(f"the document declares {name}, and the bytes here are not "
                       f"{name}: {data[e.start:e.end].hex(' ')}", line, column) from None
    except (UnicodeError, ValueError) as e:
        raise XmlError(f"the document declares {name}, and it cannot be read as "
                       f"{name}: {e}", 1, 0) from None


def _markup_charge(data: bytes) -> int:
    """The most elements `data` can make the parser build, counted from what the
    parser is handed -- before it is handed it.

    Every element has an opening `<`, so counting those bounds the cost of a
    parse whether it succeeds, refuses, or dies on a malformed token. Counted in
    the bytes where expat reads them itself; in the text where the document was
    decoded first, because there a `<` need not be the byte 0x3C -- mac-arabic
    has a byte of its own for it, and UTF-7 can write one in base64 -- and a
    count of bytes charged nothing for exactly the markup they do not show. A
    document whose bytes are not its declared encoding builds nothing.
    """
    try:
        source = _readable(data)
    except XmlError:
        return 0
    if isinstance(source, str):
        return source.count("<") - source.count("</")
    return source.count(b"<") - source.count(b"</")


def parse(data: bytes) -> Node:
    """Parse VDI 2770 metadata bytes. Raises XmlError with a line number."""
    source = _readable(data)
    root: Optional[Node] = None
    stack: List[Node] = []
    p = expat.ParserCreate(namespace_separator="\x01")

    def refuse_entity(*_args, **_kwargs):
        raise UnsafeXml("the document declares an entity; entity expansion is refused",
                        p.CurrentLineNumber, p.CurrentColumnNumber)

    def refuse_external(*_args, **_kwargs):
        raise UnsafeXml("the document references an external entity; this is refused",
                        p.CurrentLineNumber, p.CurrentColumnNumber)

    # Order matters, and it is worth writing down: expat calls EntityDeclHandler
    # for *any* entity declaration — internal, external or parameter — before the
    # entity is ever referenced, so in this configuration the external handler
    # below can never be reached. It is kept as the second line it would become
    # if the first were ever relaxed to allow harmless internal entities.
    # A DOCTYPE naming an external subset and nothing else fires neither handler;
    # expat does not fetch it, because parameter-entity parsing is off by default.
    p.EntityDeclHandler = refuse_entity
    p.ExternalEntityRefHandler = refuse_external

    built = 0

    def start(name: str, attrs: Dict[str, str]) -> None:
        nonlocal root, built, attributes
        built += 1
        if built > MAX_ELEMENTS:
            raise XmlTooLarge(
                f"the document has more than {MAX_ELEMENTS} elements; this reader "
                f"will not build a model that large",
                p.CurrentLineNumber, p.CurrentColumnNumber)
        if len(attrs) > MAX_ATTRIBUTES_PER_ELEMENT:
            raise XmlTooLarge(
                f"one element carries more than {MAX_ATTRIBUTES_PER_ELEMENT} "
                f"attributes; checking it against the schema costs time in "
                f"proportion to the square of that number",
                p.CurrentLineNumber, p.CurrentColumnNumber)
        attributes += len(attrs)
        if attributes > MAX_ATTRIBUTES:
            raise XmlTooLarge(
                f"the document carries more than {MAX_ATTRIBUTES} attributes; "
                f"this reader will not build a model that large",
                p.CurrentLineNumber, p.CurrentColumnNumber)
        ns, _, local = name.rpartition("\x01")
        node = Node(tag=local, ns=ns, attrib=dict(attrs),
                    line=p.CurrentLineNumber, column=p.CurrentColumnNumber,
                    parent=stack[-1] if stack else None)
        if stack:
            stack[-1].children.append(node)
        else:
            root = node
        stack.append(node)

    # Text arrives in as many callbacks as expat feels like, and `&#120;` forces
    # one per reference. `node.text += chunk` is quadratic through an attribute
    # -- CPython's in-place-append shortcut needs a refcount-1 local and never
    # gets one here -- so a metadata file of character references cost sixty
    # seconds for a 198 KB archive, with a clean verdict. Collected per open
    # element and joined once, which is linear; the dict holds only the elements
    # currently open, so it is O(depth).
    chunks: Dict[int, List[str]] = {}

    def end(_name: str) -> None:
        node = stack.pop()
        parts = chunks.pop(id(node), None)
        if parts:
            node.text = "".join(parts)

    pieces = 0
    attributes = 0

    def chars(data_: str) -> None:
        nonlocal pieces
        if not stack:
            return
        pieces += 1
        if pieces > MAX_TEXT_PIECES:
            raise XmlTooLarge(
                f"the document's text arrives in more than {MAX_TEXT_PIECES} "
                f"pieces; this reader will not hold that many",
                p.CurrentLineNumber, p.CurrentColumnNumber)
        chunks.setdefault(id(stack[-1]), []).append(data_)

    p.StartElementHandler = start
    p.EndElementHandler = end
    p.CharacterDataHandler = chars

    try:
        p.Parse(source, True)
    except XmlError:
        # `UnsafeXml` and `XmlTooLarge` are raised from inside the handlers and
        # travel out through `Parse`. Re-raising them unchanged keeps the
        # distinction the caller needs; catching `ExpatError` alone let one of
        # them arrive as a bare handler exception once.
        raise
    except expat.ExpatError as e:
        raise XmlError(expat.ErrorString(e.code), e.lineno, e.offset) from e
    except (LookupError, ValueError) as e:
        # expat resolves the encoding declaration through the codec registry, and
        # neither "no such encoding" (LookupError) nor "this parser will not
        # decode that one" (ValueError) is an ExpatError. Both escaped, so a
        # caller catching XmlError -- the whole contract of this module -- saw a
        # document that declares a nonexistent encoding as an unexpected crash,
        # and was told nothing in the container needed changing.
        # Name what the document declared. Python says "multi-byte encodings are
        # not supported" without saying which one, and a reader of the report has
        # only our sentence to go on.
        declared = re.search(rb'encoding\s*=\s*["\']([^"\']{1,64})["\']', data[:256])
        which = declared.group(1).decode("ascii", "replace") if declared else "the one declared"
        raise XmlError(f"the document declares an encoding this parser cannot use "
                       f"({which}): {e}", p.CurrentLineNumber, p.CurrentColumnNumber) from e

    if root is None:
        raise XmlError("the file contains no XML element", 1, 0)
    return root
