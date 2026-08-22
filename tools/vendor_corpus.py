#!/usr/bin/env python3
"""Copy the MIT conformance corpus into the repo and pin every file by hash.

A figure nobody else can reproduce is a figure, not evidence — so the corpus
travels with the tests, with its provenance and hashes recorded.

    python tools/vendor_corpus.py --from <clone of DigitalDataChainConsortium/vdi2770>
    python tools/vendor_corpus.py --check      # offline; what CI runs
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS = REPO_ROOT / "corpus"
MANIFEST = CORPUS / "MANIFEST.json"
UPSTREAM = "DigitalDataChainConsortium/vdi2770"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def collect(src: Path) -> list[Path]:
    return sorted(p for p in (src / "examples").rglob("*") if p.is_file() and p.name != ".DS_Store")


def do_vendor(src: Path) -> int:
    commit = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=True).stdout.strip()
    files = collect(src)
    if not files:
        print(f"no example files under {src}/examples", file=sys.stderr)
        return 1
    entries = {}
    for f in files:
        rel = f.relative_to(src / "examples").as_posix()
        dst = CORPUS / "examples" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
        entries[rel] = {"sha256": sha256(dst), "bytes": dst.stat().st_size}
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({
        "_upstream": {"repo": UPSTREAM, "commit": commit, "path": "examples/",
                      "licence": "MIT, Copyright (C) 2021 Johannes Schmidt"},
        "_note": "Copied verbatim. Not modified. Used as fixtures under the MIT licence.",
        "files": entries,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"vendored {len(entries)} files from {UPSTREAM}@{commit[:7]}")
    return 0


def do_check() -> int:
    if not MANIFEST.exists():
        print("corpus/MANIFEST.json missing — run --from first", file=sys.stderr)
        return 1
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    bad = []
    for rel, meta in man["files"].items():
        p = CORPUS / "examples" / rel
        if not p.exists():
            bad.append(f"missing: {rel}")
        elif sha256(p) != meta["sha256"]:
            bad.append(f"changed: {rel}")
    on_disk = {p.relative_to(CORPUS / "examples").as_posix()
               for p in (CORPUS / "examples").rglob("*") if p.is_file()}
    for extra in sorted(on_disk - set(man["files"])):
        bad.append(f"untracked: {extra}")
    if bad:
        print("corpus does not match its manifest:", file=sys.stderr)
        for b in bad:
            print(f"  {b}", file=sys.stderr)
        return 1
    print(f"corpus ok: {len(man['files'])} files match {MANIFEST.relative_to(REPO_ROOT)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--from", dest="src", type=Path, help="path to a clone of " + UPSTREAM)
    g.add_argument("--check", action="store_true")
    a = ap.parse_args()
    return do_check() if a.check else do_vendor(a.src)


if __name__ == "__main__":
    raise SystemExit(main())
