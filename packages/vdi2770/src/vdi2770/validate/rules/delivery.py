"""Rules about the delivery as a whole, rather than about one container in it.

Every other layer here is handed one container and judges it alone, which is the
right shape for almost everything: a metadata file is well-formed or it is not,
a declared file is present or it is not, and neither answer depends on what else
travelled in the same handover.

Relationships are the exception. `DocumentRelationship` names a *document*, not
a file, and the document it names lives in a sibling container — so the question
"is what this points at actually here" cannot be asked from inside the container
doing the pointing. Nothing here could ask it, and so nothing did: a
documentation container whose main document referred to two documents and
delivered neither reported `0 error(s)` and exited `0`, which is the number a CI
intake gate reads.

The judgement is the reference implementation's. Read at the commit this
project's oracle is pinned to, `Document.validateDocumentRelations` compares
each relationship's identifier against the documents known to the run and, when
it finds none, raises

    isMainDocument ? FaultLevel.ERROR : FaultLevel.INFORMATION

which is where the first version of this got two severities -- and that method
is not the surface anybody validates a container through.
`ContainerValidator.validateDocumentRelations` takes each directory's own
metadata (`VDI2770_Main.xml`, or `VDI2770_Metadata.xml` where there is no main)
and calls it with `isMainDocument` hard-coded `true`, so the information branch
never runs on a container at all. The differential sweep said so before any
reasoning did: the reference reports `D_004` as an ERROR on both fixtures here
and we reported one of them as a note, which is the expensive direction to be
wrong in -- a note passes a delivery they fail.

So: two rules, because a reader is owed a different sentence depending on which
document made the promise, and one severity, because the reference makes one
judgement. `obligation: reference` is a promise that the judgement is theirs,
and the guideline that could settle it is paid and was not read.
"""
from __future__ import annotations

from typing import Iterator

from ..catalog import rule
from ..model import MAIN_XML, Finding
from ..names import as_written


def _identity(document_id) -> tuple:
    """How the reference implementation tells two identifiers apart.

    `StringRepresentations.documentIdAsText` is `id + "@" + domainId`, compared
    with `equalsIgnoreCase`. Both halves matter and both are easy to get wrong
    in the expensive direction: comparing the bare id accepts a delivery that
    carries a different document under a coincidentally equal number, and
    comparing case-sensitively fails a delivery that carries the right one.
    """
    return (document_id.id.strip().casefold(),
            document_id.domain_id.strip().casefold())


def declarations(documents) -> tuple:
    """How many documents declare each identifier, and each document's own.

    `ContainerValidator` removes the current document from the map before
    comparing, so a relationship naming the identifier of the document it sits
    in is dangling to the reference implementation. It was not to us, and no
    container in the corpus refers to itself -- a divergence with nothing in
    the corpus to expose it, which is the kind that ships.

    Counted once for the delivery rather than built once per document that
    asks. The first spelling answered the same question with a set of every
    identity *except one document's own*, which meant one set per referring
    document, all of them held at once: R*T in time and in memory on a
    conforming delivery, and no budget in this tool watches that product.

    Counting rather than subtracting, because two documents may declare the
    same identifier: a single set with one document's own identities removed
    would drop an identifier that another document still declares, and the
    relationship naming it would be called dangling. The count, minus your own,
    is the same question asked in a way that survives repeats.
    """
    declared, own = {}, {}
    for _container, doc in documents:
        mine = {_identity(i) for i in doc.identifiers}
        own[id(doc)] = mine
        for identity in mine:
            declared[identity] = declared.get(identity, 0) + 1
    return declared, own


def refers_to(documents) -> Iterator[tuple]:
    """Each (container, document, relationship, identifier) pointed at.

    A relationship may name more than one document, and each is a separate
    promise: taking the first would let a delivery leave out every document
    after it and still come back clean.
    """
    for container, doc in documents:
        for version in doc.versions:
            for relationship in version.relationships:
                for target in relationship.identifiers:
                    yield container, doc, relationship, target


def objects_claimed(documents) -> dict:
    """Each object identifier, and every kind it was filed under, with where.

    Keyed on the identifier alone, folded for case -- *not* on the identifier
    and the register it was issued in. An earlier version keyed on both, and
    that had to go: a claim that names no register matches every register, so
    grouping by register splits claims that do contradict each other and the
    rule goes quiet for the blank one. The register is decided in
    `contradicting`, which never builds the pairs: a claim that states a
    register takes part only when a claim of another kind states the same one
    or states none.

    It still matters, and it is still the half that was once missing: an
    article number and a serial number are different registers, and this
    corpus pairs them inside one document -- `Individual/serial number/U1-99999`
    beside `Type/article number/U1`. The day a manufacturer's article number
    equals somebody's serial, a comparison on the bare string calls a correct
    delivery a contradiction. What prevents that is `contradicting` keeping the
    stated registers apart, so an article number and a serial number never meet.

    `globally_unique` is deliberately not consulted. It says whether an
    identifier may be compared *outside* this delivery, and every comparison
    here is inside one -- a sender who marks an id local has not licensed us to
    call it two kinds of thing in one handover.
    """
    seen = {}
    for container, doc in documents:
        for obj in doc.objects:
            if not obj.id or not obj.object_type:
                # Nothing to contradict. An absent type is the schema's problem
                # and an absent id is not an identifier.
                continue
            seen.setdefault(obj.id.strip().casefold(), []).append(
                (obj.object_type.strip(), obj, container))
    return seen


def _register(ref_type) -> str:
    """A `RefType` reduced to what two senders would have to agree on."""
    return " ".join(str(ref_type or "").split()).casefold()


def different_registers(a, b) -> bool:
    """True only when both claims name a register and the two differ.

    Keyed the other way round -- grouping by `(id, RefType)` -- this rule could
    be switched off by writing a `RefType` on one of two contradicting claims
    and not the other, or by spelling it `serialNumber` on one side. Measured on
    this project's own corpus container: one attribute on one side, and the
    finding disappeared. A rule a sender can silence by adding a word is worse
    than the false positive it was avoiding.

    So an absent or blank register matches every register, and only two stated
    and unequal ones mean "different things that happen to be spelled alike".
    """
    left, right = _register(a), _register(b)
    return bool(left) and bool(right) and left != right


#: How many kinds a finding prints before it says how many there were.
#: `MAX_LISTED_PER_RULE` bounds how many findings a rule may list; it does not
#: bound how large one of them is, and `M13` emits one finding per identifier,
#: so the cap never engages while the sentence grows with what the sender
#: wrote. Measured: 400 kinds under one identifier made one detail 4,096
#: characters, and 40,000 made it 430,096.
#:
#: The containers are bounded the same way, by the same function. They were
#: once listed in full, on the argument that a truncated list of them could not
#: be recovered while a truncated list of kinds could. Both are recovered the
#: same way -- by searching the delivery for the identifier the sentence names,
#: ignoring case and surrounding spaces as the grouping below does -- and the
#: full list had no bound on its *size*: `MAX_CONTAINERS` limits how
#: many containers there are, not how long their paths are, and a long name on a
#: container that holds others is repeated in every one of their paths. Forty
#: containers under a 2,000-character name made one detail 81,177 characters;
#: listing five makes it 10,270. What was wrong with the first truncation was
#: that it was silent. The count now says how many there were.
MOST_LISTED = 5


def _first_few(items, noun) -> tuple:
    """The first few, and the clause that says how many there were.

    The count is returned separately rather than appended to the list, because
    a marker inside a comma-separated run is read as one of the items. The
    project's own way of reading this sentence --
    `is declared as (.+?) in this delivery` -- returned `Kind04 -- 5 of 6
    shown` as though it were the name of a kind, and the kind that sorted after
    it vanished. A truncated list has to stay a list.

    Each item is shown as written, with what draws nothing spelled out: every
    item here is a name or a kind the sender wrote, and a newline in a
    container's name put a forged summary and a clean verdict on the page, as
    the location line was once made not to.
    """
    items = [as_written(i) for i in items]
    if len(items) <= MOST_LISTED:
        return ", ".join(items), ""
    return (", ".join(items[:MOST_LISTED]),
            f" {len(items)} {noun} in all, {MOST_LISTED} of them here;")


def contradicting(claims) -> list:
    """The claims that take part in a contradiction, in the order they were read.

    Two claims contradict when they disagree about the kind and nothing says
    they are about different registers. Answering that by building every pair
    costs the square of the claims, in time and in the list it materialises,
    and nothing bounds the claims: the reader's caps are on elements and bytes,
    and a hundred thousand `ObjectId` elements naming one identifier is a
    conforming document about a hundred kilobytes long. Measured on the first
    version: 109 KiB of container, 8.3 seconds, the curve rising with the
    square while the file grew by one kilobyte.

    It does not need the pairs. A claim takes part when some claim of another
    kind names the same register, or names none, or when this claim names none
    -- because `different_registers` is true only where *both* sides name a
    register and the two differ.

    That last clause is why this cannot simply group by register and compare
    groups: a blank register matches every register, so the relation is not an
    equivalence and the groups are not disjoint. It is also why the counts
    below are kept per kind rather than per register alone.

    Kinds are counted rather than iterated. `ObjectType` is an enumeration in
    the schema, but this rule runs whether or not the metadata conformed, so a
    document can carry as many distinct kinds as it has elements -- and a scan
    over the kinds for every claim would be the square again, wearing a
    different hat.
    """
    registers = [_register(obj.ref_type) for _kind, obj, _c in claims]

    kinds = set()
    blank_kinds = set()
    kinds_naming = {}
    for (kind, _obj, _c), register in zip(claims, registers):
        kinds.add(kind)
        if register:
            kinds_naming.setdefault(register, set()).add(kind)
        else:
            blank_kinds.add(kind)

    def elsewhere(group, kind) -> bool:
        """Is `group` non-empty once this claim's own kind is taken out of it."""
        return len(group) - (1 if kind in group else 0) > 0

    out = []
    for (kind, obj, container), register in zip(claims, registers):
        if not register:
            # A blank register matches every register, so any claim of another
            # kind contradicts this one.
            takes_part = elsewhere(kinds, kind)
        else:
            takes_part = (elsewhere(blank_kinds, kind)
                          or elsewhere(kinds_naming.get(register, set()), kind))
        if takes_part:
            out.append((kind, obj, container))
    return out


def check(documents, read_everything: bool) -> Iterator[Finding]:
    """`documents` is (container, document) for every document the run modelled.

    `read_everything` says every metadata file the archives list was actually
    read. When it is false this layer says nothing at all, and that is the whole
    guard: a set of known identifiers assembled from half a delivery cannot
    establish that anything is missing from it.

    It is not hypothetical. `corpus/examples/missingdocuments/folders.zip`
    delivers its documents as folders -- `456-29201/` and `AB393/`, each with
    its own metadata -- and its main document refers to exactly those two ids.
    The documents are in the container. This tool does not open folders, which
    is what `Z13` says and why `Z13` is `about: tool`. Without this guard the
    first version of this rule reported two errors, `about: container`, saying a
    delivery had not brought documents it had brought -- our refusal, billed to
    the sender, which is the failure this project keeps a severity axis to
    avoid.
    """
    # Said before the guard below, deliberately. `M11`/`M12` need a complete
    # read because "no document declares this" cannot be established from half a
    # delivery -- but a contradiction is the other shape. Two declarations that
    # disagree are a fact about what was actually read, and a tool that had
    # already seen both and stayed quiet because a third container would not
    # open would be hiding something it knew.
    for _folded_id, claims in sorted(objects_claimed(documents).items()):
        # Two claims are a contradiction when they disagree about the kind and
        # nothing says they are about different registers.
        claims = contradicting(claims)
        if not claims:
            continue
        kinds = {kind for kind, _obj, _c in claims}
        r = rule("M13")
        first = claims[0][1]
        shown, in_all = _first_few(sorted(kinds), "kinds")
        where, where_all = _first_few(
            sorted({c.path or "the delivery" for _k, _o, c in claims}), "containers")
        yield Finding(
            r, r.title, (first.src or claims[0][2].where),
            detail=f"{first.id!r} is declared as {shown} in this delivery "
                   f"({where});{in_all}{where_all} an identifier names one kind "
                   f"of thing")

    if not read_everything:
        return
    # Counted once for the whole delivery, and only if something asks: a
    # delivery with no relationships does no work here at all.
    declared = own = None
    for container, doc, relationship, target in refers_to(documents):
        if declared is None:
            declared, own = declarations(documents)
        identity = _identity(target)
        # "Some document other than this one declares it" -- the same
        # subtraction `contradicting` makes, for the same reason.
        if declared.get(identity, 0) - (1 if identity in own[id(doc)] else 0) > 0:
            continue
        from_main = container.metadata_name == MAIN_XML
        r = rule("M11" if from_main else "M12")
        shown = f"{target.id}@{target.domain_id}" if target.domain_id else target.id
        yield Finding(
            r, r.title,
            (target.src or relationship.src or container.where),
            detail=f"{relationship.type or 'DocumentRelationship'} names "
                   f"{shown}, and no document in this delivery declares it")
