"""Model rules (M) on the parsed metadata.

Classification is matched on ClassId and the German name, because the two
freely published sources agree on all twelve German names and disagree on five
English ones. An English name can therefore never fail a document here.
"""
from __future__ import annotations

from typing import Iterator

from ..catalog import CLASSIFICATION_SYSTEM, ISO_639_1, document_classes, english_for, german_for, rule
from ..model import Finding, Kind
from ..names import escaped, nfc, told_apart

RELEASED = "Released"


def _iso_ok(code: str) -> bool:
    """ISO 639 codes are ASCII letters. `str.isalpha()` is not — it accepts
    Cyrillic and Hangul, so `ДЕЮ` used to pass as a three-letter code."""
    c = code.strip().lower()
    if c in ISO_639_1:
        return True
    return len(c) == 3 and all("a" <= ch <= "z" for ch in c)


def _two_names(text: str, published, class_id: str, lead: str) -> str:
    """The observed class name beside the published one, told apart.

    Rendered against the first published spelling, because the run that differs
    is a fact about a pair: with two published names there is no one run, and
    picking the closest would make the report's rendering depend on which name a
    comparison happened to choose. The rest are shown as they are written.
    """
    observed, first = told_apart(text, published[0])
    rest = [f"'{escaped(w)}'" for w in published[1:]]
    return (f"'{observed}' for class {class_id}; {lead} "
            + " / ".join([f"'{first}'"] + rest))


def check(container, document) -> Iterator[Finding]:
    # An identifier is (domain, value): the schema makes DomainId required, and
    # the same drawing number registered by an OEM and by its supplier is two
    # identifiers, not one repeated. Comparing the text alone told people to
    # delete one of them.
    seen = set()
    for ident in document.identifiers:
        at = ident.src.child(container=container.path, member=container.metadata_name)
        if not ident.id:
            r = rule("M10")
            yield Finding(r, r.title, at)
        elif (ident.domain_id, ident.id) in seen:
            r = rule("M9")
            yield Finding(r, r.title, at.child(subject=ident.id),
                          detail=f"{ident.id!r} appears more than once "
                                 f"in domain {ident.domain_id!r}")
        seen.add((ident.domain_id, ident.id))

    vdi = [c for c in document.classifications if c.system == CLASSIFICATION_SYSTEM]
    if not vdi:
        r = rule("M1")
        yield Finding(r, r.title, document.src.child(container=container.path,
                                                     member=container.metadata_name))

    known = document_classes()
    for c in vdi:
        if c.class_id is None:
            # The element is absent, not wrong. M2's remedy is "use one of these
            # twelve values", which is no help when there is nothing to correct;
            # the schema layer reports the missing element, and it is right.
            # An element that is present and empty is a different matter: the
            # schema accepts it, so if we say nothing then nobody does.
            continue
        if c.class_id not in known:
            r = rule("M2")
            yield Finding(r, r.title, c.src.child(container=container.path,
                                                  member=container.metadata_name),
                          detail=f"ClassId {c.class_id!r}")
            continue
        want_de = german_for(c.class_id)
        want_en = english_for(c.class_id)
        for nm in c.names:
            # `nfc`, because a published name and the name in front of us can
            # spell the same word two legal ways -- one composed character or a
            # base and a combining mark -- and an editor chooses without telling
            # its author. Comparing the code points said `'Zeichnungen, Pläne'`
            # does not belong to class `02-02`, whose published name is
            # `'Zeichnungen, Pläne'`: a difference a reader cannot see and a
            # remedy asking them to type what they already typed. This is what
            # `names` exists to settle, and the metadata layer was comparing text
            # that had not been through it. The published names are composed, so
            # nothing that used to match stops matching.
            lang, text = nm.language, nfc(nm.text)
            if lang is None:
                continue          # no Language attribute at all; X2 says so
            # The name's own location, not the classification's. Several names
            # share one block, so `c.src` gave all of them the same line.
            where = nm.src.child(container=container.path, member=container.metadata_name)
            low = lang.strip().lower()
            if low.startswith("de"):
                if text not in want_de:
                    r = rule("M3")
                    # Both strings, side by side, rendered so the difference is
                    # on the page. `escaped` sees one string at a time and one
                    # Cyrillic `е` among the Latin ones defeats it -- both sides
                    # are their own NFC and every character is printable and
                    # non-combining, so it left them alone and the finding named
                    # the name it was asking for. This call site holds both, and
                    # `told_apart` spells the run that differs when the run is
                    # one a reader can miss.
                    yield Finding(r, r.title, where,
                                  detail=_two_names(text, want_de, c.class_id,
                                                    "published name is"))
            # Not `not (startswith("de") or startswith("en"))`: the `de` half
            # is already False on this branch, and the `en` test below could
            # never be False either. Two conditions that cannot fail read as two
            # checks and are one.
            elif not low.startswith("en"):
                r = rule("M8")
                yield Finding(r, r.title, where,
                              detail=f"{text!r} is tagged {lang!r}, which this tool does not check")
            elif text not in want_en:
                r = rule("M4")
                yield Finding(r, r.title, where,
                              detail=_two_names(text, want_en, c.class_id,
                                                "published renderings are"))

    for v in document.versions:
        for tag in v.languages:
            if not _iso_ok(tag.code):
                r = rule("M5")
                yield Finding(r, r.title, tag.src.child(container=container.path,
                                                        member=container.metadata_name),
                              detail=f"Language {tag.code!r}")
        for d in v.descriptions:
            # `and d.language` here let an empty attribute switch the check
            # off, which is the shape M8's own whyOurs warns about. `is not
            # None` keeps the absent case with the schema layer, where it
            # belongs, and brings the empty one back.
            if d.language is not None and not _iso_ok(d.language):
                r = rule("M5")
                yield Finding(r, r.title, d.src.child(container=container.path,
                                                      member=container.metadata_name),
                              detail=f"DocumentDescription Language {d.language!r}")
        if not any(f.file_format.split(";")[0].strip().lower() == "application/pdf" for f in v.files):
            r = rule("M6")
            yield Finding(r, r.title, v.src.child(container=container.path,
                                                  member=container.metadata_name))
        # The container's own kind, not a boolean passed in.
        #
        # The two are not equivalent in general, and the comment that said they
        # were was wrong: `_classify` reads `present`, so a *refused*
        # VDI2770_Main.xml still makes the archive a documentation container
        # while `metadata_name` stays None. They agree wherever this line runs,
        # because the runner does not reach these rules without metadata it
        # parsed -- which is a fact about the runner, not about the reader. If
        # that ever changes, this reads the container and the flag would have
        # read a stale summary of it.
        if (container.kind is Kind.DOCUMENTATION and v.life_cycle_status
                and v.life_cycle_status != RELEASED):
            r = rule("M7")
            yield Finding(r, r.title, v.life_cycle_src.child(container=container.path,
                                                             member=container.metadata_name),
                          detail=f"LifeCycleStatus is {v.life_cycle_status!r}")
