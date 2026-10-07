"""`NumberOfPages` is checked here, and not by a rule of ours.

`docs/divergences.md` records that the reference's `DV_013` fires on
`numberOfPages < 0` while its own message says "greater than zero", so `0`
passes there. The sentence beside it used to add that this tool "has no
numberOfPages rule yet" -- true about rules, and misleading about coverage: a
reader of that line concludes the condition goes unreported here.

It does not. The schema VDI publishes types the attribute `xs:positiveInteger`,
so `0` and a negative are refused by the schema layer as `X2`, with the
attribute named, the value quoted and the line given. That is a stronger basis
than a rule of ours would have -- `schema` rather than `ours` -- and writing one
would duplicate the check under a weaker obligation.

This file is what stops that sentence from drifting: it is the measurement the
sentence rests on: if the schema or the layer that reads it stops refusing a
zero, the page becomes wrong and this fails with it rather than after somebody
notices.
"""
import io
import json
import os
import subprocess
import sys
import zipfile

import pytest
from vdi2770_validate.runner import check_bytes

import vdi2770
from conftest import CLEAN_DOCUMENT, CORPUS, under_test
from vdi2770_validate import xsdvalidate

SAMPLE = CORPUS / "container" / "documentcontainer.zip"


def with_page_count(value):
    """The sample container, with `NumberOfPages` set on its document version."""
    out = io.BytesIO()
    with zipfile.ZipFile(SAMPLE) as z, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as o:
        for name in z.namelist():
            data = z.read(name)
            if name.endswith("VDI2770_Metadata.xml"):
                text = data.decode("utf-8")
                assert "<DocumentVersion>" in text, "the sample no longer has a bare DocumentVersion"
                data = text.replace("<DocumentVersion>",
                                    f'<DocumentVersion NumberOfPages="{value}">',
                                    1).encode("utf-8")
            o.writestr(name, data)
    return out.getvalue()


def ids(data):
    return {f.rule.id for f in check_bytes(data, "pages.zip").findings}


@pytest.mark.parametrize("value", ["0", "-3"])
def test_a_page_count_that_is_not_positive_is_refused(value):
    """By the schema, so the finding cites what VDI publishes rather than us."""
    assert "X2" in ids(with_page_count(value)), (
        f'NumberOfPages="{value}" drew no schema finding; `docs/divergences.md` '
        f"says this condition is caught here without a rule of our own")


def test_the_refusal_names_the_attribute_and_the_value():
    """A schema error that says only "does not conform" leaves a sender reading
    a 300-line file for the character that upset it."""
    said = [f for f in check_bytes(with_page_count("0"), "pages.zip").findings
            if f.rule.id == "X2"]
    assert said, "no X2 to read"
    detail = " ".join(f.detail or "" for f in said)
    assert "NumberOfPages" in detail and "0" in detail, detail
    assert any(f.where.line for f in said), (
        f"the refusal gives no line to look at: {[f.where for f in said]}")


def test_a_positive_page_count_is_left_alone():
    """The other half, and the half that decides whether this is a check or a
    nuisance: a delivery that says a true thing draws nothing for saying it."""
    assert "X2" not in ids(with_page_count("7")), (
        'NumberOfPages="7" is a conforming value and drew a schema finding'
    )


# XSD Part 2 §§3.3.13, 3.3.25 and 4.3.6: the contract is run on each Python.
# The schema places no upper bound on the digits of an integer, so a finite
# positive value is valid at any length and draws nothing. The 4300 that some
# interpreters stop at is a defence of theirs, not a fact about the document.
LONG_PAGE_COUNT_FINDINGS = ()

CASES = [
    pytest.param("9" * 4301, LONG_PAGE_COUNT_FINDINGS, id="4301-digits"),
    pytest.param("1_0", ("X2",), id="underscore"),
    pytest.param("٧", ("X2",), id="arabic-indic"),
    pytest.param("+007", (), id="plus-leading-zero"),
    pytest.param("0", ("X2",), id="zero"),
    pytest.param("-3", ("X2",), id="negative"),
    pytest.param("9" * 4300, (), id="4300-digits"),
    pytest.param("+" + "0" * 4301 + "7", LONG_PAGE_COUNT_FINDINGS, id="long-leading-zero"),
    pytest.param("0" * 4301, ("X2",), id="long-zero"),
    pytest.param(" &#x9;+007&#xD;&#xA; ", (), id="xml-whitespace"),
    pytest.param("\u00a07\u00a0", ("X2",), id="non-xml-whitespace"),
    pytest.param("1 0", ("X2",), id="internal-space"),
    pytest.param("", ("X2",), id="empty"),
    pytest.param("+000", ("X2",), id="signed-zero"),
]


def container_with(value):
    out = io.BytesIO()
    with zipfile.ZipFile(CLEAN_DOCUMENT) as source, zipfile.ZipFile(out, "w") as target:
        for name in source.namelist():
            data = source.read(name)
            if name == "VDI2770_Metadata.xml":
                assert b"<DocumentVersion>" in data
                data = data.replace(b"<DocumentVersion>",
                                    f'<DocumentVersion NumberOfPages="{value}">'.encode(), 1)
            target.writestr(name, data)
    return out.getvalue()


@pytest.mark.parametrize("value, expected", CASES)
def test_positive_integer_uses_the_xsd_lexical_and_value_spaces(value, expected):
    report = check_bytes(container_with(value), "pages.zip")
    # P4 is the sample's PDF/A claim note. Every other finding is part of this
    # contract, including a crash or an incomplete schema check.
    assert sorted(f.rule.id for f in report.findings) == sorted(["P4", *expected])
    for finding in report.findings:
        if finding.rule.id == "X2":
            assert "NumberOfPages" in finding.detail
            assert finding.where.line is not None
            assert finding.where.xpath.endswith("/DocumentVersion")


@pytest.mark.parametrize("limit", ["640", "0"])
@pytest.mark.parametrize("value, expected", CASES[:6])
def test_cli_verdict_is_independent_of_the_runtime_digit_limit(tmp_path, limit, value, expected):
    path = tmp_path / "pages.zip"
    path.write_bytes(container_with(value))
    done = subprocess.run(
        [sys.executable, "-m", "vdi2770_validate", "check", "--json", "--no-bundle", os.fspath(path)],
        env=under_test(PYTHONINTMAXSTRDIGITS=limit), capture_output=True, text=True)
    assert done.returncode == (1 if expected else 0), done.stderr
    document = json.loads(done.stdout)[0]
    assert sorted(f["rule"] for f in document["findings"]) == sorted(["P4", *expected])


@pytest.mark.parametrize("value, expected", CASES)
def test_the_original_attribute_never_reaches_the_integer_decoder(monkeypatch, value, expected):
    integer = xsdvalidate._schema().maps.types["{http://www.w3.org/2001/XMLSchema}positiveInteger"]
    real = integer.to_python
    decoded = []

    def counting(token):
        decoded.append(token)
        return real(token)

    monkeypatch.setattr(integer, "to_python", counting)
    report = check_bytes(container_with(value), "pages.zip")
    assert sorted(f.rule.id for f in report.findings) == sorted(["P4", *expected])
    assert decoded == ["1"], "the original positiveInteger reached int()"


def test_other_schema_violations_survive_a_long_positive_integer():
    with zipfile.ZipFile(io.BytesIO(container_with("9" * 4301))) as source:
        data = source.read("VDI2770_Metadata.xml")
    bad = data.replace(b"<ClassId>", b"<NotAThing>").replace(b"</ClassId>", b"</NotAThing>")
    assert bad != data
    errors = xsdvalidate.validate(bad, vdi2770.parse_xml(bad))
    assert errors and all("broken" not in error for error in errors)
    assert any("NotAThing" in error["reason"] for error in errors)
    assert all("NumberOfPages" not in error["reason"] for error in errors)


def test_a_foreign_attribute_is_not_treated_as_a_schema_positive_integer():
    data = (b'<Document xmlns="http://www.vdi.de/schemas/vdi2770">'
            b'<DocumentVersion xmlns="urn:foreign" NumberOfPages="1_0"/></Document>')
    errors = xsdvalidate.validate(data, vdi2770.parse_xml(data))
    assert errors and all("broken" not in error for error in errors)
    assert all("expected xs:positiveInteger" not in error["reason"] for error in errors)


def test_the_schema_adapter_leaves_the_reader_tree_unchanged():
    with zipfile.ZipFile(io.BytesIO(container_with("1_0"))) as source:
        data = source.read("VDI2770_Metadata.xml")
    tree = vdi2770.parse_xml(data)
    version = tree.find("DocumentVersion")
    before = dict(version.attrib)
    errors = xsdvalidate.validate(data, tree)
    assert errors and "NumberOfPages" in errors[0]["reason"]
    assert version.attrib == before == {"NumberOfPages": "1_0"}


def test_the_complaint_is_rendered_over_the_original_value():
    """The stand-in that keeps a long value away from int() must be gone again
    by the time anybody reads the element: a complaint that quoted "1" where the
    document says "1_0" would name a value the sender never wrote."""
    with zipfile.ZipFile(io.BytesIO(container_with("1_0"))) as source:
        data = source.read("VDI2770_Metadata.xml")
    before_decode, after_decode = xsdvalidate._positive_integer_hooks()
    complaints = [err for err in xsdvalidate._schema().iter_errors(
                      io.BytesIO(data), validation_hook=before_decode,
                      extra_validator=after_decode)
                  if "expected xs:positiveInteger" in (err.reason or "")]
    assert len(complaints) == 1, [err.reason for err in complaints]
    assert complaints[0].obj.attrib["NumberOfPages"] == "1_0"


# A schema of our own making, for the shapes the bundled one does not have:
# an attribute wildcard, and an attribute declared and then prohibited.
_OTHER_SHAPES = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
    targetNamespace="urn:test:shapes" xmlns="urn:test:shapes"
    elementFormDefault="qualified">
  <xs:element name="Root">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="Open" minOccurs="0">
          <xs:complexType>
            <xs:attribute name="N" type="xs:positiveInteger"/>
            <xs:anyAttribute processContents="lax"/>
          </xs:complexType>
        </xs:element>
        <xs:element name="Closed" minOccurs="0">
          <xs:complexType>
            <xs:attribute name="N" type="xs:positiveInteger"/>
            <xs:attribute name="P" type="xs:positiveInteger" use="prohibited"/>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>"""


@pytest.fixture
def other_shapes(monkeypatch):
    import xmlschema

    schema = xmlschema.XMLSchema(_OTHER_SHAPES)
    monkeypatch.setattr(xsdvalidate, "_schema", lambda: schema)
    return schema


@pytest.mark.parametrize("value, expected", [("1_0", 1), ("7", 0)])
def test_an_attribute_wildcard_beside_a_positive_integer_is_not_a_crash(other_shapes, value, expected):
    """`anyAttribute` arrives in the attribute table as a wildcard with no type.
    The check must step over it, not fall over it: a crash here is reported as
    the document's fault, with advice to simplify a document that is fine."""
    data = f'<Root xmlns="urn:test:shapes"><Open N="{value}" foo="bar"/></Root>'.encode()
    errors = xsdvalidate.validate(data, vdi2770.parse_xml(data))
    assert all("broken" not in error for error in errors), errors
    assert len([e for e in errors if "expected xs:positiveInteger" in e["reason"]]) == expected, errors


def test_a_prohibited_attribute_is_refused_once(other_shapes):
    """The schema already refuses an attribute it prohibits. Judging its value as
    well would tell the sender two things about one mistake."""
    data = b'<Root xmlns="urn:test:shapes"><Closed N="1_0" P="1_0"/></Root>'
    errors = xsdvalidate.validate(data, vdi2770.parse_xml(data))
    assert all("broken" not in error for error in errors), errors
    about_p = [e["reason"] for e in errors if "'P'" in e["reason"] or " P " in e["reason"]
               or e["reason"].startswith("attribute P")]
    assert len(about_p) == 1, errors
    assert "expected xs:positiveInteger" not in about_p[0]
    assert len([e for e in errors if "expected xs:positiveInteger" in e["reason"]]) == 1, errors
