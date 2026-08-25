"""The parsed metadata, as a model. Every node remembers where it was written.

Rules read this. Rules never read the XML tree, so a rule physically cannot
depend on how the document was spelled.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from .model import Location
from .xmlread import Node


@dataclass(frozen=True)
class ClassName:
    """One `ClassName` element, with the line it was written on.

    It was a `(language, text)` tuple, and three rules that each object to one
    name reported the enclosing `DocumentClassification`. A classification holds
    several names on several lines; one location for all of them answers "which
    name" with "the block".
    """

    # None when the Language attribute is absent, "" when present and empty --
    # see Description.language for why the two are not collapsed.
    language: Optional[str]
    text: str
    src: Location = Location()


@dataclass(frozen=True)
class Classification:
    # None when the element is absent, "" when present and empty. The schema
    # requires the element and types it `xs:string`, so an empty one is a
    # document the schema accepts and only a rule can object to.
    class_id: Optional[str]
    system: str
    names: Tuple[ClassName, ...]
    src: Location = Location()


@dataclass(frozen=True)
class DigitalFile:
    file_name: str
    file_format: str
    src: Location = Location()


@dataclass(frozen=True)
class Description:
    # None when the attribute is absent, "" when it is present and empty. A
    # caller that collapses the two cannot tell "this value is wrong" from
    # "there is no value", and will say the first when it means the second.
    language: Optional[str]
    title: str
    src: Location = Location()


@dataclass(frozen=True)
class Tagged:
    """One `Language` element, with the line it was written on.

    Same reason as `ClassName`: a `DocumentVersion` may declare several
    languages, and a rule objecting to one of them reported the block that holds
    them all.
    """

    code: str
    src: Location = Location()


@dataclass(frozen=True)
class DocumentVersion:
    version_id: str
    languages: Tuple[Tagged, ...]
    descriptions: Tuple[Description, ...]
    files: Tuple[DigitalFile, ...]
    life_cycle_status: str
    # Where `LifeCycleStatus` itself is. A `DocumentVersion` is the largest
    # element in the file -- languages, descriptions, parties, status and every
    # digital file -- so answering "where" with its opening line answers "in this
    # document somewhere".
    life_cycle_src: Location = Location()
    src: Location = Location()


@dataclass(frozen=True)
class DocumentId:
    """An identifier and the domain that issued it.

    The schema makes `DomainId` required, so an identifier is the pair. The same
    drawing number registered by an OEM and by its supplier is two identifiers,
    not one repeated -- a caller comparing the text alone will conclude otherwise.
    """

    domain_id: str
    id: str
    src: Location = Location()


@dataclass(frozen=True)
class Document:
    identifiers: Tuple[DocumentId, ...]
    classifications: Tuple[Classification, ...]
    versions: Tuple[DocumentVersion, ...]
    src: Location = Location()

    @property
    def ids(self) -> Tuple[str, ...]:
        """Just the identifier strings, without their domains. Convenient, and
        wrong to compare for equality -- see DocumentId."""
        return tuple(i.id for i in self.identifiers)

    @property
    def all_files(self) -> Tuple[DigitalFile, ...]:
        return tuple(f for v in self.versions for f in v.files)


def _loc(base: Location, n: Node, subject: Optional[str] = None) -> Location:
    return base.child(line=n.line, column=n.column, subject=subject)


def build(root: Node, base: Location) -> Document:
    identifiers = tuple(
        DocumentId(domain_id=n.attrib.get("DomainId", "").strip(),
                   id=n.text.strip(),
                   src=_loc(base, n, n.text.strip() or None))
        for n in root.find_all("DocumentId"))

    classifications = []
    for c in root.find_all("DocumentClassification"):
        names = tuple(
            ClassName(
                language=None if "Language" not in nm.attrib else nm.attrib["Language"].strip(),
                text=nm.text.strip(),
                src=_loc(base, nm, nm.text.strip() or None),
            )
            for nm in c.find_all("ClassName")
        )
        cid = c.child_text("ClassId")
        classifications.append(Classification(
            class_id=cid,
            system=c.attrib.get("ClassificationSystem", "").strip(),
            names=names,
            src=_loc(base, c, cid or None),
        ))

    versions = []
    for v in root.find_all("DocumentVersion"):
        files = tuple(
            DigitalFile(
                # the file name is the element's text; the media type is an attribute
                file_name=f.text.strip(),
                file_format=f.attrib.get("FileFormat", "").strip(),
                src=_loc(base, f, f.text.strip() or None),
            )
            for f in v.find_all("DigitalFile")
        )
        descriptions = tuple(
            Description(
                language=(None if "Language" not in d.attrib
                          else d.attrib["Language"].strip()),
                title=d.text_of("Title"),
                src=_loc(base, d),
            )
            for d in v.find_all("DocumentDescription")
        )
        lcs = v.find("LifeCycleStatus")
        versions.append(DocumentVersion(
            version_id=v.text_of("DocumentVersionId"),
            languages=tuple(Tagged(code=n.text.strip(), src=_loc(base, n, n.text.strip() or None))
                            for n in v.find_all("Language")),
            descriptions=descriptions,
            files=files,
            life_cycle_status=(lcs.attrib.get("StatusValue", "").strip() if lcs else ""),
            life_cycle_src=(_loc(base, lcs, lcs.attrib.get("StatusValue", "").strip() or None)
                            if lcs else _loc(base, v)),
            src=_loc(base, v, v.text_of("DocumentVersionId") or None),
        ))

    return Document(identifiers=identifiers, classifications=tuple(classifications),
                    versions=tuple(versions), src=_loc(base, root))
