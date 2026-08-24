#!/usr/bin/env python3
"""Run the reference implementation over our containers and record what it said.

`docs/divergences.md` is not allowed to claim "the reference does X" from reading
its source alone. This produces the receipt: `docs/oracle-sweep.json`, which holds
the reference's message *codes* per container next to our rule ids for the same
container, plus enough provenance to repeat the run.

Message text is deliberately not recorded. Codes are identifiers; the strings are
someone else's copyrighted prose, and THIRD_PARTY.md already accounts for the few
we vendor.

    python tools/capture_oracle.py --reference /path/to/vdi2770        # write
    python tools/capture_oracle.py --reference /path/to/vdi2770 --check # compare

Not part of `make check`: it needs a JDK, Maven and another project's checkout.
See tools/oracle/README.md.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "oracle-sweep.json"
PINNED_COMMIT = "e47c13c1925abc3ed4698cb5ed9e73b5eb544353"
CODE = re.compile(r"^([A-Z]{1,4}_\d{3})\b")     # D_002 has a one-letter prefix


def containers() -> list:
    out = sorted(ROOT.glob("corpus/examples/*/*.zip")) + sorted(ROOT.glob("corpus/examples/*.zip"))
    return out + sorted(ROOT.glob("tests/fixtures/*.zip"))


def their_verdicts(reference: Path, java_home: str, paths: list) -> dict:
    cp = subprocess.run(
        ["mvn", "-B", "-q", "-pl", "vdi2770-processor", "dependency:build-classpath",
         "-Dmdep.outputFile=/dev/stdout", "-DincludeScope=runtime"],
        cwd=reference, capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1]
    jars = [str(next(reference.glob(f"vdi2770-{m}/target/vdi2770-{m}-*.jar")))
            for m in ("processor", "core")]
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([f"{java_home}/bin/javac", "-cp", ":".join(jars + [cp]), "-d", tmp,
                        str(ROOT / "tools" / "oracle" / "Sweep.java")], check=True)
        raw = subprocess.run(
            [f"{java_home}/bin/java", "-Duser.language=en", "-Duser.country=US",
             "-Duser.timezone=UTC", "-Dfile.encoding=UTF-8",
             "-cp", ":".join(jars + [cp, tmp]), "Sweep", *[str(p) for p in paths]],
            capture_output=True, text=True, check=True).stdout
    out = {}
    for entry in json.loads(raw):
        per = {}
        for m in entry["messages"]:
            hit = CODE.match(m["text"])
            per.setdefault(m["level"], set()).add(hit.group(1) if hit else "«uncoded»")
        out[entry["name"]] = {k: sorted(v) for k, v in sorted(per.items())}
    return out


def our_verdicts(paths: list) -> dict:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "packages" / "vdi2770" / "src"))
    from vdi2770_validate.runner import check_file
    out = {}
    for p in paths:
        per = {}
        for f in check_file(str(p)).findings:
            per.setdefault(f.severity.value, set()).add(f.rule.id)
        out[p.name] = {k: sorted(v) for k, v in sorted(per.items())}
    return out


def build(reference: Path, java_home: str) -> dict:
    paths = containers()
    theirs, ours = their_verdicts(reference, java_home, paths), our_verdicts(paths)
    return {
        "_note": "Written by tools/capture_oracle.py. Codes only; see the docstring.",
        "reference": {"repo": "DigitalDataChainConsortium/vdi2770", "license": "MIT",
                      "commit": PINNED_COMMIT,
                      "locale": "en_US, UTC, UTF-8 — the implementation picks its "
                                "message bundle from Locale.getDefault()"},
        "containers": {name: {"reference": theirs.get(name, {}), "ours": ours.get(name, {})}
                       for name in sorted(ours)},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", required=True, type=Path)
    ap.add_argument("--java-home", default="/opt/homebrew/opt/openjdk@17")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    head = subprocess.run(["git", "-C", str(a.reference), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    if head != PINNED_COMMIT:
        print(f"reference is at {head[:12]}, not the pinned {PINNED_COMMIT[:12]}", file=sys.stderr)
        return 2

    fresh = build(a.reference, a.java_home)
    if not a.check:
        OUT.write_text(json.dumps(fresh, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)}: {len(fresh['containers'])} containers")
        return 0

    old = json.loads(OUT.read_text(encoding="utf-8"))
    moved = [n for n in fresh["containers"]
             if old["containers"].get(n) != fresh["containers"][n]]
    if moved:
        print("verdicts moved since the recorded sweep:", *moved, sep="\n  ", file=sys.stderr)
        return 1
    print(f"oracle sweep unchanged: {len(fresh['containers'])} containers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
