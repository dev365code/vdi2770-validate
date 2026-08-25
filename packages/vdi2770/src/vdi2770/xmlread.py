"""XML bytes -> a tree that remembers where every element was written.

We build our own node type rather than using ElementTree, for two reasons:
line numbers survive (ElementTree drops them), and the rules layer gets a
model it cannot use to inspect the serialisation.

Entity expansion is refused outright: a supplier archive must never be able to
make this process open a file or reach a host.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional
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
# document of three elements whose text is `&#120;` 1.3 million times decodes to
# 1.3 MB of characters -- nothing -- and cost 287 MB from a 4.2 KiB archive.
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
# both caps exactly, a 0.8 MiB document costs 1.25 s end to end.
#
# Measured over every metadata file in this repository's corpus: the worst
# element carries three attributes and the worst document fifty-one.
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
    def find_all(self, tag: str) -> List[Node]:
        return [c for c in self.children if c.tag == tag]

    def find(self, tag: str) -> Optional[Node]:
        for c in self.children:
            if c.tag == tag:
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


def parse(data: bytes) -> Node:
    """Parse VDI 2770 metadata bytes. Raises XmlError with a line number."""
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
        p.Parse(data, True)
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
