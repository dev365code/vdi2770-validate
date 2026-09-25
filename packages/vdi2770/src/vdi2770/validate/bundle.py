"""The diagnostic bundle: what one run of `check` looked like, for a person to
read and, if they choose, attach to an issue -- and nothing from the files it
read.

Nothing here opens a socket or sends anything. The bundle is a file on the
machine that ran the check, written after it has been shown. It carries
structure, counts, sizes, hashes and rule codes. It does not carry a member's
name, a path, a value or identifier from the metadata, a finding's message,
detail or remedy, a byte of a PDF or of the XML, a ZIP comment or what an extra
field holds, an environment variable's value, or a user or host name. Two
entries with one name are told apart by the index of the first of them, not by
the name or a hash of it: a hash of a name that can be guessed can be checked
against the guess.

The layout is the one the fleet's bundle schema gives, version 1, and the same
input run by the same release gives the same bytes: there is no clock in it.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import math
import os
import platform
import stat
import sys
import traceback
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

from vdi2770 import zipread

TOOL = "vdi2770-validate"
SCHEMA = 1
#: The whole file, so that it can be carried out of a closed network on anything.
LIMIT = 256 * 1024
#: Members listed one by one; past this, only how many there were.
ROWS = 5000
#: The environment variables this tool reads, by name. Their values are not taken.
ENVIRONMENT = ("PYTHONIOENCODING", "PYTHONUTF8", "NO_COLOR")
#: What a file kind is told by, and nothing else from its name.
KINDS = {".pdf": "pdf", ".xml": "xml", ".json": "json"}
#: A person's own sentence is kept, up to this many characters.
NOTE_LIMIT = 2000
#: Inputs named in `argv`, one place-holder each; past this, how many more.
INPUTS_SHOWN = 10
#: What each member row holds, in order: one short array per member.
ROW_FIELDS = ["i", "size", "csize", "method", "flagBits", "nameLen", "sameNameAs",
              "sameFoldedNameAs", "extraIds", "utf8Flag"]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _extra_ids(extra: bytes) -> List[int]:
    """The header ids of a member's extra field, and not what they hold."""
    ids, at = [], 0
    while at + 4 <= len(extra):
        header, size = int.from_bytes(extra[at:at + 2], "little"), int.from_bytes(extra[at + 2:at + 4], "little")
        ids.append(header)
        at += 4 + size
    return ids


def _members(zf: zipfile.ZipFile) -> Dict:
    infos = zf.infolist()
    first_name: Dict[str, int] = {}
    first_folded: Dict[str, int] = {}
    rows = []
    for i, info in enumerate(infos[:ROWS]):
        name = info.filename
        same = first_name.setdefault(name, i)
        same_folded = first_folded.setdefault(name.casefold(), i)
        rows.append([i, info.file_size, info.compress_size, info.compress_type,
                     info.flag_bits, len(name), same if same != i else None,
                     same_folded if same_folded != i and same == i else None,
                     _extra_ids(info.extra), bool(info.flag_bits & 0x800)])
    kinds = {"pdf": 0, "xml": 0, "json": 0, "other": 0}
    inside = 0
    for info in infos:
        suffix = os.path.splitext(info.filename.lower())[1]
        kinds[KINDS.get(suffix, "other")] += 1
        inside += suffix == ".zip"
    return {"members": {"count": len(infos), "listed": len(rows), "rowFields": ROW_FIELDS,
                        "rows": rows},
            "containersInside": inside, "fileKinds": kinds}


def _depth(container) -> int:
    return max([container.depth] + [_depth(c) for c in container.children])


def _nothing(kind: str, size=None, sha256=None) -> Dict:
    return {"kind": kind, "size": size, "sha256": sha256, "depth": 0,
            "members": {"count": 0, "listed": 0, "rowFields": ROW_FIELDS, "rows": []},
            "containersInside": 0, "fileKinds": {"pdf": 0, "xml": 0, "json": 0, "other": 0}}


def fingerprint(path: str) -> Dict:
    """The shape of what was given: size and hash, and for an archive what its
    directory lists -- sizes, methods and flags, never a name. Only a regular
    file is read again: a pipe was read once by the run, and opening it a
    second time waits for a writer that is gone."""
    try:
        given = os.stat(path)
    except OSError:
        return _nothing("file")
    if stat.S_ISDIR(given.st_mode):
        return _nothing("dir")
    if not stat.S_ISREG(given.st_mode):
        return _nothing("stream")
    try:
        data = Path(path).read_bytes()
    except OSError:
        return _nothing("file")
    # What is read again has to be what the file says it holds. A descriptor's
    # name -- `/dev/stdin`, `/dev/fd/0` -- stats as the regular file behind it,
    # and on macOS and the BSDs opening it again shares the offset the run left
    # at the end: the read comes back empty, and a bundle saying 0 bytes
    # describes a file nobody gave.
    if len(data) != given.st_size:
        return _nothing("stream")
    shape = _nothing("file", len(data), _sha256(data))
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            shape.update(_members(zf), kind="zip")
    except Exception:                       # noqa: BLE001 -- not an archive, or not one zipfile lists
        return shape
    # How deep containers nest, from the reader's own tree -- for an archive
    # small enough to list whole; past that the run has already said what it
    # could, and reading it all again to count levels is the cost it bounded.
    # The reader's own failure on this file is the run's to report, not this.
    if shape["members"]["count"] <= ROWS:
        with contextlib.suppress(Exception):
            shape["depth"] = _depth(zipread.read(data, "input"))
    return shape


def _where_kind(where) -> str:
    if isinstance(where, dict):
        if where.get("line") is not None:
            return "line"
        if where.get("member") is not None:
            return "member"
    return "none"


def outcome(report: Optional[Dict], exit_code: int, seconds: float) -> Dict:
    """What the run said, by rule code and count; no finding's words."""
    findings: Dict[str, Dict] = {}
    for f in (report or {}).get("findings", []):
        slot = findings.setdefault(f["rule"], {"severity": f["severity"], "count": 0,
                                               "whereKinds": {"member": 0, "line": 0, "none": 0}})
        slot["count"] += 1
        slot["whereKinds"][_where_kind(f.get("where"))] += 1
    read = (report or {}).get("read", {})
    archives, metadata = read.get("archives", {}), read.get("metadataFiles", {})
    stopped = [s["rule"] for s in (report or {}).get("listingStopped", [])]
    return {
        "exitCode": exit_code,
        # Whole seconds, rounded up: how long, and no clock -- a run that takes
        # a fraction of a second says 1 every time, so the bundle stays the same bytes.
        "wallSeconds": math.ceil(seconds),
        "findings": findings,
        "summary": dict((report or {}).get("summary", {})),
        "notListed": sum(n["count"] for n in (report or {}).get("notListed", [])),
        "scopeNotExamined": ((archives.get("found", 0) - archives.get("opened", 0))
                             + (metadata.get("found", 0) - metadata.get("read", 0))),
        "rulesNotAsked": sum(1 for f in (report or {}).get("findings", []) if f.get("about") == "tool"),
        "budgets": {"hit": sorted(set(stopped))},
    }


def failure(exc: BaseException) -> Dict:
    """The type, and the frames inside this package: file, line and function,
    which are public code. The message is not taken -- it quotes values -- only
    its hash, so that two bundles from one defect can be told to be one."""
    here = Path(__file__).resolve().parent.parent
    frames = []
    for frame in traceback.extract_tb(exc.__traceback__):
        try:
            rel = Path(frame.filename).resolve().relative_to(here)
        except ValueError:
            continue
        frames.append({"file": rel.as_posix(), "line": frame.lineno, "func": frame.name})
    return {"type": type(exc).__name__, "tracebackFrames": frames,
            "messageSha256": _sha256(str(exc).encode("utf-8", "replace"))}


def invocation(options: List[str], inputs: int, note: bool, out: bool) -> Dict:
    """What was asked for, rebuilt from the parsed options rather than copied
    from the command line: option names and the values they choose from, and a
    place-holder wherever a path or a sentence of the user's stood. Copied, a
    path written as `--bundle-out=DIR` or an option cut short came through
    whole."""
    shown = ["check", *sorted(options)]
    if note:
        shown += ["--note", "<note>"]
    if out:
        shown += ["--bundle-out", "<out-1>"]
    shown += [f"<input-{n}>" for n in range(1, min(inputs, INPUTS_SHOWN) + 1)]
    if inputs > INPUTS_SHOWN:
        shown.append(f"<{inputs - INPUTS_SHOWN} more inputs>")
    return {"argv": shown, "env": sorted(name for name in ENVIRONMENT if name in os.environ)}


def build(*, path: str, options: List[str], inputs: int, report: Optional[Dict],
          exit_code: int, seconds: float, trigger: str, note: Optional[str] = None,
          out: Optional[str] = None, error: Optional[BaseException] = None) -> Dict:
    from . import __version__
    bundle = {
        "bundle": {
            "bundleSchema": SCHEMA, "tool": TOOL, "toolVersion": __version__,
            "engine": {"name": "vdi2770", "version": __version__},
            "python": {"version": platform.python_version(),
                       "implementation": platform.python_implementation()},
            "platform": {"system": platform.system(), "release": platform.release(),
                         "machine": platform.machine()},
            "console": {"encoding": getattr(sys.stdout, "encoding", None) or ""},
            "trigger": trigger,
        },
        "invocation": invocation(options, inputs, note is not None, out is not None),
        "input": fingerprint(path),
        "run": outcome(report, exit_code, seconds),
    }
    if error is not None:
        bundle["error"] = failure(error)
    if note:
        note = _as_text(note)
        kept = note if len(note) <= NOTE_LIMIT else (
            note[:NOTE_LIMIT] + f" [cut at {NOTE_LIMIT:,} characters]")
        bundle["user"] = {"note": kept}
    bundle["readable"] = readable(bundle)
    return _within_limit(bundle)


def readable(bundle: Dict) -> str:
    run, shape = bundle["run"], bundle["input"]
    fired = ", ".join(f"{rule} x{slot['count']}" for rule, slot in sorted(run["findings"].items())) or "none"
    lines = [
        f"{bundle['bundle']['tool']} {bundle['bundle']['toolVersion']} on Python "
        f"{bundle['bundle']['python']['version']} ({bundle['bundle']['platform']['system']}), "
        f"trigger: {bundle['bundle']['trigger']}",
        f"input: {shape['kind']}, {shape['size']} bytes, {shape['members']['count']} members, depth {shape['depth']}",
        f"exit code {run['exitCode']}; findings: {fired}",
        f"not listed: {run['notListed']}; not examined: {run['scopeNotExamined']}; "
        f"budgets hit: {', '.join(run['budgets']['hit']) or 'none'}",
    ]
    if "error" in bundle:
        lines.append(f"stopped by {bundle['error']['type']} in this tool")
    return "\n".join(lines)


#: Stands where the member rows go while the rest is laid out.
_ROWS_HERE = "\u0000rows\u0000"


def dumps(bundle: Dict) -> str:
    """Laid out for a person to read, with each member's row on a line of its own."""
    rows = bundle["input"]["members"]["rows"]
    held = {**bundle, "input": {**bundle["input"],
                                "members": {**bundle["input"]["members"], "rows": _ROWS_HERE}}}
    text = json.dumps(held, sort_keys=True, indent=2, ensure_ascii=False)
    lines = ",\n".join("        " + json.dumps(row, separators=(",", ":")) for row in rows)
    block = "[\n" + lines + "\n      ]" if rows else "[]"
    return text.replace(json.dumps(_ROWS_HERE), block) + "\n"


def _as_text(note: str) -> str:
    """The note as UTF-8 can carry it. A byte the locale could not decode -- a
    name typed in Latin-1, Korean from a script saved in CP949 -- arrives as a
    lone surrogate, which UTF-8 cannot encode; it goes out as U+FFFD."""
    try:
        raw = note.encode("utf-8", "surrogateescape")
    except UnicodeEncodeError:
        raw = note.encode("utf-8", "replace")
    return raw.decode("utf-8", "replace")


def _within_limit(bundle: Dict) -> Dict:
    """Rows go first when the file would pass the limit; the count stays."""
    while len(dumps(bundle).encode("utf-8")) > LIMIT and bundle["input"]["members"]["rows"]:
        rows = bundle["input"]["members"]["rows"]
        del rows[len(rows) // 2:]
        bundle["input"]["members"]["listed"] = len(rows)
    return bundle


def file_name(bundle: Dict) -> str:
    sha = bundle["input"]["sha256"] or _sha256(b"")
    return f"bug-report-{TOOL}-{bundle['bundle']['toolVersion']}-{sha[:8]}.json"


def write(bundle: Dict, out_dir: Optional[str]) -> Path:
    target = Path(out_dir or ".") / file_name(bundle)
    target.write_text(dumps(bundle), encoding="utf-8")
    return target
