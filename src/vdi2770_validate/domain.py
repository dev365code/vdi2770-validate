"""The parsed metadata, as a model. Every node remembers where it was written.

Rules read this. Rules never read the XML tree, so a rule physically cannot
depend on how the document was spelled.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from .model import Location
from .readers.xmlread import Node


@dataclass(frozen=True)
class Classification:
    class_id: str
    system: str
    names: Tuple[Tuple[str, str], ...]   # (language, text)
    src: Location = Location()


@dataclass(frozen=True)
class DigitalFile:
    file_name: str
    file_format: str
    src: Location = Location()


@dataclass(frozen=True)
class Description:
    language: str
    title: str
    src: Location = Location()


@dataclass(frozen=True)
class DocumentVersion:
    version_id: str
    languages: Tuple[str, ...]
    descriptions: Tuple[Description, ...]
    files: Tuple[DigitalFile, ...]
    life_cycle_status: str
    src: Location = Location()


@dataclass(frozen=True)
class Document:
    ids: Tuple[str, ...]
    classifications: Tuple[Classification, ...]
    versions: Tuple[DocumentVersion, ...]
    src: Location = Location()

    @property
    def all_files(self) -> Tuple[DigitalFile, ...]:
        return tuple(f for v in self.versions for f in v.files)


def _loc(base: Location, n: Node, subject: Optional[str] = None) -> Location:
    return base.child(line=n.line, column=n.column, subject=subject)


def build(root: Node, base: Location) -> Document:
    ids = tuple(n.text.strip() for n in root.find_all("DocumentId"))

    classifications = []
    for c in root.find_all("DocumentClassification"):
        names = tuple(
            (nm.attrib.get("Language", "").strip(), nm.text.strip())
            for nm in c.find_all("ClassName")
        )
        cid = c.text_of("ClassId")
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
                language=d.attrib.get("Language", "").strip(),
                title=d.text_of("Title"),
                src=_loc(base, d),
            )
            for d in v.find_all("DocumentDescription")
        )
        lcs = v.find("LifeCycleStatus")
        versions.append(DocumentVersion(
            version_id=v.text_of("DocumentVersionId"),
            languages=tuple(n.text.strip() for n in v.find_all("Language")),
            descriptions=descriptions,
            files=files,
            life_cycle_status=(lcs.attrib.get("StatusValue", "").strip() if lcs else ""),
            src=_loc(base, v, v.text_of("DocumentVersionId") or None),
        ))

    return Document(ids=ids, classifications=tuple(classifications),
                    versions=tuple(versions), src=_loc(base, root))
