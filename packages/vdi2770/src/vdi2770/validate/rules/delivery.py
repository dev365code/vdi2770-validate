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
    if not read_everything:
        return
    # Counted once for the whole delivery, and only if something asks: a
    # delivery with no relationships does no work here at all.
    declared = own = None
    for container, doc, relationship, target in refers_to(documents):
        if declared is None:
            declared, own = declarations(documents)
        identity = _identity(target)
        # "Some document other than this one declares it": the count of the
        # documents that declare this identity, less your own if you are one.
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
