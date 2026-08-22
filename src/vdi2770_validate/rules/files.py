"""File-set rules (F): does the metadata agree with what is actually in the ZIP?"""
from __future__ import annotations

from typing import Iterator

from ..catalog import rule
from ..model import Finding

EXTENSION_FOR = {"application/pdf": ".pdf", "application/zip": ".zip"}


def check(container, document) -> Iterator[Finding]:
    from ..readers.zipread import MAIN_PDF, MAIN_XML, METADATA_XML

    present = set(container.file_names)
    declared = {f.file_name for f in document.all_files if f.file_name}

    for f in document.all_files:
        if f.file_name and f.file_name not in present:
            r = rule("F1")
            yield Finding(r, r.title, f.src.child(container=container.path,
                                                  member=container.metadata_name),
                          detail=f"{f.file_name!r} is declared but not in the archive")

    structural = {MAIN_XML, METADATA_XML, MAIN_PDF}
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
