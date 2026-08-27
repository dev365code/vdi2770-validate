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
    python tools/capture_oracle.py --check-ours                        # our half only
    python tools/capture_oracle.py --write-ours                        # our half only

The first two need a JDK, Maven and another project's checkout, so they are not
part of `make check`. The last two need none of that: our own column can be
recomputed from this repository alone, and it is the half that goes stale.
Nothing compared it, so changing a rule's severity and regenerating the docs left
a recorded verdict describing a tool that no longer exists — while
`docs/divergences.md` went on deriving counts from it.
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
    """Every container in the two trees, walked the way the coverage gate walks.

    This globbed fixed depths while `tools/rule_coverage.py` and the documents
    gate walk recursively, so a container one directory deeper satisfied firing
    coverage, was counted in the documents, and was invisible here -- and this
    went on saying "our half of the oracle sweep is current: 46 containers" with
    a forty-seventh in the tree. A container nobody compares against the
    reference implementation is one this project has no second opinion about,
    and the gate that says so could be made quiet by choosing a directory.
    """
    return (sorted((ROOT / "corpus").rglob("*.zip"))
            + sorted((ROOT / "tests" / "fixtures").rglob("*.zip")))


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
        # Run it from the temporary directory: its log4j writes `application.log`
        # into the working directory, and one of those was committed to this
        # repository before anybody noticed.
        raw = subprocess.run(
            [f"{java_home}/bin/java", "-Duser.language=en", "-Duser.country=US",
             "-Duser.timezone=UTC", "-Dfile.encoding=UTF-8",
             "-cp", ":".join(jars + [cp, tmp]), "Sweep", *[str(p) for p in paths]],
            cwd=tmp, capture_output=True, text=True, check=True).stdout
    out = {}
    for entry in json.loads(raw):
        per = {}
        for m in entry["messages"]:
            hit = CODE.match(m["text"])
            per.setdefault(m["level"], set()).add(hit.group(1) if hit else "«uncoded»")
        out[entry["name"]] = {k: sorted(v) for k, v in sorted(per.items())}
    return out


MESSAGES = ROOT / "tests" / "data" / "oracle-messages.json"


def their_messages(reference: Path) -> list:
    """The reference's English message strings, from its own resource bundles.

    `tests/data/oracle-messages.json` is what the licensing gate compares our
    remedies against, to show none of them is a translation of someone else's
    reading. It was extracted by hand once and had no generator, so its pinned
    commit was a claim rather than a check — the one thing `vendor_corpus.py`
    exists to prevent, applied to everything except this file.

    Written from the layout the sweep already relies on and **not run here**:
    that needs the reference checkout, which is the same constraint the sweep
    carries. Whoever has one can settle it.
    """
    found = set()
    for bundle in sorted(reference.glob("*/src/main/resources/i8n/*.properties")):
        name = bundle.name
        # The English bundle is the unsuffixed one; `_de` and friends are not
        # what the sweep pinned its locale to.
        if re.search(r"_[a-z]{2}\.properties$", name):
            continue
        for line in bundle.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "!")) or "=" not in line:
                continue
            value = line.split("=", 1)[1].strip()
            if value:
                found.add(value)
    return sorted(found)


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


def ours_only(write: bool) -> int:
    """Recompute our column and compare it, or record it, leaving theirs alone.

    Recording is safe without the reference because the two halves are
    independent: their verdicts are a fact about a pinned commit of somebody
    else's code, which this cannot change.
    """
    if not OUT.exists():
        print(f"{OUT.relative_to(ROOT)} missing — run a full sweep first", file=sys.stderr)
        return 1
    recorded = json.loads(OUT.read_text(encoding="utf-8"))
    fresh = our_verdicts(containers())

    # The canary. A comparison over an empty set passes, and this file is the
    # kind of thing that would quietly become empty.
    if not fresh or not any(v for v in fresh.values()):
        print("recomputed nothing; the corpus and fixtures are not where this "
              "expects them", file=sys.stderr)
        return 1

    known = set(recorded["containers"])
    if set(fresh) != known:
        print(f"the container set moved: only recorded {sorted(known - set(fresh))}, "
              f"only here {sorted(set(fresh) - known)}. Run a full sweep.", file=sys.stderr)
        return 1

    moved = [n for n in sorted(fresh) if recorded["containers"][n]["ours"] != fresh[n]]
    if write:
        for n in fresh:
            recorded["containers"][n]["ours"] = fresh[n]
        OUT.write_text(json.dumps(recorded, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        print(f"wrote our half of {OUT.relative_to(ROOT)}"
              + (f": {len(moved)} container(s) moved" if moved else ": nothing moved"))
        return 0

    if moved:
        for n in moved:
            print(f"{n}: recorded {recorded['containers'][n]['ours']} -> now {fresh[n]}",
                  file=sys.stderr)
        print("our recorded verdicts are stale. If this is intended, rerun with "
              "--write-ours and re-read docs/divergences.md, which counts them.",
              file=sys.stderr)
        return 1
    print(f"our half of the oracle sweep is current: {len(fresh)} containers")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", type=Path)
    ap.add_argument("--java-home", default="/opt/homebrew/opt/openjdk@17")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--check-ours", action="store_true")
    ap.add_argument("--check-swept", action="store_true",
                    help="every container has a reference verdict (no JDK needed)")
    ap.add_argument("--write-ours", action="store_true")
    ap.add_argument("--messages", action="store_true",
                    help="re-extract tests/data/oracle-messages.json from the reference")
    ap.add_argument("--check-messages", action="store_true",
                    help="compare the vendored messages against the reference")
    a = ap.parse_args()

    if a.check_swept:
        # No JDK, no Maven, no network: this reads the recorded file and nothing
        # else. It is the release gate, and a release must not depend on Maven
        # Central being up — the sweep workflow keeps the file honest, and this
        # only asks whether it is complete.
        recorded = json.loads(OUT.read_text(encoding="utf-8"))
        # Against the containers on disk, not against the file's own key set. A
        # sweep missing a fixture entirely answered "complete", and an empty one
        # answered "every one of 0 containers has a reference verdict" -- the
        # canary this file already carries for `ours_only()` and did not carry
        # here.
        here = {p.name for p in containers()}
        assert here, "no containers found; this gate would pass over nothing"
        if set(recorded["containers"]) != here:
            print(f"the sweep and the repository disagree about which containers "
                  f"exist: only swept {sorted(set(recorded['containers']) - here)}, "
                  f"only here {sorted(here - set(recorded['containers']))}",
                  file=sys.stderr)
            return 1
        waiting = sorted(recorded.get("_unswept", {}))
        if waiting:
            print(f"{len(waiting)} container(s) have never been through the reference "
                  f"implementation: {waiting}\nRun the `oracle` workflow and commit what it "
                  f"produces. Releasing now would ship divergence counts that exclude them.",
                  file=sys.stderr)
            return 1
        empty = sorted(n for n, e in recorded["containers"].items() if not e["reference"])
        if empty:
            print(f"{empty} have no reference verdict and are not listed in _unswept",
                  file=sys.stderr)
            return 1
        print(f"every one of {len(recorded['containers'])} containers has a reference verdict")
        return 0

    if a.check_ours or a.write_ours:
        return ours_only(write=a.write_ours)
    if a.reference is None:
        ap.error("--reference is required unless you asked for --check-ours/--write-ours")

    if a.messages or a.check_messages:
        fresh = their_messages(a.reference)
        if not fresh:
            print("no message bundles found under the reference checkout", file=sys.stderr)
            return 1
        recorded = json.loads(MESSAGES.read_text(encoding="utf-8"))
        if a.check_messages:
            if sorted(recorded["messages"]) != fresh:
                only_here = sorted(set(recorded["messages"]) - set(fresh))
                only_there = sorted(set(fresh) - set(recorded["messages"]))
                print(f"the vendored message set does not match the reference at "
                      f"{PINNED_COMMIT[:12]}: {len(only_here)} only here, "
                      f"{len(only_there)} only there", file=sys.stderr)
                return 1
            print(f"the vendored messages match the reference: {len(fresh)}")
            return 0
        recorded["messages"], recorded["count"] = fresh, len(fresh)
        MESSAGES.write_text(json.dumps(recorded, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
        print(f"wrote {MESSAGES.relative_to(ROOT)}: {len(fresh)} messages")
        return 0

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
