"""M3, M4 and M8 are each about one `ClassName`, and each reported the line of
the `DocumentClassification` that contains it.

A classification holds a German name, an English one, and whatever else the
document chose to add — three elements on three lines, one enclosing block. So
"line 12" was the same answer for all three, and the only thing distinguishing
"the German name is wrong" from "this tool does not check French" was the detail
string. The location is the field a user clicks. It has to differ when the thing
it points at differs.
"""
import io
import zipfile

from conftest import CLEAN_DOCUMENT
from vdi2770_validate.runner import check_bytes

SRC = zipfile.ZipFile(CLEAN_DOCUMENT)

CLASSIFICATION = """  <DocumentClassification ClassificationSystem="VDI2770:2018">
    <ClassId>02-03</ClassId>
    <ClassName Language="de">Falscher Name</ClassName>
    <ClassName Language="en">Falsches Rendering</ClassName>
    <ClassName Language="fr">Composants</ClassName>
  </DocumentClassification>"""


def _container():
    meta = SRC.read("VDI2770_Metadata.xml").decode()
    start = meta.index("<DocumentClassification")
    end = meta.rindex("</DocumentClassification>") + len("</DocumentClassification>")
    meta = meta[:start] + CLASSIFICATION.lstrip() + meta[end:]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as out:
        for name in SRC.namelist():
            out.writestr(name, meta.encode() if name.endswith("VDI2770_Metadata.xml")
                         else SRC.read(name))
    return buf.getvalue(), meta


def test_three_findings_about_three_names_point_at_three_lines():
    raw, meta = _container()
    lines = meta.splitlines()
    fired = {}
    for f in check_bytes(raw, "names.zip").findings:
        fired.setdefault(f.rule.id, f)

    assert {"M3", "M4", "M8"} <= set(fired), (
        f"the fixture was meant to break the German name, the English one and to "
        f"carry a language this tool skips; it produced {sorted(fired)}")

    at = {r: fired[r].where.line for r in ("M3", "M4", "M8")}
    assert all(at.values()), f"a finding about a name has no line: {at}"
    assert len(set(at.values())) == 3, (
        f"three names, three lines, and the findings say {at}")

    for rule, tag in (("M3", 'Language="de"'), ("M4", 'Language="en"'), ("M8", 'Language="fr"')):
        shown = lines[at[rule] - 1]
        assert tag in shown, f"{rule} points at line {at[rule]}: {shown.strip()!r}"


VERSION = """<DocumentVersion>
        <DocumentVersionId>1.0</DocumentVersionId>
        <Language>de</Language>
        <Language>deutsch</Language>
        <Party Role="Author">
            <Organization OrganizationName="Beispiel GmbH"
                OrganizationOfficialName="Beispiel GmbH &amp; Co. KGaA" OrganizationId="BSP"/>
        </Party>
        <DocumentDescription Language="de">
            <Title>Hauptdokument</Title>
            <Summary>Das Hauptdoument ist eine Auflistung aller Dokumente einer Ebene.
                Gibt es zu dieser Ebene auch eine untergeordnete Ebene, so enthält die Auflistung auch die Hauptdokumente
                der zugehörigen ersten untergeordneten Ebene.
            </Summary>
            <KeyWords>
                <KeyWord>Hauptdokument</KeyWord>
                <KeyWord>Dokumentenliste</KeyWord>
            </KeyWords>
        </DocumentDescription>
        <LifeCycleStatus StatusValue="InReview" SetDate="2018-04-04">
            <Party Role="Responsible">
                <Organization OrganizationName="Beispiel GmbH"
                    OrganizationOfficialName="Beispiel GmbH &amp; Co. KGaA" OrganizationId="BSP"/>
            </Party>
        </LifeCycleStatus>
        <DocumentRelationship Type="RefersTo">
            <DocumentId DomainId="BSP-OEM">ts-ddd-234</DocumentId>
        </DocumentRelationship>
        <DigitalFile FileFormat="application/pdf">VDI2770_Main.pdf</DigitalFile>
    </DocumentVersion>"""


def _with_version(source):
    """A documentation container carries its metadata as `VDI2770_Main.xml`, and
    `M7` only fires on that kind — a draft is a legitimate state for a single
    document and not for the delivery that collects them."""
    zf = zipfile.ZipFile(source)
    target = next(n for n in zf.namelist() if n.endswith(("VDI2770_Main.xml",
                                                          "VDI2770_Metadata.xml")))
    meta = zf.read(target).decode()
    start = meta.index("<DocumentVersion>")
    end = meta.rindex("</DocumentVersion>") + len("</DocumentVersion>")
    meta = meta[:start] + VERSION + meta[end:]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as out:
        for name in zf.namelist():
            out.writestr(name, meta.encode() if name == target else zf.read(name))
    return buf.getvalue(), meta


def test_a_bad_language_and_a_draft_status_point_at_their_own_elements():
    """The other half of the same defect. `M5` objects to one `Language` element
    and `M7` to the `LifeCycleStatus`; both reported `DocumentVersion`, which is
    the block containing every one of them.

    A `DocumentVersion` is the largest element in the file — it holds the
    languages, the descriptions, the parties, the status and every digital file.
    Answering "where" with its opening line is answering "in this document
    somewhere".
    """
    from conftest import CLEAN_DOCUMENTATION

    raw, meta = _with_version(CLEAN_DOCUMENTATION)
    lines = meta.splitlines()
    fired = {}
    for f in check_bytes(raw, "version.zip").findings:
        fired.setdefault(f.rule.id, f)

    assert {"M5", "M7"} <= set(fired), (
        f"the fixture carries an unusable language tag and a draft status; it "
        f"produced {sorted(fired)}")

    at5, at7 = fired["M5"].where.line, fired["M7"].where.line
    assert at5 and at7, f"M5 at {at5}, M7 at {at7}"
    assert at5 != at7, f"both point at line {at5}, which is the block around them"
    assert "<Language>deutsch</Language>" in lines[at5 - 1], (
        f"M5 points at line {at5}: {lines[at5 - 1].strip()!r}")
    assert "<LifeCycleStatus" in lines[at7 - 1], (
        f"M7 points at line {at7}: {lines[at7 - 1].strip()!r}")
