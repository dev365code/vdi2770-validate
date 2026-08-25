"""Validate metadata against the schema VDI publishes, and put a line number on
every complaint.

xmlschema reports an XPath but no line, because ElementTree throws lines away.
We already parsed the document ourselves and kept the lines, so we walk the
reported path through our own tree to recover the position.
"""
from __future__ import annotations

import io
import re
from itertools import islice
from typing import List, Optional

from vdi2770.xmlread import Node

from .resources import schema_path

_SEG = re.compile(r"^(?:\{(?P<ns>[^}]*)\})?(?P<tag>[^\[/]+)(?:\[(?P<idx>\d+)\])?$")


#: Schema complaints we will walk through the document. `xmlschema.iter_errors`
#: is super-linear on its own and `_resolve` was quadratic on top of it: 410 KB
#: of metadata with 16,000 violations cost 29 seconds, and `MAX_METADATA_BYTES`
#: admits forty times that. The report lists at most a hundred of one rule
#: anyway; past this the only thing another error buys is time.
MAX_SCHEMA_ERRORS = 1_000


def _first_line(text: str) -> str:
    """The first non-blank line, or empty.

    `"".strip().splitlines()` is `[]`, so subscripting it raised `IndexError`
    *inside* the handler whose comment reads "hostile input, any failure" —
    `MemoryError()` carries no args, and so does any bare `raise SomeError()`.
    The run survived because the runner catches it, and told the reader about
    this tool's internals instead of the true diagnosis.
    """
    lines = (text or "").strip().splitlines()
    return lines[0] if lines else ""


def _rendered(errors, tree: Node) -> List[dict]:
    """One dict per complaint, each with the line our own tree remembers."""
    kids_of: dict = {}
    out: List[dict] = []
    for err in errors:
        path = getattr(err, "path", "") or ""
        node = _resolve(tree, path, kids_of) if path else None
        reason = _first_line(getattr(err, "reason", None) or str(err)) or repr(err)
        out.append({
            "line": node.line if node else None,
            "column": node.column if node else None,
            "path": path,
            "reason": reason[:300],
        })
    return out


def _one_line(e: BaseException) -> str:
    return f"{type(e).__name__}: {_first_line(str(e))[:200]}".rstrip(": ")


def _resolve(root: Node, path: str, kids_of=None) -> Optional[Node]:
    """Walk an XPath through our own tree to recover a line number.

    `kids_of` is a cache keyed on (parent identity, tag). Without it this
    rebuilds the whole sibling list once per error to index one of them, which
    is quadratic in the number of errors over one parent — 38 % of the 29
    seconds above, and entirely ours.
    """
    def children(node, tag):
        if kids_of is None:
            return node.find_all(tag)
        key = (id(node), tag)
        if key not in kids_of:
            kids_of[key] = node.find_all(tag)
        return kids_of[key]

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
        kids = children(node, m.group("tag"))
        i = int(m.group("idx") or 1) - 1
        # `[0]` would give -1, which passes an upper-bound-only test and returns
        # the *last* child — a schema complaint carrying a confidently wrong line.
        if not 0 <= i < len(kids):
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
    except Exception as e:                       # noqa: BLE001 - any failure is ours
        return [{"broken": "install", "line": None, "column": None, "path": "",
                 "reason": f"the bundled schema could not be loaded: {e}"}]

    out: List[dict] = []
    try:
        # Hand it the bytes, not a decoded string: the document declares its own
        # encoding and decoding it as UTF-8 "with replacement" silently hands the
        # schema a different document than the one the model layer read.
        # `islice`, not `list`: the generator is bounded here rather than
        # materialised and then thrown away by the report's listing cap.
        errors = []
        for err in islice(schema.iter_errors(io.BytesIO(data)), MAX_SCHEMA_ERRORS + 1):
            # Appended one at a time so a crash part-way keeps what came before.
            # `list(...)` threw the whole generator away, and the reader was told
            # only "we gave up" — while `runner._into`, three files along, states
            # the opposite policy: "the findings it managed to produce before
            # crashing are kept. They are as true as they were going to be."
            errors.append(err)
    except Exception as e:                      # noqa: BLE001 - hostile input, any failure
        # The comment above says it: this is the document's doing, not ours. It
        # shared a flag with the branch above and was reported as a broken
        # installation, so a container nested a thousand levels deep was told to
        # re-install the tool.
        partial = _rendered(errors, tree)
        partial.append({"broken": "document", "line": None, "column": None, "path": "",
                        "reason": "the schema check could not complete: " + _one_line(e)})
        return partial
    stopped = len(errors) > MAX_SCHEMA_ERRORS
    if stopped:
        errors = errors[:MAX_SCHEMA_ERRORS]

    out = _rendered(errors, tree)
    if stopped:
        # `broken: document` is the flag the rules layer reads to say the check
        # could not finish. A truncated check that said nothing would leave the
        # reader taking the count as the document's error count, which is the
        # quieter-verdict failure in another costume.
        out.append({"broken": "document", "line": None, "column": None, "path": "",
                    "reason": f"the schema check stopped after {MAX_SCHEMA_ERRORS} "
                              f"violations; there are more"})
    return out
