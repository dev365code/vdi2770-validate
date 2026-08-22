"""XML bytes -> a tree that remembers where every element was written.

We build our own node type rather than using ElementTree, for two reasons:
line numbers survive (ElementTree drops them), and the rules layer gets a
model it cannot use to inspect the serialisation.

Entity expansion is refused outright: a supplier archive must never be able to
make this process open a file or reach a host.
"""
from __future__ import annotations

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

    def path(self) -> str:
        parts, n = [], self
        while n is not None:
            parts.append(n.tag)
            n = n.parent
        return "/" + "/".join(reversed(parts))

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


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

    p.EntityDeclHandler = refuse_entity
    p.ExternalEntityRefHandler = refuse_external

    def start(name: str, attrs: Dict[str, str]) -> None:
        nonlocal root
        ns, _, local = name.rpartition("\x01")
        node = Node(tag=local, ns=ns, attrib=dict(attrs),
                    line=p.CurrentLineNumber, column=p.CurrentColumnNumber,
                    parent=stack[-1] if stack else None)
        if stack:
            stack[-1].children.append(node)
        else:
            root = node
        stack.append(node)

    def end(_name: str) -> None:
        stack.pop()

    def chars(data_: str) -> None:
        if stack:
            stack[-1].text += data_

    p.StartElementHandler = start
    p.EndElementHandler = end
    p.CharacterDataHandler = chars

    try:
        p.Parse(data, True)
    except expat.ExpatError as e:
        raise XmlError(expat.ErrorString(e.code), e.lineno, e.offset) from e

    if root is None:
        raise XmlError("the file contains no XML element", 1, 0)
    return root
