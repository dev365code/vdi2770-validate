"""Access to bundled data files, resolved in one place.

One import site for the bundled data, which `tools/check_wheel.py` checks
actually ships — and one place that decides *how* it is reached, which is the
half this module used to get wrong.

It resolved everything through `Path(__file__).parent / "data"` and read it with
`.read_text()`. That works from a directory on disk and from nowhere else: put
the package inside a zip and the path names something that is not a directory,
so `load_json` raises and `schema_stamp` — which catches `OSError` — answers
`None` and reports the build as carrying no schema at all. Quietly, and while
every other check passes.

So the data is read through `importlib.resources`, which asks the package how it
is packaged rather than assuming. `schema_path()` is gone: handing a caller a
real filesystem path is the assumption itself, and its one caller wanted the
text.
"""
from __future__ import annotations

import json
import re
from functools import cache
from typing import Optional

SCHEMA_FILE = "VDI2770_Schema_2019-08-23.xsd"


def _read(name: str) -> str:
    """One bundled file, however this package happens to be stored.

    `importlib.resources.files` is 3.9+, which is this project's floor.
    """
    from importlib.resources import files

    return (files(__package__) / "data" / name).read_text(encoding="utf-8")


@cache
def schema_text() -> str:
    """The bundled schema, as text.

    Text rather than a path because `xmlschema.XMLSchema` accepts either and
    only one of the two survives being zipped. The schema declares no `import`
    or `include`, so there is no base directory for a relative reference to be
    resolved against — checked, not assumed.
    """
    return _read(SCHEMA_FILE)


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

    The catch is narrow on purpose. It used to cover the case where the data was
    unreachable *because of how the package was stored*, which is not a missing
    schema and should never have read as one.
    """
    try:
        text = schema_text()
    except (OSError, FileNotFoundError, ModuleNotFoundError):
        return None
    stamped = re.search(r'\sversion="(\d{4}-\d{2}-\d{2})"', text)
    return stamped.group(1) if stamped else None


@cache
def load_json(name: str) -> dict:
    return json.loads(_read(name))
