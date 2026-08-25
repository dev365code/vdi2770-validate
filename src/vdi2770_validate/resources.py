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
from functools import cache
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
SCHEMA_FILE = "VDI2770_Schema_2019-08-23.xsd"


def schema_path() -> Path:
    return DATA / SCHEMA_FILE


@cache
def load_json(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))
