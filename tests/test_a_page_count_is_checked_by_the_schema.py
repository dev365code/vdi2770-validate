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
# Candidate (a): a finite positive integer has no XSD upper digit bound.
# This is a candidate expectation, pending the controller's policy decision.
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
