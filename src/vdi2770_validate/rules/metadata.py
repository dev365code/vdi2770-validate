"""Model rules (M) on the parsed metadata.

Classification is matched on ClassId and the German name, because the two
freely published sources agree on all twelve German names and disagree on five
English ones. An English name can therefore never fail a document here.
"""
from __future__ import annotations

from typing import Iterator

from ..catalog import CLASSIFICATION_SYSTEM, ISO_639_1, document_classes, english_for, german_for, rule
from ..model import Finding

RELEASED = "Released"


def _iso_ok(code: str) -> bool:
    """ISO 639 codes are ASCII letters. `str.isalpha()` is not — it accepts
    Cyrillic and Hangul, so `ДЕЮ` used to pass as a three-letter code."""
    c = code.strip().lower()
    if c in ISO_639_1:
        return True
    return len(c) == 3 and all("a" <= ch <= "z" for ch in c)


def check(container, document, is_main: bool) -> Iterator[Finding]:
    where = document.src.child(container=container.path, member=container.metadata_name)

    seen = set()
    for doc_id in document.ids:
        if not doc_id:
            r = rule("M10")
            yield Finding(r, r.title, where)
        elif doc_id in seen:
            r = rule("M9")
            yield Finding(r, r.title, where.child(subject=doc_id),
                          detail=f"{doc_id!r} appears more than once")
        seen.add(doc_id)

    vdi = [c for c in document.classifications if c.system == CLASSIFICATION_SYSTEM]
    if not vdi:
        r = rule("M1")
        yield Finding(r, r.title, document.src.child(container=container.path,
                                                     member=container.metadata_name))

    known = document_classes()
    for c in vdi:
        if not c.class_id:
            # The element is absent, not wrong. M2's remedy is "use one of these
            # twelve values", which is no help when there is nothing to correct;
            # the schema layer reports the missing element, and it is right.
            continue
        if c.class_id not in known:
            r = rule("M2")
            yield Finding(r, r.title, c.src.child(container=container.path,
                                                  member=container.metadata_name),
                          detail=f"ClassId {c.class_id!r}")
            continue
        want_de = german_for(c.class_id)
        want_en = english_for(c.class_id)
        for lang, text in c.names:
            low = lang.strip().lower()
            if low.startswith("de"):
                if text not in want_de:
                    r = rule("M3")
                    published = " / ".join(repr(w) for w in want_de)
                    yield Finding(r, r.title, c.src.child(container=container.path,
                                                          member=container.metadata_name),
                                  detail=f"{text!r} for class {c.class_id}; published name is {published}")
            elif not (low.startswith("de") or low.startswith("en")):
                r = rule("M8")
                yield Finding(r, r.title, c.src.child(container=container.path,
                                                      member=container.metadata_name),
                              detail=f"{text!r} is tagged {lang!r}, which this tool does not check")
            elif low.startswith("en") and text not in want_en:
                r = rule("M4")
                both = " / ".join(repr(w) for w in want_en)
                yield Finding(r, r.title, c.src.child(container=container.path,
                                                      member=container.metadata_name),
                              detail=f"{text!r} for class {c.class_id}; published renderings are {both}")

    for v in document.versions:
        for lang in v.languages:
            if not _iso_ok(lang):
                r = rule("M5")
                yield Finding(r, r.title, v.src.child(container=container.path,
                                                      member=container.metadata_name),
                              detail=f"Language {lang!r}")
        for d in v.descriptions:
            if d.language and not _iso_ok(d.language):
                r = rule("M5")
                yield Finding(r, r.title, d.src.child(container=container.path,
                                                      member=container.metadata_name),
                              detail=f"DocumentDescription Language {d.language!r}")
        if not any(f.file_format.split(";")[0].strip().lower() == "application/pdf" for f in v.files):
            r = rule("M6")
            yield Finding(r, r.title, v.src.child(container=container.path,
                                                  member=container.metadata_name))
        if is_main and v.life_cycle_status and v.life_cycle_status != RELEASED:
            r = rule("M7")
            yield Finding(r, r.title, v.src.child(container=container.path,
                                                  member=container.metadata_name),
                          detail=f"LifeCycleStatus is {v.life_cycle_status!r}")
