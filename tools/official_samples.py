#!/usr/bin/env python3
"""Write `docs/official-samples.md`: this tool's verdict on every sample the
reference repository publishes.

    python tools/official_samples.py --write    # regenerate
    python tools/official_samples.py --check    # exit 1 if the page is not what the tool says

The samples are `corpus/examples/`, copied unmodified from the repository and
commit `corpus/MANIFEST.json` names, under the licence it names. For each
container the page gives the exit code, the counts by severity, and every rule
that fired with where its requirement comes from. It says nothing about what any
other tool makes of them: it is a record of this one, regenerated from the tool
itself, so a rule that changes what it says about a sample changes this page in
the same commit.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "docs" / "official-samples.md"
MANIFEST = ROOT / "corpus" / "MANIFEST.json"
SAMPLES = ROOT / "corpus" / "examples"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(1, str(ROOT / "packages" / "vdi2770" / "src"))

from vdi2770_validate.model import Severity  # noqa: E402
from vdi2770_validate.runner import check_file  # noqa: E402

#: Where a rule's requirement comes from, as the table writes it; the legend
#: under the table says the same in full.
SOURCE = {"schema": "schema", "table": "table", "container": "container",
          "reference": "reference", "ours": "ours"}


def verdicts():
    """(sample, exit, errors, warnings, notes, rules) for every container, and
    the samples that are not containers."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    judged, not_containers = [], []
    for name in sorted(manifest["files"]):
        path = SAMPLES / name
        if path.suffix.lower() != ".zip":
            not_containers.append(name)
            continue
        try:
            report = check_file(str(path))
        except Exception:                       # noqa: BLE001 -- the page says so rather than stopping
            judged.append((name, 2, None, None, None, "this tool could not read it"))
            continue
        fired = Counter(f.rule.id for f in report.findings)
        source = {f.rule.id: SOURCE[f.rule.obligation.value] for f in report.findings}
        rules = ", ".join(f"{rid} ×{n} ({source[rid]})" for rid, n in sorted(fired.items())) or "none"
        errors = report.count(Severity.ERROR)
        judged.append((name, 1 if errors else 0, errors, report.count(Severity.WARNING),
                       report.count(Severity.INFO), rules))
    return manifest["_upstream"], judged, not_containers


def render() -> str:
    upstream, judged, not_containers = verdicts()
    lines = [
        "# The published samples, and what this tool says about them",
        "",
        "The reference repository publishes sample files beside its code. They are",
        f"copied here unmodified: from `{upstream['repo']}`",
        f"at commit `{upstream['commit']}`, path `{upstream['path']}`,",
        f"under the licence it carries ({upstream['licence']}).",
        "`corpus/MANIFEST.json` holds the SHA-256 of each. This page is this tool's",
        "verdict on every container among them, and where each rule that fired takes its",
        "requirement from. `tools/official_samples.py` writes it from the tool itself,",
        "and the build fails when the two differ.",
        "",
        "| Sample | Exit | Errors | Warnings | Notes | Rules that fired |",
        "|---|---|---|---|---|---|",
    ]
    for name, code, errors, warnings, notes, rules in judged:
        cells = [f"`{name}`", str(code)] + ["" if n is None else str(n) for n in (errors, warnings, notes)]
        lines.append("| " + " | ".join(cells + [rules]) + " |")
    lines += [
        "",
        "Where a requirement comes from: **schema**, the XSD VDI publishes free; **table**,",
        "a table published free (IDTA 02004); **container**, the mechanics of ZIP and XML,",
        "true without VDI 2770; **reference**, observed in the reference implementation",
        "and not verified against the guideline, which is not published free; **ours**,",
        "this tool's own judgement, with its reason. Each rule, its source and its remedy",
        "are in [docs/rules.md](rules.md).",
        "",
        "Exit `1` is at least one error, `0` none -- warnings and notes do not move it",
        "unless `--fail-on warning` says they should.",
    ]
    if not_containers:
        lines += ["", "Not containers, so not on this page: "
                  + ", ".join(f"`{name}`" for name in not_containers) + "."]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    page = render()
    if args.check:
        if not PAGE.exists() or PAGE.read_text(encoding="utf-8") != page:
            print("docs/official-samples.md is not what this tool says about the samples; "
                  "run python tools/official_samples.py --write", file=sys.stderr)
            return 1
        print("docs/official-samples.md is what this tool says about the samples")
        return 0
    PAGE.write_text(page, encoding="utf-8")
    print("wrote docs/official-samples.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
