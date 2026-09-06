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

which is why there are two rules here and not one severity. Promoting their
information to our error would be a claim about VDI 2770 that nobody here can
support -- the guideline is paid and was not read -- and `obligation: reference`
is a promise that the judgement is theirs.
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


def known_document_ids(documents) -> set:
    """Every identifier the delivery declares, from every container in it."""
    return {_identity(i) for _container, doc in documents for i in doc.identifiers}


def refers_to(documents) -> Iterator[tuple]:
    """Each (container, relationship, identifier) the delivery points at.

    A relationship may name more than one document, and each is a separate
    promise: taking the first would let a delivery leave out every document
    after it and still come back clean.
    """
    for container, doc in documents:
        for version in doc.versions:
            for relationship in version.relationships:
                for target in relationship.identifiers:
                    yield container, relationship, target


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
    known = known_document_ids(documents)
    for container, relationship, target in refers_to(documents):
        if _identity(target) in known:
            continue
        from_main = container.metadata_name == MAIN_XML
        r = rule("M11" if from_main else "M12")
        shown = f"{target.id}@{target.domain_id}" if target.domain_id else target.id
        yield Finding(
            r, r.title,
            (target.src or relationship.src or container.where),
            detail=f"{relationship.type or 'DocumentRelationship'} names "
                   f"{shown}, and no document in this delivery declares it")
