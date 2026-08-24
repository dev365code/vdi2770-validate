"""Read a VDI 2770 handover-documentation container without trusting it.

    import vdi2770

    box = vdi2770.read_container_file("manuals.zip")
    for c in box.walk():
        if c.metadata_bytes is None:
            continue
        doc = vdi2770.build_document(vdi2770.parse_xml(c.metadata_bytes), c.where)
        print(c.path, doc.ids, [k.class_id for k in doc.classifications])

Three properties this library holds to, each of them tested rather than
promised:

* **Nothing is extracted to disk.** Members are decompressed into memory
  under a budget and dropped. There is no temporary directory to clean up
  and no path traversal to get wrong, because no path is ever joined.
* **Nothing is fetched.** No socket is opened, for any input, ever --
  including XML that asks for one. Entity declarations are refused outright
  rather than resolved-but-locally.
* **A refusal is reported, not raised.** A member that blows a budget
  becomes a `Defect` on the container and the read continues, so one hostile
  file inside an archive does not cost you the other four hundred.

It has **no dependencies**, and it decides nothing. Whether a container is
*correct* is a question about VDI 2770, and this library does not answer it;
it tells you what is in the file and where. If you want the verdict too, see
`vdi2770-validate`, which is this library plus a rule set.

Unofficial. Not affiliated with VDI, the Digital Data Chain Consortium, or
IDTA. VDI 2770 is a guideline published by VDI; this is an independent
reader for the container format it describes.
"""
from .domain import (
    Classification,
    Description,
    DigitalFile,
    Document,
    DocumentVersion,
)
from .domain import build as build_document
from .model import Defect, Location
from .pdfread import PdfFacts
from .pdfread import read as read_pdf
from .xmlread import NS, Node, UnsafeXml, XmlError
from .xmlread import parse as parse_xml
from .zipread import (
    MAIN_PDF,
    MAIN_XML,
    METADATA_XML,
    Container,
    Kind,
    Member,
    member_bytes,
)
from .zipread import read as read_container
from .zipread import read_file as read_container_file

__version__ = "0.2.1"

__all__ = [
    "Classification", "Container", "Defect", "Description", "DigitalFile",
    "Document", "DocumentVersion", "Kind", "Location", "MAIN_PDF", "MAIN_XML",
    "METADATA_XML", "Member", "NS", "Node", "PdfFacts", "UnsafeXml", "XmlError",
    "build_document", "member_bytes", "parse_xml", "read_container",
    "read_container_file", "read_pdf", "__version__",
]
