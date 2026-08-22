"""Access to bundled data files. Kept in one place so the zipapp build has a
single thing to get right."""
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
