"""Access to bundled data files, resolved in one place.

The reason written here used to be "so the zipapp build has a single thing
to get right", and there is no zipapp build -- the only mention of one in
this repository was that sentence. It could not survive one either: the
data is resolved as a filesystem path and read with `.read_text()`, and
`schema_path()` hands a caller a real path, none of which works inside a
zip. The real reason is smaller and true: one import site for the bundled
data, which `tools/check_wheel.py` checks actually ships.
"""
from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Optional

DATA = Path(__file__).resolve().parent / "data"
SCHEMA_FILE = "VDI2770_Schema_2019-08-23.xsd"


def schema_path() -> Path:
    return DATA / SCHEMA_FILE


@cache
def schema_stamp() -> Optional[str]:
    """The version the bundled schema stamps on itself, read from the file
    rather than from its name so the two cannot drift apart unnoticed.

    Named for what it is — a property of this build — and not "the version this
    run was checked against". `X0` and `X4` exist because the schema check can
    fail to run, and a field that implied it had run would be the over-claim the
    rest of this report is built to avoid. `None` when there is no schema to
    read, which is the same condition `X0` reports: a document that named a
    version it could not find would be worse than one that says there is none.
    """
    try:
        text = schema_path().read_text(encoding="utf-8")
    except OSError:
        return None
    stamped = re.search(r'\sversion="(\d{4}-\d{2}-\d{2})"', text)
    return stamped.group(1) if stamped else None


@cache
def load_json(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))
