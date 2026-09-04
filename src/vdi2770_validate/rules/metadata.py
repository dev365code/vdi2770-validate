"""Model rules (M) on the parsed metadata.

Classification is matched on ClassId and the German name, because the two
freely published sources agree on all twelve German names and disagree on five
English ones. An English name can therefore never fail a document here.
"""
from __future__ import annotations

from typing import Iterator

from ..catalog import CLASSIFICATION_SYSTEM, ISO_639_1, document_classes, english_for, german_for, rule
from ..model import NS, Finding, Kind
from ..names import as_written, escaped, nfc, spelled_where_not_ascii, told_apart

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
    # `told_apart` aligns position by position and gives up when the lengths
    # differ. Quoting what the sender wrote rather than its normalisation is
    # what makes them differ -- a name with a decomposed umlaut is one character
    # longer than the published one -- and a Cyrillic `е` in the same name then
    # went unspelled, which is the failure that helper exists to prevent.
    # `escaped` is the answer for exactly this input: a name that is not its own
    # NFC has every character outside ASCII spelled out, and the Cyrillic one is
    # outside it.
    if nfc(text) != text:
        observed, first = escaped(text), escaped(published[0])
    else:
        observed, first = told_apart(text, published[0])
    rest = [f"'{escaped(w)}'" for w in published[1:]]
    return (f"'{observed}' for class {class_id}; {lead} "
            + " / ".join([f"'{first}'"] + rest))


def check(container, document, foreign) -> Iterator[Finding]:
    """`foreign` is the namespace the metadata's names are in, when it is not ours.

    Reading elements by local name alone let another vocabulary's names satisfy
    these rules, and the repair -- matching the namespace too -- has a cost that
    has to be paid rather than absorbed: a document in the wrong namespace, or in
    none, now holds nothing this layer can see. Saying `M1` about it would be
    true and useless, and would send its sender to add a classification when the
    one they wrote is sitting there in the wrong vocabulary. So the layer says
    the one thing that is wrong, and stops: everything below reads a model built
    from names that are not in this document.
    """
    if foreign is not None:
        # `M1` reached its second way. The first is a document that declares no
        # classification; this is a document whose classification is not one of
        # ours, because none of its names are -- and both are "this document
        # carries no VDI 2770 classification". One rule, two ways to reach it,
        # each carrying the sentence that names what to do about *it*, which is
        # the shape `REMEDY_FOR_DEFECT` already gives `Z5`.
        #
        # It has to be said by a layer that always runs. The namespace is the
        # schema's own `targetNamespace` and the schema layer reports it -- as
        # `'Document' is not an element of the schema`, which for a file whose
        # root element *is* `Document` sends its sender to rename an element
        # that is not wrong. And that layer does not always run.
        r = rule("M1")
        yield Finding(
            r, r.title,
            container.where.child(member=container.metadata_name, line=1),
            detail=("this metadata's names are in no namespace at all"
                    if not foreign else
                    f"this metadata's names are in {foreign!r}")
                   + f", and VDI 2770 names are in {NS!r}, so nothing in it is "
                     f"a VDI 2770 element — the classification included",
            fix=f'Declare the VDI 2770 namespace on the root element — '
                f'xmlns="{NS}" — or put the prefix that binds it on every '
                f'element and not only on the root. The schema declares its '
                f'elements qualified, so a file in another namespace, or in '
                f'none, holds no VDI 2770 names at all, and nothing else in '
                f'this report could look at the metadata\'s content.')
        return

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
                          detail=f"'{as_written(ident.id)}' appears more than once "
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
                          detail=f"ClassId '{spelled_where_not_ascii(c.class_id)}'")
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
            # Compare normalised, quote what the sender wrote. Printing the
            # normalisation put a string on the page that is not in the file
            # the report just read -- a `Pläne` a search for will not find --
            # and it also blinded the rendering: `escaped` spells a name out
            # only when it is not its own NFC, and `nfc()` had just made it
            # one, so the helper that exists to tell two canonically equivalent
            # spellings apart could no longer see there were two.
            lang, text, written = nm.language, nfc(nm.text), nm.text
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
                                  detail=_two_names(written, want_de, c.class_id,
                                                    "published name is"))
            # Not `not (startswith("de") or startswith("en"))`: the `de` half
            # is already False on this branch, and the `en` test below could
            # never be False either. Two conditions that cannot fail read as two
            # checks and are one.
            elif not low.startswith("en"):
                r = rule("M8")
                yield Finding(r, r.title, where,
                              detail=f"'{escaped(written)}' is tagged "
                                     f"'{spelled_where_not_ascii(lang)}', which "
                                     f"this tool does not check")
            elif text not in want_en:
                r = rule("M4")
                yield Finding(r, r.title, where,
                              detail=_two_names(written, want_en, c.class_id,
                                                "published renderings are"))

    for v in document.versions:
        for tag in v.languages:
            if not _iso_ok(tag.code):
                r = rule("M5")
                yield Finding(r, r.title, tag.src.child(container=container.path,
                                                        member=container.metadata_name),
                              detail=f"Language '{spelled_where_not_ascii(tag.code)}'")
        for d in v.descriptions:
            # `and d.language` here let an empty attribute switch the check
            # off, which is the shape M8's own whyOurs warns about. `is not
            # None` keeps the absent case with the schema layer, where it
            # belongs, and brings the empty one back.
            if d.language is not None and not _iso_ok(d.language):
                r = rule("M5")
                yield Finding(r, r.title, d.src.child(container=container.path,
                                                      member=container.metadata_name),
                              detail=f"DocumentDescription Language '{spelled_where_not_ascii(d.language)}'")
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
                          detail=f"LifeCycleStatus is '{as_written(v.life_cycle_status)}'")
