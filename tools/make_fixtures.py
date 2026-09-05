#!/usr/bin/env python3
"""Build the violating half of each rule's fixture pair.

Every fixture is ONE deliberate change to a container from the vendored corpus,
and it records which member it changed. A pair that differs in eleven files is
not evidence about any one rule, so the difference is kept minimal and written
down in fixtures/MANIFEST.json.

    python tools/make_fixtures.py
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "vdi2770" / "src"))
from vdi2770 import pdfread  # noqa: E402 - after sys.path
from vdi2770.xmlread import MAX_ELEMENTS  # noqa: E402 - after sys.path

CORPUS = ROOT / "corpus" / "examples"
OUT = ROOT / "tests" / "fixtures"

DOC = CORPUS / "container" / "documentcontainer.zip"          # a clean document container
DOCN = CORPUS / "container" / "documentationcontainer.zip"    # a clean documentation container
META = "VDI2770_Metadata.xml"
MAIN_XML = "VDI2770_Main.xml"


def members(path: Path):
    zf = zipfile.ZipFile(path)
    return {n: zf.read(n) for n in zf.namelist()}


def write_bytes(files: dict, compress=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compress) as z:
        for n, data in files.items():
            z.writestr(n, data)
    return buf.getvalue()


def write(name: str, files: dict, *, compress=zipfile.ZIP_DEFLATED) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compress) as z:
        for n, data in files.items():
            z.writestr(n, data)
    (OUT / name).write_bytes(buf.getvalue())


def edit(text: bytes, old: str, new: str) -> bytes:
    s = text.decode("utf-8")
    assert s.count(old) >= 1, f"anchor not found: {old!r}"
    return s.replace(old, new, 1).encode("utf-8")


def main() -> int:
    # The generator is the source of truth for this directory, which means it
    # owns what is *not* in it as well. It only ever wrote, so a fixture deleted
    # from this file stayed on disk and went on satisfying the gates: removing
    # M9's block left `m9-repeated-document-id.zip` behind and firing coverage
    # reported M9 covered. A fresh clone would have disagreed with the machine
    # that had built before, which is the whole failure this project keeps
    # finding in its own workspaces.
    if OUT.exists():
        for stale in sorted(OUT.iterdir()):
            if stale.is_file():
                stale.unlink()
    base = members(DOC)
    basen = members(DOCN)
    made = {}

    def add(name, files, rule, changed, note):
        write(name, files)
        made[name] = {"rule": rule, "basedOn": "documentcontainer.zip" if META in files else "documentationcontainer.zip",
                      "changed": changed, "note": note}

    # Z1 — not a ZIP at all
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "z1-not-a-zip.zip").write_bytes(b"this is not a zip file, it only has the extension\n")
    made["z1-not-a-zip.zip"] = {"rule": "Z1", "basedOn": None, "changed": ["<whole file>"],
                                "note": "plain text with a .zip name"}

    # Z4 — a member name that would escape the extraction directory
    f = dict(base)
    f["../escaped.txt"] = b"x"
    add("z4-path-traversal.zip", f, "Z4", ["../escaped.txt"], "added one member with a parent-directory segment")

    # Z5 — a member that expands far beyond this tool's ratio budget
    f = dict(base)
    f["bomb.txt"] = b"0" * (40 * 1024 * 1024)
    add("z5-compression-ratio.zip", f, "Z5", ["bomb.txt"], "40 MiB of a single repeated byte")

    # Z6 — one nesting level deeper than VDI 2770 uses
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in base.items():
            z.writestr(n, d)
    deep = io.BytesIO()
    with zipfile.ZipFile(deep, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(META, base[META])
        z.writestr("deeper.zip", inner.getvalue())
    mid = io.BytesIO()
    with zipfile.ZipFile(mid, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(META, base[META])
        z.writestr("deep.zip", deep.getvalue())
    f = dict(basen)
    f["level2.zip"] = mid.getvalue()
    add("z6-nesting-too-deep.zip", f, "Z6", ["level2.zip"], "four container levels instead of two")

    # X1 — the metadata does not parse
    f = dict(base)
    f[META] = base[META].replace(b"</Document>", b"</Documen")
    add("x1-malformed-xml.zip", f, "X1", [META], "closing tag truncated")

    # X2 — parses, but the schema refuses it
    f = dict(base)
    f[META] = edit(base[META], "<ClassId>02-01</ClassId>", "<NotAThing>02-01</NotAThing>")
    add("x2-schema-violation.zip", f, "X2", [META], "ClassId replaced by an element the schema does not declare")

    # X3 — the metadata tries to expand an entity
    xxe = (b'<?xml version="1.0"?>\n<!DOCTYPE Document [<!ENTITY x SYSTEM "file:///etc/passwd">]>\n'
           b'<Document xmlns="http://www.vdi.de/schemas/vdi2770"><DocumentId DomainId="d">&x;</DocumentId></Document>\n')
    f = dict(base)
    f[META] = xxe
    add("x3-entity-expansion.zip", f, "X3", [META], "DOCTYPE with an external entity")

    # F3 — declared media type disagrees with the file name
    f = dict(base)
    f[META] = edit(base[META], '<DigitalFile FileFormat="application/pdf">B.pdf</DigitalFile>',
                                   '<DigitalFile FileFormat="application/pdf">B.docx</DigitalFile>')
    add("f3-format-extension.zip", f, "F3", [META], "application/pdf declared for a .docx name")

    # M1 — no VDI 2770 classification at all
    f = dict(base)
    f[META] = edit(base[META], 'ClassificationSystem="VDI2770:2018"',
                                   'ClassificationSystem="SomethingElse"')
    add("m1-no-vdi-classification.zip", f, "M1", [META], "the only VDI2770:2018 classification renamed")

    # M2 — a class id that is not one of the twelve
    f = dict(base)
    f[META] = edit(base[META], "<ClassId>02-01</ClassId>", "<ClassId>99-99</ClassId>")
    add("m2-unknown-class-id.zip", f, "M2", [META], "ClassId 99-99")

    # M5 — a language code that is not ISO 639
    f = dict(base)
    f[META] = edit(base[META], "<Language>de</Language>", "<Language>deutsch</Language>")
    add("m5-bad-language-code.zip", f, "M5", [META], "Language 'deutsch'")

    # M6 — the version declares no PDF
    f = dict(base)
    f[META] = edit(base[META], 'FileFormat="application/pdf">B.pdf',
                                   'FileFormat="application/msword">B.pdf')
    add("m6-no-pdf-declared.zip", f, "M6", [META], "the only PDF re-declared as msword")

    # M7 — a main document that is not released
    f = dict(basen)
    f[MAIN_XML] = edit(basen[MAIN_XML], 'StatusValue="Released"', 'StatusValue="InReview"')
    add("m7-main-not-released.zip", f, "M7", [MAIN_XML], "LifeCycleStatus InReview")

    # P1 — a file declared as PDF that is not one
    f = dict(base)
    f["B.pdf"] = b"I am not a PDF.\n"
    add("p1-not-a-pdf.zip", f, "P1", ["B.pdf"], "PDF bytes replaced with text")

    # P2 — an encrypted PDF (taken from the corpus, so this is real, not simulated)
    f = dict(base)
    f["B.pdf"] = (CORPUS / "pdf" / "encrypted.pdf").read_bytes()
    add("p2-encrypted-pdf.zip", f, "P2", ["B.pdf"], "B.pdf replaced with the corpus's encrypted.pdf")

    # Z5b — a bomb the metadata declares as a PDF.
    # Regression: the size caps used to be enforced in the reader only, while the
    # PDF layer re-opened the raw archive and decompressed whatever the metadata
    # named. The caps have to hold on every path that reaches a member.
    f = dict(base)
    f["bomb.pdf"] = b"0" * (40 * 1024 * 1024)
    f[META] = edit(base[META], '<DigitalFile FileFormat="application/pdf">B.pdf</DigitalFile>',
                   '<DigitalFile FileFormat="application/pdf">B.pdf</DigitalFile>\n'
                   '        <DigitalFile FileFormat="application/pdf">bomb.pdf</DigitalFile>')
    add("z5b-declared-bomb.zip", f, "Z5", ["bomb.pdf", META],
        "a rejected member that the metadata declares as a PDF")

    # F4 — the metadata promises a document and names nothing
    f = dict(base)
    f.pop("B.pdf")
    f[META] = edit(base[META], '<DigitalFile FileFormat="application/pdf">B.pdf</DigitalFile>',
                   '<DigitalFile FileFormat="application/pdf"></DigitalFile>')
    add("f4-nameless-file.zip", f, "F4", [META, "B.pdf"],
        "the only PDF removed and its DigitalFile emptied — the evasion this rule exists for")

    # M8 — a class name tagged with a language we do not check
    f = dict(base)
    f[META] = edit(base[META], '<ClassName Language="de">Technische Spezifikation</ClassName>',
                   '<ClassName Language="">COMPLETE NONSENSE</ClassName>')
    add("m8-unlabelled-class-name.zip", f, "M8", [META],
        "the German class name relabelled with an empty language")

    # X4 — metadata the schema checker will not follow to the end. `xmlschema`
    # stops at a thousand levels; nothing in the XSD forbids the depth, so this
    # is our checker giving up rather than the document being wrong.
    f = dict(base)
    f[META] = (b'<?xml version="1.0" encoding="utf-8"?>\n'
               b'<Document xmlns="http://www.vdi.de/schemas/vdi2770">'
               + b"<a>" * 1001 + b"</a>" * 1001 + b"</Document>")
    add("x4-too-deep.zip", f, "X4", [META],
        "the metadata replaced with a thousand and one levels of nesting")

    # X6 — well-formed metadata this reader will not build a model of. Not the
    # same statement as X1: nothing here is malformed. Deliberately breadth and
    # not depth, so this stays distinct from x4 above -- that one is about the
    # schema checker's limit and reaches it at a thousand levels, which is well
    # inside what this reader will parse.
    f = dict(base)
    f[META] = (b'<?xml version="1.0" encoding="utf-8"?>\n'
               b'<Document xmlns="http://www.vdi.de/schemas/vdi2770">'
               + b"<a/>" * (MAX_ELEMENTS + 1) + b"</Document>")
    add("x6-too-many-elements.zip", f, "X6", [META],
        f"the metadata replaced with {MAX_ELEMENTS + 1} sibling elements")

    # F2 — a file in the container that the metadata does not name.
    # This used to be covered by `folders.zip` in the corpus, until that
    # container's files turned out to be declared in a folder's own metadata
    # that this tool never opens: accusing them was the false positive, and the
    # rule was left with nowhere to fire.
    f = dict(base)
    f["beilage.txt"] = b"a file nobody declared"
    add("f2-undeclared-file.zip", f, "F2", ["beilage.txt"],
        "one extra file, named nowhere in the metadata")

    # Z12 — a member listed in the directory that cannot be decompressed.
    # Written by hand: no ZIP writer produces a broken CRC on purpose.
    OUT.mkdir(parents=True, exist_ok=True)
    raw = bytearray(write_bytes(dict(base)))
    info = zipfile.ZipFile(io.BytesIO(bytes(raw))).getinfo("B.pdf")
    start = info.header_offset + 30 + len(info.filename) + 1000
    for k in range(start, start + 40):
        raw[k] ^= 0xFF
    (OUT / "z12-unreadable-member.zip").write_bytes(bytes(raw))
    made["z12-unreadable-member.zip"] = {
        "rule": "Z12", "basedOn": "documentcontainer.zip", "changed": ["B.pdf"],
        "note": "forty bytes of B.pdf's deflate stream flipped -- the shape of a truncated transfer"}

    # Z10 — two members with one name
    OUT.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in base.items():
            z.writestr(n, d)
        z.writestr(META, b"<Document/>")
    (OUT / "z10-duplicate-member.zip").write_bytes(buf.getvalue())
    made["z10-duplicate-member.zip"] = {
        "rule": "Z10", "basedOn": "documentcontainer.zip", "changed": [META],
        "note": "VDI2770_Metadata.xml stored twice; readers disagree about which wins"}

    # Z11 — a container smuggled inside a document container
    f = dict(base)
    f["stowaway.zip"] = write_bytes(base)
    add("z11-container-in-document.zip", f, "Z11", ["stowaway.zip"],
        "a document container carrying another container")

    # M9 — the same identifier twice
    f = dict(base)
    f[META] = edit(base[META], '<DocumentId DomainId="BSP-OEM">data-sheet-br-01-26</DocumentId>',
                   '<DocumentId DomainId="BSP-OEM">ts-ddd-234</DocumentId>')
    add("m9-repeated-document-id.zip", f, "M9", [META], "the second DocumentId set to the first")

    # M10 — an identifier that names nothing
    f = dict(base)
    f[META] = edit(base[META],
                   '<DocumentId DomainId="BSP-OEM" IsPrimary="true">ts-ddd-234</DocumentId>',
                   '<DocumentId DomainId="BSP-OEM" IsPrimary="true"></DocumentId>')
    add("m10-empty-document-id.zip", f, "M10", [META], "the primary DocumentId emptied")

    # P3 — a PDF that makes no PDF/A claim
    f = dict(base)
    f["B.pdf"] = (CORPUS / "pdf" / "scan.pdf").read_bytes()
    add("p3-no-pdfa-claim.zip", f, "P3", ["B.pdf"], "B.pdf replaced with the corpus's scan.pdf")

    # P5 — a declared PDF the scan for an indirect object cannot answer. The
    # header is there and the first `MAX_OBJ_PROBES` occurrences of `obj` are
    # all decoys, so the scan ends without finding one and without having read
    # to the end of the file. Not "not a PDF": that is the point of the rule.
    f = dict(base)
    f["B.pdf"] = (b"%PDF-1.4\nheader and decoys\n"
                  + b"obj " * pdfread.MAX_OBJ_PROBES)
    add("p5-unconfirmed-pdf.zip", f, "P5", ["B.pdf"],
        "B.pdf replaced with a header and enough decoy `obj` tokens to end the "
        "search for an indirect object before it finds one")

    (OUT / "MANIFEST.json").write_text(json.dumps({
        "_about": "The violating half of each rule's fixture pair. Each is one deliberate change to a corpus container.",
        "_conforming": {"document": "corpus/examples/container/documentcontainer.zip",
                        "documentation": "corpus/examples/container/documentationcontainer.zip"},
        "fixtures": made,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"built {len(made)} fixtures in {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
