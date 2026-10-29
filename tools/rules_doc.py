#!/usr/bin/env python3
"""Render the rule catalogue as `docs/rules.md`.

    python tools/rules_doc.py --write    # regenerate
    python tools/rules_doc.py --check    # byte comparison, run by `make check`

Every rule this tool applies, and the only way to read them was `rules.json` or running
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

from vdi2770.model import Defect, Location  # noqa: E402
from vdi2770.validate.rules import container, files, metadata, pdf, schema  # noqa: E402

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


def reason_rows():
    """Reason-specific advice, read from the same names the findings use."""
    rows = {
        "Z5": [(when, container.REMEDY_FOR_DEFECT[kind]) for kind, when in [
            ("member-budget-exhausted", "the tree names more members than this read will hold"),
            ("too-many-members", "`<count> entries, limit is <limit>`"),
            ("member-too-large", "`the archive says <size> bytes, over the` limit, or a folder's members exceed it"),
            ("suspicious-compression", "`the archive says it expands` past this tool's ratio limit"),
            ("archive-too-large", "`the sizes this archive declares add up to` more than this tool will read"),
            ("metadata-too-large", "`<size> bytes; this tool parses at most <limit>`"),
            ("container-budget-exhausted", "this read has opened its limit of containers, or reading metadata would pass its byte limit"),
            ("decompression-budget-exhausted", "`this read has inflated` its allowance"),
        ]] + [("`this read spent its <limit> GiB budget for inflating PDF streams`", pdf.SPLIT_PDF_READ)],
        "Z9": [
            ("a folder is a container this tool did not open",
             container.folder_remedy(["<member>"], [], {})),
            ("a folder this tool opened holds a reserved name",
             container.folder_remedy([], ["<member>"], {"<member>/": {"<reserved-name>"}})),
        ],
        "Z10": [
            ("`<count> entries in this archive carry this name`",
             container.REMEDY_FOR_DEFECT["ambiguous-name"]),
            ("`Two members of the archive extract to the same path`", container.ONE_PATH),
            ("`Two members of the archive come to one name`", container.ONE_SPELLING_AND_PATH),
            ("two spellings print alike", container.ONE_SPELLING),
            ("two names become one when case is folded", container.ONE_CASE),
        ],
        "Z11": [
            ("a declared file is a container whose root holds a reserved name", container.MOVE_CONTAINER),
            ("a folder holds a container delivered unzipped", container.MOVE_FOLDER),
        ],
        "Z12": [
            ("the entry needs a password",
             container._remedy_for(Defect("member-unreadable", Location(), "encrypted"))),
            ("an Info-ZIP Unicode Path field names another file, or occurs more than once", container.ONE_NAME),
            ("`its local header, at byte` or `its data runs to byte` describes an entry's placement",
             container.layout_remedy("its data runs to byte <offset>")),
            ("`member compressed with <method>`", container.method_remedy("member compressed with <method>;")),
        ],
        "F1": [
            ("`A file named in the metadata matches more than one member of the container`, with names that print alike", files.ONE_PRINTED_NAME),
            ("`A file named in the metadata matches more than one member of the container`, with names that extract to the same path", files.ONE_EXTRACTED_PATH),
            ("`A file named in the metadata is in the container more than once`", files.REMOVE_REPEATS),
            ("`A file named in the metadata is in the container under a name read as IBM Code Page 437`", files.name_flag_remedy("<member>")),
            ("`A file named in the metadata is in the container and this tool declined to read it`", files.READ_SEPARATELY),
            ("`A file named in the metadata has a name that would escape the extraction directory`", files.RENAME_RELATIVE),
            ("`A file named in the metadata is in the container and needs a password`", files.REMOVE_PASSWORD),
            ("`A file named in the metadata is in the container under an entry that names itself more than once`", files.ONE_NAME),
            ("`its local header, at byte` or `its data runs to byte` describes the declared entry", files.layout_remedy("its data runs to byte <offset>")),
            ("`A file named in the metadata is in the container, compressed with a method this tool does not expand`", files.method_remedy("member compressed with <method>;")),
            ("`A file named in the metadata is in the container but could not be read`", files.SEND_AGAIN),
            ("`A file named in the metadata is in the container under a name no declaration can reach`", files.RENAME_DECLARED),
        ],
        "F2": [
            ("the other kind's classifying name is present at the root", files.ONE_KIND),
            ("whitespace at the edge of the name cannot be declared", files.RENAME_EDGE_SPACE),
        ],
        "M1": [("`this metadata's names are in` another namespace, or `in no namespace at all`", metadata.NAMESPACE_DECLARATION)],
        "M4": [("`The English class name is not the published one`", metadata.PUBLISHED_ENGLISH)],
        "P1": [("the reserved main document has no indirect object within this scan", pdf.REEXPORT_MAIN)],
        "P4": [("a PDF/A part 1, 2 or 3 claim has no conformance level", pdf.WRITE_CONFORMANCE)],
        "P6": [("`The PDF's page tree could not be read`", pdf.CHECK_PAGE_TREE)],
        "X1": [("`the document is in <encoding>, as its first bytes say, and this reader does not read <encoding>`",
                schema.encoding_remedy(", as its first bytes say, and this reader does not read <encoding>"))],
        "X4": [("the schema violation listing reached its limit", schema.CORRECT_LISTED)],
    }
    return rows


def page() -> str:
    catalogue = sorted(rules().values(), key=in_order)
    reasons = reason_rows()
    out = [
        "# The rules",
        "",
        "Generated from [`rules.json`](../packages/vdi2770/src/vdi2770/validate/data/rules.json) by",
        "`tools/rules_doc.py`, which also reads reason-specific remedies from the rule modules.",
        "Edit those sources, not this page — `make check` compares them.",
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
    # some of the rules have and that means something else, and some of those
    # hold the empty string.
    for kind, meaning in BASIS.items():
        held = [r for r in catalogue if r.obligation is kind]
        out.append(f"- **`{kind.value}`** ({len(held)}) — {meaning}")
    out += ["", f"{len(catalogue)} rules.", ""]

    # And how those fall across the layers, which is the shape of the answer
    # somebody wants when they ask what this tool's judgements rest on: most of
    # the container layer is this tool's own judgement around three rules of ZIP
    # mechanics, the files layer is entirely the reference implementation's, and
    # the pdf layer is almost all our own. The
    # counts come from the catalogue rather than from a sentence, because a
    # table of numbers written by hand is right on the day it is written.
    kinds = [k.value for k in BASIS]
    out += [
        "Where each layer stands:",
        "",
        "| layer | " + " | ".join(f"`{k}`" for k in kinds) + " | total |",
        "|---" * (len(kinds) + 2) + "|",
    ]
    for layer in sorted({r.layer for r in catalogue}):
        here = [r for r in catalogue if r.layer == layer]
        cells = [str(sum(1 for r in here if r.obligation.value == k)) for k in kinds]
        out.append(f"| `{layer}` | " + " | ".join(cells) + f" | {len(here)} |")
    totals = [str(sum(1 for r in catalogue if r.obligation.value == k)) for k in kinds]
    out += ["| **total** | " + " | ".join(f"**{n}**" for n in totals)
            + f" | **{len(catalogue)}** |", ""]

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
            if r.id in reasons:
                out += [f"- When the finding says {when}: {remedy}"
                        for when, remedy in reasons[r.id]] + [""]
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    made = page()
    if a.write:
        OUT.write_bytes(made.encode("utf-8"))
        print(f"wrote {OUT.relative_to(ROOT)}")
        return 0
    if a.check:
        if not OUT.exists():
            print(f"{OUT.relative_to(ROOT)} missing — run --write", file=sys.stderr)
            return 1
        if OUT.read_bytes() != made.encode("utf-8"):
            print(f"{OUT.relative_to(ROOT)} is not what the catalogue renders. "
                  f"Run `python tools/rules_doc.py --write`.", file=sys.stderr)
            return 1
        print(f"docs/rules.md matches the catalogue ({len(rules())} rules)")
        return 0
    print(made)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
