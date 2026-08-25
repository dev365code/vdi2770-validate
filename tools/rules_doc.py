#!/usr/bin/env python3
"""Render the rule catalogue as `docs/rules.md`.

    python tools/rules_doc.py --write    # regenerate
    python tools/rules_doc.py --check    # byte comparison, run by `make check`

Thirty-six rules and the only way to read them was `rules.json` or running
`vdi2770-validate rules`. Someone deciding whether this tool is worth installing
should be able to see what it checks, and what each check is based on, from a
link. The generator is the source of truth: editing the page by hand is what
`--check` exists to catch.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "rules.md"
#: Both, and in this order. A tool that inserts only `src` measures whichever
#: `vdi2770` happens to be installed — on a machine with the reader from PyPI
#: that is a different library than the one in this commit, and the gate then
#: reports coverage for code nobody is changing.
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(1, str(ROOT / "packages" / "vdi2770" / "src"))

from vdi2770_validate.catalog import rules  # noqa: E402
from vdi2770_validate.model import About, Obligation  # noqa: E402

BASIS = {
    Obligation.SCHEMA: "the XSD VDI publishes free says so, mechanically",
    Obligation.PUBLISHED_TABLE: "a freely published table says so (IDTA 02004)",
    Obligation.CONTAINER: "mechanics of ZIP and XML — true without VDI 2770",
    Obligation.REFERENCE: "observed in the MIT reference implementation, **not** "
                          "verified against the guideline, which is paywalled",
    Obligation.OURS: "our own judgement, and it carries a reason",
}


def in_order(r):
    letters = r.id.rstrip("0123456789")
    return (r.layer, letters, int(r.id[len(letters):] or 0))


def page() -> str:
    catalogue = sorted(rules().values(), key=in_order)
    out = [
        "# The rules",
        "",
        "Generated from [`rules.json`](../src/vdi2770_validate/data/rules.json) by",
        "`tools/rules_doc.py`. Edit the data, not this page — `make check` compares them.",
        "",
        "`obligation` says where a requirement comes from, and the vocabulary is deliberately",
        "not MUST/SHOULD: this project has not read VDI 2770, so it never claims to quote",
        "it. `about` separates a statement about the container from a statement about this",
        "tool, because both are errors on purpose and severity cannot carry the difference.",
        "",
    ]
    # `basis` is a different field on the same rule -- the free source a rule
    # cites, `IDTA 02004 v2.0.1 Table 1`. Calling `obligation` by that name here
    # sent a reader who followed this page to the data looking for a key that
    # five of the rules have and that means something else, and two of those
    # five hold the empty string.
    for kind, meaning in BASIS.items():
        held = [r for r in catalogue if r.obligation is kind]
        out.append(f"- **`{kind.value}`** ({len(held)}) — {meaning}")
    out += ["", f"{len(catalogue)} rules.", ""]

    for layer in sorted({r.layer for r in catalogue}):
        out += [f"## {layer}", ""]
        for r in (x for x in catalogue if x.layer == layer):
            tool = " · **about: this tool**" if r.about is About.TOOL else ""
            out += [f"### `{r.id}` — {r.title}", "",
                    f"*{r.severity.value}* · obligation `{r.obligation.value}`{tool}", ""]
            if r.basis:
                out += [f"Source: `{r.basis}`.", ""]
            if r.ref_keys:
                # The keys, not only the codes. `divergences.md` spends a
                # section arguing that a displayed code is ambiguous -- thirteen
                # of them are emitted from more than one key with different
                # meanings -- and this page showed nothing else.
                shown = ", ".join(f"`{k}`" for k in r.ref_keys)
                codes = ", ".join(f"`{c}`" for c in r.ref_codes)
                out += [f"Reference implementation: {shown}"
                        + (f" (displayed as {codes})" if codes else "")
                        + ". Citing a key records that the other project checks something in "
                          "the same area; it does not borrow its claim.", ""]
            if getattr(r, "why_ours", ""):
                out += [f"Why this is ours: {r.why_ours}", ""]
            out += [f"**Remedy.** {r.remedy}", ""]
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    made = page()
    if a.write:
        OUT.write_text(made, encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)}")
        return 0
    if a.check:
        if not OUT.exists():
            print(f"{OUT.relative_to(ROOT)} missing — run --write", file=sys.stderr)
            return 1
        if OUT.read_text(encoding="utf-8") != made:
            print(f"{OUT.relative_to(ROOT)} is not what the catalogue renders. "
                  f"Run `python tools/rules_doc.py --write`.", file=sys.stderr)
            return 1
        print(f"docs/rules.md matches the catalogue ({len(rules())} rules)")
        return 0
    print(made)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
