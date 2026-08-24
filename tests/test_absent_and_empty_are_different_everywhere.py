"""The distinction `M5` learned has to hold wherever the reader flattens a value.

`Description.language` was given the None/"" distinction and `Classification`
was not, so the same mistake survived twice over in the class table: an empty
`<ClassId></ClassId>` — which the schema accepts, since the element is required
and typed `xs:string` — switched `M2` off entirely, and a `ClassName` with no
`Language` attribute at all produced `M8` *and* `X2` for one defect.

Absent is the schema layer's business. Empty is ours.
"""
import io
import zipfile

from conftest import CLEAN_DOCUMENT
from vdi2770_validate.runner import check_file

SRC = zipfile.ZipFile(CLEAN_DOCUMENT)
META = SRC.read("VDI2770_Metadata.xml").decode()
PDF = SRC.read("B.pdf")
DOCX = SRC.read("B.docx")

CLASS_ID = "<ClassId>02-01</ClassId>"
CLASS_NAME = '<ClassName Language="de">'


def test_the_fixture_has_the_elements_this_file_edits():
    assert META.count(CLASS_ID) == 1 and META.count(CLASS_NAME) == 1


def build(tmp_path, name, meta):
    p = tmp_path / name
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VDI2770_Metadata.xml", meta)
        z.writestr("B.pdf", PDF)
        z.writestr("B.docx", DOCX)
    p.write_bytes(buf.getvalue())
    return {f.rule.id for f in check_file(str(p)).findings}


def test_an_empty_class_id_is_reported(tmp_path):
    """The schema accepts it, so nothing else will say a word."""
    got = build(tmp_path, "empty_id.zip", META.replace(CLASS_ID, "<ClassId></ClassId>"))
    assert "M2" in got, got
    assert "X2" not in got, "the premise is that the schema accepts an empty ClassId"


def test_an_absent_class_id_stays_with_the_schema_layer(tmp_path):
    got = build(tmp_path, "no_id.zip", META.replace(CLASS_ID, ""))
    assert "X2" in got and "M2" not in got, got


def test_an_empty_class_name_language_is_ours(tmp_path):
    got = build(tmp_path, "empty_lang.zip", META.replace(CLASS_NAME, '<ClassName Language="">'))
    assert "M8" in got and "X2" not in got, got


def test_an_absent_class_name_language_is_not_reported_twice(tmp_path):
    got = build(tmp_path, "no_lang.zip", META.replace(CLASS_NAME, "<ClassName>"))
    assert "X2" in got, got
    assert "M8" not in got, "one defect, two findings, and M8's is about a value that is not there"


def test_a_wrong_class_id_is_still_wrong(tmp_path):
    got = build(tmp_path, "bad_id.zip", META.replace(CLASS_ID, "<ClassId>99-99</ClassId>"))
    assert "M2" in got, got


def test_a_normal_container_gains_nothing(tmp_path):
    assert build(tmp_path, "fine.zip", META) == {"P4"}
