"""Validate metadata against the schema VDI publishes, and put a line number on
every complaint.

xmlschema reports an XPath but no line, because ElementTree throws lines away.
We already parsed the document ourselves and kept the lines, so we walk the
reported path through our own tree to recover the position.
"""
from __future__ import annotations

import re
from typing import List, Optional

from ..resources import schema_path
from .xmlread import Node

_SEG = re.compile(r"^(?:\{(?P<ns>[^}]*)\})?(?P<tag>[^\[/]+)(?:\[(?P<idx>\d+)\])?$")


def _resolve(root: Node, path: str) -> Optional[Node]:
    segs = [s for s in path.split("/") if s]
    node = root
    if not segs:
        return None
    first = _SEG.match(segs[0])
    if not first or first.group("tag") != root.tag:
        return None
    for seg in segs[1:]:
        m = _SEG.match(seg)
        if not m:
            return None
        kids = node.find_all(m.group("tag"))
        i = int(m.group("idx") or 1) - 1
        if i >= len(kids):
            return None
        node = kids[i]
    return node


def _schema():
    import xmlschema  # imported lazily so `--version` works without it
    return xmlschema.XMLSchema(str(schema_path()))


def validate(data: bytes, tree: Node) -> List[dict]:
    """Return one dict per schema complaint: {line, column, path, reason}."""
    try:
        schema = _schema()
    except Exception as e:                       # pragma: no cover - build error
        return [{"line": None, "column": None, "path": "", "reason": f"cannot load bundled schema: {e}"}]

    out: List[dict] = []
    for err in schema.iter_errors(data.decode("utf-8", "replace")):
        path = getattr(err, "path", "") or ""
        node = _resolve(tree, path) if path else None
        reason = (getattr(err, "reason", None) or str(err)).strip().splitlines()[0]
        out.append({
            "line": node.line if node else None,
            "column": node.column if node else None,
            "path": path,
            "reason": reason[:300],
        })
    return out
