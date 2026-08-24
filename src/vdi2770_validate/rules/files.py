"""File-set rules (F): does the metadata agree with what is actually in the ZIP?"""
from __future__ import annotations

from typing import Iterator

from ..catalog import rule
from ..model import Finding, nfc

EXTENSION_FOR = {"application/pdf": ".pdf", "application/zip": ".zip"}


def check(container, document) -> Iterator[Finding]:
    from vdi2770.zipread import MAIN_PDF, MAIN_XML, METADATA_XML, Kind

    # macOS stores filenames decomposed and its Finder writes them that way into
    # the ZIP; metadata authored anywhere else is composed. The two spellings are
    # canonically equivalent and print identically, so the report used to say the
    # same name was both missing and undeclared.
    present  = {nfc(n) for n in container.file_names}
    declared = {nfc(f.file_name) for f in document.all_files if f.file_name}

    for f in document.all_files:
        if not f.file_name:
            r = rule("F4")
            yield Finding(r, r.title, f.src.child(container=container.path,
                                                  member=container.metadata_name),
                          detail=f"declared as {f.file_format!r} with no file name")
            continue
        if nfc(f.file_name) not in present:
            rejected = container.rejected.get(f.file_name)
            detail = (f"{f.file_name!r} is in the archive but was refused: {rejected}"
                      if rejected else
                      f"{f.file_name!r} is declared but not in the archive")
            r = rule("F1")
            yield Finding(r, r.title, f.src.child(container=container.path,
                                                  member=container.metadata_name),
                          detail=detail)

    # Reserved where it is reserved, and nowhere else. Exempting all three names
    # everywhere meant a stray VDI2770_Main.pdf inside a document container -- a
    # name that means nothing there -- was never reported as undeclared.
    structural = ({MAIN_XML, MAIN_PDF} if container.kind is Kind.DOCUMENTATION
                  else {METADATA_XML})
    for name in sorted(present - declared - structural):
        if name.lower().endswith(".zip"):
            continue
        r = rule("F2")
        yield Finding(r, r.title, container.where.child(member=name, subject=name))

    for f in document.all_files:
        want = EXTENSION_FOR.get(f.file_format.split(";")[0].strip().lower())
        if want and f.file_name and not f.file_name.lower().endswith(want):
            r = rule("F3")
            yield Finding(r, r.title,
                          f.src.child(container=container.path, member=container.metadata_name),
                          detail=f"{f.file_name!r} is declared as {f.file_format!r}")
